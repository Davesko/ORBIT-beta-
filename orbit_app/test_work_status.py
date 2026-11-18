"""Status questions are answered from the job table, never invented; a plan cut off for length restarts smaller."""
import json,tempfile,time,unittest
from pathlib import Path

import assistant_resilience
import quick_status
from studio import Studio

ASKED=['most éppen mi dolgozik?','szóval most jelenleg min dolgozik az orbit , hogy nem tudnak működni az agentek?',
       'a youtube shorts projektbe 2 agent is azt írja hogy “a helyi ai ra vár…” ez miért van?',
       'nem látom a javításnak a futását sehol? és azt sem látom hogy mi lesz az eredménye.']


class WorkStatus(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
        self.pid=self.s.create_project('Shorts');self.agent=self.s.rows('SELECT id,name FROM agents WHERE project=? LIMIT 1',(self.pid,))[0]

    def test_the_real_questions_get_a_factual_answer(self):
        for prompt in ASKED:
            self.assertIn('semmi nem fut',quick_status.answer(self.s,prompt),prompt)
        self.assertIsNone(quick_status.answer(self.s,'készíts egy videót a kutyámról'))

    def test_running_and_waiting_jobs_are_named_with_the_reason(self):
        first=self.s.enqueue(self.agent['id'],'render');second=self.s.enqueue(self.agent['id'],'upload')
        self.s.db.execute("UPDATE jobs SET status='running',started=? WHERE id=?",(time.time()-120,first))
        self.s.db.execute('INSERT INTO job_dependencies VALUES(?,?)',(second,first));self.s.db.commit()
        text=quick_status.answer(self.s,'most éppen mi dolgozik?')
        self.assertIn('Most dolgozik',text);self.assertIn(self.agent['name'],text)
        self.assertIn('most dolgozik',text.split('Sorban áll:')[1])

    def test_a_plan_cut_off_for_length_is_retried_as_a_small_step(self):
        from commander import schema
        schema(self.s)
        jid=self.s.enqueue(self.agent['id'],'hozz létre projektet és weboldalt')
        self.s.db.execute("UPDATE jobs SET kind='command',status='running',payload=? WHERE id=?",(json.dumps(dict(turn='t1')),jid))
        cols=[c[1] for c in self.s.db.execute('PRAGMA table_info(command_turns)')]
        self.s.db.execute('INSERT INTO command_turns('+','.join(cols)+') VALUES('+','.join('?'*len(cols))+')',
                          tuple('t1' if c=='id' else 'queued' if c=='status' else time.time() if c=='created' else '[]' if c=='actions' else '' for c in cols));self.s.db.commit()
        job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
        self.assertTrue(assistant_resilience.retry_plan(self.s,job,ValueError('A terv túl hosszú lett. Részleges műveletsor nem hajtható végre; kérj kisebb lépéseket.')))
        saved=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])
        self.assertTrue(saved['shorter_plan']);self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'queued')

    def test_a_passing_model_fault_reruns_a_background_step_three_times(self):
        jid=self.s.enqueue(self.agent['id'],'elemzés')
        self.s.db.execute("UPDATE jobs SET kind='mission_agent',status='running' WHERE id=?",(jid,));self.s.db.commit()
        job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
        for attempt in range(3):
            self.assertTrue(self.s.retry_transient(job,ValueError('A modell válasza nem teljes JSON-objektum. Részleges tervet nem hajtunk végre.')),attempt)
            self.s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,));self.s.db.commit()
        self.assertFalse(self.s.retry_transient(job,ValueError('A modell válasza nem teljes JSON-objektum.')))
        self.assertFalse(self.s.retry_transient(job,ValueError('A fájl nem található.')))
        chat=dict(job,kind='graph');self.assertFalse(self.s.retry_transient(chat,ValueError('XML syntax error')))

    def test_a_story_step_survives_a_passing_ssd_read_fault(self):
        jid=self.s.enqueue(self.agent['id'],'hang','graph',payload=dict(run='r',story_step='sound'))
        self.s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,));self.s.db.commit()
        job=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
        self.assertTrue(self.s.retry_transient(job,OSError("[Errno 4] Interrupted system call: '/Volumes/SSD/audio'")))
        self.assertEqual(self.s.db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'queued')
        self.s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,));self.s.db.commit()
        self.assertFalse(self.s.retry_transient(job,ValueError('A párbeszéd nem fér el az epizódban')),'a real fault is not retried')


class VideoIntent(unittest.TestCase):
    def test_the_three_video_workflows_are_told_apart(self):
        import story_animation as sa
        own=['készíts egy videót a youtube shorts projektbe amiben egy a referenciához hasonló stílusban készítesz egy kreatív videót. Referencia: https://www.youtube.com/shorts/YYExVIHhZO0',
             'készíts egy videót a youtube shorts projektbe ... Referencia: https://www.youtube.com/shorts/YYExVIHhZO0 a saját helyi video generáló modellt használd.',
             'készíts egy videót a helyi video generáló modellel amiben egy ijesztő hangulatú videót csinálsz, a többit találd ki.',
             'indíts egy saját animációs videót két stoner pálcikaemberrel']
        for prompt in own:
            self.assertEqual(sa.video_intent(prompt),'own',prompt);self.assertTrue(sa.production_request(prompt),prompt)
        clip=['vágj egy shorts videót Kai Cenat legjobb pillanataiból','készíts shorts klipet ebből: https://www.youtube.com/watch?v=abc','MrBeast best moments shorts videó']
        for prompt in clip:
            self.assertEqual(sa.video_intent(prompt),'clip',prompt);self.assertFalse(sa.production_request(prompt),prompt)
        self.assertEqual(sa.video_intent('indítsd a gta 6 clip farmot'),'gta6')
        self.assertEqual(sa.video_intent('vágj klipet a legújabb gta 6 streamből'),'gta6')
        studio='indíts egy animációs stúdióban videó generálást a saját helyi modellel.az   legyen a témájaa videónak a gta 6 release, A műhelyben az agentekkel végezd a munkát.'
        self.assertEqual(sa.video_intent(studio),'own');self.assertTrue(sa.production_request(studio))
        self.assertEqual(sa.video_intent('készíts saját animációt a gta 6 megjelenéséről'),'own')
        self.assertIsNone(sa.video_intent('készíts shorts videót Kai Cenatról'))

    def test_own_animation_moves_to_its_own_project(self):
        import story_animation as sa
        with tempfile.TemporaryDirectory() as folder:
            s=Studio(Path(folder));self.addCleanup(s.db.close)
            old=s.create_project('YouTube Shorts','t');sa.install_team(s,old)
            self.assertEqual(sa.project(s),old)
            pid=sa.separate(s)
            self.assertNotEqual(pid,old);self.assertEqual(sa.project(s),pid);self.assertEqual(sa.separate(s),pid)
            self.assertTrue(s.db.execute('SELECT 1 FROM agents WHERE id=?',(sa.agent_ids(pid)['hook'],)).fetchone())
            archived={r[0] for r in s.db.execute('SELECT id FROM agent_archive')}
            self.assertEqual(archived,set(sa.agent_ids(old).values()))
            self.assertTrue((Path(folder)/'projects'/pid/'story-studio/series-v2.json').is_file())
            run=s.enqueue_graph(pid,sa.agent_ids(pid)['hook'],'készíts egy saját animációs videót')
            self.assertEqual(len(run['jobs']),6)


if __name__=='__main__':
    unittest.main()
