import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import venture

class WorkTimeTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.s=Studio(Path(tmp.name));self.addCleanup(self.s.db.close);self.s.create_project('Műhely','',pid=venture.PID)
  self.f=dict(idea_id='abc123',name='TermékE');self.n=0
 def job(self,run,node,started,finished,status='done',kind='mission_agent'):
  self.n+=1;self.s.db.execute('INSERT INTO jobs(id,project,agent,kind,status,prompt,created,started,finished,payload) VALUES(?,?,?,?,?,?,?,?,?,?)',('j'+str(self.n),venture.PID,'a',kind,status,'p',started-999,started,finished,json.dumps(dict(mission_run=run,mission_node=node))));self.s.db.commit()
 def test_the_total_is_the_ais_running_time_by_step(self):
  # The owner (2 Nov): how much the AI worked on one project in total, e.g. the space adventure.
  self.job('r1','research',1000,1600);self.job('r1','build',2000,5600);self.job('r2','review',6000,6300);self.job('other','build',0,50000)
  self.job('r1','build',7000,7999,kind='mission_dispatch')
  w=venture.project_work(self.s,self.f,[dict(run='r1'),dict(run='r2')])
  self.assertEqual((w['total'],w['parts'],w['running']),(4500,dict(research=600,build=3600,review=300),False),'the queue wait and other projects do not count')
 def test_reading_the_time_never_leaves_a_write_lock(self):
  # 3 Nov: an INSERT OR IGNORE with nothing new left a transaction open; the worker then held the database while
  # waiting for a model, and every other request failed with "database is locked".
  self.job('r1','build',0,100);venture.project_work(self.s,self.f,[dict(run='r1')]);self.assertFalse(self.s.db.in_transaction,'first time')
  venture.project_work(self.s,self.f,[dict(run='r1')]);self.assertFalse(self.s.db.in_transaction,'nothing new')
 def test_a_running_job_counts_up_to_now(self):
  now=int(time.time());self.job('r1','build',now-600,None,status='running');self.job('r2','build',now-600,None,status='failed')
  w=venture.project_work(self.s,self.f,[dict(run='r1'),dict(run='r2')],venture.run_times(self.s,now));self.assertEqual((w['total'],w['running']),(600,True))
 def test_the_total_survives_the_cycles_leaving_the_recent_history(self):
  self.job('r1','build',0,100);venture.project_work(self.s,self.f,[dict(run='r1')]);self.job('r2','build',0,50)
  self.assertEqual(venture.project_work(self.s,self.f,[dict(run='r2')])['total'],150)
 def test_drawing_the_pictures_counts_from_their_files(self):
  base=self.s.safe_path(venture.PID,'workspace/product-abc123/designs');base.mkdir(parents=True)
  for name,seconds,done in (('a',120,True),('b',100000,True),('c',120,False)):
   path=base/(name+'.png');path.write_bytes(b'x');os.utime(path,(1000+seconds,1000+seconds))
  (base/'render.json').write_text(json.dumps(dict(a=dict(at=1000,done=True),b=dict(at=1000,done=True),c=dict(at=1000,done=False),gone=dict(at=1000,done=True))))
  w=venture.project_work(self.s,self.f,[]);self.assertEqual((w['parts'],w['drawn'],w['total']),(dict(drawing=1920),2,1920),'a file touched much later is capped')

class ReportTests(unittest.TestCase):
 def test_the_assistant_gets_the_measured_facts(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);s=Studio(Path(tmp.name));self.addCleanup(s.db.close)
  fake=dict(id='m',status='paused',mode='build',revenue='nincs igazolt bevétel',ideas=[dict(name='Gyenge',score=dict(total=10)),dict(name='Erős',score=dict(total=20,demand=5),cycles=[1,2],problem='x'*500)],projects=[dict(name='Erős',type_label='SaaS',state_label='Félretéve',done=9,total=10,cycles=45,work=dict(total=7200),score=20)],focus=None,feed=[dict(cycle=3,text='kész')],portfolio=[])
  from missions import schema
  schema(s)
  with patch('venture.status',return_value=fake):got=venture.report(s)
  self.assertEqual(got['ideas'][0]['name'],'Erős','the best first');self.assertEqual(got['ideas'][0]['demand'],5);self.assertEqual(len(got['ideas'][0]['problem']),140);self.assertEqual(got['projects'][0]['ai_hours'],2.0);self.assertEqual(got['revenue'],'nincs igazolt bevétel');self.assertEqual(got['recent'],['3. kör: kész'])

if __name__=='__main__':unittest.main()
