"""Deterministic strategy backtests and virtual-money forward tests on public candles.

The model only writes a rule specification; ORBIT's own code evaluates it. Read-only public
market data, no keys, no order endpoints. Results are research measurements, not advice.
"""
import json,math,time,urllib.request

HOST='https://api.hyperliquid.xyz/info'
INTERVALS={'1h':3600,'4h':14400,'1d':86400}
RULES=('sma_cross','rsi_reversion','breakout')

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):raise ValueError('Átirányítás nem engedélyezett.')

def candles(coin,interval,days):
 if interval not in INTERVALS:raise ValueError('Ismeretlen időtáv.')
 end=int(time.time()*1000);start=end-int(days*86400*1000)
 body=json.dumps({'type':'candleSnapshot','req':{'coin':coin,'interval':interval,'startTime':start,'endTime':end}}).encode()
 req=urllib.request.Request(HOST,data=body,headers={'Content-Type':'application/json'},method='POST')
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=20) as r:raw=r.read(4_000_001)
 if len(raw)>4_000_000:raise ValueError('Túl nagy piaci adatválasz.')
 rows=[dict(t=int(c['t']),o=float(c['o']),h=float(c['h']),l=float(c['l']),c=float(c['c'])) for c in json.loads(raw)]
 if len(rows)<60:raise ValueError('Kevés történeti adat ehhez a piachoz: '+coin)
 return rows

def validate(spec):
 if not isinstance(spec,dict):raise ValueError('A stratégia JSON objektum legyen.')
 coin=str(spec.get('coin','')).upper()
 if not coin.isalnum() or len(coin)>12:raise ValueError('Érvénytelen piac (coin).')
 rules=spec.get('rules') if isinstance(spec.get('rules'),dict) else {}
 kind=rules.get('type')
 if kind not in RULES:raise ValueError('A szabály típusa: '+', '.join(RULES))
 def num(d,k,lo,hi,default):
  v=d.get(k,default)
  if not isinstance(v,(int,float)) or not lo<=v<=hi:raise ValueError('Érvénytelen paraméter: '+k)
  return float(v)
 clean=dict(type=kind)
 if kind=='sma_cross':clean.update(fast=int(num(rules,'fast',2,200,10)),slow=int(num(rules,'slow',3,400,30)))
 if kind=='sma_cross' and clean['fast']>=clean['slow']:raise ValueError('A gyors átlag legyen rövidebb a lassúnál.')
 if kind=='rsi_reversion':clean.update(period=int(num(rules,'period',2,100,14)),buy=num(rules,'buy',1,50,30),sell=num(rules,'sell',50,99,70))
 if kind=='breakout':clean.update(lookback=int(num(rules,'lookback',3,200,20)))
 return dict(coin=coin,interval=spec.get('interval') if spec.get('interval') in INTERVALS else '1d',rules=clean,
  side='long_short' if spec.get('side')=='long_short' else 'long',
  stop_loss_pct=num(spec,'stop_loss_pct',.2,50,5),take_profit_pct=num(spec,'take_profit_pct',.2,500,15),
  fee_pct=num(spec,'fee_pct',0,1,.05),position_pct=num(spec,'position_pct',1,100,100),days=int(num(spec,'days',30,720,365)))

def _signal(spec,closes,i):
 r=spec['rules']
 if r['type']=='sma_cross':
  if i<r['slow']:return 0
  f=sum(closes[i-r['fast']+1:i+1])/r['fast'];s=sum(closes[i-r['slow']+1:i+1])/r['slow']
  return 1 if f>s else -1
 if r['type']=='rsi_reversion':
  p=r['period']
  if i<p:return 0
  gains=[max(0,closes[j]-closes[j-1]) for j in range(i-p+1,i+1)];losses=[max(0,closes[j-1]-closes[j]) for j in range(i-p+1,i+1)]
  rs=(sum(gains)/p)/((sum(losses)/p) or 1e-12);rsi=100-100/(1+rs)
  return 1 if rsi<r['buy'] else -1 if rsi>r['sell'] else 0
 lb=r['lookback']
 if i<lb:return 0
 window=closes[i-lb:i]
 return 1 if closes[i]>max(window) else -1 if closes[i]<min(window) else 0

