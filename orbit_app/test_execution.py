import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
from render_tools import render_arguments,shifted_subtitles
from youtube import save_config,read_state

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        language=patch('language_bridge.translate_many',side_effect=lambda texts,root:list(texts));language.start();self.addCleanup(language.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Studio(Path(self.tmp.name)/'orbit');self.addCleanup(self.s.db.close)
        self.agents=[self.s.agent(r['id']) for r in self.s.rows("SELECT id FROM agents WHERE project='universe' ORDER BY rowid")]
    def graph(self):
        a,b=self.agents[:2];cid=self.s.save_connection('universe',dict(source=a['id'],target=b['id'],name='Test',mode='both',instructions='Keep evidence',task='Review'))
        run=self.s.enqueue_graph('universe',a['id'],'Test goal')
        return a,b,cid,run
    def test_handoff_only_after_completed_parent_and_actual_context(self):
        a,b,cid,run=self.graph();first=self.s.claim(('graph',));self.assertEqual(first['agent'],a['id'])
        second=self.s.rows('SELECT * FROM jobs WHERE id=?',(run['jobs'][b['id']],))[0]
        self.assertFalse(self.s.job_detail('universe',second['id'])['received'])
        with self.assertRaises(ValueError):self.s.handoff_context(second)
        self.s.finish(first,'Verified data');second=self.s.claim(('graph',));context=self.s.handoff_context(second)
        detail=self.s.job_detail('universe',second['id']);self.assertEqual(len(detail['received']),1)
        self.assertIn('Verified data',context);self.assertEqual(detail['received'][0]['connection'],cid)
        self.s.handoff_context(second);self.assertEqual(len(self.s.job_detail('universe',second['id'])['received']),1)
        with self.assertRaises(ValueError):self.s.job_detail('missing',second['id'])
    def test_model_and_tool_observations_persist_without_thoughts(self):
        a=self.agents[0];jid=self.s.enqueue(a['id'],'List files')
        replies=[{'message':{'tool_calls':[{'function':{'name':'project_files','arguments':{}}}]}},{'message':{'content':'Finished'}}]
        with patch('studio.local_api',side_effect=replies):self.s.run_next(('chat',))
        detail=self.s.job_detail('universe',jid)
        self.assertEqual(detail['status'],'done');self.assertEqual(detail['runtime']['input'],'List files')
        self.assertIn('tool_done',[e['kind'] for e in detail['log']]);self.assertEqual(detail['runtime']['phase'],'done')
    def test_complete_run_snapshot_and_failed_dependencies(self):
        a,b,cid,run=self.graph();first=self.s.claim(('graph',));self.s.finish(first,error='Deliberate failure');self.s.claim(('graph',))
        snapshot=self.s.snapshot('universe');jobs=snapshot['workflow_runs'][0]['jobs']
        self.assertEqual({j['status'] for j in jobs},{'failed','blocked'});self.assertEqual(snapshot['handoff_receipts'],[])
    def test_render_validation_and_subtitle_shift(self):
        path=self.s.safe_path('universe','inputs/source.mp4');path.parent.mkdir();path.write_bytes(b'test')
        args=dict(name='inputs/source.mp4',start=2,duration=3,layout='fit',subtitle='')
        self.assertEqual(render_arguments(self.s,'universe',args)['duration'],3)
        for key,value in [('start',-1),('duration',float('nan')),('duration',181),('layout','shell'),('name','/tmp/private.mp4')]:
            with self.assertRaises(ValueError):render_arguments(self.s,'universe',dict(args,**{key:value}))
        source=Path(self.tmp.name)/'in.srt';source.write_text('1\n00:00:01,000 --> 00:00:03,000\nHello\n\n2\n00:00:04,000 --> 00:00:06,000\nWorld')
        result=Path(self.tmp.name)/'out.srt';shifted_subtitles(source,2,3,result)
        self.assertIn('00:00:00,000 --> 00:00:01,000',result.read_text());self.assertIn('00:00:02,000 --> 00:00:03,000',result.read_text())
    def test_graph_does_not_reuse_unrelated_old_chat_or_test_inputs(self):
        a,b,cid,run=self.graph()
        old=self.s.enqueue(a['id'],'UNRELATED_OLD_TEST_SOURCE')
        self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(old,));self.s.db.commit()
        job=self.s.claim(('graph',))
        with patch('studio.local_api',return_value={'message':{'content':'Actual current reply'}}) as api:
            self.s.run_agent(job)
        content=json.dumps(api.call_args.args[2]['messages'])
        self.assertNotIn('UNRELATED_OLD_TEST_SOURCE',content)
        self.assertIn('Test goal',content)
    def test_required_video_blocks_text_only_success(self):
        a,b,cid,run=self.graph()
        jid=run['jobs'][b['id']]
        payload=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0]);payload['required_outputs']=['video']
        self.s.db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),jid));self.s.db.commit()
        first=self.s.claim(('graph',));self.s.finish(first,'Source complete')
        with patch('studio.local_api',return_value={'message':{'content':'Claimed finished without a real video'}}):self.s.run_next(('graph',))
        job=self.s.job_detail('universe',jid);self.assertEqual(job['status'],'failed');self.assertIn('video',job['error'])
    def test_connection_contract_applies_when_starting_at_receiver(self):
        a,b,c=self.agents
        self.s.save_connection('universe',dict(source=a['id'],target=b['id'],output_kind='video'))
        self.s.save_connection('universe',dict(source=b['id'],target=c['id']))
        run=self.s.enqueue_graph('universe',b['id'],'Render a real video')
        payload=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(run['jobs'][b['id']],)).fetchone()[0])
        self.assertEqual(payload['required_outputs'],['video'])
    def test_youtube_config_rejects_foreign_endpoints_and_no_upload_without_connection(self):
        client={'client_id':'example.apps.googleusercontent.com','client_secret':'public desktop client','auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token'}
        save_config(self.s.root,'universe',json.dumps({'installed':client}));self.assertTrue(read_state(self.s.root,'universe')['configured'])
        self.assertEqual((self.s.root/'integrations/youtube/universe/client.json').stat().st_mode&0o777,0o600)
        with self.assertRaises(ValueError):save_config(self.s.root,'universe',json.dumps({'installed':dict(client,token_uri='https://attacker.invalid/token')}))
        with self.assertRaises(ValueError):dispatch(dict(action='youtube_upload',project='universe',id='missing'),self.s)

if __name__=='__main__':unittest.main()
