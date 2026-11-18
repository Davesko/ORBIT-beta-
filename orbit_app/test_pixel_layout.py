import tempfile,unittest
from pathlib import Path
from studio import Studio
from pixel_layout import migrate

class PixelLayoutTests(unittest.TestCase):
 def test_reflow_preserves_agents_links_jobs_and_is_idempotent(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder));before=s.rows('SELECT * FROM agents');connections=s.rows('SELECT * FROM connections');jid=s.enqueue(before[0]['id'],'Keep this task');migrate(s)
   self.assertEqual(before,s.rows('SELECT * FROM agents'));self.assertEqual(connections,s.rows('SELECT * FROM connections'));self.assertEqual(s.db.execute('SELECT prompt FROM jobs WHERE id=?',(jid,)).fetchone()[0],'Keep this task')
   rooms=s.rows('SELECT * FROM rooms WHERE archived=0')
   for r in rooms:self.assertTrue(s.room_available(r['project'],r['x'],r['y'],r['width'],r['height'],r['id']))
   self.assertEqual(migrate(s),[]);self.assertEqual(rooms,s.rows('SELECT * FROM rooms WHERE archived=0'));s.db.close()
 def test_customization_after_upgrade_is_not_reset(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Studio(Path(folder));migrate(s);room=s.rows('SELECT * FROM rooms WHERE project=\'universe\' LIMIT 1')[0];s.save_room('universe',dict(room,name='My room',floor='#123456'));migrate(s)
   self.assertEqual(s.room('universe',room['id'])['floor'],'#123456');self.assertEqual(s.room('universe',room['id'])['name'],'My room');s.db.close()
