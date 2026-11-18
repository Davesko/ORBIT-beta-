import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import publish_hub as hub

class PublishHubTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name));self.addCleanup(self.s.db.close)
  self.path=self.s.safe_path('universe','renders/a.mp4');self.path.parent.mkdir(exist_ok=True);self.path.write_bytes(b'video')
  self.path.with_suffix('.json').write_text(json.dumps(dict(width=1080,height=1920,duration=30,bytes=5)))
  self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('vid','universe','a.mp4',str(self.path),'video',time.time(),'render'));self.s.db.commit()
  hub.schema(self.s)
 def connected(self,platform='instagram'):
  aid=hub.account_add(self.s,platform,'Teszt')['id']
  self.s.db.execute("UPDATE social_accounts SET status='connected' WHERE id=?",(aid,));self.s.db.commit();return aid
 def test_videos_of_every_project_are_listed_with_suggested_text(self):
  v=hub.videos(self.s)
  self.assertEqual([x['id'] for x in v],['vid']);self.assertEqual(v[0]['state'],'new');self.assertTrue(v[0]['short']);self.assertEqual(v[0]['title'],'a')
 def test_post_goes_to_several_accounts_once(self):
  a,b=self.connected('instagram'),self.connected('tiktok')
  r=hub.post(self.s,'vid',[a,b],'Cím','szöveg #tag')
  self.assertEqual(len(r['posts']),2)
  jobs=self.s.rows("SELECT payload FROM jobs WHERE kind='youtube_upload'")
  self.assertEqual({json.loads(j['payload'])['platform'] for j in jobs},{'instagram','tiktok'})
  again=hub.post(self.s,'vid',[a],'Cím')
  self.assertTrue(again['posts'][0]['existing']);self.assertEqual(len(self.s.rows("SELECT 1 FROM jobs WHERE kind='youtube_upload'")),2)
  self.assertEqual(hub.videos(self.s)[0]['state'],'active')
 def test_unconnected_account_and_missing_title_are_refused(self):
  aid=hub.account_add(self.s,'instagram')['id']
  with self.assertRaises(ValueError):hub.post(self.s,'vid',[aid],'Cím')
  with self.assertRaises(ValueError):hub.post(self.s,'vid',[],'Cím')
 def test_schedule_waits_for_its_time_and_can_be_cancelled(self):
  a,b=self.connected(),self.connected('facebook')
  at=time.time()+3600
  r=hub.post(self.s,'vid',[a,b],'Cím',when=at)
  self.assertFalse(self.s.rows("SELECT 1 FROM jobs WHERE kind='youtube_upload'"))
  hub.cancel(self.s,r['posts'][1]['id'])
  hub.tick(self.s,now=at-10);self.assertFalse(self.s.rows("SELECT 1 FROM jobs WHERE kind='youtube_upload'"))
  hub.tick(self.s,now=at+1);self.assertEqual(len(self.s.rows("SELECT 1 FROM jobs WHERE kind='youtube_upload'")),1)
 def test_run_post_saves_the_platform_id_and_blocks_a_second_upload(self):
  a=self.connected()
  pid=hub.post(self.s,'vid',[a],'Cím')['posts'][0]['id']
  job=self.s.claim(('youtube_upload',))
  class Done:
   pid=1
   def __init__(self,*args,**kw):pass
   def communicate(self,raw=None,timeout=None):return json.dumps(dict(ok=True,id='IG123',url='https://www.instagram.com/reel/x/')).encode(),b''
  (self.s.root/'media-runtime/bin').mkdir(parents=True,exist_ok=True)
  with patch('subprocess.Popen',Done):
   from youtube import upload_job
   text=upload_job(self.s,job)
  row=self.s.db.execute('SELECT * FROM social_posts WHERE id=?',(pid,)).fetchone()
  self.assertEqual((row['status'],row['external_id']),('published','IG123'));self.assertIn('instagram.com',text)
  self.assertTrue(hub.post(self.s,'vid',[a],'Cím')['posts'][0]['existing'])
 def test_failed_post_with_platform_id_cannot_be_retried(self):
  a=self.connected()
  pid=hub.post(self.s,'vid',[a],'Cím')['posts'][0]['id']
  self.s.db.execute("UPDATE social_posts SET status='failed' WHERE id=?",(pid,));self.s.db.execute("UPDATE jobs SET status='failed'");self.s.db.commit()
  with self.assertRaises(ValueError):hub.retry(self.s,pid)
  hub.retry(self.s,pid,confirmed_absent=True)
  self.s.db.execute("UPDATE social_posts SET status='failed',external_id='X' WHERE id=?",(pid,));self.s.db.commit()
  with self.assertRaises(ValueError):hub.retry(self.s,pid,confirmed_absent=True)
 def test_project_channel_becomes_an_account_and_routes(self):
  base=self.s.root/'integrations/youtube/universe';base.mkdir(parents=True)
  (base/'status.json').write_text(json.dumps(dict(connected=True,channel='Csatornám',channel_id='UC1')));(base/'client.json').write_text('{}')
  with patch('youtube.schedule_upload_refresh'):
   snap=hub.snapshot(self.s)
  acc=snap['accounts'][0]
  self.assertEqual((acc['platform'],acc['status'],acc['legacy_project']),('youtube','connected','universe'))
  self.assertEqual(snap['routes']['universe'],[acc['id']]);self.assertTrue(snap['google_client'])
  hub.route(self.s,'universe',acc['id'],False);self.assertNotIn('universe',hub.snapshot(self.s)['routes'])
 def test_dispatch_goes_through_project_apps(self):
  import project_apps
  out=project_apps.dispatch(self.s,'universe','publish_snapshot')
  self.assertEqual(out['app'],'publish_hub');self.assertEqual(out['result']['counts']['new'],1)

