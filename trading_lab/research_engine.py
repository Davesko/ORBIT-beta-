"""Persistent bounded strategy research. Never submits orders or alters trading settings."""
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from agent import number

MINUTE=60000
SYMBOLS=('BTC','ETH','SOL','PUMP')
# Minute scalping rarely beats ~0.3% round-trip costs; 15-minute bars held 1-8 hours give moves that can.
BARS={'1m':MINUTE,'15m':15*MINUTE}
SWING=('BTC','ETH','SOL')


@dataclass(frozen=True)
class Strategy:
    family:str
    window:int
    threshold:float
    stop:float
    hold:int=3
    bar:str='1m'
    @property
    def id(self):return self.family+'-'+str(self.window)+'-'+str(self.threshold)+'-'+str(self.stop)+'-h'+str(self.hold)+('' if self.bar=='1m' else '@'+self.bar)
    @property
    def step(self):return BARS[self.bar]


def series_key(symbol,bar='1m'):return symbol if bar=='1m' else symbol+'@'+bar


STRATEGIES=tuple(Strategy(f,w,t,s) for f in ('momentum','reversion') for w in (3,5,10) for t in (.0015,.003) for s in (.005,.0075))
CATALOG=tuple(Strategy(f,w,t,s,h) for f in ('momentum','reversion') for w in (3,5,10) for t in (.0015,.003,.005,.008) for s in (.005,.0075,.01) for h in (2,3,5))
CATALOG_15M=tuple(Strategy(f,w,t,s,h,'15m') for f in ('momentum','reversion') for w in (4,8,16) for t in (.01,.02,.03) for s in (.01,.015,.025) for h in (4,8,16))


def daily_strategies(day,catalog=CATALOG):
    offset=(day.toordinal()*24)%len(catalog)
    return tuple(catalog[(offset+i)%len(catalog)] for i in range(24))


def normalized_candles(rows,symbol,now_ms,interval='1m'):
    output={};step=BARS[interval]
    for row in rows:
        if row.get('s')!=symbol or row.get('i')!=interval:raise ValueError('Másik termék vagy gyertyafelbontás.')
        timestamp,end=int(row['t']),int(row['T'])
        if timestamp%step or end<timestamp or end>=timestamp+step:raise ValueError('Hibás gyertyaidő.')
        if end>now_ms:continue
        o,h,l,c=[number(row[key]) for key in ('o','h','l','c')]
        volume=number(row['v'])
        if min(o,h,l,c)<=0 or h<max(o,c,l) or l>min(o,c,h) or volume<0:raise ValueError('Hibás OHLC/forgalom.')
        candle={'t':timestamp,'T':end,'o':float(o),'h':float(h),'l':float(l),'c':float(c),'v':float(volume)}
        if not all(math.isfinite(candle[key]) for key in ('o','h','l','c','v')):raise ValueError('Túl nagy kutatási számérték.')
        if timestamp in output and output[timestamp]!=candle:raise ValueError('Ellentmondó gyertya ugyanarra az időre.')
        output[timestamp]=candle
    return [output[t] for t in sorted(output)]