def simulate(spec,rows,start=0):
 """Bar-by-bar: signals on close, fills next open, stops/targets intrabar, fees both ways."""
 closes=[r['c'] for r in rows];equity=1.0;peak=1.0;dd=0.0;pos=0;entry=0.0;trades=[];curve=[]
 size=spec['position_pct']/100;fee=spec['fee_pct']/100
 def close_at(price,i,reason):
  nonlocal equity,pos
  ret=(price/entry-1)*pos
  equity*=1+size*ret-size*fee;trades.append(dict(t=rows[i]['t'],side='long' if pos>0 else 'short',ret_pct=round(ret*100,2),reason=reason));pos=0
 for i in range(max(start,1),len(rows)):
  bar=rows[i]
  if pos:
   stop=entry*(1-pos*spec['stop_loss_pct']/100);target=entry*(1+pos*spec['take_profit_pct']/100)
   if (pos>0 and bar['l']<=stop) or (pos<0 and bar['h']>=stop):close_at(stop,i,'stop')
   elif (pos>0 and bar['h']>=target) or (pos<0 and bar['l']<=target):close_at(target,i,'target')
  sig=_signal(spec,closes,i-1)
  want=1 if sig>0 else (-1 if sig<0 and spec['side']=='long_short' else 0)
  if pos and want!=pos and (sig!=0 or spec['rules']['type']=='sma_cross'):close_at(bar['o'],i,'signal')
  if not pos and want:pos=want;entry=bar['o'];equity*=1-size*fee
  mark=equity*(1+size*((bar['c']/entry-1)*pos if pos else 0))
  peak=max(peak,mark);dd=max(dd,1-mark/peak);curve.append(mark)
 if pos:close_at(rows[-1]['c'],len(rows)-1,'end')
 wins=[t for t in trades if t['ret_pct']>0]
 hold=rows[-1]['c']/rows[max(start,1)]['o']-1
 rets=[curve[k]/curve[k-1]-1 for k in range(1,len(curve)) if curve[k-1]]
 sd=(sum((x-sum(rets)/len(rets))**2 for x in rets)/len(rets))**.5 if len(rets)>2 else 0
 per_year=365*86400/INTERVALS[spec['interval']]
 return dict(return_pct=round((equity-1)*100,2),buy_hold_pct=round(hold*100,2),max_drawdown_pct=round(dd*100,2),trades=len(trades),
  win_rate_pct=round(100*len(wins)/len(trades),1) if trades else 0,sharpe=round((sum(rets)/len(rets))/sd*math.sqrt(per_year),2) if sd else 0,last_trades=trades[-8:])

def backtest(spec,rows=None):
 spec=validate(spec);rows=rows or candles(spec['coin'],spec['interval'],spec['days'])
 cut=int(len(rows)*.7)
 full=simulate(spec,rows);ins=simulate(spec,rows[:cut]);out=simulate(spec,rows,start=cut)
 verdict='promising' if full['return_pct']>0 and out['return_pct']>0 and out['return_pct']>out['buy_hold_pct'] and max(full['max_drawdown_pct'],out['max_drawdown_pct'])<30 and out['trades']>=3 else 'weak'
 return dict(spec=spec,bars=len(rows),period=dict(start=rows[0]['t'],end=rows[-1]['t']),full=full,in_sample=ins,out_of_sample=out,verdict=verdict,measured_at=time.time(),
  note='Visszamenőleges mérés díjjal, csúszás nélkül. Nem garancia és nem befektetési tanács; csak virtuális tesztre alkalmas.')

def forward(spec,started,rows=None):
 """Virtual-money test: the same rules applied only to bars after the test started."""
 spec=validate(spec);rows=rows or candles(spec['coin'],spec['interval'],max(60,spec['days']))
 start=next((i for i,r in enumerate(rows) if r['t']>=started*1000),len(rows))
 if start>=len(rows)-1:return dict(started=started,bars=0,status='waiting',note='Még nincs elég új gyertya a teszt kezdete óta.')
 res=simulate(spec,rows,start=start)
 return dict(res,started=started,bars=len(rows)-start,status='running',virtual_capital=1000,virtual_value=round(1000*(1+res['return_pct']/100),2))

def economics(e):
 """Dropshipping unit economics from explicit, labelled inputs."""
 def f(k,default=0.0):
  v=e.get(k,default)
  if not isinstance(v,(int,float)) or v<0:raise ValueError('Érvénytelen szám: '+k)
  return float(v)
 price,cogs,ship,fees_pct,cac,ret_pct=f('price'),f('product_cost'),f('shipping_cost'),f('payment_fee_pct',3),f('ad_cost_per_sale'),f('return_rate_pct',5)
 if price<=0:raise ValueError('Az eladási ár legyen pozitív.')
 gross=price-cogs-ship-price*fees_pct/100
 profit=gross*(1-ret_pct/100)-cac-(cogs+ship)*ret_pct/100*0.5
 return dict(currency=str(e.get('currency','EUR'))[:5],price=price,contribution_before_ads=round(gross,2),profit_per_order=round(profit,2),margin_pct=round(100*profit/price,1),
  breakeven_ad_cost=round(gross*(1-ret_pct/100)-(cogs+ship)*ret_pct/100*0.5,2),verdict='viable' if profit>0 and profit/price>=.15 else 'thin' if profit>0 else 'loss',
  note='A bemenetek becslések, amíg valós beszállítói és hirdetési adat nincs.')
