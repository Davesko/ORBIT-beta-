import datetime,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import daily_report,venture
class DailyReportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
 def test_compose_is_short_and_plain(self):
  text=daily_report.compose(self.s)
  self.assertTrue(text.startswith('🌅 ORBIT napi összefoglaló'));self.assertNotIn('**',text);self.assertLess(len(text),1500)
  venture.configure(self.s,dict(enabled=True))
  self.assertIn('Autopilóta (fut)',daily_report.compose(self.s))
 def test_finished_improvements_are_listed_in_hungarian(self):
  today=datetime.date.today().isoformat()
  (self.s.root/'improvements.md').write_text('| # | Ötlet | Haszon | Méret | Állapot |\n|---|---|---|---|---|\n'
   '| 1 | **Regressziós védelem.** Leírás | Haszon | M | kész ('+today+'): részletek |\n| 2 | **Még nincs kész** | x | S | ötlet |\n| 3 | **Régi munka** | x | S | kész (2020-01-01) |\n')
  self.assertEqual(daily_report.improvements(self.s,time.time()-3600),['Regressziós védelem'])
  self.assertIn('🛠 Az ORBIT 1 fejlesztést kapott: Regressziós védelem',daily_report.today(self.s))
 def test_app_gets_the_same_day_summary_through_the_bridge(self):
  import bridge
  r=bridge.dispatch(dict(action='enterprise_status',scope='business_lab',day_summary=True,project='universe'),self.s)
  self.assertTrue(r['ok']);self.assertTrue(r['text'].startswith('📋 ORBIT ma'))
 def test_main_assistant_can_read_the_day_summary(self):
  from assistant_context import read_app
  import commander
  from assistant_resilience import planner_system
  self.assertTrue(read_app(self.s,'universe','today')['summary'].startswith('📋 ORBIT ma'))
  self.assertIn('{"app":"today"',planner_system(commander.SYSTEM));self.assertIn('{"app":"autopilot"',planner_system(commander.SYSTEM),'the assistant is told about both supported reads')
  self.assertIn('never guess durations',planner_system(commander.SYSTEM))
 def test_sends_once_per_day_after_eight(self):
  sent=[]
  cfg=dict(mode='local',providers=dict(telegram=dict(notifications=True,chat_id='1')))
  morning=datetime.datetime(2026,10,30,7,0).timestamp();later=datetime.datetime(2026,10,30,9,0).timestamp()
  with patch('connections.settings',return_value=cfg),patch('connections.allowed',return_value=True),patch('connections.http',side_effect=lambda *a,**k:sent.append(a[2]['text'])):
   self.assertFalse(daily_report.tick(self.s,morning))
   self.assertTrue(daily_report.tick(self.s,later));self.assertFalse(daily_report.tick(self.s,later+3600))
   self.assertTrue(daily_report.tick(self.s,later+86400))
  self.assertEqual(len(sent),2)
 def test_evening_summary_only_after_the_owner_switches_it_on(self):
  sent=[]
  cfg=dict(mode='local',providers=dict(telegram=dict(notifications=True,chat_id='1')))
  morning=datetime.datetime(2026,10,30,9,0).timestamp();night=datetime.datetime(2026,10,30,22,30).timestamp()
  with patch('connections.settings',return_value=cfg),patch('connections.allowed',return_value=True),patch('connections.http',side_effect=lambda *a,**k:sent.append(a[2]['text'])):
   self.assertTrue(daily_report.tick(self.s,morning));self.assertFalse(daily_report.tick(self.s,night),'off by default')
   self.assertTrue(daily_report.toggle_evening(self.s))
   self.assertTrue(daily_report.tick(self.s,night));self.assertFalse(daily_report.tick(self.s,night+600),'once per evening')
  self.assertTrue(sent[-1].startswith('🌙 ORBIT esti összefoglaló'))
  self.assertFalse(daily_report.toggle_evening(self.s))
if __name__=='__main__':unittest.main()
