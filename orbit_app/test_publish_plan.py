import json,tempfile,time,unittest
from datetime import datetime
from pathlib import Path
from studio import Studio
import publish_hub as hub, publish_plan as plan, publish_library as lib, publish_reach as reach

class PublishPlanTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.s=Studio(Path(self.temp.name));self.addCleanup(self.s.db.close)
  hub.schema(self.s)
 def video(self,pid,folder,name,aid):
  path=self.s.safe_path(pid,folder+'/'+name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'v')
  path.with_suffix('.json').write_text(json.dumps(dict(width=1080,height=1920,duration=25)))
  self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(aid,pid,name,str(path),'video',time.time(),'j'));self.s.db.commit()
 def account(self,platform='instagram',**settings):
  aid=hub.account_add(self.s,platform,'Csat')['id']
  self.s.db.execute("UPDATE social_accounts SET status='connected' WHERE id=?",(aid,));self.s.db.commit()
  if settings:plan.save(self.s,aid,**settings)
  return aid
 def test_simulation_files_count_and_sources_do_not(self):
  pid=self.s.db.execute("SELECT id FROM projects LIMIT 1").fetchone()
  self.video('universe','simulations','sim-1.mp4','a');self.video('universe','sources','raw.mp4','b')
  ids=[v['id'] for v in hub.videos(self.s)]
  self.assertEqual(ids,['a'])
 def test_type_follows_project_name(self):
  self.assertEqual(lib.type_of('Szimgyár','general','/x'),'sim');self.assertEqual(lib.type_of('Animációs stúdió','general','/x'),'story')
  self.assertEqual(lib.type_of('CLIP FARM','general','/x'),'clip');self.assertEqual(lib.type_of('Saját univerzum','general','/projects/universe/media/a.mp4'),'gen')
 def test_next_slot_uses_channel_times_and_daily_limit(self):
  a=self.account(slots=['10:00','20:00'],per_day=1)
  first=plan.next_slot(self.s,a)
  self.assertIn(datetime.fromtimestamp(first, plan.TZ).strftime('%H:%M'),('10:00','20:00'))
  self.s.db.execute("INSERT INTO social_posts(id,artifact,project,account,platform,status,created,scheduled) VALUES('p','a','universe',?,'instagram','scheduled',?,?)",(a,time.time(),first));self.s.db.commit()
  second=plan.next_slot(self.s,a)
  self.assertNotEqual(datetime.fromtimestamp(second, plan.TZ).date(),datetime.fromtimestamp(first, plan.TZ).date())   # per_day=1
 def test_suggestion_is_confirmed_before_anything_is_queued(self):
  self.video('universe','simulations','sim-1.mp4','a');self.video('universe','simulations','sim-2.mp4','b')
  x=self.account('instagram',types=['gen','sim','other'],slots=['10:00'],per_day=2);y=self.account('tiktok',types=['gen','sim','other'],slots=['11:00'])
  out=plan.suggest(self.s,days=5)
  self.assertTrue(out['items']);self.assertEqual(self.s.rows("SELECT 1 FROM social_posts"),[])
  by={}
  for i in out['items']:by.setdefault(i['video'],[]).append(i['when'])
  for times in by.values():
   if len(times)==2:self.assertGreaterEqual(abs(times[0]-times[1]),2*3600)   # the same video is staggered between channels
  done=plan.apply(self.s,out['items'][:2])
  self.assertEqual(done['done'],2);self.assertEqual(len(self.s.rows("SELECT 1 FROM social_posts WHERE status='scheduled'")),2)
  p=self.s.rows("SELECT id FROM social_posts")[0]['id']
  plan.reschedule(self.s,p,time.time()+86400*3)
  with self.assertRaises(ValueError):plan.reschedule(self.s,p,time.time()-5)
 def test_each_channel_gets_its_own_time_and_text(self):
  self.video('universe','simulations','sim-1.mp4','a')
  x=self.account('instagram');y=self.account('tiktok');at=time.time()+7200
  hub.post(self.s,'a',None,'','', 'public',False,None,plan=[dict(account=x,when=at,caption='IG'),dict(account=y,when=at+86400,caption='TT')])
  rows=self.s.rows("SELECT account,caption,scheduled FROM social_posts ORDER BY caption")
  self.assertEqual([r['caption'] for r in rows],['IG','TT']);self.assertEqual(rows[0]['scheduled'],at)
 def test_reach_sums_and_filters_by_account(self):
  x=self.account('instagram');y=self.account('tiktok')
  for aid,views in ((x,100),(y,40)):
   key=self.s.db.execute('SELECT key FROM social_accounts WHERE id=?',(aid,)).fetchone()['key']
   f=reach.folder(self.s,key);f.mkdir(parents=True);(f/'reach.json').write_text(json.dumps(dict(fetched=time.time(),channel=dict(views=views,subscribers=5),items=[dict(id='i'+aid,title='t',views=views,likes=1,comments=2)])))
  allv=reach.snapshot(self.s);one=reach.snapshot(self.s,x)
  self.assertEqual(allv['totals']['views'],140);self.assertEqual(one['totals']['views'],100);self.assertEqual(len(one['items']),1)

 def story(self, review, engineering=None):
  self.s.db.execute("UPDATE projects SET name='Animációs stúdió' WHERE id='universe'");self.s.db.commit()
  self.video('universe','renders','stickman-abc.mp4','st')
  check=self.s.safe_path('universe','runs/abc/stickman-render-check.json');check.parent.mkdir(parents=True,exist_ok=True)
  check.write_text(json.dumps(dict(story_review=dict(status=review),engineering=engineering,timing='estimated')))
 def test_an_unverified_story_is_not_posted_without_the_owners_acceptance(self):
  self.story('not_verified')
  a=self.account('instagram',types=['story'],slots=['10:00'])
  v=[x for x in hub.videos(self.s) if x['id']=='st'][0]
  self.assertEqual(v['quality']['status'],'not_verified')
  with self.assertRaises(ValueError) as ctx:hub.post(self.s,'st',[a],'T','c')
  self.assertIn('ellenőrzése',str(ctx.exception))
  self.assertEqual(plan.suggest(self.s,days=3)['items'],[])      # and never proposed by the planner
  self.assertEqual(hub.post(self.s,'st',[a],'T','c',accept_unverified=True)['posts'][0]['existing'],False)
 def test_a_needs_revision_story_stays_unverified_even_when_the_text_review_passed(self):
  self.story('verified',dict(status='needs_revision',note='a mérnöki kifogás nincs megoldva'))
  v=[x for x in hub.videos(self.s) if x['id']=='st'][0]
  self.assertEqual(v['quality']['status'],'needs_revision')
 def test_a_fully_verified_story_posts_normally(self):
  self.story('verified',dict(status='verified'))
  a=self.account('instagram',types=['story'])
  self.assertEqual(hub.post(self.s,'st',[a],'T','c')['posts'][0]['existing'],False)
 def test_posting_times_are_budapest_time(self):
  a=self.account(slots=['18:00'])
  from datetime import datetime
  at=plan.next_slot(self.s,a)
  self.assertEqual(datetime.fromtimestamp(at,plan.TZ).strftime('%H:%M'),'18:00')
if __name__=='__main__':unittest.main()
