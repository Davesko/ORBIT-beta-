import json,time,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from video_intelligence import reframe_points,crop_filter
from studio import Studio
from ai_runtime import unresponsive_models

class TrackingTests(unittest.TestCase):
 def test_empty_tracking_preserves_full_frame(self):
  self.assertEqual(reframe_points(dict(frames=[]),0,10),[])
 def test_track_stays_on_same_subject_and_is_relative_to_cut(self):
  frames=[dict(seconds=10+i*.5,scene=0,people=[dict(id='0:1',box=[.6,0,.9,1]),dict(id='0:2',box=[0,.1,.1,.2])]) for i in range(8)]
  points=reframe_points(dict(frames=frames),10,4)
  self.assertEqual(points[0]['seconds'],0);self.assertGreater(points[-1]['center'],.7);self.assertLess(points[-1]['center'],.76)
 def test_crop_rejects_injected_and_nonfinite_values(self):
  for points in ([dict(seconds=0,center='shell')]*2,[dict(seconds=0,center=.5),dict(seconds=float('nan'),center=.5)],[dict(seconds=1,center=.5),dict(seconds=0,center=.5)]):
   with self.assertRaises(ValueError):crop_filter(points)
 def test_crop_expression_is_bounded(self):
  result=crop_filter([dict(seconds=i*.25,center=.5) for i in range(300)])
  self.assertLessEqual(result.count('if('),24);self.assertIn('iw-1080',result)

class RoutingHealthTests(unittest.TestCase):
 def test_recent_manual_timeout_is_excluded_from_auto_routing(self):
  with tempfile.TemporaryDirectory() as temp:
   s=Studio(Path(temp));agent=s.rows('SELECT id FROM agents LIMIT 1')[0]['id'];jid=s.enqueue(agent,'test')
   s.db.execute("UPDATE jobs SET status='failed',error='A helyi AI nem válaszolt az időkereten belül.',finished=?,payload=? WHERE id=?",(time.time(),json.dumps(dict(selected_model='qwen3.8:27b')),jid));s.db.commit();s.db.close()
   with patch('connections.ROOT',Path(temp)):self.assertIn('qwen3.8:27b',unresponsive_models())

class ProductionStartTests(unittest.TestCase):
 def test_verbal_start_without_action_is_corrected(self):
  from commander import enqueue,run,schema
  with tempfile.TemporaryDirectory() as temp:
   s=Studio(Path(temp));schema(s);s.db.execute("UPDATE projects SET name='YouTube Shorts' WHERE id='universe'");s.db.commit()
   with patch('model_hub.models',return_value=[dict(name='qwen3.5:9b')]):jid=enqueue(s,'universe','kezdj el egy youtube short videót készíteni Ronaldo legjobb pillanataiból','auto')
   job=dict(s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
   replies=[dict(reply='A videó gyártása indult.',actions=[],reads=[]),dict(reply='Indítás',actions=[dict(type='start_shorts',project='universe',query='Cristiano Ronaldo best moments')],reads=[])]
   from execution_queue import DeferredExecution
   with patch('studio.local_api',side_effect=[dict(message=dict(content=json.dumps(r))) for r in replies]):
    with self.assertRaises(DeferredExecution):run(s,job)
    run(s,job)
   actions=json.loads(s.db.execute('SELECT actions FROM command_turns WHERE job!=? OR job=?',(jid,jid)).fetchone()[0]);self.assertEqual(actions[0]['type'],'start_shorts');s.db.close()

class MediaSummaryTests(unittest.TestCase):
 def test_visual_and_tracking_jobs_do_not_use_face_summary_format(self):
  with tempfile.TemporaryDirectory() as temp:
   s=Studio(Path(temp));aid=s.rows('SELECT id FROM agents LIMIT 1')[0]['id']
   for operation,summary in [('analyze_video',dict(summary='A person turns around.')),('track_subject',dict(samples=12))]:
    jid=s.enqueue(aid,'test local tool','media_analysis',payload=dict(operation=operation,args={}))
    with patch.object(s,'tool',return_value=dict(files=['results/proof.json'],summary=summary)):s.run_next(('media_analysis',))
    row=s.db.execute('SELECT status,error FROM jobs WHERE id=?',(jid,)).fetchone();self.assertEqual(row['status'],'done',row['error'])
   s.db.close()
