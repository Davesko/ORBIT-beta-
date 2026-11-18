"""Fresh official US Google Trending Now seeds for the existing source pipeline."""
import json,time
URL='https://trends.google.com/trending/rss?geo=US'
PAGE='https://trends.google.com/trending?geo=US'

def seeds(s,pid,spec):
 from public_web import fetch
 from growth import parse_feed
 from clip_farm import report_matches
 path=s.safe_path(pid,'insights/google-trends-us.json')
 try:
  saved=json.loads(path.read_text())
 except (OSError,ValueError):saved={}
 if time.time()-saved.get('collected_at',0)<300:items=saved.get('items',[])
 else:
  raw,_=fetch(URL,1500000);items=parse_feed(raw)
  saved=dict(source=URL,page=PAGE,country='US',collected_at=time.time(),items=items)
  path.parent.mkdir(parents=True,exist_ok=True)
  from youtube_runtime import atomic_json
  atomic_json(path,saved)
 items=[i for i in items if -300<=time.time()-i['published_at']<=24*3600]
 selected=[i for i in items if report_matches(dict(title=i['topic'],content=' '.join(i.get('news_titles',[]))),spec)]
 selected.sort(key=lambda i:(i.get('google_search_traffic') or 0,i['published_at']),reverse=True)
 return dict(saved,items=selected[:8])
