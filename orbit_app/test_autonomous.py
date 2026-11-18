import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from autonomous import start,role_agents,choose_window,save_settings,schedule,status
from clip_sources import youtube_id,find_clips,download_clip

class AutoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Studio(Path(self.temp.name)/'orbit');self.addCleanup(self.s.db.close)
        for name in ('Echo','Scout','Lex','Reach','Vega'):
            self.s.save_agent(dict(project='universe',name=name,role=name,room='bridge',tools=['project_files','read_file','write_file','transcribe_media','detect_faces','render_short']))
        self.roles=role_agents(self.s,'universe')
        for role in ('producer','source'):
            a=self.s.agent(self.roles[role]);a['tools']+=['find_stream_clips','download_stream_clip','start_short_production'];self.s.save_agent(a)
    def test_private_hosts_and_non_youtube_urls_are_rejected(self):
        self.assertEqual(youtube_id('https://youtu.be/AtbESdM3bBs'),'AtbESdM3bBs')
        for url in ('http://youtube.com/watch?v=AtbESdM3bBs','https://127.0.0.1/v','https://youtube.com.attacker.invalid/watch?v=AtbESdM3bBs','https://user:pass@youtube.com/watch?v=AtbESdM3bBs'):
            self.assertIsNone(youtube_id(url))
        with self.assertRaises(ValueError):start(self.s,'universe','https://localhost:11434/')
    def test_eight_steps_are_queued_once_and_handoffs_wait_for_parents(self):
        result=start(self.s,'universe','IShowSpeed funny highlights')
        self.assertEqual(len(result['jobs']),8)
        with self.assertRaises(ValueError):start(self.s,'universe','Another clip')
        first=self.s.claim(('graph',));self.assertEqual(json.loads(first['payload'])['auto_step'],'producer')
        self.assertIsNone(self.s.claim(('graph',)))
        self.s.finish(first,'Plan complete');second=self.s.claim(('graph',));self.assertEqual(json.loads(second['payload'])['auto_step'],'source')
        render=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(result['jobs']['render'],)).fetchone()[0]);self.assertEqual(render['required_outputs'],['video'])
    def test_source_failure_blocks_every_downstream_step(self):
        run=start(self.s,'universe','IShowSpeed public highlights');first=self.s.claim(('graph',));self.s.finish(first,'Plan')
        source=self.s.claim(('graph',));self.s.finish(source,error='Public source unavailable');self.s.claim(('graph',))
        states={j['id']:j['status'] for j in self.s.rows('SELECT id,status FROM jobs')}
        self.assertEqual(states[run['jobs']['render']],'blocked');self.assertFalse(self.s.rows('SELECT * FROM handoff_receipts'))
    def test_source_candidates_are_project_scoped_and_deduplicated(self):
        agent=self.s.agent(self.roles['source']);job=self.s.enqueue(agent['id'],'Search')
        with patch('clip_sources.network',return_value={'candidates':[dict(id='AtbESdM3bBs',title='Public clip',duration=607)]}):
            result=find_clips(self.s,agent,dict(query='Speed highlights'),job)
        self.assertEqual(len(result),1);self.assertFalse(result[0]['used'])
        with self.assertRaises(ValueError):download_clip(self.s,agent,dict(candidate_id='different-project-id'),job)
        with self.assertRaises(ValueError):download_clip(self.s,agent,dict(candidate_id=result[0]['candidate_id'],start=0,duration=999999),job)
    def test_bad_ai_time_bounds_cannot_escape_real_source(self):
        segments=[dict(start=0,end=18,text='real speech'),dict(start=18,end=40,text='real second passage')]
        for choice in ({'start':-5,'end':900},{'start':float('nan'),'end':20},{}):
            result=choose_window(choice,segments,50);self.assertEqual(result['selection'],'segment_fallback');self.assertGreaterEqual(result['start'],0);self.assertLessEqual(result['start']+result['duration'],50)
        result=choose_window({'start':5,'end':30,'reason':'real evidence'},segments,50);self.assertEqual(result['selection'],'local_ai')
    def test_autopilot_cap_and_pause(self):
        save_settings(self.s,'universe','Speed highlights',True,180,1)
        self.s.db.execute('INSERT INTO short_runs VALUES(?,?,?,?,?)',('already','universe','q','{"automatic":true}',time.time()));self.s.db.commit()
        with patch('autonomous.start') as launch:schedule(self.s);launch.assert_not_called()
        self.assertGreater(status(self.s,'universe')['settings']['next_run'],time.time())
        save_settings(self.s,'universe','Speed highlights',False,180,1)
        with patch('autonomous.start') as launch:schedule(self.s);launch.assert_not_called()
    def test_multiday_plan_persists_gates_runs_and_expires(self):
        import datetime
        from zoneinfo import ZoneInfo
        zone=ZoneInfo('Europe/Budapest')
        stamp=lambda hour:datetime.datetime(2030,1,7,hour,tzinfo=zone).timestamp()
        plan=dict(start_date='2030-01-07',end_date='2030-01-07',weekdays=[0],from_time='09:00',to_time='17:00')
        with patch('autonomous.time.time',return_value=stamp(8)):
            save_settings(self.s,'universe','Speed highlights',True,180,3,plan)
            self.assertEqual(status(self.s,'universe')['settings']['plan'],plan)
            with patch('autonomous.start') as launch:schedule(self.s);launch.assert_not_called()
        with patch('autonomous.time.time',return_value=stamp(10)):
            with patch('autonomous.start') as launch:schedule(self.s);launch.assert_called_once()
        with patch('autonomous.time.time',return_value=stamp(18)):
            with patch('autonomous.start') as launch:schedule(self.s);launch.assert_not_called()
        self.assertFalse(status(self.s,'universe')['settings']['enabled'])

    def test_renamed_producer_keeps_its_assignment(self):
        a=self.s.agent(self.roles['producer']);a['name']='KING';self.s.save_agent(a)
        self.assertEqual(role_agents(self.s,'universe')['producer'],a['id'])

if __name__=='__main__':unittest.main()