if __name__=='__main__':unittest.main()


class MergeTests(PublishHubTests):
 def yt(self,label,key,status,channel_id,created):
  self.s.db.execute('INSERT INTO social_accounts(id,platform,label,key,handle,external_id,status,created) VALUES(?,?,?,?,?,?,?,?)',(key,'youtube',label,key,label,channel_id,status,created));self.s.db.commit()
 def test_the_same_channel_connected_twice_is_one_account(self):
  self.yt('Shortsfarmer','acct-old','expired','UC1',1);self.yt('Shortsfarmer','acct-new','connected','UC1',2)
  self.s.db.execute("INSERT INTO social_posts(id,artifact,project,account,platform,title,status,created) VALUES('p','vid','universe','acct-new','youtube','t','scheduled',1)");self.s.db.commit()
  hub.merge_duplicates(self.s)
  rows=self.s.rows("SELECT id,key,status FROM social_accounts")
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],'acct-old');self.assertEqual(rows[0]['key'],'acct-new');self.assertEqual(rows[0]['status'],'connected')
  self.assertEqual(self.s.db.execute("SELECT account FROM social_posts WHERE id='p'").fetchone()[0],'acct-old')
 def test_different_channels_stay_apart(self):
  self.yt('A','acct-a','connected','UC1',1);self.yt('B','acct-b','connected','UC2',2)
  hub.merge_duplicates(self.s);self.assertEqual(self.s.db.execute('SELECT count(*) FROM social_accounts').fetchone()[0],2)


class NowTests(PublishHubTests):
 def test_a_scheduled_post_can_go_out_now(self):
  a=self.connected('instagram')
  r=hub.post(self.s,'vid',[a],'Cím','szöveg',when=time.time()+7200)
  pid=r['posts'][0]['id'];self.assertEqual(self.s.db.execute('SELECT status FROM social_posts WHERE id=?',(pid,)).fetchone()[0],'scheduled')
  hub.publish_now(self.s,pid)
  row=self.s.db.execute('SELECT status,scheduled,job FROM social_posts WHERE id=?',(pid,)).fetchone()
  self.assertEqual(row['status'],'queued');self.assertIsNone(row['scheduled']);self.assertTrue(row['job'])
  with self.assertRaises(ValueError):hub.publish_now(self.s,pid)


