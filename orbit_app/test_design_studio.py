import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio import Studio
import design_studio,venture,venture_build

DESIGNS=dict(designs=[dict(id='Fox Camping',title='Kempingező róka',kind='apparel',prompt='a cheerful fox camping under the stars, retro badge'),
 dict(id='dino-1',title='Dínó színező',kind='coloring',prompt='a friendly dinosaur in a jungle'),
 dict(id='dino-1',title='duplikátum',kind='coloring',prompt='a second dinosaur, same id'),
 dict(id='mouse',title='Egér',kind='apparel',prompt='Mickey Mouse waving at the crowd'),
 dict(id='short',kind='art',prompt='tiny')])

class DesignStudioTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
  venture.configure(self.s,dict(enabled=True));self.product=self.s.safe_path(venture.PID,'workspace/product-abc');self.product.mkdir(parents=True)
  (self.product/'designs.json').write_text(json.dumps(DESIGNS))
 def fake_flux(self,s,prompt,w,h,seed,output):
  self.prompts.append(prompt);Path(output).write_bytes(b'raw')
 def fake_post(self,s,args):
  if args[0]=='book':Path(args[1]).write_bytes(b'%PDF')
  else:Path(args[2]).write_bytes(b'png');Path(args[3]).write_bytes(b'jpg')
  return subprocess.CompletedProcess(args,0,'','')
 def test_designs_are_rendered_one_by_one_into_print_files(self):
  # The owner asked for t-shirt graphics and colouring pages (1 Nov); ORBIT draws them with its local model.
  spec=design_studio.spec(self.product)
  self.assertEqual([(d['id'],d['kind']) for d in spec],[('fox-camping','apparel'),('dino-1','coloring'),('mouse','apparel')],'cleaned ids, no duplicate, no too-short prompt')
  self.prompts=[]
  with patch('design_studio.flux',side_effect=self.fake_flux),patch('design_studio.post',side_effect=self.fake_post):
   for _ in range(3):design_studio.render(self.s,self.product,design_studio.pending(self.product)[0])
  st=design_studio.state(self.product)
  self.assertTrue(st['fox-camping']['done']);self.assertTrue(st['dino-1']['done'])
  self.assertFalse(st['mouse']['done']);self.assertIn('Védett márka',st['mouse']['error'])
  self.assertEqual(len(self.prompts),2,'a protected character is never rendered');self.assertIn('plain pure white background',self.prompts[0]);self.assertIn('colouring book page',self.prompts[1])
  self.assertEqual(design_studio.pending(self.product),[],'done, and the refused one is not retried')
  self.assertTrue((self.product/'designs'/'coloring-book.pdf').is_file(),'all colouring pages are bound into a PDF')
  self.assertFalse(any(p.name.endswith('.raw.png') for p in (self.product/'designs').iterdir()))
  sm=design_studio.summary(self.s,self.product)
  self.assertEqual((sm['done'],sm['total'],sm['failed'],sm['book']),(2,3,1,True));self.assertTrue(sm['items'][0]['artifact'],'a rendered design is a creation the app can show')
  # A changed description is rendered again.
  d=json.loads((self.product/'designs.json').read_text());d['designs'][0]['prompt']='a fox fishing at a lake, retro badge';(self.product/'designs.json').write_text(json.dumps(d))
  self.assertEqual([x['id'] for x in design_studio.pending(self.product)],['fox-camping'])
 def test_a_failed_render_is_retried_once_then_shown(self):
  def broken(*a,**k):raise ValueError('A képgenerálás nem sikerült: out of memory')
  with patch('design_studio.flux',side_effect=broken):
   e=design_studio.render(self.s,self.product,design_studio.spec(self.product)[0])
   self.assertFalse(e['done']);self.assertIn('out of memory',e['error'])
   self.assertIn('fox-camping',[x['id'] for x in design_studio.pending(self.product)])
   design_studio.render(self.s,self.product,design_studio.spec(self.product)[0])
  self.assertNotIn('fox-camping',[x['id'] for x in design_studio.pending(self.product)],'two tries, then it waits for a new description')
 def test_rendering_waits_while_the_model_is_in_use(self):
  aid=self.s.rows("SELECT id FROM agents WHERE project='universe' LIMIT 1")[0]['id']
  jid=self.s.enqueue(aid,'build','mission_agent');self.s.db.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,));self.s.db.commit()
  with patch('design_studio.render') as render:
   self.assertIsNone(design_studio.work(self.s));render.assert_not_called()
   self.s.db.execute("UPDATE jobs SET status='done' WHERE id=?",(jid,));self.s.db.commit()
   design_studio.work(self.s);self.assertEqual(render.call_args[0][2]['id'],'fox-camping')

 def test_a_digital_product_is_ready_when_every_design_has_its_file_and_listing(self):
  plan=dict(name='Dínós színezőfüzet',business_type='digital',problem='p',buyer='szülők',offer='Nyomtatható dínós színezők PDF-ben az Etsy-n',revenue_model='letöltés',costs='c',hypothesis='h',validation='v',progress='p',next_action='n',decision='continue',evidence=[],automation_level=95,human_steps=[],files=[dict(name='README.md',content='terv')])
  with patch('venture.idea_scores',return_value={}):iid=venture.save_result(self.s,venture.PID,'r1',plan)['idea_id']
  venture_build.choose(self.s,iid);f=venture_build.active(self.s);self.assertEqual(f['type'],'digital')
  product=self.s.safe_path(venture.PID,venture_build.folder(f));product.mkdir(parents=True,exist_ok=True)
  (product/'designs.json').write_text(json.dumps(dict(designs=[dict(id='dino',title='Dínó',kind='coloring',prompt='a friendly dinosaur in a jungle')])))
  mid=venture_build.mission_id(self.s)
  v=venture_build.view(self.s,mid,f);self.assertFalse(v['ready']);self.assertEqual(v['designs']['total'],1)
  self.prompts=[]
  with patch('design_studio.flux',side_effect=self.fake_flux),patch('design_studio.post',side_effect=self.fake_post):design_studio.render(self.s,product,design_studio.spec(product)[0])
  self.assertFalse(venture_build.view(self.s,mid,f)['ready'],'a design without its listing is not for sale yet')
  (product/'listings.json').write_text(json.dumps(dict(listings=[dict(id='dino',marketplace='Etsy',title='Dínós színező')])))
  v=venture_build.view(self.s,mid,f);self.assertTrue(v['ready'])
  self.assertTrue(v['owner_actions'][0]['title'].startswith('Feltöltés a piacterekre'),'uploading is the owner\'s step; ORBIT publishes nothing')
