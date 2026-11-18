"""Skills behave like memory: what worked once is known, the fitting ones are found by meaning and used together, and
without a search key the Mac's own browser does the research."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import assistant_skills as skills
import assistant_tools
import browser_web
from studio import Studio

BING='''<html><body><ol><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=x&amp;u=a1aHR0cHM6Ly9leGFtcGxlLm9yZy9ndWlkZQ&amp;ntb=1">The <strong>Guide</strong></a></h2><p>How it works &amp; why.</p></li>
<li class="b_algo"><h2><a href="https://docs.example.com/start">Start here</a></h2><p>Second.</p></li>
<li class="b_algo"><h2><a href="https://www.bing.com/internal">Bing itself</a></h2></li></ol></body></html>'''


class SkillGrowth(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)

    def test_a_combined_request_is_learned_once_and_found_by_meaning(self):
        actions=[dict(type='generate_image',prompt='x',save_as='/c/cafe/hero.png'),dict(type='memory_save'),dict(type='write_file',path='/c/cafe/index.html',content='SECRET BODY')]
        first=skills.learn_from_turn(self.s,'Készíts egy weboldalt a kávézómnak saját képpel',actions)
        self.assertTrue(first['new'])
        again=skills.learn_from_turn(self.s,'Készíts weboldalt a kávézómnak, saját képpel legyen',actions)
        self.assertEqual((again['id'],again['uses'],again['new']),(first['id'],2,False))
        stored=json.loads(self.s.db.execute('SELECT data FROM assistant_skills WHERE id=?',(first['id'],)).fetchone()[0])
        self.assertEqual(stored['signature'],'generate_image+write_file')
        self.assertNotIn('SECRET BODY',json.dumps(stored))
        found=[m['id'] for m in skills.select(self.s,'csinálj egy kávézós weboldalt képpel a pékségemnek')]
        self.assertIn(first['id'],found)
        self.assertIn('site-media',found)

    def test_single_step_requests_and_secrets_are_not_learned(self):
        self.assertIsNone(skills.learn_from_turn(self.s,'Készíts egy képet a kutyámról',[dict(type='generate_image')]))
        both=[dict(type='generate_image'),dict(type='write_file',path='/a/b.html')]
        self.assertIsNone(skills.learn_from_turn(self.s,'weboldal a kulcsommal sk-test_test_test_test_test1 és képpel',both))

    def test_unrelated_requests_get_no_skill(self):
        self.assertEqual(skills.select(self.s,'mennyi kettő meg kettő összesen'),[])

    def test_a_web_page_request_keeps_file_and_media_tools_in_scope(self):
        names=set(assistant_tools.catalog('csinálj egy weboldalt saját képpel')['actions'])
        self.assertTrue({'write_file','generate_image','generate_video'}<=names)
        self.assertIn('save_as',assistant_tools.ACTION_CONTRACTS['generate_image'])

    def test_browser_results_are_unwrapped_and_walls_are_not_bypassed(self):
        run=lambda command,**k:SimpleNamespace(returncode=0,stdout=BING.encode())
        self.assertEqual(browser_web.search('how it works',run=run),[dict(title='The Guide',url='https://example.org/guide',description='How it works & why.'),
                                                                    dict(title='Start here',url='https://docs.example.com/start',description='Second.')])
        wall=lambda command,**k:SimpleNamespace(returncode=0,stdout=b'<html>Please solve this CAPTCHA to continue</html>')
        self.assertEqual(browser_web.search('anything',run=wall),[])
        self.assertEqual(browser_web.read('https://example.org/x',run=wall)['text'],'')

    def test_generated_asset_lands_next_to_the_page(self):
        import commander
        made=Path(self.tmp.name)/'flux.png';made.write_bytes(b'png');target=Path(self.tmp.name)/'site/hero.png'
        self.assertEqual(commander.place_asset(str(made),dict(save_as=str(target))),str(made))
        self.assertEqual(target.read_bytes(),b'png');self.assertTrue(made.exists())

    def test_search_falls_back_to_the_own_browser_without_a_key(self):
        import research
        hit=[dict(title='T',url='https://example.org/a',description='d')]
        with patch('connections.allowed',return_value=False),patch('public_web.search',return_value=[]),patch('browser_web.search',return_value=hit):
            got=research.search('valami ritka kérdés',root=self.s.root)
        self.assertEqual((got['provider'],got['results']),('Saját böngésző (háttérben)',hit))


if __name__=='__main__':
    unittest.main()