class CoverHookTest(unittest.TestCase):
    def test_cover_follows_title_and_keeps_ends(self):
        import publish_library as lib
        self.assertEqual(lib.cover_hook('xQc | crashes the car | GTA6'), 'xQc · crashes the car · GTA6')
        out = lib.cover_hook('IShowSpeed | ' + 'very long scene ' * 6 + '| GTA6')
        self.assertTrue(out.startswith('IShowSpeed') and out.endswith('GTA6') and len(out) <= 60)
        self.assertEqual(lib.cover_hook(''), '')


class ScoreTests(unittest.TestCase):
 def test_chat_peak_short_scores_high_and_other_game_is_capped(self):
  import publish_score as ps
  facts=dict(short=True,duration=35,width=1080,height=1920)
  run=dict(layout='stack',captions=True,decode='passed',complete=True)
  gta=ps.compute('clip',facts,'xQc | Wild chase | GTA6',run,dict(score=30,kind='funny',game='Grand Theft Auto VI'))
  self.assertGreaterEqual(gta['score'],85);self.assertEqual({p['key'] for p in gta['parts']},{'chat','format','frame','title','check'})
  zelda=ps.compute('clip',facts,'xQc | Wild chase',run,dict(score=30,kind='funny',game='The Legend of Zelda'))
  self.assertLessEqual(zelda['score'],39);self.assertIn('NEM GTA 6',zelda['basis'])
 def test_unchecked_or_unnamed_videos_score_low(self):
  import publish_score as ps
  facts=dict(short=True,duration=35)
  bad=ps.compute('clip',facts,'short 82d0a6249b51',dict(layout='fit',captions=True,decode='passed',complete=False),dict(score=30,kind='funny',game='GTA VI'))
  self.assertLessEqual(bad['score'],39)
 def test_video_without_chat_data_never_beats_a_chat_peak(self):
  import publish_score as ps
  sim=ps.compute('sim',dict(short=True,duration=30),'Will it get out?',None,None)
  self.assertLessEqual(sim['score'],70)
 def test_auto_schedule_is_off_by_default_and_saves(self):
  import tempfile
  from pathlib import Path
  from studio import Studio
  import publish_plan as pl
  with tempfile.TemporaryDirectory() as t:
   s=Studio(Path(t))
   self.assertFalse(pl.auto_settings(s)['enabled'])
   import publish_hub as hh
   hh.schema(s);aid=hh.account_add(s,'instagram','T')['id']
   pl.auto_save(s,True,60);self.assertEqual(pl.auto_settings(s),dict(enabled=True,min_score=60,ahead_hours=24))
   with self.assertRaises(ValueError):pl.auto_save(s,None,150)
   s.db.close()


class LearnTests(unittest.TestCase):
 def test_history_part_needs_real_data_and_is_shrunk(self):
  import publish_learn as L, publish_score as ps
  self.assertIsNone(L.factor(dict(mean=1000,n=3,by={'xqc':(2000,3)}),'xqc'))                      # too little data overall
  self.assertIsNone(L.factor(dict(mean=1000,n=9,by={}),'xqc'))                                     # unknown streamer
  f=L.factor(dict(mean=1000,n=9,by={'xqc':(3000,1)}),'xqc')
  self.assertTrue(1.0<f<3.0)                                                                        # shrunk towards 1 with a single sample
  base=ps.compute('clip',dict(short=True,duration=30),'xQc | a | GTA6',dict(layout='stack',captions=True,decode='passed',complete=True),dict(score=20,kind='funny',game='GTA VI'))
  better=ps.compute('clip',dict(short=True,duration=30),'xQc | a | GTA6',dict(layout='stack',captions=True,decode='passed',complete=True),dict(score=20,kind='funny',game='GTA VI'),1.8)
  self.assertGreater(better['score'],base['score']);self.assertIn('history',{p['key'] for p in better['parts']})
 def test_old_clips_lose_pull(self):
  import publish_plan as pl,time
  now=time.time()
  self.assertAlmostEqual(pl.freshness(dict(type='clip',created=now),now),1.0,2)
  self.assertLess(pl.freshness(dict(type='clip',created=now-4*86400),now),0.35+1e-9+0.01)
  self.assertEqual(pl.freshness(dict(type='sim',created=now-9*86400),now),1.0)


