"""Owner, 13 Nov: not the same lofi under every episode, but trending music, and only while it is current."""
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import music_trends as mt

PAGE = '''<p>Last updated: 2026/11/11</p><table><tr><th>Pos</th><th>P+</th><th>Artist and Title</th><th>Days</th></tr>
<tr><td>1</td><td>=</td><td><a>KAROL G</a> - <a>BbY WOW</a></td><td>92</td></tr>
<tr><td>19</td><td>+24</td><td>Coldplay - Yellow</td><td>2144</td></tr>
<tr><td>30</td><td>NEW</td><td>Some Artist - Brand New</td><td>1</td></tr>
<tr><td>40</td><td>+2</td><td>Slow Band - Barely</td><td>50</td></tr>
</table>'''
TAGS = {'Coldplay': ['alternative rock', 'pop'], 'Some Artist': ['reggaeton', 'latin'], 'KAROL G': ['reggaeton']}


class Trends(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fetch(self, now):
        with patch('music_trends._get', return_value=PAGE), patch('music_trends.artist_tags', side_effect=lambda a: TAGS.get(a, [])), patch('music_trends.time.sleep'):
            return mt.current(self.root, now)

    def test_new_and_climbing_songs_become_styles_while_the_chart_is_fresh(self):
        items = self.fetch(datetime.date(2026, 11, 13))
        self.assertEqual([i['title'] for i in items], ['Brand New', 'Yellow'])          # not the steady #1, not a +2
        self.assertIn('reggaeton', items[0]['style'])
        self.assertIn('rock', items[1]['style'])

    def test_an_old_chart_is_not_current(self):
        self.assertEqual(self.fetch(datetime.date(2026, 11, 20)), [])

    def test_the_strongest_tag_decides_the_style(self):
        self.assertIn('dreamy', mt.style_for(['indie pop', 'pop', 'electronic'])[0])
        self.assertIn('house', mt.style_for(['electro house'])[0])
        self.assertEqual(mt.style_for(['spoken word']), (None, None))

    def test_the_score_follows_the_trend_not_lofi(self):
        import story_music
        plan = dict(title='T', profile=dict(music='lofi'), music_prompt='slow melancholic lofi beat',
                    music_trend=dict(artist='A', title='B', style='modern reggaeton dembow groove', bpm=95))
        tags, bpm, key = story_music.prompt(plan)
        self.assertIn('reggaeton', tags)
        self.assertNotIn('lofi', tags.lower())
        self.assertEqual(bpm, 95)

    def test_the_upload_text_names_the_real_song_to_add_from_the_platform_library(self):
        import story_animation as sa
        copy = sa.publish_copy(dict(title='T', music_trend=dict(artist='Coldplay', title='Yellow')), dict(hook_caption='Why is it called that?'))
        self.assertIn('Coldplay – Yellow', copy['text'])
        self.assertIn('hangtárából', copy['text'])
        self.assertNotIn('TRENDHANG', sa.publish_copy(dict(title='T'), {})['text'])

    def test_nothing_personal_is_sent(self):
        self.assertNotIn('@', mt.AGENT)
        self.assertTrue(mt.CHART.startswith('https://kworb.net/'))


if __name__ == '__main__':
    unittest.main()
