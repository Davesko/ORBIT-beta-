"""Persistent research-only loop. Own datasets/trials, no account or trading imports."""
import json
import os
import shutil
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from agent import number
from continuous_data import atomic_json, utcnow
from market_data import public_info
from research_engine import ResearchStore,SYMBOLS,STRATEGIES,MINUTE,BARS,SWING,CATALOG_15M,normalized_candles,daily_strategies,series_key
from research_technology import PersistentInfo,benchmark_transport,official_releases,local_plan

ROOT=Path.home()/'Library/Application Support/ReszvenyAI'


class ResearchWorker:
    def __init__(self,root,stop):
        self.root=root;self.stop=stop
        (root/'data').mkdir(parents=True,exist_ok=True)
        self.store=ResearchStore(root/'data/research-lab.sqlite')
        self.transport=PersistentInfo();self.state={}
    def publish(self,phase,**values):
        self.state.update(values,phase=phase,updated_at=utcnow().isoformat(),mode='RESEARCH_ONLY')
        atomic_json(self.root/'reports/research-state.json',self.state)
    def collect(self):
        now_ms=int(utcnow().timestamp()*1000);errors=[]
        for symbol in SYMBOLS:
            if self.stop.is_set():break
            last=self.store.last_time(symbol)
            start=last+MINUTE if last is not None else now_ms-5000*MINUTE
            if start>now_ms-MINUTE:continue
            payload={'type':'candleSnapshot','req':{'coin':symbol,'interval':'1m','startTime':start,'endTime':now_ms}}
            try:
                selected=self.store.get_setting('technology',{}).get('benchmark',{}).get('selected')
                if selected=='persistent':
                    try:raw=self.transport.info(payload)
                    except Exception:raw=public_info(payload)
                else:raw=public_info(payload)
                rows=normalized_candles(raw,symbol,now_ms)
                self.store.ingest(symbol,rows)
                self.publish('Árfolyamtörténet gyűjtése · '+symbol,**self.store.overview())
            except Exception as exc:errors.append(symbol+': '+str(exc))
            if last is None and self.stop.wait(15):break # paced initial history download
        # 15-minute bars for the most liquid coins: one request brings 52 days, enough to test right away.
        step=BARS['15m']
        for symbol in self.swing_symbols():
            if self.stop.is_set():break
            key=series_key(symbol,'15m');last=self.store.last_time(key)
            start=last+step if last is not None else now_ms-5000*step
            if start>now_ms-step:continue
            try:
                raw=public_info({'type':'candleSnapshot','req':{'coin':symbol,'interval':'15m','startTime':start,'endTime':now_ms}})
                self.store.ingest(key,normalized_candles(raw,symbol,now_ms,'15m'))
            except Exception as exc:errors.append(symbol+' 15p: '+str(exc))
            if last is None and self.stop.wait(2):break
        # Bounded retention; trials keep their immutable historical metrics and data digest.
        with self.store.db:self.store.db.execute('DELETE FROM candles WHERE t<?',(now_ms-180*86400000,))
        return errors
    def swing_symbols(self,count=10):
        """BTC, ETH, SOL and the most traded other coins of the moment (by 24-hour volume)."""
        try:rows=json.loads((self.root/'reports/market-state.json').read_text()).get('rows',[])
        except (OSError,ValueError):rows=[]
        busy=[r['symbol'] for r in sorted(rows,key=lambda r:-float(r.get('volume') or 0)) if r.get('symbol') and r['symbol'].isalnum()]
        return list(dict.fromkeys(list(SWING)+busy))[:count]
    def technology(self):
        previous=self.store.get_setting('technology',{})
        if time.time()-previous.get('checked_epoch',0)<21600:return previous
        self.publish('Adatlekérési technológiák mérése')
        result={'checked_epoch':time.time(),'updated_at':utcnow().isoformat()}
        try:result['benchmark']=benchmark_transport()
        except Exception as exc:result['benchmark']={'error':str(exc),'selected':'standard'}
        if self.stop.is_set():return previous
        self.publish('Hivatalos technológiai kiadások ellenőrzése')
        result['releases']=official_releases()
        self.store.put_setting('technology',result)
        return result
    def cycle(self):
        if shutil.disk_usage(self.root).free<1024**3:raise ValueError('Kevés szabad tárhely a további kutatási adatokhoz.')
        self.publish('Új adatok ellenőrzése',error=None)
        errors=self.collect()
        if self.stop.is_set():return
        technology=self.technology()
        if self.stop.is_set():return
        epoch=utcnow().date().isoformat()
        if not self.store.trial_exists(epoch):
            self.publish('Stratégiaváltozatok összehasonlítása')
            series={}
            now_ms=int(utcnow().timestamp()*1000)
            for symbol in SYMBOLS:
                bars=self.store.candles(symbol,now_ms-45*86400000)
                if len(bars)>=1000 and 0<=now_ms-bars[-1]['T']<=180000:series[symbol]=bars
            strategies=daily_strategies(utcnow().date())
            choices=self.store.shortlist(series,strategies)
            if choices:
                self.store.put_setting('scores/'+epoch,choices)
                self.publish('Helyi AI-kutatási terv készül')
                ai_error=None
                try:
                    plan=local_plan(choices,technology.get('releases',[]))
                    chosen=next(row for row in choices[:3] if row['id']==plan['candidate_id'])
                    self.store.put_setting('ai_plan',dict(plan,updated_at=utcnow().isoformat()))
                    reason=plan['reason']
                except Exception as exc:
                    ai_error=str(exc);chosen=choices[0];reason='Rögzített pontozás alapján kiválasztott kutatási jelölt; az AI-terv nem elérhető.'
                if self.stop.is_set():return
                self.store.freeze_trial(epoch,chosen,series[chosen['symbol']],utcnow(),reason,len(STRATEGIES)*len(series))
                self.store.put_setting('last_ai_error',ai_error)
                self.publish('Elkülönített teszt rögzítve · új adatokon folytatódik a megfigyelés')
        swing_epoch=epoch+'@15m'
        if not self.store.trial_exists(swing_epoch):
            now_ms=int(utcnow().timestamp()*1000);series={}
            for symbol in self.swing_symbols():
                bars=self.store.candles(series_key(symbol,'15m'),now_ms-60*86400000)
                if len(bars)>=1000 and 0<=now_ms-bars[-1]['T']<=2*BARS['15m']:series[symbol]=bars
            choices=self.store.shortlist(series,daily_strategies(utcnow().date(),CATALOG_15M)) if series else []
            if choices and not self.stop.is_set():
                self.store.freeze_trial(swing_epoch,choices[0],series[choices[0]['symbol']],utcnow(),'Rögzített pontozás: a legjobb tanuló- és ellenőrzőszakasz (15 perces sáv).',len(CATALOG_15M)*len(series))
        self.publish('Új adaton végzett megfigyelések frissítése')
        trials=self.store.forward_update()
        latest=trials[0] if trials else None
        positive=sum(1 for trial in trials if trial['status']['eligible'])
        detail={}
        if latest:
            h=latest['historical'];f=latest['forward']
            detail={'candidate':h['id'],'history_days':round(h['history_days'],2),'test_net_percent':h['test']['net_percent'],
                    'test_trades':h['test']['trades'],'forward_net_percent':f['net_percent'],'forward_trades':f['trades'],
                    'forward_days':round(f['days'],2),'reasons':latest['status']['reasons'],'selection_trials':h['selection_trials']}
        # What the fast trader may use: strategies that passed the test and the new-data observation.
        def brief(trial):
            h,f=trial['historical'],trial['forward']
            return dict(id=h.get('id'),symbol=h.get('symbol') or str(h.get('id','')).split('/')[0],strategy=h.get('strategy'),
                        test_net_percent=(h.get('test') or {}).get('net_percent'),forward_net_percent=f.get('net_percent',0),
                        forward_trades=f.get('trades',0),forward_days=round(f.get('days',0),2),reasons=trial['status']['reasons'][:3])
        eligible=[brief(trial) for trial in trials if trial['status']['eligible'] and trial['historical'].get('strategy')]
        watching=[brief(trial) for trial in trials[:6]]
        self.publish('Kutatás folytatódik · következő lezárt gyertyákra vár',**self.store.overview(),
                     candidate_summary=detail,eligible_count=positive,data_errors=errors,
                     eligible=sorted(eligible,key=lambda e:-e['forward_net_percent']),watching=watching,swing_symbols=self.swing_symbols(),
                     status='Tesztfeltételeket teljesítő jelölt megfigyelés alatt' if positive else 'Még nincs megerősített módszer',
                     technology=technology,ai_plan=self.store.get_setting('ai_plan'),ai_error=self.store.get_setting('last_ai_error'),
                     next_cycle_at=datetime.fromtimestamp(time.time()+60,timezone.utc).isoformat(),
                     notice='A kutatás nem állít át kereskedési módot. A teszteredmény nem garantál jövőbeli profitot.')
    def close(self):self.transport.close();self.store.close()


def main():
    try:os.nice(10)
    except OSError:pass
    stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    worker=ResearchWorker(ROOT,stop)
    try:
        while not stop.is_set():
            try:worker.cycle()
            except Exception as exc:worker.publish('Átmeneti kutatási hiba · újrapróbálás',error=str(exc))
            # Keeps searching even after a candidate passes. Manual pause is respected.
            stop.wait(60)
    finally:worker.close()


if __name__=='__main__':main()