class AutoReplanTests(PublishHubTests):
 def test_future_auto_posts_are_taken_back_and_close_ones_stay(self):
  import publish_plan as pl
  a=self.connected('instagram')
  far=hub.post(self.s,'vid',[a],'Cím','sz',when=time.time()+6*3600)['posts'][0]['id']
  self.s.db.execute("INSERT INTO social_posts(id,artifact,project,account,platform,title,status,created,scheduled) VALUES('near','vid','universe',?,'instagram','t','scheduled',?,?)",(a,time.time(),time.time()+600));self.s.db.commit()
  pl.auto_mark(self.s,[far,'near'])
  n=pl.auto_cancel_future(self.s,time.time())
  self.assertEqual(n,1)
  st={r['id']:r['status'] for r in self.s.rows('SELECT id,status FROM social_posts')}
  self.assertIn(st.get(far),(None,'cancelled'));self.assertEqual(st['near'],'scheduled')
 def test_a_hand_scheduled_post_is_never_touched(self):
  import publish_plan as pl
  a=self.connected('instagram')
  mine=hub.post(self.s,'vid',[a],'Cím','sz',when=time.time()+6*3600)['posts'][0]['id']
  self.assertEqual(pl.auto_cancel_future(self.s,time.time()),0)
  self.assertEqual(self.s.db.execute('SELECT status FROM social_posts WHERE id=?',(mine,)).fetchone()[0],'scheduled')


class SlotTests(PublishHubTests):
 def test_pasted_list_and_interval_become_slots(self):
  import publish_plan as pl
  pasted='00:00, 02:00, 04:00, 06:00, 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00,'
  self.assertEqual(len(pl.parse_slots(pasted)),12)
  self.assertEqual(pl.parse_slots('4:00;06.30 25:00 x'),['04:00','06:30'])
  self.assertEqual(pl.every_slots(2,'00:00','22:00'),pl.parse_slots(pasted))
  self.assertEqual(pl.every_slots(1.5,'08:00','12:00'),['08:00','09:30','11:00'])
 def test_saving_every_two_hours_sets_twelve_slots_and_the_daily_limit(self):
  import publish_plan as pl
  a=self.connected('instagram')
  out=pl.save(self.s,a,every=dict(hours=2,start='00:00',end='22:00'))
  self.assertEqual(len(out['slots']),12);self.assertEqual(out['per_day'],12)
  out=pl.save(self.s,a,slots='08:00, 20:00');self.assertEqual(out['per_day'],2)
  with self.assertRaises(ValueError):pl.save(self.s,a,slots='nem idő')
 def test_next_slots_follow_a_two_hour_rhythm(self):
  import publish_plan as pl
  a=self.connected('instagram');pl.save(self.s,a,every=dict(hours=2,start='00:00',end='22:00'))
  first=pl.next_slot(self.s,a);second=pl.next_slot(self.s,a,after=first+60)
  self.assertEqual(round((second-first)/3600),2)


class ChannelPlanTests(PublishHubTests):
 def test_the_daily_limit_is_the_number_of_times_and_auto_is_per_channel(self):
  import publish_plan as pl
  a=self.connected('instagram');b=self.connected('tiktok')
  pl.save(self.s,a,every=dict(hours=2,start='00:00',end='22:00'))
  accs={x['id']:x for x in hub.accounts(self.s)}
  self.assertEqual(accs[a]['per_day'],12)
  self.assertFalse(accs[a]['auto'])
  pl.auto_save(self.s,True,None,a)
  self.assertEqual(pl.auto_accounts(self.s),[a])
  self.assertTrue(pl.auto_settings(self.s)['enabled'])
  pl.auto_save(self.s,False,None,a)
  self.assertEqual(pl.auto_accounts(self.s),[]);self.assertFalse(pl.auto_settings(self.s)['enabled'])
 def test_upcoming_lists_scheduled_and_empty_times_in_order(self):
  import publish_plan as pl
  a=self.connected('instagram');pl.save(self.s,a,every=dict(hours=2,start='00:00',end='22:00'))
  first=pl.next_slot(self.s,a)
  hub.post(self.s,'vid',[a],'Cím','sz',when=first)
  rows=pl.upcoming(self.s,a,hub.videos(self.s),n=5)
  self.assertEqual(len(rows),5)
  self.assertEqual([r['status'] for r in rows][:1],['scheduled'])
  self.assertTrue(all(r['status']=='empty' for r in rows[1:]))
  self.assertEqual(sorted(r['when'] for r in rows),[r['when'] for r in rows])
 def test_two_hour_rhythm_fills_every_slot_not_ten_of_twelve(self):
  import publish_plan as pl
  a=self.connected('instagram');pl.save(self.s,a,every=dict(hours=2,start='00:00',end='22:00'))
  taken=[];at=0
  for _ in range(12):
   at=pl.next_slot(self.s,a,after=at+1,taken=taken);taken.append(at)
  days={time.strftime('%Y-%m-%d',time.localtime(x)) for x in taken}
  self.assertLessEqual(len(days),2)                      # 12 consecutive slots span at most two calendar days


