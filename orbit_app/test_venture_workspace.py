import json
import tempfile
import unittest
from pathlib import Path

import chat_attachment
import commander
import project_apps
import venture
import venture_build
import workspace_app
from bridge import dispatch
from studio import Studio


class WorkshopFlowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.s = Studio(Path(directory.name))
        self.addCleanup(self.s.db.close)

    def test_chat_steers_next_project_and_custom_type(self):
        prompt = 'A következő autopilóta projekt foglalkozzon DaVinci Resolve presetek fejlesztésével.'
        job = commander.enqueue(self.s, 'universe', prompt, global_mode=True)
        result = commander.run(self.s, dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()))
        self.assertIn('DaVinci Resolve', result)
        saved = venture_build.read(self.s)
        self.assertEqual(saved['next_direction'], 'DaVinci Resolve presetek fejlesztésével.')
        self.assertEqual(venture_build.plan_cycle(self.s, 2), 'explore')
        self.assertEqual(venture_build.classify(dict(name='DaVinci Resolve preset', business_type='saas')), 'toolkit')
        self.assertIsNone(venture.chat_steering(self.s, 'A következő autopilóta projekt foglalkozzon a levelekkel és utána írj összegzést.'))

    def test_import_keeps_workspace_edits_and_project_direction(self):
        idea = 'aabbccd1'
        self.s.create_project('Üzleti labor', '', 'general', venture.PID)
        result = self.s.safe_path(venture.PID, 'workspace/ventures/seed/result.json')
        result.parent.mkdir(parents=True)
        result.write_text(json.dumps(dict(idea_id=idea,name='Preset műhely',offer='Reusable presets')))
        source = self.s.safe_path(venture.PID, 'workspace/product-'+idea+'/test.setting')
        source.parent.mkdir()
        source.write_text('original')
        venture.steer(self.s, idea, 'Create two native variants')
        self.assertEqual(venture.direction_for(self.s, idea),'Create two native variants')
        pid = project_apps.import_venture(self.s,idea)['project']
        copy = self.s.safe_path(pid, 'workspace/product/test.setting')
        copy.write_text('edited')
        self.assertTrue(project_apps.import_venture(self.s,idea)['existing'])
        self.assertEqual(copy.read_text(),'edited')
        self.assertEqual(source.read_text(),'original')
        self.assertIn('test.setting',[x['name'] for x in project_apps.workspace(self.s,pid)['files']])

    def test_handoff_keeps_previous_work_and_excludes_other_ideas(self):
        pid=venture.PID
        self.s.create_project('Autopilóta', '', 'general', pid)
        root=self.s.safe_path(pid,'workspace/ventures')
        for idea,run,name in [('aabbccdd','first','Próba'),('ddeeffaa','other','Másik')]:
            directory=root/run
            directory.mkdir(parents=True)
            (directory/'result.json').write_text(json.dumps(dict(idea_id=idea,name=name,offer='Terv')))
            (directory/'research.md').write_text(name)
        copied=project_apps.import_venture(self.s,'aabbccdd')['project']
        archive=self.s.safe_path(copied,'workspace/autopilot/revisions')
        self.assertEqual((archive/'first/research.md').read_text(),'Próba')
        self.assertFalse((archive/'other').exists())
        edited=archive/'first/research.md'
        edited.write_text('Helyi jegyzet')
        (root/'first'/'new.md').write_text('Új adat')
        result=project_apps.import_venture(self.s,'aabbccdd')
        self.assertEqual(result['copied'],1)
        self.assertEqual(edited.read_text(),'Helyi jegyzet')
        self.assertEqual((archive/'first/new.md').read_text(),'Új adat')

    def test_attachment_local_scope_and_reference_content(self):
        src = self.s.root/'notes.txt'
        src.write_text('Project input sample',encoding='utf-8')
        file = chat_attachment.import_file(self.s,'universe',src)
        job = commander.enqueue(self.s,'universe','Foglald össze',attachment=file['token'])
        payload = json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(job,)).fetchone()[0])
        self.assertIs(payload['local_only'],True)
        self.assertIn('Project input sample',chat_attachment.note(self.s,dict(project='universe',id=job),file['token']))
        other = self.s.create_project('Másik projekt')
        with self.assertRaises(ValueError):
            chat_attachment.lookup(self.s,other,file['token'])


    def test_runnable_app_bundles_project_assets_and_keeps_project_data_isolated(self):
        self.s.safe_path('universe','workspace/product').mkdir(parents=True)
        self.s.safe_path('universe',workspace_app.IMPORTED).write_text('<h1>Imported</h1>')
        self.assertTrue(project_apps.workspace(self.s,'universe')['app']['imported'])
        entry=self.s.safe_path('universe',workspace_app.ENTRY)
        entry.parent.mkdir()
        entry.write_text('<link rel="stylesheet" href="ui.css"><script src="ui.js"></script><script src="../private.js"></script>')
        (entry.parent/'ui.js').write_text('document.title="Counter"')
        (entry.parent/'ui.css').write_text('body{color:red}')
        (entry.parent.parent/'private.js').write_text('Secret data')
        view=project_apps.workspace(self.s,'universe')['app']
        self.assertFalse(view['imported'])
        rendered=dispatch(dict(action='artifact',project='universe',id=view['id']),self.s)
        page=Path(rendered['path']).read_text()
        self.assertIn('data:text/css;base64,',page)
        self.assertRegex(page,r'data:(?:text|application)/javascript;base64,')
        self.assertNotIn('Secret data',page)
        other=self.s.create_project('Másik projekt')
        with self.assertRaises(ValueError):
            dispatch(dict(action='artifact',project=other,id=view['id']),self.s)
        workspace_app.data(self.s,'universe',{'value':{'count':5}})
        self.assertEqual(workspace_app.data(self.s,'universe',{}),{'count':5})
        self.assertIsNone(workspace_app.data(self.s,other,{}))
        job=commander.enqueue(self.s,other,'Készíts projektalkalmazást',workspace=True)
        payload=json.loads(self.s.db.execute('SELECT payload FROM jobs WHERE id=?',(job,)).fetchone()[0])
        self.assertTrue(payload['local_only'])
        self.assertEqual(payload['route']['task'],'code')


    def test_custom_api_contract_is_used_before_imported_api(self):
        imported=self.s.safe_path('universe','workspace/product')
        custom=self.s.safe_path('universe','workspace/app')
        for folder,endpoint in ((imported,'/old'),(custom,'/current')):
            folder.mkdir(parents=True)
            (folder/'server.py').write_text('# sample server')
            (folder/'smoke.json').write_text(json.dumps({'requests':[{'path':endpoint}]}))
        root,examples=project_apps.workspace_api_root(self.s,'universe')
        self.assertEqual(root,custom)
        self.assertEqual(examples[0]['path'],'/current')


    def test_manual_api_calls_are_saved_as_openable_project_artifacts(self):
        from unittest.mock import patch
        response=dict(status=200,body='{"ok":true}')
        with patch('product_check.try_api',return_value=response):
            dispatch(dict(action='project_app',project='universe',op='workspace_api',
                          args=dict(index=0,body='{}',record=True)),self.s)
            dispatch(dict(action='project_app',project='universe',op='workspace_api',
                          args=dict(index=0,body='{}')),self.s)
        saved=[f for f in project_apps.workspace(self.s,'universe')['files'] if f['category']=='api']
        self.assertEqual(len(saved),1)
        content=json.loads(self.s.safe_path('universe',saved[0]['path']).read_text())
        self.assertEqual(content['response'],response)


    def test_named_project_gallery_creates_an_application_not_an_agent(self):
        project=self.s.create_project('TermékC – Ruhagrafikák',kind='venture')
        count=len(self.s.rows('SELECT id FROM agents WHERE project=?',(project,)))
        prompt='Építs egy egyszerű projekt alkalmazást a TermékC projekthez ahol látom az elkészült grafikákat'
        job=commander.enqueue(self.s,'universe',prompt,global_mode=True)
        commander.run(self.s,dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()))
        approved=self.s.rows("SELECT * FROM jobs WHERE kind IN ('command_apply','control_apply')")[0]
        commander.apply(self.s,approved)
        self.assertIn('Elkészült grafikák',self.s.safe_path(project,workspace_app.ENTRY).read_text())
        self.assertEqual(len(self.s.rows('SELECT id FROM agents WHERE project=?',(project,))),count)