def simulate(candles,strategy,cost_multiplier=1,trade_start=None,liquidate_end=True):
    """Close-based signal -> next open; stop-first OHLC ambiguity; costs on both legs.

    Minute bars cannot reproduce news/LLM decisions, book depth or tick execution.
    Floating-point research metrics only; the user's account is never touched.
    """
    cash=10000.0;initial=cash;peak=cash;dd=0.0;position=None;profits=[];fees=0.0;gaps=0;last_open=-1000;step=strategy.step
    fee=.0005*cost_multiplier;friction=.001*cost_multiplier # slippage + assumed half-spread
    def close(price):
        nonlocal cash,position,fees
        exit_price=price*(1-position['direction']*friction)
        exit_fee=abs(position['quantity'])*exit_price*fee
        gain=position['quantity']*(exit_price-position['entry'])-exit_fee-position['entry_fee']
        cash+=position['quantity']*(exit_price-position['entry'])-exit_fee
        fees+=exit_fee;profits.append(gain);position=None
    for i,bar in enumerate(candles):
        contiguous=i==0 or bar['t']-candles[i-1]['t']==step
        if not contiguous:
            gaps+=1
            if position:close(bar['o']) # first available price after a gap, not a fabricated stop fill
        if position:
            direction=position['direction'];entry=position['entry']
            stop=entry*(1-direction*strategy.stop);take=entry*(1+direction*strategy.stop*2)
            opening=bar['o']
            if (direction>0 and opening<=stop) or (direction<0 and opening>=stop):close(opening)
            elif (direction>0 and bar['l']<=stop) or (direction<0 and bar['h']>=stop):close(stop)
            elif (direction>0 and bar['h']>=take) or (direction<0 and bar['l']<=take):close(take)
            elif i-position['index']>=strategy.hold:close(bar['c'])
        # Only information known before this bar opened can generate its entry.
        if position is None and i>strategy.window and i-last_open>=strategy.hold+1 and (trade_start is None or bar['t']>=trade_start):
            window=candles[i-strategy.window-1:i]
            if all(b['t']-a['t']==step for a,b in zip(window,window[1:])):
                move=candles[i-1]['c']/candles[i-strategy.window-1]['c']-1
                if abs(move)>=strategy.threshold:
                    direction=(1 if move>0 else -1)*(1 if strategy.family=='momentum' else -1)
                    price=bar['o']*(1+direction*friction)
                    quantity=cash*.10/(price*(1+fee))*direction
                    entry_fee=abs(quantity)*price*fee
                    cash-=entry_fee;fees+=entry_fee
                    position={'entry':price,'direction':direction,'quantity':quantity,'index':i,'entry_fee':entry_fee}
                    last_open=i
                    # Stop/take on entry bar: both are possible, so adverse touch wins.
                    stop=price*(1-direction*strategy.stop);take=price*(1+direction*strategy.stop*2)
                    if (direction>0 and bar['l']<=stop) or (direction<0 and bar['h']>=stop):close(stop)
                    elif (direction>0 and bar['h']>=take) or (direction<0 and bar['l']<=take):close(take)
        equity=cash+(position['quantity']*(bar['c']-position['entry']) if position else 0)
        peak=max(peak,equity);dd=max(dd,(peak-equity)/peak if peak>0 else 1)
    if position and candles and liquidate_end:close(candles[-1]['c'])
    ending=cash+(position['quantity']*(candles[-1]['c']-position['entry']) if position and candles else 0)
    peak=max(peak,ending);dd=max(dd,(peak-ending)/peak if peak>0 else 1)
    wins=sum(p for p in profits if p>0);losses=-sum(p for p in profits if p<0)
    if not all(math.isfinite(value) for value in (ending,dd,wins,losses,fees)):raise ValueError('Nem értelmezhető kutatási eredmény.')
    return {'net_percent':(ending/initial-1)*100,'closed_net_percent':(cash/initial-1)*100,'open_positions':1 if position else 0,'trades':len(profits),'drawdown_percent':dd*100,
            'profit_factor':min(999,wins/losses) if losses else (999 if wins else 0),'costs':fees,'gaps':gaps,
            'ending_equity':ending,'start':candles[0]['t'] if candles else None,'end':candles[-1]['T'] if candles else None}


def partitions(candles):
    n=len(candles);a=int(n*.6);b=int(n*.8);purge=20
    if min(a,b-a,n-b)<100:raise ValueError('Kevés lezárt gyertya az elkülönített teszthez.')
    return candles[:a],candles[a+purge:b],candles[b+purge:]


def grade(historical,forward):
    reasons=[]
    # Swing trades are fewer by nature: 20 test and 10 new-data trades instead of 50 and 30.
    swing=(historical.get('strategy') or {}).get('bar','1m')!='1m'
    least_test,least_forward=(20,10) if swing else (50,30)
    if historical['history_days']<30:reasons.append('Legalább 30 nap megfigyelt árfolyamtörténet szükséges')
    if historical['test']['trades']<least_test:reasons.append('Kevés elkülönített tesztügylet (minimum '+str(least_test)+')')
    if historical['test']['net_percent']<=0:reasons.append('A lezárt történelmi teszt nettó eredménye nem pozitív')
    if historical['stress']['net_percent']<=0:reasons.append('Dupla költséggel nem pozitív a teszt')
    if historical['test']['drawdown_percent']>5:reasons.append('Túl nagy teszt-visszaesés')
    if historical['test']['profit_factor']<1.2:reasons.append('Alacsony teszt profitfaktor')
    if historical['test']['gaps']:reasons.append('Időkimaradás a tesztadatokban')
    if any(block['net_percent']<=0 for block in historical.get('blocks',[])):reasons.append('Nem pozitív mindhárom elkülönített tesztidőszak')
    if forward.get('days',0)<7:reasons.append('Legalább 7 nap új adaton végzett megfigyelés szükséges')
    if forward.get('trades',0)<least_forward:reasons.append('Kevés jövőbeli megfigyelt ügylet (minimum '+str(least_forward)+')')
    if forward.get('net_percent',0)<=0:reasons.append('Az új adaton mért nettó eredmény nem pozitív')
    if forward.get('closed_net_percent',forward.get('net_percent',0))<=0:reasons.append('A jövőbeli lezárt eredmény nem pozitív')
    if forward.get('gaps',0):reasons.append('Kimaradás a jövőbeli megfigyelésben')
    if forward.get('drawdown_percent',0)>5:reasons.append('Nagy visszaesés a jövőbeli megfigyelésben')
    return {'eligible':not reasons,'reasons':reasons,'label':'Tesztfeltételeket teljesítő kutatási jelölt' if not reasons else 'Még nincs megerősített módszer'}


