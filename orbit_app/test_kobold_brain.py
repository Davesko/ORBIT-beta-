"""The smarter Kobold link: needs out, fitting skills only, help asked when stuck, answers become cards, real feedback."""
import json,tempfile,time,unittest
from pathlib import Path

import kobold_link as link
import kobold_brain as brain
import assistant_skills
from studio import Studio

SECRET=bytes(range(32)).hex()


class Brain(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
        link.set_setting(self.s,'shared_root',str(Path(self.tmp.name)/'KoboldOrbit'));link.pair(self.s,SECRET)
        self.pid=self.s.create_project('Hírgyár')
        self.aid=self.s.db.execute('SELECT id FROM agents WHERE project=? LIMIT 1',(self.pid,)).fetchone()[0]
        for i in range(3):
            jid=self.s.enqueue(self.aid,f'Írj hírt #{i}')
            self.s.db.execute("UPDATE jobs SET status='failed',error=?,finished=? WHERE id=?",(f'A modell válasza nem teljes JSON-objektum ({i}).',time.time(),jid))
        self.s.db.commit()

    def out(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in (Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')]

    def deliver(self,kind,body,reply_to=None,title='x'):
        inbox=Path(self.tmp.name)/'KoboldOrbit/kobold/kimeno';inbox.mkdir(parents=True,exist_ok=True)
        m=dict(protocol=link.PROTOCOL,id=__import__('uuid').uuid4().__str__(),time='2026-11-11T10:00:00Z',**{'from':'kobold'},to='orbit',type=kind,reply_to=reply_to,title=title,body=body)
        m['sig']=link.sign(m,SECRET);(inbox/link.file_name(m)).write_text(json.dumps(m,ensure_ascii=False),encoding='utf-8');link.read_inbox(self.s)
        return m

    def test_repeated_failures_become_a_need_and_a_help_question_once(self):
        found=brain.needs(self.s)
        self.assertEqual((found[0]['count'],found[0]['project']),(3,'Hírgyár'),'numbers in the error are folded together')
        brain.share_needs(self.s);brain.ask_help(self.s);brain.ask_help(self.s)
        out=self.out()
        need=next(m for m in out if m['type']=='info')
        self.assertIn('igeny',need['body']['tags']);self.assertIn('Hírgyár',need['body']['text'])
        self.assertEqual(len([m for m in out if m['type']=='question']),1,'asked once a week')
        self.assertTrue(all(link.check(m,SECRET)==[] for m in out))

    def test_an_answer_to_help_becomes_an_improvement_card(self):
        brain.ask_help(self.s)
        q=next(m for m in self.out() if m['type']=='question')
        self.deliver('answer',dict(text='Kérj rövidebb JSON-t, és adj sémát a modellnek.',origin='assistant'),reply_to=q['id'])
        card=self.s.db.execute("SELECT scope,title,why FROM improvement_ideas WHERE source='kobold'").fetchone()
        self.assertEqual(card['scope'],self.pid);self.assertIn('sémát',card['why'])

    def test_kobolds_need_gets_only_fitting_orbit_skills(self):
        assistant_skills.save(self.s,dict(id='json-fix',title='JSON-javítás',description='Hiányos JSON-válasz javítása séma szerint',steps=['Kérj sémát.','Ellenőrizd.'],verification=['Érvényes JSON.'],tags=['json'],status='published'))
        before=len([m for m in self.out() if m['type']=='skill'])
        m=self.deliver('info',dict(category='warning',text='IGÉNY (Kobold):\n- Storyfarm: hiányos JSON válasz a modelltől',tags=['igeny']))
        skills=[x for x in self.out() if x['type']=='skill']
        self.assertEqual(len(skills)-before,1);self.assertEqual(skills[-1]['reply_to'] if len(skills)==1 else [x for x in skills if x['reply_to']][0]['reply_to'],m['id'])

    def test_use_of_a_kobold_workshop_is_reported_with_numbers(self):
        m=self.deliver('skill',dict(skill_id='kabin-x',kind='procedure',summary='Kobold „X” gyártósora (Kabin, egymás után dolgozó AI-ügynökök).',
                                    steps=['💡 Ötlet – Ötletel.: Invent one idea.','🧐 Bíráló – Bírál.: Score it.'],version=1),title='Kabin: X')
        pid=self.s.db.execute('SELECT note FROM kobold_messages WHERE id=?',(m['id'],)).fetchone()[0].split(': ')[1]
        aid=self.s.db.execute('SELECT id FROM agents WHERE project=? LIMIT 1',(pid,)).fetchone()[0]
        for status in ('done','done','failed'):
            jid=self.s.enqueue(aid,'run');self.s.db.execute('UPDATE jobs SET status=?,finished=? WHERE id=?',(status,time.time(),jid))
        self.s.db.commit()
        link.set_setting(self.s,'feedback_at',time.time()-2*86400)
        self.assertEqual(brain.report_feedback(self.s),1)
        r=[x for x in self.out() if x['type']=='receipt' and x['reply_to']==m['id'] and x['body']['status'] in ('worked','failed')][0]
        self.assertEqual(r['body']['status'],'worked');self.assertIn('3×',r['body']['note']);self.assertIn('2 sikeres',r['body']['note'])

    def test_library_and_kobold_skills_are_not_resent(self):
        self.assertFalse(brain.shareable(dict(id='lib-x',source='library')))
        self.assertFalse(brain.shareable(dict(id='kobold-y',source='taught')))
        self.assertTrue(brain.shareable(dict(id='animation-studio',source='taught')))
