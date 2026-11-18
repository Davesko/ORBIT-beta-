import json,tempfile,unittest
from pathlib import Path
from studio import Studio
import assistant_skills as skills,assistant_tools as tools,skill_api

WEATHER=dict(title='Időjárás',description='Current weather for coordinates.',tags=['weather','idojaras','homerseklet','forecast'],
             steps=['Geocode the city, then call forecast.'],verification=['Quote the temperature and the source.'],
             api=dict(base='https://api.example-weather.com/v1',auth=dict(kind='none'),endpoints=[
                 dict(name='forecast',path='forecast',params={'latitude':'number (required)','longitude':'number (required)','current':'comma list'},fixed={'timezone':'auto'}),
                 dict(name='city',path='city/{name}',params={})]),
             test=dict(endpoint='forecast',params={'latitude':47.5,'longitude':19.04,'current':'temperature_2m'}))
PAGES=[dict(url='https://docs.example-weather.com/',text='Weather API docs. '*40)]

class Fetch:
 def __init__(self,status=200,body=b'{"current":{"temperature_2m":7.4}}',kind='application/json'):self.status,self.body,self.kind,self.urls=status,body,kind,[]
 def __call__(self,url,headers):self.urls.append((url,headers));return self.status,self.kind,self.body

class SkillApiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.s=Studio(Path(self.tmp.name));self.addCleanup(self.s.db.close)
 def learn(self,spec=WEATHER,fetch=None,answers=None,goal='current weather for a city'):
  answers=list(answers or [spec])
  return skill_api.learn(self.s,goal,ask=lambda m:answers.pop(0) if len(answers)>1 else answers[0],fetch=fetch or Fetch(),
                         apis=[dict(name='ExWeather',url='https://example-weather.com/',description='Weather forecast',auth='none',https=True,category='Weather')],
                         fetch_html=lambda u:('<p>'+'Weather API home. '*30+'</p><a href="/docs/forecast">Docs</a>','https://example-weather.com/'),read=lambda u:PAGES[0],
                         search=lambda q:[dict(url='https://docs.example-weather.com/',title='Docs')])

 def test_learned_skill_is_tested_live_published_and_selected(self):
  out=self.learn()
  self.assertEqual(out['status'],'learned');self.assertTrue(out['test']['ok'])
  d=next(x for x in skills.listing(self.s) if x['id']==out['skill']['id'])
  self.assertEqual((d['source'],d['status']),('learned','published'))
  picked=skills.select(self.s,'milyen az idojaras ma Budapesten?')
  self.assertEqual(picked[0]['id'],d['id']);self.assertIn('skill_call',picked[0]['how'])
  self.assertEqual(self.learn()['status'],'known')  # reused, not learned twice

 def test_call_builds_declared_url_and_shrinks_response(self):
  sid=self.learn()['skill']['id']
  f=Fetch(body=json.dumps(dict(items=list(range(40)),text='x'*900)).encode())
  r=skill_api.call(self.s,sid,'forecast',dict(latitude=47.5,longitude=19.0),fetch=f)
  url=f.urls[0][0]
  self.assertTrue(url.startswith('https://api.example-weather.com/v1/forecast?'));self.assertIn('timezone=auto',url);self.assertIn('latitude=47.5',url)
  self.assertEqual(len(r['data']['items']),16);self.assertEqual(len(r['data']['text']),400)
  f2=Fetch();skill_api.call(self.s,sid,'city',dict(name='Szeged/../x'),fetch=f2)
  self.assertIn('/v1/city/Szeged%2F..%2Fx',f2.urls[0][0])
  with self.assertRaisesRegex(ValueError,'Ismeretlen paraméter'):skill_api.call(self.s,sid,'forecast',dict(evil=1),fetch=f)
  with self.assertRaisesRegex(ValueError,'Ismeretlen végpont'):skill_api.call(self.s,sid,'delete_all',{},fetch=f)

 def test_failed_test_is_repaired_once_then_kept_as_draft(self):
  bad=dict(WEATHER,api=dict(WEATHER['api'],endpoints=[dict(name='forecast',path='wrong',params={'latitude':'n','longitude':'n','current':'c'})]))
  calls=[]
  def fetch(url,headers):
   calls.append(url);return (200,'application/json',b'{"ok":1}') if '/forecast' in url else (404,'text/plain',b'not found')
  out=self.learn(fetch=fetch,answers=[bad,WEATHER])
  self.assertEqual(out['status'],'learned');self.assertEqual(len(calls),2)
  out=self.learn(fetch=lambda u,h:(500,'text/plain',b'down'),answers=[dict(WEATHER,title='Masik')],goal='another service xyz')
  self.assertEqual(out['status'],'draft_failed_test')
  self.assertEqual(skills.select(self.s,'masik'),[])

 def test_write_methods_foreign_hosts_and_http_are_refused(self):
  for api in (dict(WEATHER['api'],endpoints=[dict(name='post',method='POST',path='x')]),dict(WEATHER['api'],base='http://api.example.com/'),
              dict(WEATHER['api'],endpoints=[dict(name='x',path='https://evil.com/a')]),dict(WEATHER['api'],endpoints=[dict(name='x',path='../admin')])):
   with self.assertRaises(ValueError):skill_api.validate_api(api)

 def test_key_skill_waits_for_owner_key_and_never_leaks_it(self):
  keyed=dict(WEATHER,title='Árfolyam',tags=['exchange','arfolyam','currency'],api=dict(WEATHER['api'],base='https://api.rates.example.com/',auth=dict(kind='query',name='apikey'),key_url='https://rates.example.com/signup'))
  out=self.learn(spec=keyed,goal='exchange rates')
  self.assertEqual(out['status'],'needs_key');sid=out['skill']['id']
  self.assertEqual(skills.select(self.s,'arfolyam'),[])
  with self.assertRaisesRegex(ValueError,'API-kulcs'):skill_api.call(self.s,sid,'forecast',{},fetch=Fetch())
  f=Fetch(body=b'{"echo":"secretKEY123"}')
  import unittest.mock as m
  with m.patch.object(skill_api,'_fetch',f):r=skills.dispatch(self.s,'skill_key_save',dict(id=sid,key='secretKEY123'))
  self.assertTrue(r['published']);self.assertIn('apikey=secretKEY123',f.urls[0][0])
  self.assertNotIn('secretKEY123',json.dumps(skills.listing(self.s)))
  self.assertEqual(skills.select(self.s,'arfolyam')[0]['id'],sid)
  r=skill_api.call(self.s,sid,'forecast',{},fetch=f);self.assertNotIn('secretKEY123',json.dumps(r))

 def test_owner_edit_keeps_api_and_contract_is_offered(self):
  sid=self.learn()['skill']['id'];d=next(x for x in skills.listing(self.s) if x['id']==sid)
  skills.save(self.s,dict(id=sid,title='Időjárás 2',description=d['description'],steps=d['steps'],verification=d['verification'],tags=d['tags'],status='published'))
  d=next(x for x in skills.listing(self.s) if x['id']==sid)
  self.assertEqual(d['title'],'Időjárás 2');self.assertIn('api',d);self.assertEqual(d['source'],'learned')
  self.assertIn('learn_skill',tools.prompt_contract('szia'));self.assertIn('skill_call',tools.prompt_contract('szia'))

 def test_rate_limit(self):
  sid=self.learn()['skill']['id'];f=Fetch()
  for _ in range(skill_api.CALLS_PER_HOUR):skill_api.call(self.s,sid,'forecast',{},fetch=f)
  with self.assertRaisesRegex(ValueError,'Óránként'):skill_api.call(self.s,sid,'forecast',{},fetch=f)

class CatalogTests(unittest.TestCase):
 def test_catalog_rows_and_candidates(self):
  raw='### Weather\n| API | Description | Auth | HTTPS | CORS |\n|---|---|---|---|---|\n| [Open-Meteo](https://open-meteo.com/) | Free weather API for non-commercial use | No | Yes | Yes |\n| [Keyed](https://k.example.com/) | Weather forecasts | `apiKey` | Yes | No |\n### Games\n| [Xbox](https://xbox.example.com/) | Console games | No | Yes | Yes |\n'
  with tempfile.TemporaryDirectory() as d:
   apis=skill_api.catalog(d,fetch=lambda u:raw)
   self.assertEqual([a['name'] for a in apis],['Open-Meteo','Keyed','Xbox']);self.assertEqual(apis[1]['auth'],'apiKey')
   self.assertEqual([a['name'] for a in skill_api.candidates('current weather forecast for a city',apis)],['Open-Meteo','Keyed'])
   self.assertEqual(skill_api.catalog(d,fetch=lambda u:''),apis)  # cached

if __name__=='__main__':unittest.main()
