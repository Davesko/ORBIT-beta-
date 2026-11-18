import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
from bridge import dispatch
import connections,model_finder as mf

MAC=dict(chip='Apple M4',ram_gb=32,usable_gb=26.0,bandwidth=120,disk_free_gb=100.0,disk='Belső lemez',needs_disk=False)
SMALL=dict(MAC,ram_gb=8,usable_gb=4.8,bandwidth=68)
GB=1024**3
TREE=[dict(path='model-Q4_K_M.gguf',size=5*GB),dict(path='model-Q8_0.gguf',size=9*GB),dict(path='model-draft-Q4_0.gguf',size=GB),dict(path='mmproj-model-F16.gguf',size=GB),dict(path='README.md',size=1),dict(path='big/model-Q6_K-00001-of-00002.gguf',size=5*GB),dict(path='big/model-Q6_K-00002-of-00002.gguf',size=5*GB)]

class Case(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);self.s=Studio(self.root);self.addCleanup(self.s.db.close)
  for p in (patch('model_finder.machine',return_value=MAC),patch('model_hub.ROOT',self.root),patch('model_hub.models',return_value=[]),patch('model_hub.inventory',return_value=([],[dict(port=11434,available=True)]))):
   p.start();self.addCleanup(p.stop)
 def op(self,op,**args):return dispatch(dict(action='project_app',project='universe',op=op,args=args),self.s)['result']

class FitTests(Case):
 def test_the_fit_follows_this_machines_memory(self):
  # The owner (3 Nov): the finder checks what runs well on the user's machine.
  self.assertEqual([mf.fit(g*GB,MAC)['level'] for g in (5,14,20,30)],['fast','good','tight','no'])
  self.assertEqual(mf.fit(5*GB,SMALL)['level'],'no','the same model does not run on a smaller Mac')
  self.assertEqual(mf.fit(6*GB,MAC)['speed'],20);self.assertIsNone(mf.fit(30*GB,MAC)['speed'])
  self.assertIsNone(mf.fit(5*GB,dict(MAC,bandwidth=None))['speed'],'no number is invented for an unknown chip')
 def test_a_real_machine_is_read(self):
  patch.stopall();m=mf.machine();self.assertGreater(m['ram_gb'],0);self.assertGreater(m['usable_gb'],0);self.assertIn('disk_free_gb',m)
 def test_the_recommended_size_runs_well_and_odd_builds_are_ignored(self):
  with patch('model_finder.get',return_value=TREE):v=mf.variants('bartowski/Model-GGUF')
  self.assertEqual({x['quant']:x['fit']['size_gb'] for x in v['variants']},{'Q4_K_M':5.0,'Q8_0':9.0,'Q6_K':10.0},'split files add up; draft and vision files are not models to chat with')
  self.assertEqual(v['best'],'Q4_K_M');self.assertEqual(v['variants'][0]['name'],'hf.co/bartowski/Model-GGUF:Q4_K_M')
  with patch('model_finder.get',return_value=TREE),patch('model_finder.machine',return_value=dict(MAC,usable_gb=2)):self.assertIsNone(mf.variants('a/b')['best'],'nothing fits, nothing is recommended')
  with self.assertRaises(ValueError):mf.variants('../../etc')

class SearchTests(Case):
 def test_video_search_filters_the_downloadable_catalog(self):
  with patch('model_hub.config',return_value={}),patch('model_finder.get') as get:
   all_video=self.op('finder_search',category='video')['items']
   self.assertEqual(len(all_video),7)
   self.assertEqual([m['id'] for m in self.op('finder_search',category='video',query='Wan 2.2')['items']],['wan22'])
   from_image=self.op('finder_search',category='video',query='kepbol')['items']
   self.assertEqual({m['id'] for m in from_image},{'wan21-i2v','wan22','wan21-camera','svd-xt'})
   self.assertTrue(all(m['path'] and m['download_gb']>0 and not m['ready'] for m in all_video))
   self.assertEqual(self.op('finder_search',category='video',query='sdxl')['items'],[])
   get.assert_not_called()
 def test_diffusion_is_not_an_ollama_chat_candidate(self):
  rows=[dict(id='a/Qwen-Image-2.1-GGUF'),dict(id='a/new-generator',pipeline_tag='text-to-video'),dict(id='a/new-picture',tags=['text-to-image']),dict(id='a/Qwen-VL-GGUF',pipeline_tag='image-text-to-text')]
  with patch('model_finder.get',return_value=rows):self.assertEqual([r['repo'] for r in mf.search()],['a/Qwen-VL-GGUF'])
 def test_gated_and_non_chat_models_are_left_out(self):
  rows=[dict(id='a/good-GGUF',downloads=5),dict(id='a/gated-GGUF',gated='auto'),dict(id='a/nomic-embed-GGUF'),dict(id='a/private-GGUF',private=True)]
  with patch('model_finder.get',return_value=rows) as get:found=mf.search('llama')
  self.assertEqual([r['repo'] for r in found],['a/good-GGUF']);self.assertEqual(get.call_args.args[1]['search'],'llama');self.assertEqual(get.call_args.args[1]['filter'],'gguf')
 def test_recommendations_fit_are_cached_and_family_friendly(self):
  calls=[]
  def fake(path,params=None,timeout=15):
   calls.append(path)
   if path=='models':return [dict(id=params['author']+'/Llama-GGUF',downloads=9),dict(id=params['author']+'/Qwen-Uncensored-GGUF',downloads=99),dict(id=params['author']+'/Huge-GGUF',downloads=8)]
   return [dict(path='Huge-Q4_K_M.gguf',size=40*GB)] if 'Huge' in path else [dict(path='Llama-Q4_K_M.gguf',size=5*GB)]
  with patch('model_finder.get',side_effect=fake):
   items=mf.recommend(now=1000);self.assertEqual(len(items),1,'one family once; too big and uncensored ones stay out')
   self.assertTrue(items[0]['repo'].endswith('/Llama-GGUF'));n=len(calls);self.assertEqual(mf.recommend(now=1100),items);self.assertEqual(len(calls),n,'asked once in a while');mf.recommend(now=1000+mf.CACHE_HOURS*3600+1);self.assertGreater(len(calls),n)
 def test_a_test_never_reaches_the_network(self):
  with self.assertRaisesRegex(ValueError,'Tesztfutás'):mf.get('models')

