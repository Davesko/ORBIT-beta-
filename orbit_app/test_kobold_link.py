"""kobold-orbit/1: ORBIT signs, checks and files messages exactly like the shared contract, and never leaks."""
import json,tempfile,unittest
from pathlib import Path

import kobold_link as link
from studio import Studio

HERE=Path(link.__file__).with_name('kobold_contract')
TEST_SECRET=bytes(range(32)).hex()


class Contract(unittest.TestCase):
    def test_the_shipped_schema_is_the_contract_schema(self):
        self.assertEqual((HERE/'schema.json').read_bytes(),Path(link.__file__).with_name('kobold_orbit_schema.json').read_bytes())

    def test_the_test_vector_signs_byte_for_byte(self):
        vector=json.loads((HERE/'tesztvektor.json').read_text(encoding='utf-8'))
        self.assertEqual(link.canonical(vector['message']).decode('utf-8'),vector['canonical'])
        self.assertEqual(link.sign(vector['message'],vector['secret']),vector['expected_sig'])

    def test_good_examples_pass_and_bad_ones_fail_for_the_expected_reason(self):
        for path in sorted((HERE/'peldak/jo').glob('*.json')):
            self.assertEqual(link.check(json.loads(path.read_text(encoding='utf-8')),TEST_SECRET,path.name,path.stat().st_size),[],path.name)
        expected=json.loads((HERE/'peldak/rossz/varhato.json').read_text(encoding='utf-8'))
        for name,reason in expected.items():
            path=HERE/'peldak/rossz'/name
            try:message=json.loads(path.read_text(encoding='utf-8'))
            except ValueError:message=None
            errors=link.check(message,TEST_SECRET,name,path.stat().st_size)
            self.assertTrue(any(reason in e for e in errors),(name,errors))