class PrintFileTests(unittest.TestCase):
 def test_print_ready_files(self):
  try:from PIL import Image,ImageDraw
  except ImportError:self.skipTest('Pillow missing')
  import design_post
  img=Image.new('RGB',(400,500),'white');ImageDraw.Draw(img).ellipse((100,100,300,300),fill=(200,40,40),outline='black',width=6)
  shirt=design_post.apparel(img)
  self.assertEqual(shirt.mode,'RGBA');self.assertEqual(max(shirt.size),4096,'print-on-demand size')
  self.assertEqual(shirt.getpixel((5,5))[3],0,'white became transparent');self.assertEqual(shirt.getpixel((shirt.width//2,shirt.height//2))[3],255)
  page=design_post.coloring(img)
  self.assertEqual(page.size,design_post.A4);self.assertEqual(set(page.getdata())<={0,255},True,'pure black lines on white')
  with tempfile.TemporaryDirectory() as d:
   pages=[]
   for i in range(2):p=Path(d,str(i)+'.png');page.save(p);pages.append(str(p))
   design_post.main(['book',str(Path(d,'book.pdf'))]+pages)
   self.assertTrue(Path(d,'book.pdf').read_bytes().startswith(b'%PDF'))

class DigitalIdeaTests(unittest.TestCase):
 def test_creative_products_are_scouted_and_built_as_digital_products(self):
  self.assertEqual(venture_build.SECTORS[0][0],'Ruhagrafika (print-on-demand)');self.assertEqual(venture_build.SECTORS[2][0],'Gyerek színezők és nyomtathatók')
  self.assertEqual(venture_build.classify(dict(offer='Gyerek színezőlapok PDF-ben az Etsy-n',automation_level=95)),'digital')
  # The owner's direction keeps scouting in the creative sectors; without it every sector takes its turn.
  asked=[venture_build.sector(c,'Find print-on-demand t-shirt graphics and colouring pages')[0] for c in range(0,40,3)]
  self.assertEqual(set(asked),{'Ruhagrafika (print-on-demand)','Gyerek színezők és nyomtathatók','Matricák, falikép, poszter','Digitális sablonok és letölthetők'})
  self.assertEqual(len({venture_build.sector(c)[0] for c in range(0,48,3)}),16)
  self.assertEqual([m[0] for m in venture_build.ROADMAPS['digital']],['niche','designs','listings','pricing','promo','launch'])
  # Uploading to a marketplace is the owner's publishing step, not human work in delivery.
  self.assertTrue(venture.automated(dict(name='Kempingező póló-grafikák',offer='POD grafikák a Redbubble-ön',revenue_model='jutalék',automation_level=95,human_steps=['A tulajdonos feltölti a grafikákat a Redbubble-re'])))

if __name__=='__main__':unittest.main()