class DownloadTests(Case):
 def test_a_download_is_a_normal_model_job(self):
  r=self.op('finder_pull',name='hf.co/a/b-GGUF:Q4_K_M',size=5*GB);row=dict(self.s.db.execute('SELECT kind,payload,prompt FROM jobs WHERE id=?',(r['job'],)).fetchone())
  self.assertEqual((row['kind'],json.loads(row['payload'])['model']),('model_pull','hf.co/a/b-GGUF:Q4_K_M'))
  with self.assertRaisesRegex(ValueError,'folyamatban'):self.op('finder_pull',name='hf.co/a/c-GGUF:Q4_K_M')
  st=self.op('finder_status');self.assertEqual((st['pulling']['name'],st['pulling']['percent']),('hf.co/a/b-GGUF:Q4_K_M',None));self.assertTrue(st['ollama'])
  self.s.db.execute("INSERT OR REPLACE INTO job_runtime(job,phase,label,updated,input) VALUES(?,'x','Letöltés · 42%',1,'')",(r['job'],));self.s.db.commit();self.assertEqual(self.op('finder_status')['pulling']['percent'],42)
 def test_not_enough_disk_and_odd_names_are_refused(self):
  with self.assertRaisesRegex(ValueError,'Nincs elég hely'):self.op('finder_pull',name='hf.co/a/b:Q4',size=200*GB)
  for bad in ('http://evil/x','hf.co/a/b','../x','hf.co/a/b:Q4;rm -rf','llama3'):
   with self.assertRaises(ValueError):self.op('finder_pull',name=bad)
  with patch('model_finder.machine',return_value=dict(MAC,needs_disk=True)):
   with self.assertRaisesRegex(ValueError,'modelltár'):self.op('finder_pull',name='hf.co/a/b:Q4')
 def test_an_installed_model_appears_with_its_fit_and_measured_speed(self):
  with patch('model_hub.models',return_value=[dict(name='qwen:9b',size=5*GB,storage='SSD'),dict(name='nomic-embed-text',size=GB,storage='SSD')]):
   agent=self.s.db.execute("SELECT id FROM agents WHERE project='universe' LIMIT 1").fetchone()[0];job=self.op('finder_benchmark',name='qwen:9b')['job'];row=dict(self.s.db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone())
   self.assertTrue(json.loads(row['payload'])['local_only']);self.assertTrue(agent)
   with patch('studio.local_api',return_value=dict(eval_count=100,eval_duration=4*10**9)):self.assertIn('25.0',mf.benchmark(self.s,row))
   got=self.op('finder_status')['installed'];self.assertEqual([m['name'] for m in got],['qwen:9b'],'an embedding model is not offered for chat');self.assertEqual(got[0]['measured']['tokens_per_second'],25.0);self.assertEqual(got[0]['fit']['level'],'fast')
  with self.assertRaisesRegex(ValueError,'nincs a gépen'):self.op('finder_benchmark',name='nincs:1')
 def test_only_known_help_pages_open(self):
  with patch('model_finder.subprocess.run') as run:
   self.op('finder_open',target='ollama')
   with self.assertRaises(ValueError):self.op('finder_open',target='https://evil.example')
  self.assertEqual(run.call_count,1)

class DeepSeekTests(unittest.TestCase):
 def test_deepseek_is_an_optional_cloud_choice_that_starts_off(self):
  # The owner (3 Nov) asked whether deepseek-v4-flash is worth adding: 167 GB of weights do not run on a Mac; the API is cheap.
  self.assertEqual(connections.PROVIDERS['deepseek']['model'],'deepseek-flash');self.assertEqual(connections.PROVIDERS['deepseek']['base'],'https://api.deepseek.com/')
  with tempfile.TemporaryDirectory() as tmp:
   self.assertFalse(connections.allowed('deepseek',Path(tmp)));self.assertEqual(connections.settings(Path(tmp))['mode'],'local')

if __name__=='__main__':unittest.main()
