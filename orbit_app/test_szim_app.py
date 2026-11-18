import json
import os
import tempfile
import unittest
from pathlib import Path

import szim_app

RUNTIME = Path.home() / 'Library/Application Support/Orbit/media-runtime/bin/python3'


class FakeStudio:
    def __init__(self, root):
        self.root = Path(root)


@unittest.skipUnless(RUNTIME.is_file(), 'media runtime missing')
class SzimAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = FakeStudio(self.tmp.name)
        self.s.root.joinpath('media-runtime').symlink_to(RUNTIME.parent.parent)
        (self.s.root / 'projects' / 'p1' / 'simulations').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_settings_are_validated_and_saved(self):
        szim_app.save_settings(self.s, 'p1', {'palettes': ['neon', 'nincs-ilyen'], 'seconds_min': 20, 'seconds_max': 30, 'recipes': {'szokes': False}})
        cfg = szim_app.settings(self.s, 'p1')
        self.assertEqual(cfg['palettes'], ['neon'])
        self.assertEqual((cfg['seconds_min'], cfg['seconds_max']), (20, 30))
        self.assertFalse(cfg['recipes']['szokes'])

    def test_all_types_cannot_be_switched_off(self):
        ids = [r['azon'] for r in szim_app.catalog(self.s)['recipes']]
        with self.assertRaises(ValueError):
            szim_app.save_settings(self.s, 'p1', {'recipes': {i: False for i in ids}})

    def test_length_range_must_make_sense(self):
        with self.assertRaises(ValueError):
            szim_app.save_settings(self.s, 'p1', {'seconds_min': 40, 'seconds_max': 20})

    def test_rating_is_stored_in_the_record(self):
        path = self.s.root / 'projects' / 'p1' / 'simulations' / 'v1.json'
        path.write_text(json.dumps({'szim': {'spec': {}}, 'artifact': 'a1'}))
        szim_app.rate(self.s, 'p1', {'id': 'v1', 'state': 'elvetve', 'note': 'unalmas'})
        rec = json.loads(path.read_text())
        self.assertEqual((rec['allapot'], rec['megjegyzes']), ('elvetve', 'unalmas'))
        with self.assertRaises(ValueError):
            szim_app.rate(self.s, 'p1', {'id': '../x', 'state': 'elvetve'})


if __name__ == '__main__':
    unittest.main()
