import tempfile
import unittest
from pathlib import Path
from studio import Studio
from gallery import classify,page
from bridge import dispatch

class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Studio(Path(self.temp.name)/'orbit');self.addCleanup(self.s.db.close)
        self.base=self.s.root/'projects/universe'
    def add(self,name,kind,relative,index):
        self.s.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(str(index),'universe',name,str(self.base/relative),kind,index,'fixture'));self.s.db.commit()
    def test_project_picker_exposes_existing_project_counts_without_moving_files(self):
        other=self.s.create_project('Clip Farm test')
        result=page(self.s,other)
        listed={p['id']:p for p in result['projects']}
        self.assertIn('universe',listed);self.assertIn(other,listed)
        self.assertEqual(result['project'],other)
        self.assertEqual(result['artifacts'],[])

    def test_finished_video_folder_excludes_sources_and_sidecars(self):
        self.add('done.mp4','video','renders/done.mp4',1)
        self.add('source.mp4','video','sources/a/source.mp4',2)
        self.add('input.mp4','video','inputs/media/input.mp4',3)
        self.add('done.json','text','renders/done.json',4)
        self.add('done.srt','text','renders/done.srt',5)
        root=page(self.s,'universe');self.assertEqual(root['counts']['ready'],1);self.assertEqual(root['counts']['sources'],2);self.assertEqual(root['counts']['production'],1);self.assertEqual(root['counts']['transcripts'],1)
        result=dispatch(dict(action='gallery_list',project='universe',folder='ready'),self.s)
        self.assertEqual([a['name'] for a in result['artifacts']],['done.mp4'])
    def test_pagination_preserves_older_files_and_does_not_move_anything(self):
        for i in range(85):self.add('done-'+str(i)+'.mp4','video','renders/'+str(i)+'.mp4',i)
        first=page(self.s,'universe','ready',0);last=page(self.s,'universe','ready',80)
        self.assertEqual(first['total'],85);self.assertEqual(len(first['artifacts']),40);self.assertTrue(first['has_more']);self.assertEqual(len(last['artifacts']),5);self.assertFalse(last['has_more'])
        self.assertFalse({a['id'] for a in first['artifacts']}&{a['id'] for a in last['artifacts']})
        self.assertEqual(self.s.db.execute('SELECT path FROM artifacts WHERE id=?',('0',)).fetchone()[0],str(self.base/'renders/0.mp4'))
    def test_invalid_folder_and_cross_project_read_rejected_or_empty(self):
        self.add('done.mp4','video','renders/done.mp4',1)
        with self.assertRaises(ValueError):page(self.s,'universe','../../secret')
        with self.assertRaises(ValueError):page(self.s,'universe','ready',-1)
        pid=self.s.create_project('Other');self.assertEqual(page(self.s,pid)['counts']['ready'],0)
    def test_external_path_is_never_a_finished_project_video(self):
        self.assertEqual(classify(self.base,dict(name='private.mp4',kind='video',path='/tmp/renders/private.mp4')),'other')

if __name__=='__main__':unittest.main()