class Exchange(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
        link.set_setting(self.s,'shared_root',str(Path(self.tmp.name)/'KoboldOrbit'))
        link.pair(self.s,TEST_SECRET)

    def test_a_sent_message_is_signed_valid_and_named_by_the_contract(self):
        result=link.send(self.s,'info','Tipp',dict(category='tip',text='A 3 mp alatti hook jobban tart.'))
        self.assertEqual(result['status'],'sent')
        path=next((Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json'))
        message=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(link.check(message,TEST_SECRET,path.name,path.stat().st_size),[])
        self.assertFalse((Path(self.tmp.name)/'KoboldOrbit'/'secret').exists())
        self.assertNotIn(TEST_SECRET,path.read_text(encoding='utf-8'))

    def test_personal_data_is_held_back(self):
        for text in ('írj a pelda@gmail.com címre','a fájl a /Users/anna/Desktop alatt van','kulcs: sk_live_abcdefghijklmnop'):
            self.assertEqual(link.send(self.s,'info','x',dict(category='tip',text=text))['status'],'held',text)
        self.assertEqual(list((Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')),[])

    def test_received_messages_are_checked_receipted_and_a_skill_becomes_a_draft(self):
        inbox=Path(self.tmp.name)/'KoboldOrbit/kobold/kimeno';inbox.mkdir(parents=True)
        for path in (HERE/'peldak/jo').glob('*.json'):
            message=json.loads(path.read_text(encoding='utf-8'))
            if message['from']=='kobold':(inbox/path.name).write_bytes(path.read_bytes())
        forged=json.loads(next((HERE/'peldak/jo').glob('*.json')).read_text(encoding='utf-8'));forged.update(id='0000000f-0000-4000-8000-00000000000f',sig='a'*64,**{'from':'kobold','to':'orbit'})
        (inbox/link.file_name(forged)).write_text(json.dumps(forged),encoding='utf-8')
        link.read_inbox(self.s)
        rows={r['id']:r for r in self.s.rows("SELECT id,type,status FROM kobold_messages WHERE direction='in'")}
        self.assertEqual(rows[forged['id']]['status'],'unverified')
        skill=next(r for r in rows.values() if r['type']=='skill')
        self.assertEqual(link.read_inbox(self.s),0,'a message is handled once')
        self.assertTrue(link.adopt(self.s,skill['id'])['queued'],'a data skill with a working source is learned live')
        receipts=[json.loads(p.read_text(encoding='utf-8')) for p in (Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')]
        self.assertIn('delivered',[m['body']['status'] for m in receipts if m['type']=='receipt'])
        self.assertTrue(all(link.check(m,TEST_SECRET)==[] for m in receipts))

    def test_channel_lessons_and_the_studio_method_are_shared_once(self):
        from unittest.mock import patch
        lesson=dict(trait='hook',best='5 mp alatti',worst='10 mp feletti',best_avg=71.0,worst_avg=52.5,sample=9,text='5 mp alatti nyitású videók: átlag 71% megnézve')
        self.s.create_project('YouTube Shorts')
        with patch('short_feedback.read',return_value=dict(recommendation=dict(lessons=[lesson]),videos=[])):
            self.assertGreaterEqual(link.share_insights(self.s,1000.),1)
            self.assertEqual(link.share_insights(self.s,1000.+2*86400),0,'a lesson goes once')
        self.assertEqual(link.share_studio(self.s)['status'],'sent');self.assertIsNone(link.share_studio(self.s))
        out=[json.loads(p.read_text(encoding='utf-8')) for p in (Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')]
        self.assertTrue(all(link.check(m,TEST_SECRET)==[] for m in out))
        self.assertIn('procedure',[m['body'].get('kind') for m in out if m['type']=='skill'])

    def test_a_skill_request_is_answered_with_the_skill_itself(self):
        inbox=Path(self.tmp.name)/'KoboldOrbit/kobold/kimeno';inbox.mkdir(parents=True,exist_ok=True)
        q=dict(protocol=link.PROTOCOL,id='0000000a-0000-4000-8000-00000000000a',time='2026-11-11T10:00:00Z',**{'from':'kobold'},to='orbit',type='question',reply_to=None,
               title='Skill-kérés',body=dict(text='SKILL-KÉRÉS: animation-studio\nA Storyfarmhoz kellene.',origin='assistant'))
        q['sig']=link.sign(q,TEST_SECRET);(inbox/link.file_name(q)).write_text(json.dumps(q,ensure_ascii=False),encoding='utf-8')
        link.read_inbox(self.s)
        out=[json.loads(p.read_text(encoding='utf-8')) for p in (Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')]
        skill=next(m for m in out if m['type']=='skill')
        self.assertEqual((skill['reply_to'],skill['body']['skill_id']),(q['id'],'animation-studio'))
        self.assertIn('answer',[m['type'] for m in out])
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM jobs WHERE json_extract(payload,'$.task')='kobold_answer'").fetchone()[0],0,'no model needed')

    def deliver(self,mid,body,title):
        inbox=Path(self.tmp.name)/'KoboldOrbit/kobold/kimeno';inbox.mkdir(parents=True,exist_ok=True)
        m=dict(protocol=link.PROTOCOL,id=mid,time='2026-11-11T10:00:00Z',**{'from':'kobold'},to='orbit',type='skill',reply_to=None,title=title,body=body)
        m['sig']=link.sign(m,TEST_SECRET);(inbox/link.file_name(m)).write_text(json.dumps(m,ensure_ascii=False),encoding='utf-8')
        link.read_inbox(self.s)

    def test_a_kobold_data_skill_is_learned_from_its_working_sources(self):
        import skill_api
        self.deliver('0000000b-0000-4000-8000-00000000000b',dict(skill_id='spacex_kovetkezo_inditas',kind='data',summary='A következő SpaceX rakétaindítás időpontja és küldetése.',
            examples=['Mikor lesz a következő SpaceX indítás?'],sources=[dict(url='https://spacexnow.example/api',works=False,needs_key=False),dict(url='https://ll.thespacedevs.com/2.2.0/launch/upcoming/',works=True,needs_key=False)],version=1),'SpaceX következő indítás')
        mid=link.find_received(self.s,'használd a kobold spacex skilljét, mikor lesz a következő indítás?')
        self.assertEqual(mid,'0000000b-0000-4000-8000-00000000000b')
        self.assertTrue(link.adopt(self.s,mid)['queued'])
        job=dict(self.s.db.execute("SELECT * FROM jobs WHERE json_extract(payload,'$.task')='kobold_learn'").fetchone())
        seen={}
        def learn(s,goal,job=None,apis=None,**k):
            seen['apis']=apis;return dict(status='learned',skill=dict(id='spacex-launch'))
        old=skill_api.learn;skill_api.learn=learn
        try:link.learn_job(self.s,job)
        finally:skill_api.learn=old
        self.assertEqual([a['url'] for a in seen['apis']],['https://ll.thespacedevs.com/2.2.0/launch/upcoming/'],'only the working source')
        self.assertEqual(skill_api.candidates('következő SpaceX rakétaindítás időpontja',seen['apis']),seen['apis'],'the learner accepts the source as a catalog entry')
        self.assertEqual(self.s.db.execute('SELECT status FROM kobold_messages WHERE id=?',(mid,)).fetchone()[0],'adopted')
        out=[json.loads(p.read_text(encoding='utf-8')) for p in (Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')]
        self.assertIn('adopted',[m['body'].get('status') for m in out if m['type']=='receipt'])

    def test_a_kobold_agent_chain_becomes_an_orbit_project(self):
        self.deliver('0000000c-0000-4000-8000-00000000000c',dict(skill_id='hirlevel_gyar',kind='procedure',summary='Heti hírlevél három ügynökkel.',
            steps=['Kutató: gyűjts öt friss hírt forrással.','Író: írj belőlük rövid hírlevelet.','Bíráló: ellenőrizd a tényeket és a hangnemet.'],verification=['Minden hírnek van forrása.'],version=1),'Hírlevél-gyár')
        made=link.as_project(self.s,'0000000c-0000-4000-8000-00000000000c')
        agents=self.s.rows('SELECT name,prompt FROM agents WHERE project=? ORDER BY rowid',(made['project'],))
        self.assertEqual([a['name'] for a in agents],['Kutató','Író','Bíráló'])
        self.assertIn('Minden hírnek van forrása',agents[-1]['prompt'])
        self.assertEqual(made['agents'],3)
        self.assertEqual(self.s.db.execute('SELECT status FROM kobold_messages WHERE id=?',('0000000c-0000-4000-8000-00000000000c',)).fetchone()[0],'adopted')

    def test_a_kobold_kabin_is_recognised_and_built_as_a_workshop_on_arrival(self):
        mid='0000000d-0000-4000-8000-00000000000d'
        self.deliver(mid,dict(skill_id='kabin-szimgyar',kind='procedure',summary='Kobold „Szimgyár” gyártósora (Kabin, egymás után dolgozó AI-ügynökök): fizikai szimulációs shortok. Kimenet: szimulacio, nyelv: en.',
            steps=['💡 Ötletgazda – Kitalálja a videó ötletét.: You invent ONE simulation short idea.',
                   '📐 Tervező – Az ötletből pontos koncepciót ír.: Turn the idea into a precise concept.',
                   '🧐 Bíráló – Ellenőrzi a koncepciót.: Score the concept 1-10. [bíráló: ha gyenge, visszaküldi javításra]',
                   '🎱 Szimulátor – Beépített: a koncepciót szimulációs tervre fordítja és rendereli'],
            expectations=['Tanulság: **Maintain strict single-track logic:** never two environments.'],verification=['Bíráló: érthető és megépíthető-e.'],version=1),'Kabin: Szimgyár')
        note=self.s.db.execute('SELECT status,note FROM kobold_messages WHERE id=?',(mid,)).fetchone()
        self.assertEqual(note[0],'adopted',note[1])
        pid=note[1].split(': ')[1]
        agents=self.s.rows('SELECT name,role,prompt,tools FROM agents WHERE project=? ORDER BY rowid',(pid,))
        self.assertEqual([a['name'] for a in agents],['💡 Ötletgazda','📐 Tervező','🧐 Bíráló','🎱 Szimulátor'])
        self.assertEqual(agents[0]['role'],'Kitalálja a videó ötletét')
        self.assertIn('single-track',agents[0]['prompt'])
        self.assertIn('ha gyenge',agents[2]['prompt']);self.assertNotIn('[bíráló',agents[2]['prompt'])
        self.assertIn('render_simulation',json.loads(agents[3]['tools']),'the engine step renders with ORBIT\'s own simulator')
        self.assertIn('render_simulation',agents[3]['prompt'])
        rooms=[r['room'] for r in self.s.rows('SELECT room FROM agents WHERE project=? ORDER BY rowid',(pid,))]
        self.assertEqual(rooms,['research','workshop','bridge','media'],'each step in the room of its job, not all in one')
        self.assertIn('single-track',(self.s.root/'projects'/pid/'kobold_muhely.md').read_text(encoding='utf-8'))
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM connections WHERE project=?',(pid,)).fetchone()[0],3)
        self.assertIn('BUILDING BLOCKS of the 2D physics simulation engine',agents[1]['prompt'],'the planner gets the engine\'s blocks')
        self.assertEqual(link.as_project(self.s,mid)['note'],'Ez a műhely már be van építve.')
        self.assertEqual(next(m for m in link.overview(self.s)['items'] if m['id']==mid)['kind'],'műhely')

    def test_a_skill_kobold_has_is_requested_instead_of_learned(self):
        link.set_setting(self.s,'peer_profile',dict(skills=[dict(skill_id='ai_ceg_arfolyamok',title='AI cégek árfolyamai',kind='data',summary='Microsoft, Google aktuális árfolyama')]))
        got=link.request_known(self.s,'AI cégek aktuális árfolyamai, például a Microsoft')
        self.assertEqual(got['skill_id'],'ai_ceg_arfolyamok')
        out=[json.loads(p.read_text(encoding='utf-8')) for p in (Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')]
        self.assertTrue(out[0]['body']['text'].startswith('SKILL-KÉRÉS: ai_ceg_arfolyamok'))
        self.assertIn('nemrég',link.request_known(self.s,'AI cégek árfolyamai')['note'],'asked once a week')
        self.assertIsNone(link.request_known(self.s,'időjárás Budapesten holnap'))

    def test_own_skills_go_out_without_code_and_the_profile_is_written(self):
        import assistant_skills
        assistant_skills.save(self.s,dict(id='video-tip',title='Gyors hook',description='Az első 2 mp-ben legyen konfliktus.',tags=['shorts'],steps=['Nyiss a konfliktussal.'],verification=['2 mp alatt látszik a gond.'],status='published'))
        link.auto_share(self.s);link.profile(self.s)
        out=[json.loads(p.read_text(encoding='utf-8')) for p in (Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')]
        skill=next(m for m in out if m['type']=='skill' and m['title']=='Gyors hook')
        self.assertEqual(skill['body']['kind'],'procedure');self.assertEqual(link.check(skill,TEST_SECRET),[])
        self.assertTrue((Path(self.tmp.name)/'KoboldOrbit/orbit/nevjegy.json').is_file())
        link.auto_share(self.s)
        before=len(list((Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json')))
        link.auto_share(self.s)
        self.assertEqual(len(list((Path(self.tmp.name)/'KoboldOrbit/orbit/kimeno').glob('*.json'))),before,'sent once per version')


if __name__=='__main__':
    unittest.main()
