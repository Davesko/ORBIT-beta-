"""Mailbox search never treats a bounded language-model context as the entire inbox."""
import re
from model_router import normalized

def search_request(prompt):
 p=normalized(prompt)
 if not re.search(r'keres|talald|find|search',p):return None
 patterns=[r'(?:kozott|kozul)\s+(.+?)\s+(?:al|el|val|vel)\b',r'(?:nekem\s+)?(?:az?\s+)?(.+?)\s+(?:al|el|val|vel)\s+kapcsolatos',r'(?:from|about)\s+([\w@. -]+)']
 for pattern in patterns:
  m=re.search(pattern,p)
  if m:
   q=re.sub(r'^.*?\b(?:nekem|kozott|kozul)\s+','',m.group(1));q=re.sub(r'^az?\s+','',q).strip()
   if q and len(q)<100:return q
 return None

def find(s,query):
 needle=normalized(query).strip();out=[]
 for r in s.rows('SELECT id,account,sender,sender_name,recipients,subject,date,body FROM emails WHERE removed=0 ORDER BY date DESC'):
  if needle in normalized(' '.join(str(r.get(k) or '') for k in ('sender','sender_name','recipients','subject','body'))):out.append(r)
  if len(out)>=50:break
 return out
