"""Requests are understood from what each workflow does; unclear ones are decided by the model or asked back, and
corrections are remembered."""
import json,tempfile,time,unittest
from pathlib import Path

import intent_router as router
from studio import Studio


class IntentRouter(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
        self.job=dict(id='j1',project='p')

    def test_clear_wording_needs_no_model(self):
        boom=lambda *a:self.fail('the model was asked')
        self.assertEqual(router.understand(self.s,self.job,'vágj egy shorts klipet Kai Cenat legjobb pillanataiból',boom)['workflow'],'clip')
        self.assertEqual(router.understand(self.s,self.job,'készíts egy saját animációs videót',boom)['by'],'words')
        self.assertIsNone(router.understand(self.s,self.job,'mi az a shorts videó?',boom))
        self.assertIsNone(router.understand(self.s,self.job,'írj egy verset a tavaszról',boom))

    def test_unclear_wording_is_decided_by_the_model_from_descriptions(self):
        seen={}
        def model(s,job,prompt,known):
            seen['known']=known;return dict(workflow='own',reason='wants something new',question='')
        got=router.understand(self.s,self.job,'csinálj nekem valami vicces shorts videót a macskákról',model)
        self.assertEqual((got['workflow'],got['by']),('own','model'))

    def test_unsure_asks_one_question_and_a_dead_model_changes_nothing(self):
        got=router.understand(self.s,self.job,'készíts egy shorts videót ebből https://youtu.be/abc',lambda *a:dict(workflow='unsure',reason='',question=''))
        self.assertEqual((got['workflow'],got['question']),('unsure',router.QUESTION))
        def dead(*a):raise OSError('no model')
        self.assertIsNone(router.understand(self.s,self.job,'készíts egy shorts videót a macskákról',dead))
        self.assertIsNone(router.understand(self.s,self.job,'készíts egy shorts videót a macskákról',lambda *a:dict(workflow='invented')))

    def test_a_remembered_request_is_followed_without_the_model(self):
        router.remember(self.s,'csinálj egy vicces shorts videót a macskákról','own')
        got=router.understand(self.s,self.job,'csinálj egy vicces shorts videót a macskákról',lambda *a:self.fail('asked'))
        self.assertEqual((got['workflow'],got['by']),('own','example'))
        shown={}
        router.understand(self.s,self.job,'készíts shorts videót macskákról a kertben este',lambda s,j,p,known:shown.update(known=known) or dict(workflow='own',reason='',question=''))
        self.assertEqual(shown['known'][0]['workflow'],'own')

    def test_a_correction_teaches_the_earlier_request(self):
        from commander import schema
        schema(self.s)
        pid=self.s.create_project('P');agent=self.s.rows('SELECT id FROM agents WHERE project=? LIMIT 1',(pid,))[0]['id']
        cols=[c[1] for c in self.s.db.execute('PRAGMA table_info(command_turns)')]
        for i,(prompt,workflow) in enumerate([('készíts shorts videót a reggeli kávéról','clip'),('nem klip kell, saját animációs videót készíts','own')]):
            tid='t%d'%i;jid=self.s.enqueue(agent,prompt)
            self.s.db.execute("UPDATE jobs SET kind='command',payload=? WHERE id=?",(json.dumps(dict(turn=tid,workflow=workflow)),jid))
            self.s.db.execute('INSERT INTO command_turns('+','.join(cols)+') VALUES('+','.join('?'*len(cols))+')',
                              tuple(tid if c=='id' else pid if c=='project' else prompt if c=='prompt' else 'done' if c=='status' else time.time()+i if c=='created' else '[]' if c=='actions' else '' for c in cols))
        self.s.db.commit()
        self.assertEqual(router.learn_correction(self.s,pid,'nem klip kell, saját animációs videót készíts','own'),'készíts shorts videót a reggeli kávéról')
        self.assertEqual(router.examples(self.s,'készíts shorts videót a reggeli kávéról')[0]['workflow'],'own')
        self.assertIsNone(router.learn_correction(self.s,pid,'készíts még egy saját videót','own'))


if __name__=='__main__':
    unittest.main()
