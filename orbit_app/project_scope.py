"""Resolve user-visible project names without asking people for database IDs."""
import re
from model_router import normalized

def key(value):
 return re.sub(r'[^a-z0-9]+','',normalized(value))

def directory(s,prompt):
 rows=s.rows('SELECT id,name FROM projects')
 text=key(prompt)
 matches=[r for r in rows if key(r['name']) and key(r['name']) in text]
 return dict(projects=rows,matched_projects=matches)

def mentioned(s,prompt):
 """Resolve an unambiguous project name or its visible title before the dash."""
 text=key(prompt);matches=[]
 for row in s.rows('SELECT id,name FROM projects'):
  names=[row['name'],re.split(r'\s+[–—-]\s+',row['name'],maxsplit=1)[0]]
  if any(len(key(n))>=4 and key(n) in text for n in names):matches.append(row['id'])
 if len(matches)==1:return matches[0]
 return None

def resolve(s,value):
 rows=s.rows('SELECT id,name FROM projects')
 exact=[r for r in rows if r['id']==value or key(r['name'])==key(value)]
 if len(exact)==1:return exact[0]['id']
 # A model shortens "venture-a9084641" to "a9084641": a unique ID ending in it is that project.
 tail=[r for r in rows if isinstance(value,str) and len(value)>=6 and r['id'].endswith('-'+value)]
 if len(tail)==1:return tail[0]['id']
 raise ValueError('A projekt neve nem egyértelmű vagy nem létezik: '+str(value)+'. Létező projektek (id: név): '+'; '.join(r['id']+': '+r['name'] for r in rows[:30]))

def asks_known_id(reply,scope):
 p=normalized(reply)
 known=scope['matched_projects'] or [r for r in scope['projects'] if key(r['name']) in key(reply)]
 return bool(known) and bool(re.search(r'add meg|kerlek.*(?:azonosit|id)|provide|specify',p)) and bool(re.search(r'azonosit|\bid\b|identifier',p))
