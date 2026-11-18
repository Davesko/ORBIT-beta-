"""Verified revenue from the owner's Stripe account, read-only (restricted rk_ key, GET only).

Revenue shown anywhere in ORBIT comes from here or nowhere: no estimate is ever displayed as
income. Results are cached for an hour.
"""
import json,os,time,urllib.parse
import connections

STALE=3600

def cache_path(s):return s.root/'revenue.json'

def read(s):
 try:return json.loads(cache_path(s).read_text())
 except (OSError,ValueError):return None

def fetch(root=None,days=30,now=None):
 """Sum succeeded charges minus refunds over the window, per currency (smallest unit -> major)."""
 now=now or time.time();since=int(now-days*86400)
 totals={};count=0;after=None
 for _ in range(10):
  q=dict(limit=100,**{'created[gte]':since});q.update(starting_after=after) if after else None
  page=connections.http('stripe','balance_transactions?'+urllib.parse.urlencode(q),root=root)
  for t in page.get('data',[]):
   if t.get('type') not in ('charge','payment','refund','payment_refund'):continue
   cur=str(t.get('currency','')).upper();totals.setdefault(cur,dict(gross=0,fees=0,net=0))
   totals[cur]['gross']+=t.get('amount',0);totals[cur]['fees']+=t.get('fee',0);totals[cur]['net']+=t.get('net',0)
   count+=t.get('type') in ('charge','payment')
  if not page.get('has_more') or not page.get('data'):break
  after=page['data'][-1]['id']
 # Stripe amounts are in the smallest unit; zero-decimal currencies are already whole units.
 zero_decimal={'JPY','KRW','VND','CLP','ISK','UGX','XAF','XOF'}
 money={c:{k:(v if c in zero_decimal else round(v/100,2)) for k,v in t.items()} for c,t in totals.items()}
 return dict(days=days,payments=count,totals=money,at=now)

def refresh(s,force=False):
 """Hourly cache; silent when Stripe is not connected."""
 if not connections.secret('stripe'):return None
 if not connections.settings()['providers'].get('stripe',{}).get('enabled'):return None
 old=read(s)
 if old and not force and time.time()-old.get('at',0)<STALE:return old
 try:value=fetch()
 except Exception as e:value=dict(old or {},error=str(e)[:200],at=time.time())
 tmp=cache_path(s).with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False));os.replace(tmp,cache_path(s))
 return value

def label(value):
 """'1 234,00 EUR · 3 fizetés (30 nap)' or None."""
 if not value or value.get('error') or not value.get('totals'):return None
 parts=[f"{t['net']:,.2f}".replace(',',' ').replace('.',',')+' '+c for c,t in value['totals'].items() if t.get('net')]
 return (' + '.join(parts) or '0')+' nettó · '+str(value.get('payments',0))+' fizetés ('+str(value.get('days',30))+' nap)'