class ResearchStore:
    def __init__(self,path):
        self.db=sqlite3.connect(str(path),timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS candles(symbol TEXT,t INTEGER,payload TEXT,PRIMARY KEY(symbol,t))')
        self.db.execute('CREATE TABLE IF NOT EXISTS trials(epoch TEXT PRIMARY KEY,created_at TEXT,symbol TEXT,strategy TEXT,payload TEXT,forward TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,payload TEXT)')
        self.db.commit()
    def ingest(self,symbol,candles):
        with self.db:
            for bar in candles:
                old=self.db.execute('SELECT payload FROM candles WHERE symbol=? AND t=?',(symbol,bar['t'])).fetchone()
                encoded=json.dumps(bar,sort_keys=True)
                if old and json.loads(old[0])!=bar:raise ValueError('A korábban lezárt gyertya megváltozott; felülvizsgálat szükséges.')
                self.db.execute('INSERT OR IGNORE INTO candles VALUES(?,?,?)',(symbol,bar['t'],encoded))
    def candles(self,symbol,start=None):
        query='SELECT payload FROM candles WHERE symbol=?';args=[symbol]
        if start is not None:query+=' AND t>=?';args.append(start)
        return [json.loads(row[0]) for row in self.db.execute(query+' ORDER BY t',args)]
    def last_time(self,symbol):return self.db.execute('SELECT MAX(t) FROM candles WHERE symbol=?',(symbol,)).fetchone()[0]
    def get_setting(self,key,default=None):
        row=self.db.execute('SELECT payload FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def put_setting(self,key,value):
        with self.db:self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
    def trial_exists(self,epoch):return self.db.execute('SELECT 1 FROM trials WHERE epoch=?',(epoch,)).fetchone() is not None
    def shortlist(self,series,strategies=STRATEGIES):
        results=[]
        for symbol,candles in series.items():
            train,valid,_=partitions(candles)
            for strategy in strategies:
                training=simulate(train,strategy);validation=simulate(valid,strategy)
                if training['trades']<5 or validation['trades']<3:continue
                score=min(training['net_percent'],validation['net_percent'])-validation['drawdown_percent']*.5
                results.append({'symbol':symbol,'strategy':asdict(strategy),'id':symbol+'/'+strategy.id,'train':training,'validation':validation,'score':score})
        return sorted(results,key=lambda row:row['score'],reverse=True)
    def freeze_trial(self,epoch,choice,candles,now,ai_reason,selection_count=None):
        if self.trial_exists(epoch):return False
        strategy=Strategy(**choice['strategy']);_,_,test=partitions(candles)
        result={'id':choice['id'],'symbol':choice['symbol'],'strategy':choice['strategy'],'train':choice['train'],'validation':choice['validation'],
                'test':simulate(test,strategy),'stress':simulate(test,strategy,2),'history_days':(candles[-1]['T']-candles[0]['t'])/86400000,
                'forward_start':max(candles[-1]['T']+1,(int(now.timestamp()*1000)//strategy.step+1)*strategy.step),
                'blocks':[simulate(test[i*len(test)//3:(i+1)*len(test)//3],strategy) for i in range(3)],
                'ai_reason':ai_reason,'dataset_hash':hashlib.sha256(json.dumps(candles,sort_keys=True).encode()).hexdigest(),
                'selection_trials':selection_count or len(STRATEGIES),'method':'One fixed candidate per UTC day; 60/20/20 chronological split with 20-bar purge. Test is not used for selection.'}
        with self.db:self.db.execute('INSERT INTO trials VALUES(?,?,?,?,?,?)',(epoch,now.isoformat(),choice['symbol'],json.dumps(choice['strategy']),json.dumps(result,ensure_ascii=False),'{}'))
        return True
    def forward_update(self):
        trials=self.db.execute('SELECT epoch,symbol,strategy,payload FROM trials ORDER BY epoch DESC LIMIT 20').fetchall()
        summaries=[]
        for epoch,symbol,strategy,raw in trials:
            historical=json.loads(raw);strategy=Strategy(**json.loads(strategy));start=historical['forward_start']
            bars=self.candles(series_key(symbol,strategy.bar),start-(strategy.window+2)*strategy.step)
            future=[b for b in bars if b['t']>=start]
            result=simulate(bars,strategy,trade_start=start,liquidate_end=False)
            result['days']=(future[-1]['T']-start)/86400000 if future else 0
            result['days']=max(0,result['days'])
            status=grade(historical,result)
            with self.db:self.db.execute('UPDATE trials SET forward=? WHERE epoch=?',(json.dumps(result),epoch))
            summaries.append(dict(epoch=epoch,historical=historical,forward=result,status=status))
        return summaries
    def overview(self):
        count=self.db.execute('SELECT COUNT(*) FROM candles').fetchone()[0]
        trials=self.db.execute('SELECT COUNT(*) FROM trials').fetchone()[0]
        return {'candles':count,'trial_count':trials,'parameter_variants':len(STRATEGIES),'symbols':list(SYMBOLS)}
    def close(self):self.db.close()
