"""The Autopilot over the whole app: standing goals, the live list, and one step per idle stretch."""
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch

import autopilot_hub as hub
from studio import Studio


class AutopilotHub(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
        hub._pace['at']=0

    def test_a_standing_goal_is_recognised_and_typed(self):
        night='dolgozz éjszaka azon, hogy minnél tökéletesebbre fejleszd az animációs studiót, a célem hogy minnél több helyzetet tudjon'
        self.assertTrue(hub.standing_goal(night));self.assertEqual(hub.kind_of(night),'own_video')
        self.assertEqual(hub.kind_of('fejleszd az animációs stúdiót, hogy a legkisebb hibával generáljon'),'own_video')
        self.assertEqual(hub.kind_of('javítsd az animációs stúdió hibáit'),'repair')
        self.assertEqual(hub.kind_of('fejleszd az animációs stúdiót, javítsd a hibákat és generálj videókat tesztnek'),'own_video')
        self.assertTrue(hub.standing_goal('javítsd folyamatosan a visszatérő hibákat'));self.assertEqual(hub.kind_of('javítsd folyamatosan a visszatérő hibákat'),'repair')
        self.assertEqual(hub.kind_of('haladj a weboldalkészítő ötletemmel'),'general')
        for single in ('készíts egy videót a macskákról','mi fut most éjszaka?','generálj egy képet'):
            self.assertFalse(hub.standing_goal(single),single)

    def test_goals_are_added_once_paused_found_and_removed(self):
        first=hub.act(self.s,dict(op='goal_add',text='Dolgozz a saját animációkon, legyenek viccesebbek'))
        self.assertTrue(hub.act(self.s,dict(op='goal_add',text='Dolgozz a saját animációkon, legyenek viccesebbek'))['existing'])
        self.assertEqual(len(hub.goals(self.s)),1)
        hub.act(self.s,dict(op='goal_pause',text='az animációs célt állítsd le, a saját animációkon ne dolgozz'))
        self.assertFalse(hub.goals(self.s)[0]['enabled'])
        hub.act(self.s,dict(op='goal_remove',id=first['id']));self.assertEqual(hub.goals(self.s),[])
        with self.assertRaises(ValueError):hub.act(self.s,dict(op='goal_add',text='kulcs sk-test_test_test_test_test1'))

    def test_an_idle_stretch_takes_one_step_for_the_goal_that_waited_longest(self):
        hub.goal_add(self.s,'Dolgozz a saját animációkon');hub.goal_add(self.s,'Haladj a weboldalkészítő ötletemmel')
        self.s.db.execute("INSERT OR REPLACE INTO autopilot_settings VALUES('default_seeded','1')");self.s.db.commit()
        started=[]
        with patch('self_improve.idle',return_value=True),patch.object(hub,'step_for',side_effect=lambda s,g,now:started.append(g['kind']) or 'Elindult.'):
            now=time.time()
            self.assertTrue(hub.tick(self.s,now));self.assertFalse(hub.tick(self.s,now+10),'paced')
            self.assertTrue(hub.tick(self.s,now+200));self.assertFalse(hub.tick(self.s,now+400),'both goals rest for hours')
        self.assertEqual(started,['own_video','general'])
        self.assertEqual([g['runs'] for g in hub.goals(self.s)],[1,1])

    def test_nothing_starts_when_busy_or_switched_off(self):
        hub.goal_add(self.s,'Dolgozz a saját animációkon')
        with patch.object(hub,'step_for',side_effect=AssertionError('started')):
            with patch('self_improve.idle',return_value=False):self.assertFalse(hub.tick(self.s,time.time()))
            hub.set_mode(self.s,False);hub._pace['at']=0
            with patch('self_improve.idle',return_value=True):self.assertFalse(hub.tick(self.s,time.time()+500))

    def test_a_general_goal_becomes_a_task_for_the_main_assistant(self):
        hub.goal_add(self.s,'Haladj a weboldalkészítő ötletemmel')
        with patch('commander.enqueue') as sent:
            note=hub.step_for(self.s,hub.goals(self.s)[0],time.time())
        prompt=sent.call_args[0][2]
        self.assertIn(hub.GOAL_MARK,prompt);self.assertIn('ne hajtsd végre',prompt);self.assertIn('agent_save',prompt);self.assertIn('asszisztens',note)
        import computer_agent
        self.assertTrue(computer_agent.internal_task(prompt),'an Autopilot step never moves the mouse')

    def test_the_open_project_decides_an_unclear_video_request(self):
        import intent_router
        pid=self.s.create_project('Animációs stúdió');shorts=self.s.create_project('YouTube Shorts')
        ask=lambda *a:self.fail('the model was asked')
        got=intent_router.understand(self.s,dict(id='j',project=pid),'kezdj el videót gyártani egy virális mostani témáról',ask)
        self.assertEqual((got['workflow'],got['by']),('own','project'))
        self.assertEqual(intent_router.understand(self.s,dict(id='j',project=shorts),'kezdj el videót gyártani a mai témáról',ask)['workflow'],'clip')
        self.assertEqual(intent_router.understand(self.s,dict(id='j',project=pid),'kezdj el videót gyártani: What did ancient humans do when they were bored?',ask)['workflow'],'own')
        self.assertIsNone(intent_router.understand(self.s,dict(id='j',project=pid),'mi az a jó videó?',ask))

    def test_live_list_shows_one_line_per_piece_of_work(self):
        pid=self.s.create_project('Animációs stúdió');agent=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(pid,))[0]['id']
        for i,step in enumerate(('sound','render')):
            jid=self.s.enqueue(agent,'A folyamat közös célja:\\nvicces videó','graph',payload=dict(run='r1',story_step=step,story_brief='vicces videó'))
            if not i:self.s.db.execute("UPDATE jobs SET status='running',started=? WHERE id=?",(time.time(),jid))
        self.s.db.commit()
        live=hub.live(self.s)
        self.assertEqual([(x['kind'],x['running'],x['waiting'],x['title']) for x in live],[('Saját animáció',True,1,'vicces videó')])
        self.assertIn('hang',live[0]['detail'])
        data=hub.overview(self.s)
        self.assertEqual((data['mode'],len(data['live']),data['goals']),(True,1,[]))

    def test_a_default_project_goal_is_seeded_once_and_studio_goals_alternate(self):
        with patch('self_improve.idle',return_value=False):hub.tick(self.s,time.time())
        self.assertEqual([g['kind'] for g in hub.goals(self.s)],['projects'])
        hub.goal_remove(self.s,hub.goals(self.s)[0]['id']);hub._pace['at']=0
        with patch('self_improve.idle',return_value=False):hub.tick(self.s,time.time()+500)
        self.assertEqual(hub.goals(self.s),[],'a deleted default stays deleted')
        hub.goal_add(self.s,'Fejleszd az animációs stúdiót, legyenek viccesebbek a videók')
        goal=dict(hub.goals(self.s)[0],runs=1)
        with patch.object(hub,'queue_tune') as queued,patch('story_animation.project',return_value='p1'):
            self.assertIn('fejlesztése',hub.step_for(self.s,goal,time.time()))
        self.assertEqual(queued.call_args[0][2],'p1')

    def test_tuning_rewrites_one_agent_and_keeps_a_revision(self):
        pid=self.s.create_project('Animációs stúdió');agent=self.s.rows('SELECT * FROM agents WHERE project=? LIMIT 1',(pid,))[0]
        better='Write funnier, faster stories with at least three physical actions per episode, built on one current trend, and vary the place every time. '*2
        note=hub.tune(self.s,pid,'viccesebb videók',ask=lambda system,data,shape:dict(agent=agent['id'],prompt=better,reason='Változatosabb történetekért.'))
        self.assertIn(agent['name'],note)
        self.assertEqual(self.s.agent(agent['id'])['prompt'],' '.join(better.split()))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM orbit_agent_revisions WHERE agent=?',(agent['id'],)).fetchone()[0],1)
        self.assertEqual(hub.project_log(self.s)[0]['items'][0]['kind'],'Ügynök fejlesztve')
        self.assertIn('Most nem',hub.tune(self.s,pid,'x',ask=lambda *a:dict(agent='none',prompt='',reason='')))



class FreeMachinePace(unittest.TestCase):
    def test_a_free_machine_goes_on_past_the_daily_count(self):
        import datetime
        import time as _t
        import autopilot_hub as hub
        now = _t.time()
        day = datetime.date.fromtimestamp(now).isoformat()
        goal = dict(kind='projects', day=day, today=hub.PER_DAY['projects'], last_run=now - hub.GAP['projects'] - 1)
        self.assertGreater(hub.next_in(goal, now), 0)          # half pace past the count
        goal['last_run'] = now - 2 * hub.GAP['projects'] - 1
        self.assertEqual(hub.next_in(goal, now), 0)
        goal['today'] = hub.PER_DAY['projects'] * hub.FREE_FACTOR
        self.assertIsNone(hub.next_in(goal, now))               # a hard ceiling remains
        goal.update(today=99, day='2000-01-01')
        self.assertEqual(hub.next_in(goal, now), 0)             # a new day starts from zero


if __name__=='__main__':
    unittest.main()
