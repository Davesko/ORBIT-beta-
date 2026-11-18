import json
import tempfile
import threading
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import MagicMock,patch

from research_engine import Strategy,STRATEGIES,CATALOG,daily_strategies,ResearchStore,normalized_candles,simulate,partitions,grade,MINUTE
from research_technology import PersistentInfo,benchmark_transport,local_plan
from watch_research import ResearchWorker
import ui_bridge

BASE=1789689600000
NOW=datetime(2026,10,19,tzinfo=timezone.utc)


def bars(n=1200):
    result=[];price=100
    for i in range(n):
        o=price;price*=1.002 if (i//30)%2==0 else .998
        result.append({'t':BASE+i*MINUTE,'T':BASE+(i+1)*MINUTE-1,'o':o,'h':max(o,price)*1.0002,'l':min(o,price)*.9998,'c':price,'v':100})
    return result


def choice(store,data):return store.shortlist({'BTC':data})[0]


def good_history():
    test={'trades':100,'net_percent':1,'drawdown_percent':1,'profit_factor':1.5,'gaps':0}
    return {'history_days':35,'test':test,'stress':dict(test,net_percent=.3),'blocks':[test,test,test]}


class ResearchTests(unittest.TestCase):
    def test_candles_exclude_unfinished_bars_and_reject_wrong_identity(self):
        raw={'s':'BTC','i':'1m','t':BASE,'T':BASE+MINUTE-1,'o':'100','h':'102','l':'99','c':'101','v':'10'}
        self.assertEqual(normalized_candles([raw],'BTC',BASE+1),[])
        self.assertEqual(len(normalized_candles([raw],'BTC',BASE+MINUTE)),1)
        for wrong in [dict(raw,s='ETH'),dict(raw,l='103'),dict(raw,c='Infinity')]:
            with self.assertRaises(ValueError):normalized_candles([wrong],'BTC',BASE+MINUTE)

    def test_conflicting_duplicate_bars_are_rejected(self):
        raw={'s':'BTC','i':'1m','t':BASE,'T':BASE+MINUTE-1,'o':'100','h':'102','l':'99','c':'101','v':'10'}
        with self.assertRaises(ValueError):normalized_candles([raw,dict(raw,c='100')],'BTC',BASE+MINUTE)

    def test_grid_is_bounded_unique_and_rotates_by_day(self):
        self.assertEqual(len(CATALOG),216);self.assertEqual(len({s.id for s in CATALOG}),216)
        a=daily_strategies(NOW.date());b=daily_strategies((NOW+timedelta(days=1)).date())
        self.assertEqual(len(a),24);self.assertNotEqual(a,b);self.assertTrue(set(a)<=set(CATALOG))

    def test_training_and_validation_do_not_read_holdout_values(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ResearchStore(Path(directory)/'research.sqlite');original=bars()
            modified=json.loads(json.dumps(original));boundary=int(len(original)*.8)
            for row in modified[boundary:]:
                for field in ('o','h','l','c'):row[field]*=10
            one=store.shortlist({'BTC':original});two=store.shortlist({'BTC':modified})
            self.assertTrue(one);self.assertEqual(one,two);store.close()

    def test_purge_separates_evaluation_windows(self):
        train,valid,test=partitions(bars())
        self.assertGreater(valid[0]['t']-train[-1]['t'],20*MINUTE)
        self.assertGreater(test[0]['t']-valid[-1]['t'],20*MINUTE)

    def test_extra_costs_reduce_net_return(self):
        data=bars();strategy=Strategy('momentum',3,.0015,.0075)
        normal=simulate(data,strategy);stress=simulate(data,strategy,2)
        self.assertGreater(normal['trades'],0);self.assertLess(stress['net_percent'],normal['net_percent'])

    def test_no_signal_uses_current_bar_close_before_its_open(self):
        data=bars(30)
        for row in data:
            row.update(o=100,h=100,l=100,c=100)
        data[-1].update(h=200,c=200)
        result=simulate(data,Strategy('momentum',3,.0015,.0075))
        self.assertEqual(result['trades'],0)

    def test_future_shadow_does_not_force_close_at_each_refresh(self):
        data=bars(8);strategy=Strategy('momentum',3,.0015,.05,5)
        result=simulate(data,strategy,trade_start=data[5]['t'],liquidate_end=False)
        self.assertEqual(result['open_positions'],1);self.assertEqual(result['trades'],0)

    def test_gaps_are_visible_and_disqualify_a_method(self):
        data=bars();del data[600]
        result=simulate(data,STRATEGIES[0]);self.assertEqual(result['gaps'],1)
        historical=good_history();historical['test']=dict(historical['test'],gaps=1)
        self.assertFalse(grade(historical,{'days':10,'trades':100,'net_percent':1})['eligible'])

    def test_one_positive_backtest_never_satisfies_forward_gate(self):
        result=grade(good_history(),{'days':0,'trades':0,'net_percent':0})
        self.assertFalse(result['eligible']);self.assertTrue(any('7 nap' in s for s in result['reasons']))
        good={'days':10,'trades':100,'net_percent':.5,'closed_net_percent':.4,'gaps':0,'drawdown_percent':1}
        self.assertTrue(grade(good_history(),good)['eligible'])
        short=good_history();short['history_days']=3
        self.assertFalse(grade(short,good)['eligible'])

    def test_double_cost_failure_blocks_qualification(self):
        h=good_history();h['stress']['net_percent']=-1
        self.assertFalse(grade(h,{'days':10,'trades':100,'net_percent':1})['eligible'])

    def test_fixed_trial_survives_restart_and_cannot_be_reselected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'research.sqlite';store=ResearchStore(path);data=bars();selected=choice(store,data)
            self.assertTrue(store.freeze_trial('2026-10-19',selected,data,NOW,'test'))
            payload=json.loads(store.db.execute('SELECT payload FROM trials').fetchone()[0])
            self.assertGreater(payload['forward_start'],int(NOW.timestamp()*1000))
            store.close();store=ResearchStore(path)
            self.assertFalse(store.freeze_trial('2026-10-19',selected,data,NOW,'changed'))
            self.assertEqual(json.loads(store.db.execute('SELECT payload FROM trials').fetchone()[0]),payload);store.close()

    def test_forward_cannot_reuse_historical_test_as_new_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ResearchStore(Path(directory)/'research.sqlite');data=bars();store.ingest('BTC',data)
            store.freeze_trial('day',choice(store,data),data,NOW,'test')
            forward=store.forward_update()[0]['forward']
            self.assertEqual(forward['trades'],0);self.assertEqual(forward['days'],0);store.close()

    def test_closed_history_cannot_be_silently_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ResearchStore(Path(directory)/'research.sqlite');data=bars(10);store.ingest('BTC',data)
            changed=dict(data[0],c=999)
            with self.assertRaises(ValueError):store.ingest('BTC',[changed])
            self.assertEqual(store.candles('BTC'),data);store.close()

    def test_transport_cannot_send_trading_payload(self):
        with patch('research_technology.http.client.HTTPSConnection') as network:
            with self.assertRaises(ValueError):PersistentInfo().info({'type':'order'})
            network.assert_not_called()

    def test_transport_comparison_requires_same_market_scope(self):
        values=[{'universe':[{'name':'BTC'}]},[{}]]
        persistent=MagicMock();persistent.info.return_value=values
        ticks=[]
        for i in range(3):ticks.extend([i*2,i*2+.2,i*2+1,i*2+1.05])
        with patch('research_technology.public_info',return_value=values),patch('research_technology.PersistentInfo',return_value=persistent),patch('research_technology.time.perf_counter',side_effect=ticks):
            result=benchmark_transport(3)
        self.assertEqual(result['selected'],'persistent');persistent.close.assert_called_once()

    def test_ai_cannot_add_arbitrary_strategy_or_command(self):
        selected=[{'id':'BTC/allowed','symbol':'BTC','train':{},'validation':{},'score':0}]
        response=MagicMock();response.read.return_value=json.dumps({'done':True,'message':{'content':json.dumps({'candidate_id':'execute shell','reason':'x','technology_proposal':'x','validation_test':'x'})}}).encode()
        opener=MagicMock();opener.open.return_value.__enter__.return_value=response
        with patch('research_technology.urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ValueError):local_plan(selected,[])

    def test_manual_research_pause_is_honored_on_app_reopen(self):
        with tempfile.TemporaryDirectory() as directory,patch('ui_bridge.ROOT',Path(directory)),patch('ui_bridge.Path.home',return_value=Path(directory)),patch('ui_bridge.job_running',return_value=False),patch('ui_bridge.subprocess.run') as process:
            ui_bridge.research_control('research_stop')
            ui_bridge.research_control('research_ensure')
            process.assert_not_called()
            self.assertFalse(json.loads((Path(directory)/'research-control.json').read_text())['enabled'])

    def test_start_research_never_changes_portfolio_or_trading_mode(self):
        with tempfile.TemporaryDirectory() as directory,patch('ui_bridge.ROOT',Path(directory)),patch('ui_bridge.Path.home',return_value=Path(directory)),patch('ui_bridge.job_running',return_value=False),patch('ui_bridge.subprocess.run'),patch('ui_bridge.prepare_account') as account:
            sentinel=Path(directory)/'portfolio-account.json';sentinel.write_text('{"mode":"copy","database":"test.sqlite"}')
            before=sentinel.read_bytes();ui_bridge.research_control('research_start')
            self.assertEqual(sentinel.read_bytes(),before);account.assert_not_called()

    def test_worker_continues_instead_of_stopping_after_favorable_result(self):
        with tempfile.TemporaryDirectory() as directory:
            worker=ResearchWorker(Path(directory),threading.Event())
            h=good_history();h.update(id='BTC/test',selection_trials=24)
            f={'net_percent':1,'trades':100,'days':10}
            with patch.object(worker,'collect',return_value=[]),patch.object(worker,'technology',return_value={}),patch.object(worker.store,'trial_exists',return_value=True),patch.object(worker.store,'forward_update',return_value=[{'historical':h,'forward':f,'status':{'eligible':True,'reasons':[]}}]):
                worker.cycle();self.assertFalse(worker.stop.is_set());self.assertEqual(worker.state['eligible_count'],1)
                self.assertIn('folytatódik',worker.state['phase'])
            worker.close()


if __name__=='__main__':unittest.main()