class BestSwapTests(PublishHubTests):
 def video(self,vid,score,age_h=1):
  return dict(id=vid,hidden=False,score=score,quality=None,created=time.time()-age_h*3600,type='clip',short=True,title=vid,caption='c',variants=dict(instagram=dict(title=vid,caption='c')),posts=[])
 def setup_channel(self):
  import publish_plan as pl
  a=self.connected('instagram');pl.save(self.s,a,types=['clip'],every=dict(hours=2,start='00:00',end='22:00'))
  p2=self.s.safe_path('universe','renders/b.mp4');p2.write_bytes(b'video');p2.with_suffix('.json').write_text(json.dumps(dict(width=1080,height=1920,duration=30,bytes=5)))
  self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',('vid2','universe','b.mp4',str(p2),'video',time.time(),'render'));self.s.db.commit()
  return a
 def test_a_better_video_takes_the_scheduled_time_of_a_weaker_one(self):
  import publish_plan as pl
  from unittest.mock import patch
  a=self.setup_channel()
  when=time.time()+4*3600
  pid=hub.post(self.s,'vid',[a],'Cím','sz',when=when)['posts'][0]['id'];pl.auto_mark(self.s,[pid])
  pl._best['at']=0
  with patch.object(hub,'videos',return_value=[self.video('vid',60),self.video('vid2',90)]):
   n=pl.rebalance(self.s,time.time())
  self.assertEqual(n,1)
  rows={r['artifact']:r for r in self.s.rows("SELECT artifact,status,scheduled FROM social_posts WHERE account=?",(a,))}
  self.assertNotIn('vid',rows)                      # the weaker one was taken back
  self.assertEqual(rows['vid2']['status'],'scheduled');self.assertAlmostEqual(rows['vid2']['scheduled'],when,delta=1)
 def test_hand_scheduled_posts_and_slots_close_to_the_time_are_never_swapped(self):
  import publish_plan as pl
  from unittest.mock import patch
  a=self.setup_channel()
  hub.post(self.s,'vid',[a],'Cím','sz',when=time.time()+4*3600)            # by hand: not marked
  pl._best['at']=0
  with patch.object(hub,'videos',return_value=[self.video('vid',60),self.video('vid2',95)]):
   self.assertEqual(pl.rebalance(self.s,time.time()),0)
  pid=self.s.db.execute("SELECT id FROM social_posts WHERE account=?",(a,)).fetchone()[0]
  self.s.db.execute("UPDATE social_posts SET scheduled=? WHERE id=?",(time.time()+600,pid));self.s.db.commit();pl.auto_mark(self.s,[pid]);pl._best['at']=0
  with patch.object(hub,'videos',return_value=[self.video('vid',60),self.video('vid2',95)]):
   self.assertEqual(pl.rebalance(self.s,time.time()),0)                     # ten minutes away: on its way out
 def test_the_setting_can_be_switched_off_per_channel(self):
  import publish_plan as pl
  from unittest.mock import patch
  a=self.setup_channel();pl.save(self.s,a,best=False)
  when=time.time()+4*3600;pid=hub.post(self.s,'vid',[a],'Cím','sz',when=when)['posts'][0]['id'];pl.auto_mark(self.s,[pid]);pl._best['at']=0
  with patch.object(hub,'videos',return_value=[self.video('vid',60),self.video('vid2',95)]):
   self.assertEqual(pl.rebalance(self.s,time.time()),0)
