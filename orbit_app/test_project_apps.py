import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import project_apps

class ProjectAppTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  self.trading=self.s.create_project('Kereskedési labor','Virtuális számla','trading')
  self.root=Path(self.tmp.name)/'ReszvenyAI';(self.root/'core').mkdir(parents=True);(self.root/'core'/'ui_bridge.py').write_text('# MiLLIONS bridge')
 def test_a_trading_project_brings_the_millions_app_others_keep_the_map(self):
  # The owner (1 Nov): projects such as MiLLIONS need their own Műhely, with entirely different functions.
  with patch('project_apps.MILLIONS',self.root):
   app=project_apps.describe(self.s,self.trading)
   self.assertEqual((app['app'],app['title'],app['installed']),('millions','MiLLIONS',True))
   self.assertEqual([(p['id'],p['label']) for p in app['pages']],[('overview','Áttekintés'),('fast','Gyors AI'),('copy','Másolás'),('market','Hírek és piac'),('details','Haladó')])
   self.assertEqual(project_apps.describe(self.s,'universe')['app'],'workspace')
   self.assertEqual(dispatch(dict(action='snapshot',project=self.trading),self.s)['project_app']['app'],'millions')
   self.assertEqual(dispatch(dict(action='snapshot',project='universe'),self.s)['project_app']['app'],'workspace')
 def test_only_paper_operations_reach_millions(self):
  sent=[]
  def run(cmd,input=None,**k):
   sent.append(json.loads(input));return subprocess.CompletedProcess(cmd,0,json.dumps(dict(ok=True,message='Virtuális portfólió',equity='10000')),'')
  with patch('project_apps.MILLIONS',self.root),patch('project_apps.subprocess.run',side_effect=run):
   r=dispatch(dict(action='project_app',project=self.trading,op='paper_start',args=dict(symbol='0x'+'a'*40,extra='x')),self.s)
   self.assertEqual((r['app'],r['result']['equity']),('millions','10000'));self.assertEqual(sent[-1],dict(action='paper_start',symbol='0x'+'a'*40),'only the known fields go through')
   # The owner (2 Nov) could not stop the portfolio: one button stops trading and closes the open virtual trades.
   dispatch(dict(action='project_app',project=self.trading,op='stop_all'),self.s);self.assertEqual(sent[-1],dict(action='stop_all'))
   # Its own model calls and model server switch would load a second large model next to ORBIT's.
   for op in ('analyze','evaluate','demo','start','stop','real_order'):
    with self.assertRaisesRegex(ValueError,'nem indítja'):dispatch(dict(action='project_app',project=self.trading,op=op),self.s)
   with self.assertRaisesRegex(ValueError,'nincs saját alkalmazása'):dispatch(dict(action='project_app',project='universe',op='dashboard_snapshot'),self.s)
 def test_millions_errors_reach_the_owner_in_words(self):
  bad=lambda cmd,**k:subprocess.CompletedProcess(cmd,0,json.dumps(dict(ok=False,message='A művelet nem sikerült: Már fut virtuális követés.')),'')
  with patch('project_apps.subprocess.run',side_effect=bad),self.assertRaisesRegex(ValueError,'Már fut virtuális követés'):project_apps.millions('paper_start',dict(symbol='x'),root=self.root)
  with self.assertRaisesRegex(ValueError,'nincs telepítve'):project_apps.millions('dashboard_snapshot',root=Path(self.tmp.name)/'nincs')

if __name__=='__main__':unittest.main()
