import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import model_locator as ml,seed_projects as sp,services

def store(folder,names):
 for host,ns,model,tag in names:
  f=Path(folder)/'manifests'/host/ns/model/tag;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('{}')
 (Path(folder)/'blobs').mkdir(parents=True,exist_ok=True)

class LocatorTests(unittest.TestCase):
 def setUp(self):self.tmp=Path(tempfile.mkdtemp())
 def test_ollama_manifests_become_model_names(self):
  store(self.tmp,[('registry.ollama.ai','library','qwen3.5','9b'),('hf.co','unsloth','gemma-4-12b-it-GGUF','Q4_K_M')])
  self.assertEqual(ml.ollama_models(self.tmp),['hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M','qwen3.5:9b'])
  self.assertEqual(ml.ollama_models(self.tmp/'nincs'),[])
 def test_a_chosen_store_is_served_in_place(self):
  models=self.tmp/'Drive/ORBIT-Models/ollama';store(models,[('registry.ollama.ai','library','gemma4','26b')]);root=self.tmp/'root'
  with patch.object(ml,'OLLAMA_APP',self.tmp),patch.object(ml,'ssd_agent',return_value=True) as agent,patch.object(ml,'mount_of',return_value=str(self.tmp)):
   r=ml.use(None,str(self.tmp/'Drive/ORBIT-Models'),root=root)
  self.assertEqual(r['kind'],'ollama-store');self.assertEqual(r['models'],['gemma4:26b']);agent.assert_called_once()
  cfg=json.loads((root/'model-storage.json').read_text());self.assertEqual(cfg['ollama'],str(models));self.assertEqual(cfg['mount'],str(self.tmp))
 def test_gguf_files_are_offered_and_a_folder_without_models_says_so(self):
  big=self.tmp/'lm/model-q4.gguf';big.parent.mkdir(parents=True)
  with open(big,'wb') as f:f.truncate(60_000_000)
  r=ml.use(None,str(self.tmp/'lm'),root=self.tmp/'root');self.assertEqual(r['kind'],'gguf');self.assertEqual(r['files'][0]['name'],'model-q4')
  (self.tmp/'empty').mkdir()
  with self.assertRaises(ValueError):ml.use(None,str(self.tmp/'empty'),root=self.tmp/'root')
 def test_import_needs_ollama_and_writes_a_modelfile(self):
  f=self.tmp/'a.gguf';f.write_bytes(b'x')
  with patch.object(ml,'ollama_cli',return_value=None):
   with self.assertRaises(ValueError):ml.import_gguf(None,str(f),root=self.tmp/'root')
  with patch.object(ml,'ollama_cli',return_value='/bin/echo'),patch.object(ml,'running',return_value=[]),patch('subprocess.Popen') as run:
   r=ml.import_gguf(None,str(f),'Saját Modell',root=self.tmp/'root')
  self.assertEqual(r['name'],'sajat-modell');run.assert_called_once()
  self.assertIn('FROM '+str(f),(self.tmp/'root/imports'/(r['name']+'.Modelfile')).read_text())

class ServiceTests(unittest.TestCase):
 def test_the_worker_is_installed_only_from_the_installed_core_and_never_over_an_existing_one(self):
  self.assertFalse(services.installed_core(),'tests run from the source folder')
  with patch.object(services,'installed_core',return_value=False):self.assertFalse(services.ensure_worker())

class SeedTests(unittest.TestCase):
 def test_a_fresh_orbit_gets_only_the_seeded_projects_agents_and_prompts(self):
  tmp=Path(tempfile.mkdtemp());src=Studio(tmp/'src');pid=src.create_project('YouTube Shorts','x')
  aid=src.save_agent(dict(project=pid,name='KING',role='Producer',room='bridge',prompt='Lead the team.',tools=['read_file']))
  src.db.execute("INSERT INTO jobs(id,project,agent,kind,status,prompt,created) VALUES('j',?,?,'chat','done','titok',1)",(pid,aid));src.db.commit()
  f=tmp/'seed.json';f.write_text(json.dumps(sp.export(src,[pid])))
  with patch.object(sp,'SEED',f),patch.object(sp,'FORCE',True),patch('studio.TRADING',tmp/'nincs'):fresh=Studio(tmp/'fresh')
  self.assertEqual({r['name'] for r in fresh.rows('SELECT name FROM projects')},{'Saját univerzum','YouTube Shorts'})
  self.assertEqual(fresh.agent(aid)['prompt'],'Lead the team.')
  self.assertEqual(fresh.rows('SELECT * FROM jobs'),[])
  self.assertNotIn('titok',f.read_text())

if __name__=='__main__':unittest.main()
