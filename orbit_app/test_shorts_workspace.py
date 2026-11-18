import tempfile
import unittest
from pathlib import Path
from studio import Studio
from configure_shorts import configure,PROJECT,STATUS

class ShortsWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.s=Studio(Path(self.temp.name));self.s.create_project('Youtube shorts','Eredeti részletes feladatleírás.',pid=PROJECT)
    def tearDown(self):self.s.db.close();self.temp.cleanup()
    def test_configures_six_rooms_eight_roles_and_seven_edges(self):
        result=configure(self.s);self.assertEqual(len(result['rooms']),6);self.assertEqual(len(result['agents']),8);self.assertEqual(result['connections'],7)
        snapshot=self.s.snapshot(PROJECT);self.assertEqual(sum(a['room']=='shorts-discovery' for a in snapshot['agents']),2);self.assertEqual(sum(a['room']=='shorts-publish' for a in snapshot['agents']),2)
        self.assertEqual(snapshot['jobs'],[]);self.assertTrue(all(a['interval']==0 for a in snapshot['agents']))
    def test_idempotent_and_preserves_other_projects_and_original_agents(self):
        other=self.s.snapshot('universe');before={a['name']:a['id'] for a in self.s.snapshot(PROJECT)['agents']};configure(self.s);configure(self.s)
        after=self.s.snapshot(PROJECT);self.assertEqual(len(after['artifacts']),6);self.assertEqual({k:v for k,v in self.s.snapshot('universe').items() if k!='projects'},{k:v for k,v in other.items() if k!='projects'})
        for a in after['agents']:
            if a['name'] in before:self.assertEqual(a['id'],before[a['name']])
        original=self.s.safe_path(PROJECT,'workspace/ORIGINAL-BRIEF.md').read_text();self.assertIn('Eredeti részletes',original)
    def test_english_content_hungarian_operator_and_honest_capabilities(self):
        configure(self.s);snapshot=self.s.snapshot(PROJECT)
        self.assertTrue(all('angol' in a['prompt'] and 'Nincs közvetlen streamfigyelő' in a['prompt'] for a in snapshot['agents']))
        self.assertFalse(STATUS['youtube_upload_connected']);self.assertFalse(STATUS['video_render_connected'])
        self.assertEqual(STATUS['content_language'],'en')
    def test_active_work_is_not_reconfigured(self):
        a=self.s.snapshot(PROJECT)['agents'][0];self.s.enqueue(a['id'],'Feladat');before=self.s.snapshot(PROJECT)
        with self.assertRaises(ValueError):configure(self.s)
        self.assertEqual(self.s.snapshot(PROJECT),before)
    def test_manual_config_file_is_not_overwritten(self):
        configure(self.s);p=self.s.safe_path(PROJECT,'workspace/sources.json');p.write_text('Saját változat')
        with self.assertRaises(ValueError):configure(self.s)
        self.assertEqual(p.read_text(),'Saját változat')

if __name__=='__main__':unittest.main()
