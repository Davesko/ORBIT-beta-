import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio,now
from bridge import dispatch

class StudioTests(unittest.TestCase):
    def setUp(self):
        language=patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts));language.start();self.addCleanup(language.stop)
        self.temp=tempfile.TemporaryDirectory();self.s=Studio(Path(self.temp.name));self.pid='universe'
        self.a=self.s.snapshot(self.pid)['agents'][0]
    def tearDown(self):self.s.db.close();self.temp.cleanup()
    def request(self,action,**data):return dispatch(dict(action=action,project=self.pid,**data),self.s)
    def test_project_isolation_and_durable_chat(self):
        other=self.s.create_project('Másik világ');jid=self.s.enqueue(self.a['id'],'Egy helyi feladat')
        self.assertEqual(len(self.s.snapshot(other)['messages']),0)
        self.assertEqual(self.s.snapshot(self.pid)['messages'][0]['job'],jid)
        reopened=Studio(Path(self.temp.name));self.assertEqual(reopened.snapshot(self.pid)['messages'][0]['content'],'Egy helyi feladat');reopened.db.close()
    def test_cannot_run_another_projects_agent(self):
        other=self.s.create_project('Másik');a=self.s.snapshot(other)['agents'][0]
        with self.assertRaises(ValueError):self.request('chat',agent=a['id'],prompt='hello')
    def test_model_configuration_and_permissions(self):
        data=dict(self.a,model='gemma3:4b',tools=['project_files'],interval=10,room='research')
        self.request('agent_save',agent=data);r=self.s.agent(self.a['id']);self.assertEqual(r['model'],'gemma3:4b');self.assertEqual(r['interval'],10)
        with self.assertRaises(ValueError):self.s.tool(r,'write_file',{'name':'test.txt','content':'hi'},'none')
    def test_no_terminal_or_trading_orders(self):
        with self.assertRaises(ValueError):self.s.save_agent(dict(self.a,tools=['terminal']))
        with self.assertRaises(ValueError):self.s.save_agent(dict(self.a,tools=['trading_snapshot']))
        with self.assertRaises(ValueError):self.request('trade',symbol='BTC')
    def test_file_escape_and_symlink_rejected(self):
        with self.assertRaises(ValueError):self.s.safe_path(self.pid,'../../outside.txt')
        base=self.s.root/'projects'/self.pid;base.mkdir(parents=True,exist_ok=True)
        (base/'escape').symlink_to('/tmp',target_is_directory=True)
        with self.assertRaises(ValueError):self.s.safe_path(self.pid,'escape/test.txt')
    def test_write_file_no_overwrite_and_cancelled_has_no_effect(self):
        jid=self.s.enqueue(self.a['id'],'Készíts fájlt');self.s.claim()
        self.s.tool(self.s.agent(self.a['id']),'write_file',{'name':'notes/plan.md','content':'Terv'},jid)
        with self.assertRaises(ValueError):self.s.tool(self.s.agent(self.a['id']),'write_file',{'name':'notes/plan.md','content':'Másik'},jid)
        self.s.cancel(jid)
        with self.assertRaises(ValueError):self.s.tool(self.s.agent(self.a['id']),'write_file',{'name':'cancel.md','content':'Másik'},jid)
        self.assertFalse(self.s.safe_path(self.pid,'cancel.md').exists())
    def test_pipeline_dependency_failure_blocks_downstream(self):
        agents=[a['id'] for a in self.s.snapshot(self.pid)['agents']]
        self.request('pipeline',agents=agents,prompt='Készítsetek tervet')
        first=self.s.claim();self.assertIsNone(self.s.claim());self.s.finish(first,error='Model offline')
        self.assertIsNone(self.s.claim());self.assertTrue(all(j['status']=='blocked' for j in self.s.snapshot(self.pid)['jobs'] if j['id']!=first['id']))
    def test_pipeline_passes_previous_output(self):
        agents=[a['id'] for a in self.s.snapshot(self.pid)['agents']]
        self.request('pipeline',agents=agents[:2],prompt='Tervezzetek');first=self.s.claim();self.s.finish(first,'Az első eredmény')
        second=self.s.claim()
        with patch('studio.local_api',return_value={'message':{'content':'Kész'}}) as api:
            self.s.run_agent(second)
            messages=api.call_args.args[2]['messages'];self.assertIn('Az első eredmény',messages[-1]['content'])
    def test_cancelled_result_not_saved(self):
        jid=self.s.enqueue(self.a['id'],'Ezt állítsd le');job=self.s.claim();self.s.cancel(jid);self.s.finish(job,'Nem kerülhet a chatbe')
        result=self.s.snapshot(self.pid);self.assertEqual(result['jobs'][0]['status'],'cancelled');self.assertFalse(any(m['role']=='assistant' for m in result['messages']))
    def test_cancel_during_inference_prevents_tools(self):
        jid=self.s.enqueue(self.a['id'],'Ne készüljön fájl');job=self.s.claim()
        def response(*args,**kwargs):
            self.s.cancel(jid);return {'message':{'tool_calls':[{'function':{'name':'write_file','arguments':{'name':'forbidden.md','content':'bad'}}}]}}
        with patch('studio.local_api',side_effect=response):self.s.run_agent(job)
        self.assertFalse(self.s.safe_path(self.pid,'forbidden.md').exists())
    def test_real_tools_loop_and_artifact(self):
        self.s.enqueue(self.a['id'],'Készíts tervet');job=self.s.claim()
        responses=[{'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'write_file','arguments':{'name':'plan.md','content':'Valós mentés'}}}]}},{'message':{'content':'Mentve.'}}]
        with patch('studio.local_api',side_effect=responses):self.s.finish(job,self.s.run_agent(job))
        self.assertEqual(self.s.safe_path(self.pid,'plan.md').read_text(),'Valós mentés');self.assertEqual(len(self.s.snapshot(self.pid)['artifacts']),1)
    def test_unknown_model_tool_is_denied(self):
        self.s.enqueue(self.a['id'],'Teszt');job=self.s.claim()
        responses=[{'message':{'tool_calls':[{'function':{'name':'shell','arguments':{'command':'bad'}}}]}},{'message':{'content':'Nincs ilyen eszköz.'}}]
        with patch('studio.local_api',side_effect=responses) as api:self.s.run_agent(job);self.assertIn('nincs jogosultsága',api.call_args.args[2]['messages'][-1]['content'])
    def test_schedule_skips_missed_intervals_and_does_not_duplicate(self):
        self.s.save_agent(dict(self.a,interval=5));self.s.db.execute('UPDATE agents SET next_run=? WHERE id=?',(now()-50000,self.a['id']));self.s.db.commit()
        self.s.schedule();self.s.schedule();jobs=self.s.snapshot(self.pid)['jobs'];self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['kind'],'scheduled')
    def test_schedule_limits(self):
        for invalid in (1,-1,10081):
            with self.assertRaises(ValueError):self.s.save_agent(dict(self.a,interval=invalid))
        self.s.save_agent(dict(self.a,interval=5))
        for _ in range(48):
            jid=self.s.enqueue(self.a['id'],'Scheduled','scheduled');self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(jid,))
        self.s.db.execute('UPDATE agents SET next_run=0 WHERE id=?',(self.a['id'],));self.s.db.commit();self.s.schedule();self.assertEqual(len(self.s.snapshot(self.pid)['jobs']),48)
    def test_import_is_copy_and_size_limited(self):
        import base64
        self.request('import_file',name='notes.md',data=base64.b64encode('Tartalom'.encode()).decode());self.assertEqual(self.s.safe_path(self.pid,'inputs/notes.md').read_text(),'Tartalom')
        with self.assertRaises(ValueError):self.request('import_file',name='notes.md',data=base64.b64encode(b'duplicate').decode())
    def test_workflow_prompt_input_validation(self):
        graph={'3':{'class_type':'CLIPTextEncode','inputs':{'text':'initial'}}}
        self.request('workflow_save',name='Helyi kép',graph=graph,prompt_node='3',prompt_field='text');self.assertEqual(len(self.s.snapshot(self.pid)['workflows']),1)
        with self.assertRaises(ValueError):self.request('workflow_save',name='Wrong',graph=graph,prompt_node='7',prompt_field='text')
        with self.assertRaises(ValueError):self.request('workflow_save',name='Canvas not API',graph={'nodes':[]},prompt_node='1')
    def test_media_without_engine_not_enqueued(self):
        graph={'3':{'class_type':'CLIPTextEncode','inputs':{'text':'initial'}}};wid=self.request('workflow_save',name='Kép',graph=graph,prompt_node='3')['id']
        with patch('bridge.local_api',side_effect=ConnectionError('offline')):
            with self.assertRaises(ConnectionError):self.request('media_generate',workflow=wid,prompt='Hegy')
        self.assertFalse(self.s.snapshot(self.pid)['jobs'])
    def test_lanes_claim_only_their_jobs(self):
        self.s.enqueue(self.a['id'],'Chat');self.s.enqueue(self.a['id'],'Pull','model_pull',payload={'model':'test:1b'})
        model=self.s.claim(('model_pull',));self.assertEqual(model['kind'],'model_pull');self.assertEqual(self.s.claim(('chat',))['kind'],'chat')
    def test_model_url_or_paths_denied(self):
        for name in ('https://evil/model','../model','/tmp/model'):
            with self.assertRaises(ValueError):self.request('model_pull',model=name)

    def test_pipeline_enqueue_is_atomic_when_capacity_exceeded(self):
        for _ in range(29):self.s.enqueue(self.a['id'],'Várakozik')
        agents=[a['id'] for a in self.s.snapshot(self.pid)['agents']]
        with self.assertRaises(ValueError):self.request('pipeline',agents=agents,prompt='Ne legyen részlegesen létrehozva')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM jobs').fetchone()[0],29)
    def test_recipe_persisted_and_due_chain_not_duplicated(self):
        agents=[a['id'] for a in self.s.snapshot(self.pid)['agents']][:2]
        rid=self.request('recipe_save',name='Napi terv',agents=agents,prompt='Tervezz',interval=5)['id']
        self.s.db.execute('UPDATE recipes SET next_run=0 WHERE id=?',(rid,));self.s.db.commit();self.s.schedule()
        self.assertEqual(len(self.s.snapshot(self.pid)['jobs']),2)
        self.s.db.execute('UPDATE recipes SET next_run=0 WHERE id=?',(rid,));self.s.db.commit();self.s.schedule()
        self.assertEqual(len(self.s.snapshot(self.pid)['jobs']),2)
        self.assertEqual(self.s.snapshot(self.pid)['recipes'][0]['name'],'Napi terv')
    def test_recipe_cross_project_agent_rejected(self):
        pid=self.s.create_project('Másik');other=self.s.snapshot(pid)['agents'][0]['id']
        with self.assertRaises(ValueError):self.request('recipe_save',name='Hiba',agents=[self.a['id'],other],prompt='No')
    def test_media_only_replaces_selected_prompt_and_copies_output(self):
        import io
        graph={'3':{'class_type':'CLIPTextEncode','inputs':{'text':'selected'}},'4':{'class_type':'CLIPTextEncode','inputs':{'text':'negative'}}}
        wid=self.request('workflow_save',name='Kép',graph=graph,prompt_node='3')['id']
        jid=self.s.enqueue(self.a['id'],'Új prompt','media',payload={'workflow':wid});job=self.s.claim(('media',))
        history={'r1':{'status':{'status_str':'success'},'outputs':{'9':{'images':[{'filename':'generated.png','type':'output','subfolder':''}]}}}}
        with patch('studio.local_api',side_effect=[{'prompt_id':'r1'},history]) as api,patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(b'local-test-image')
            result=self.s.run_media(job)
            request=api.call_args_list[0].args[2]['prompt'];self.assertEqual(request['3']['inputs']['text'],'Új prompt');self.assertEqual(request['4']['inputs']['text'],'negative')
        artifacts=self.s.snapshot(self.pid)['artifacts'];self.assertEqual(len(artifacts),1);self.assertEqual(Path(artifacts[0]['path']).read_bytes(),b'local-test-image')
    def test_project_rename_keeps_identity_and_agents(self):
        self.request('project_save',name='Új név',description='Leírás');self.assertEqual(self.s.project(self.pid)['name'],'Új név');self.assertEqual(len(self.s.snapshot(self.pid)['agents']),3)

if __name__=='__main__':unittest.main()
