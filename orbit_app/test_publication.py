import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from autonomous import plan_schema,run_step,daily_progress
from publication import prepare,approve,listing,settings
from short_style import DEFAULT,caption_preset

class PublicationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name));self.addCleanup(self.s.db.close);plan_schema(self.s)
  self.a=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id'];self.path=self.s.safe_path('universe','renders/test.mp4');self.path.parent.mkdir(exist_ok=True);self.path.write_bytes(b'local video')
  self.style=dict(DEFAULT,min_seconds=10,max_seconds=20,target_seconds=15,min_shots=4,publish_to_youtube=True,review_before_upload=True)
  self.manifest=dict(width=1080,height=1920,duration=12,bytes=self.path.stat().st_size,source='source.mp4',captions=True,caption_style=caption_preset(self.style),shot_count=4,segments=[dict(source_video='source.mp4')])
  self.path.with_suffix('.json').write_text(json.dumps(self.manifest));self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('artifact','universe','test.mp4',str(self.path),'video',time.time(),'render'));self.s.db.commit()
 def data(self):
  return dict(style=self.style,automatic=True,source=dict(source_video='source.mp4',metadata=dict(url='https://www.youtube.com/watch?v=abcdefghijk',title='Actual source')),tracks=[dict(source=dict(source_video='source.mp4'))],render=dict(saved='renders/test.mp4'),montage=dict(duration=12,shots=[dict(source=0,start=i*3,end=(i+1)*3) for i in range(4)]),clip=dict(start=0,duration=3,selection='grounded_story_units'),metadata=dict(title='Verified title',description='Actual content'),subtitle='source.srt',layout='fit',camera_plan=[dict() for _ in range(4)])
 def verify(self,review):
  d=self.data();d['style']['review_before_upload']=review
  self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('run','universe','real topic',json.dumps(d),time.time()));self.s.db.commit();jid=self.s.enqueue(self.a,'verify','graph',payload=dict(run='run',auto_step='verify'));job=self.s.claim(('graph',));run_step(self.s,job)
  return json.loads(self.s.db.execute('SELECT data FROM short_runs').fetchone()[0])
 def test_failed_upload_retry_requires_absence_and_deduplicates(self):
  prepare(self.s,'universe','artifact',dict(title='Ready'))
  with patch('youtube.read_state',return_value=dict(connected=True)):
   first=approve(self.s,'universe','artifact')
   self.s.db.execute("UPDATE jobs SET status='failed' WHERE id=?",(first['job'],));self.s.db.commit()
   with self.assertRaises(ValueError):approve(self.s,'universe','artifact',retry=True)
   second=approve(self.s,'universe','artifact',retry=True,confirmed_absent=True)
   self.assertNotEqual(first['job'],second['job'])
   again=approve(self.s,'universe','artifact',retry=True,confirmed_absent=True)
   self.assertEqual(second['job'],again['job'])
 def test_returned_youtube_id_blocks_retry(self):
  prepare(self.s,'universe','artifact',dict(title='Ready'))
  with patch('youtube.read_state',return_value=dict(connected=True)):
   first=approve(self.s,'universe','artifact')
   self.s.db.execute("UPDATE jobs SET status='failed' WHERE id=?",(first['job'],));self.s.db.commit()
   base=self.s.root/'integrations/youtube/universe';base.mkdir(parents=True,exist_ok=True)
   (base/('upload-'+first['job']+'.json')).write_text(json.dumps(dict(id='abcdefghijk')))
   with self.assertRaises(ValueError):approve(self.s,'universe','artifact',retry=True,confirmed_absent=True)
 def test_review_stops_before_upload_and_counts_completed_production(self):
  d=self.verify(True);self.assertTrue(d['complete']);self.assertNotIn('youtube',d);self.assertTrue(d['publication_review'])
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='youtube_upload'").fetchone()[0],0)
  self.assertEqual(daily_progress(self.s,'universe')['completed'],1)
 def test_automatic_upload_uses_the_same_review_record_once(self):
  with patch('youtube.read_state',return_value=dict(connected=True)):d=self.verify(False)
  self.assertIn('youtube',d);self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='youtube_upload'").fetchone()[0],1)
 def test_approval_is_project_scoped_and_repeat_click_deduplicated(self):
  prepare(self.s,'universe','artifact',dict(title='Ready'))
  with patch('youtube.read_state',return_value=dict(connected=True)):
   with self.assertRaises(ValueError):approve(self.s,'another-project','artifact')
   first=approve(self.s,'universe','artifact');second=approve(self.s,'universe','artifact')
  self.assertEqual(first['job'],second['job']);self.assertTrue(second['existing'])
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE kind='youtube_upload'").fetchone()[0],1)
 def test_completed_runs_backfill_without_publishing_and_reflect_job_status(self):
  d=self.data();d['complete']=True;self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('run','universe','real topic',json.dumps(d),time.time()));self.s.db.commit()
  with patch('youtube.read_state',return_value=dict(connected=True,channel='Test channel',uploads=[])):
   first=listing(self.s,'universe');listing(self.s,'universe');self.assertEqual(len(first['items']),1);self.assertEqual(first['items'][0]['status'],'pending')
   approve(self.s,'universe','artifact');self.assertEqual(listing(self.s,'universe')['items'][0]['status'],'queued')
 def test_portrait_render_fills_frame_even_when_previous_layout_was_fit(self):
  d=self.data();d['transcript']='source.json';d['tracks'][0]['transcript_file']='source.json';d['tracks'][0]['source']['duration']=12;self.s.safe_path('universe','source.json').write_text(json.dumps(dict(segments=[dict(start=0,end=12,text='Actual source speech.')])))
  self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('run','universe','real topic',json.dumps(d),time.time()));self.s.db.commit();self.s.enqueue(self.a,'render','graph',payload=dict(run='run',auto_step='render'));job=self.s.claim(('graph',))
  with patch.object(self.s,'tool',return_value=dict(saved='renders/new.mp4')) as tool:run_step(self.s,job)
  args=tool.call_args.args[2];self.assertEqual(args['layout'],'cover');self.assertTrue(all(x['layout']=='cover' for x in args['segments']))
 def test_policy_is_validated_and_project_scoped(self):
  with self.assertRaises(ValueError):settings(self.s,'universe','unknown')
  self.assertTrue(settings(self.s,'universe','review')['review_before_upload']);self.assertFalse(settings(self.s,'universe','auto')['review_before_upload']);self.assertFalse(settings(self.s,'universe','local')['publish_to_youtube'])
 def test_fill_geometry_crops_without_padding(self):
  from video_render import frame_geometry
  self.assertIn('crop=1080:1920',frame_geometry('cover'));self.assertNotIn('pad=',frame_geometry('cover'));self.assertIn('pad=',frame_geometry('fit'))

 def test_pending_metadata_refreshes_but_approved_metadata_is_immutable(self):
  prepare(self.s,'universe','artifact',dict(title='File name'))
  prepare(self.s,'universe','artifact',dict(title='Final verified title',description='Actual metadata'),'verified-run')
  row=self.s.db.execute('SELECT title,run FROM publication_reviews').fetchone();self.assertEqual(row['title'],'Final verified title');self.assertEqual(row['run'],'verified-run')
  with patch('youtube.read_state',return_value=dict(connected=True)):approve(self.s,'universe','artifact',title='Operator title')
  prepare(self.s,'universe','artifact',dict(title='Another title'))
  self.assertEqual(self.s.db.execute('SELECT title FROM publication_reviews').fetchone()[0],'Operator title')
 def test_unverified_automatic_render_does_not_appear_as_approved_ready_video(self):
  d=self.data();self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('run','universe','topic',json.dumps(d),time.time()));self.s.db.commit()
  jid=self.s.enqueue(self.a,'render','graph',payload=dict(run='run',auto_step='render'));self.s.db.execute('UPDATE artifacts SET job=? WHERE id=?',(jid,'artifact'));self.s.db.commit()
  with patch('youtube.read_state',return_value=dict(connected=True,channel='Test',uploads=[])):self.assertEqual(listing(self.s,'universe')['items'],[])
