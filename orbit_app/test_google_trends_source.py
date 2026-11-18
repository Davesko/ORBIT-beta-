import unittest,tempfile,time,json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from google_trends_source import seeds
class TrendsTests(unittest.TestCase):
 def test_cache_topic_filter_and_age(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'trends.json';now=time.time()
   path.write_text(json.dumps(dict(collected_at=now,items=[dict(topic='Fortnite update',news_titles=[],published_at=now,google_search_traffic=1000),dict(topic='Football',news_titles=[],published_at=now,google_search_traffic=9000),dict(topic='Fortnite old',news_titles=[],published_at=now-90000)])))
   s=SimpleNamespace(safe_path=lambda *args:path)
   with patch('public_web.fetch',side_effect=AssertionError('cache should avoid network')):
    result=seeds(s,'project',dict(terms=['fortnite'],gaming=True))
   self.assertEqual([i['topic'] for i in result['items']],['Fortnite update'])

class InstructionTests(unittest.TestCase):
 def test_generic_hungarian_is_not_a_keyword_filter(self):
  from clip_farm import research_spec
  for text in ['Keress egy aktuális hírt ami alapján videót készítetek a csapattal.','https://trends.google.com/trending?geo=US google trend oldal alpaján találjon egy most felívelőben lévő témát, erre a témára készítsen egy videót.']:
   self.assertEqual(research_spec(text)['terms'],[])
 def test_specific_subject_is_retained(self):
  from clip_farm import research_spec
  self.assertEqual(research_spec('john anderson')['terms'],['john','anderson'])
