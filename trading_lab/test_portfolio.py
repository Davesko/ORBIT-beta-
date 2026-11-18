import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

from portfolio import value_portfolio
from account import prepare_account, active_account, read_book
from copy_trading import PaperCopyLedger
import ui_bridge

BTC='hyperliquid:default:perpetual:BTC:USDC'
ETH='hyperliquid:default:perpetual:ETH:USDC'


class PortfolioTests(unittest.TestCase):
    def book(self):
        return {'settled':'9990','currency':'USDC','positions':{
            BTC:{'quantity':'0.1','entry':'60000'},ETH:{'quantity':'-1','entry':'3000'}}}

    def test_long_short_cash_and_total_reconcile_without_double_counting_exposure(self):
        result=value_portfolio(self.book(),{'BTC':'61000','ETH':'2900'},True)
        self.assertEqual(result['equity'],'10190.0')
        self.assertEqual(result['unrealized_pnl'],'200.0')
        self.assertEqual(result['gross_exposure'],'9000.0')
        self.assertEqual(result['available_capacity'],'1190.0')
        self.assertEqual(result['paper_positions'][1]['direction'],'short')
        self.assertEqual(result['paper_positions'][1]['unrealized_pnl'],'100')

    def test_stale_or_missing_price_does_not_invent_zero_pnl_or_partial_totals(self):
        for prices,fresh in [({'BTC':'61000'},True),({'BTC':'61000','ETH':'2900'},False)]:
            result=value_portfolio(self.book(),prices,fresh)
            self.assertIsNone(result['equity']);self.assertIsNone(result['available_capacity'])
            self.assertEqual(result['settled_balance'],'9990');self.assertEqual(result['position_count'],2)
            self.assertTrue(any(row['error'] for row in result['paper_positions']))

    def test_spot_or_foreign_currency_instrument_is_never_priced_as_perp(self):
        for identifier in ['hyperliquid:default:spot:BTC:USDC','hyperliquid:default:perpetual:BTC:EUR']:
            result=value_portfolio({'settled':'10000','positions':{identifier:{'quantity':'1','entry':'60000'}}},{'BTC':'61000'},True)
            self.assertIsNone(result['equity']);self.assertIsNone(result['paper_positions'][0]['notional'])

    def test_capacity_limit_can_be_exceeded_without_hiding_positions(self):
        result=value_portfolio(self.book(),{'BTC':'61000','ETH':'2900'},True,'50')
        self.assertEqual(result['available_capacity'],'0');self.assertEqual(result['capacity_deficit'],'3905.0')
        self.assertEqual(result['position_count'],2)

    def test_switching_modes_preserves_money_and_requires_flat_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            account=prepare_account(root,'copy','0x'+'1'*40)
            path=root/'data'/account['database'];ledger=PaperCopyLedger(path)
            ledger.connection.execute('UPDATE book SET payload=? WHERE id=1',(json.dumps(self.book()),));ledger.close()
            with self.assertRaises(ValueError):prepare_account(root,'fast_ai')
            self.assertEqual(active_account(root)['mode'],'copy')
            ledger=PaperCopyLedger(path)
            ledger.connection.execute('UPDATE book SET payload=? WHERE id=1',(json.dumps({'settled':'10037','positions':{}}),));ledger.close()
            fast=prepare_account(root,'fast_ai')
            self.assertEqual(fast['database'],account['database']);self.assertEqual(read_book(root,fast)['settled'],'10037')

    def test_resume_same_mode_preserves_open_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);account=prepare_account(root,'copy','0x'+'1'*40)
            ledger=PaperCopyLedger(root/'data'/account['database'])
            ledger.connection.execute('UPDATE book SET payload=? WHERE id=1',(json.dumps(self.book()),));ledger.close()
            prepare_account(root,'copy','0x'+'1'*40)
            self.assertEqual(len(read_book(root,account)['positions']),2)

    def test_dashboard_and_balance_share_one_valuation(self):
        with tempfile.TemporaryDirectory() as directory,patch('ui_bridge.ROOT',Path(directory)),patch('ui_bridge.job_running',return_value=False):
            root=Path(directory);(root/'reports').mkdir()
            (root/'reports/paper-copy-state.json').write_text(json.dumps({'book':self.book()}))
            (root/'reports/market-state.json').write_text(json.dumps({'updated_at':datetime.now(timezone.utc).isoformat(),'rows':[{'symbol':'BTC','price':'61000'},{'symbol':'ETH','price':'2900'}]}))
            result=ui_bridge.dashboard_snapshot()
            self.assertEqual(result['equity'],'10190.0');self.assertEqual(len(result['paper_positions']),2)

    def test_fast_cannot_start_while_copying_and_flatten_cannot_race_a_worker(self):
        with patch('ui_bridge.job_running',return_value=True),patch('ui_bridge.job_active',return_value=True),patch('ui_bridge.prepare_account') as change:
            with self.assertRaises(ValueError):ui_bridge.fast_control(True)
            with self.assertRaises(ValueError):ui_bridge.flatten_paper()
            change.assert_not_called()

    def test_one_stop_button_stops_trading_and_closes_open_trades(self):
        # 2 Nov: the owner could not stop the portfolio; three copied trades stayed open after trading stopped.
        with patch('ui_bridge.dispatch',wraps=ui_bridge.dispatch) as call,patch('ui_bridge.job_running',return_value=False),patch('ui_bridge.job_active',return_value=False),\
             patch('ui_bridge.read_book',return_value={'positions':{'x':{}}}),patch('ui_bridge.active_account',return_value={'mode':'copy'}),\
             patch('ui_bridge.flatten_paper',return_value={'ok':True,'message':'Minden virtuális pozíció lezárva, szimulált költségekkel.'}) as flatten:
            r=ui_bridge.dispatch({'action':'stop_all'})
        self.assertTrue(r['message'].startswith('Minden leállítva.'));self.assertIn('lezárva',r['message']);flatten.assert_called_once()
        with patch('ui_bridge.job_running',return_value=False),patch('ui_bridge.job_active',return_value=False),patch('ui_bridge.read_book',return_value={'positions':{}}),\
             patch('ui_bridge.active_account',return_value={'mode':'copy'}),patch('ui_bridge.flatten_paper') as flatten:
            self.assertIn('Nem volt nyitott',ui_bridge.dispatch({'action':'stop_all'})['message']);flatten.assert_not_called()

    def test_copying_another_trader_starts_from_a_flat_book_at_the_chosen_size(self):
        # 2 Nov: the owner chooses whom to copy, an outside address too, and how big.
        other='0x'+'b'*40
        def started(request):
            if request['action']=='paper_start':return {'ok':True,'message':'x','sent':request}
            return original(request)
        original=ui_bridge.dispatch
        with patch('ui_bridge.dispatch',side_effect=started),patch('ui_bridge.job_running',return_value=False),patch('ui_bridge.job_active',return_value=False),\
             patch('ui_bridge.read_book',return_value={'positions':{'x':{}}}),patch('ui_bridge.active_account',return_value={'mode':'copy','leader':'0x'+'a'*40}),\
             patch('ui_bridge.flatten_paper',return_value={'ok':True,'message':'Lezárva.'}) as flatten:
            r=original({'action':'copy_start','symbol':other.upper().replace('0X','0x'),'settings':json.dumps({'size_percent':50,'auto_best':False})})
        flatten.assert_called_once();self.assertIn('méret 50%',r['message']);self.assertEqual((r['sent']['symbol'],r['sent']['size_percent']),(other,50))
        with self.assertRaises(ValueError):original({'action':'copy_start','symbol':'nem-cím'})

    def test_the_main_switch_turns_everything_off_and_back_on(self):
        # The owner (2 Nov): one switch that turns off the news search and everything else when MiLLIONS is not wanted.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stopped=[];original=ui_bridge.dispatch
            def fake(request):
                if request['action']=='stop_all':return {'ok':True,'message':'Minden leállítva. Minden virtuális pozíció lezárva.'}
                return original(request)
            with patch('ui_bridge.ROOT',root),patch('ui_bridge.dispatch',side_effect=fake),patch('ui_bridge.unload',side_effect=stopped.append),\
                 patch('ui_bridge.results',return_value={'mode':'fast'}):
                r=original({'action':'power_off'})
            self.assertEqual(stopped,list(ui_bridge.POWER_JOBS));self.assertIn('kikapcsolva',r['message']);self.assertIn('lezárva',r['message'])
            self.assertEqual(json.loads((root/'research-control.json').read_text()),{'enabled':False})
            self.assertEqual(json.loads((root/'power.json').read_text())['resume'],{'mode':'fast'})
            with patch('ui_bridge.ROOT',root):
                for action in ('fast_start','monitor_start','copy_best','copy_start','paper_start','research_start'):
                    with self.assertRaisesRegex(ValueError,'ki van kapcsolva'):original({'action':action})
                self.assertIn('ki van kapcsolva',original({'action':'research_ensure'})['message'],'the old window cannot switch it back on')
            with patch('ui_bridge.ROOT',root),patch('ui_bridge.monitor_control') as monitor,patch('ui_bridge.research_control') as research,\
                 patch('ui_bridge.fast_control',return_value={'ok':True,'message':'Gyors AI elindítva.'}) as fast:
                r=original({'action':'power_on'})
            monitor.assert_called_once_with(True);research.assert_called_once_with('research_start');fast.assert_called_once_with(True)
            self.assertTrue(json.loads((root/'power.json').read_text())['on']);self.assertIn('Gyors AI elindítva',r['message'])

    def test_a_loaded_but_idle_job_is_not_shown_as_running(self):
        # After a restart both jobs sat loaded with 'state = not running'; the page said they were on for days.
        from subprocess import CompletedProcess
        idle=CompletedProcess([],0,'gui/501/hu.reszvenyai.fast-ai = {\n\tstate = not running\n}','')
        busy=CompletedProcess([],0,'gui/501/hu.reszvenyai.fast-ai = {\n\tstate = running\n}','')
        with patch('ui_bridge.subprocess.run',return_value=idle):
            self.assertTrue(ui_bridge.job_running('hu.reszvenyai.fast-ai'));self.assertFalse(ui_bridge.job_active('hu.reszvenyai.fast-ai'))
        with patch('ui_bridge.subprocess.run',return_value=busy):self.assertTrue(ui_bridge.job_active('hu.reszvenyai.fast-ai'))


if __name__=='__main__':unittest.main()
