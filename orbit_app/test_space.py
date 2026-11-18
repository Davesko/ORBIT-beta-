import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch

class SpaceTests(unittest.TestCase):
    def setUp(self):
        language=patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts));language.start();self.addCleanup(language.stop)
        self.temp=tempfile.TemporaryDirectory();self.s=Studio(Path(self.temp.name));self.pid='universe';self.agents=self.s.snapshot(self.pid)['agents'];self.a,self.b,self.c=[a['id'] for a in self.agents]
    def tearDown(self):self.s.db.close();self.temp.cleanup()
    def req(self,action,**kwargs):return dispatch(dict(action=action,project=self.pid,**kwargs),self.s)
    def connect(self,a,b,**kwargs):return self.req('connection_save',connection=dict(source=a,target=b,**kwargs))['id']
    def test_existing_installation_gets_default_rooms_once(self):
        self.assertEqual(len(self.s.snapshot(self.pid)['rooms']),4)
        self.req('room_archive',id='media');self.s.ensure_rooms(self.pid)
        self.assertEqual(self.s.room(self.pid,'media',False)['archived'],1)
        reopened=Studio(Path(self.temp.name));self.assertEqual(reopened.room(self.pid,'media',False)['archived'],1);reopened.db.close()
    def test_custom_room_persists_membership_colors_and_geometry(self):
        rid=self.req('room_save',room={'name':'Közös műhely','sub':'Saját csapat','width':10,'height':9,'decor':'lounge','floor':'#d8a688','wall':'#eddacd','accent':'#afefac','members':[self.a,self.b]})['id']
        room=self.s.room(self.pid,rid);self.assertEqual(room['width'],10);self.assertEqual(room['decor'],'lounge');self.assertEqual(room['floor'],'#d8a688')
        self.assertEqual(self.s.agent(self.a)['room'],rid);self.assertEqual(self.s.agent(self.b)['room'],rid)
        self.assertEqual(self.s.agent(self.a)['tools'],self.agents[0]['tools'])
    def test_room_membership_removal_requires_destination_and_is_atomic(self):
        r=self.s.room(self.pid,'bridge')
        with self.assertRaises(ValueError):self.req('room_save',room=dict(r,members=[],move_to='missing'))
        self.assertEqual(self.s.agent(self.a)['room'],'bridge')
        self.req('room_save',room=dict(r,members=[],move_to='research'));self.assertEqual(self.s.agent(self.a)['room'],'research')
    def test_room_geometry_rejects_overlap_nonfinite_and_bad_color(self):
        for data in [{'name':'Overlap','x':0,'y':0},{'name':'NaN','x':float('nan')},{'name':'Bad','floor':'red'},{'name':'Huge','width':900}]:
            with self.assertRaises(ValueError):self.req('room_save',room=data)
        self.assertEqual(len(self.s.snapshot(self.pid)['rooms']),4)
    def test_archive_moves_agents_without_changing_jobs_or_model(self):
        self.s.enqueue(self.a,'Feladat');before=self.s.snapshot(self.pid)['jobs']
        self.req('room_archive',id='bridge',move_to='research');self.assertEqual(self.s.agent(self.a)['room'],'research');self.assertEqual(self.s.snapshot(self.pid)['jobs'],before)
        self.req('room_restore',id='bridge');self.assertFalse(self.s.room(self.pid,'bridge')['archived'])
        self.assertEqual(self.s.agent(self.a)['room'],'research')
    def test_last_room_cannot_be_archived(self):
        for rid in ['research','workshop','media']:self.req('room_archive',id=rid,move_to='bridge')
        with self.assertRaises(ValueError):self.req('room_archive',id='bridge')
    def test_archived_room_not_recreated_or_assignable(self):
        self.req('room_archive',id='media')
        with self.assertRaises(ValueError):self.req('agent_save',agent=dict(self.agents[0],room='media'))
        with self.assertRaises(ValueError):self.req('room_save',room=dict(self.s.room(self.pid,'media',False)))
    def test_cross_project_rooms_and_members_are_isolated(self):
        other=self.s.create_project('Másik');oa=self.s.snapshot(other)['agents'][0]['id']
        with self.assertRaises(ValueError):self.req('room_save',room={'name':'Wrong','members':[oa]})
        self.assertEqual(self.s.agent(oa)['project'],other)
        custom=self.s.save_room(other,{'name':'Other'})
        with self.assertRaises(ValueError):self.req('room_archive',id='bridge',move_to=custom)
    def test_multiple_agents_are_spaced_and_capped(self):
        for i in range(15):self.s.save_agent(dict(self.agents[0],id=None,name='Társ '+str(i)))
        with self.assertRaises(ValueError):self.s.save_agent(dict(self.agents[0],id=None,name='Nincs hely'))
    def test_connection_saved_without_creating_jobs_and_upserts(self):
        first=self.connect(self.a,self.b,name='Elemzés',mode='both',instructions='A fő pontokat használd.',task='Írj tervet.')
        second=self.connect(self.a,self.b,name='Új cím');self.assertEqual(first,second)
        state=self.s.snapshot(self.pid);self.assertEqual(len(state['connections']),1);self.assertEqual(len(state['jobs']),0)
    def test_self_links_cycles_and_cross_project_links_rejected(self):
        with self.assertRaises(ValueError):self.connect(self.a,self.a)
        self.connect(self.a,self.b);self.connect(self.b,self.c)
        with self.assertRaises(ValueError):self.connect(self.c,self.a)
        other=self.s.create_project('Other');oa=self.s.snapshot(other)['agents'][0]['id']
        with self.assertRaises(ValueError):self.connect(self.a,oa)
    def test_graph_fanout_join_waits_all_parents(self):
        d=self.s.save_agent(dict(self.agents[2],id=None,name='Ellenőr'))
        for a,b in [(self.a,self.b),(self.a,self.c),(self.b,d),(self.c,d)]:self.connect(a,b)
        self.req('graph_run',agent=self.a,prompt='Közös cél')
        first=self.s.claim(('graph',));self.assertEqual(first['agent'],self.a);self.assertIsNone(self.s.claim(('graph',)))
        self.s.finish(first,'Forrás eredménye');second=self.s.claim(('graph',));third=self.s.claim(('graph',));self.assertEqual({second['agent'],third['agent']},{self.b,self.c})
        self.s.finish(second,'Első ág');self.assertIsNone(self.s.claim(('graph',)));self.s.finish(third,'Másik ág');last=self.s.claim(('graph',));self.assertEqual(last['agent'],d)
        context=self.s.handoff_context(last);self.assertIn('Első ág',context);self.assertIn('Másik ág',context)
    def test_cancel_blocks_descendants_but_not_other_branch(self):
        self.connect(self.a,self.b);self.connect(self.a,self.c);self.connect(self.b,self.s.save_agent(dict(self.agents[2],id=None,name='Utód')))
        self.req('graph_run',agent=self.a,prompt='Teszt');first=self.s.claim(('graph',));self.s.finish(first,'Kész');second=self.s.claim(('graph',));third=self.s.claim(('graph',));failed=second if second['agent']==self.b else third
        self.s.cancel(failed['id']);self.assertIsNone(self.s.claim(('graph',)));statuses=self.s.rows('SELECT agent,status FROM jobs');self.assertEqual(sum(j['status']=='blocked' for j in statuses),1)
    def test_handoff_modes_files_only_do_not_pass_response(self):
        self.connect(self.a,self.b,mode='files');self.req('graph_run',agent=self.a,prompt='Feladat')
        first=self.s.claim(('graph',));self.s.tool(self.s.agent(self.a),'write_file',{'name':'result.md','content':'Tartalom'},first['id']);self.s.finish(first,'PRIVATE_NOT_PASSED')
        second=self.s.claim(('graph',));context=self.s.handoff_context(second);self.assertIn('result.md',context);self.assertNotIn('PRIVATE_NOT_PASSED',context)
        with patch('studio.local_api',return_value={'message':{'content':'Kész'}}) as api:self.s.run_agent(second);self.assertIn('result.md',api.call_args.args[2]['messages'][-1]['content'])
    def test_running_graph_freezes_contract_on_edit_or_archive(self):
        cid=self.connect(self.a,self.b,mode='result',instructions='Eredeti útmutató')
        self.req('graph_run',agent=self.a,prompt='Feladat');self.req('connection_archive',id=cid)
        self.connect(self.a,self.b,mode='files',instructions='Másik útmutató')
        first=self.s.claim(('graph',));self.s.finish(first,'Átadott szöveg');second=self.s.claim(('graph',));context=self.s.handoff_context(second)
        self.assertIn('Eredeti útmutató',context);self.assertIn('Átadott szöveg',context);self.assertNotIn('Másik útmutató',context)
    def test_queue_capacity_does_not_create_partial_graph(self):
        self.connect(self.a,self.b)
        for _ in range(29):self.s.enqueue(self.a,'Várakozik')
        with self.assertRaises(ValueError):self.req('graph_run',agent=self.a,prompt='Nem fér el')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM jobs').fetchone()[0],29);self.assertEqual(self.s.db.execute('SELECT count(*) FROM job_dependencies').fetchone()[0],0)
    def test_graph_messages_are_durable(self):
        self.connect(self.a,self.b);self.req('graph_run',agent=self.a,prompt='Cél');first=self.s.claim(('graph',));self.s.finish(first,'Valós eredmény')
        messages=self.s.snapshot(self.pid)['messages'];self.assertTrue(any(m['content']=='Valós eredmény' and m['role']=='assistant' for m in messages))

if __name__=='__main__':unittest.main()
