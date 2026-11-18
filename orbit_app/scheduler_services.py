"""Isolated scheduler services: one broken integration cannot stop all supervision."""
import time

def tick(s):
 from growth import tick as growth_tick
 from missions import tick as mission_tick
 from assistant_context import publish
 health={}
 from storage_guard import storage_ok,check,keep_awake
 def schedules():
  # Low disk stops new admissions only; running work and reconciliation continue.
  if storage_ok(s):s.schedule()
 import autonomy
 hold=autonomy.paused(s)
 for name,callback in [('storage',lambda:check(s)),('schedules',schedules),('growth',lambda:growth_tick(s)),('missions',lambda:mission_tick(s)),('keep_awake',lambda:keep_awake(s)),('context',lambda:publish(s)),('daily_report',lambda:__import__('daily_report').tick(s)),('self_improve',lambda:__import__('self_improve').tick(s)),('autopilot',lambda:__import__('autopilot_hub').tick(s)),('kobold',lambda:__import__('kobold_link').tick(s)),('self_heal',lambda:__import__('self_heal').tick(s)),('housekeeping',lambda:__import__('housekeeping').tick(s)),('concierge',lambda:__import__('concierge').tick(s)),('clip_farm_setup',lambda:__import__('clip_farm').configure(s)),('gta6',lambda:__import__('gta6').tick(s)),('etsy',lambda:__import__('etsy').tick(s)),('memory',lambda:__import__('memory_brain').tick(s)),('publish',lambda:__import__('publish_hub').tick(s)),('stream_watch',lambda:__import__('stream_watch').tick(s)),('stickman',lambda:__import__('stickman_studio').tick(s))]:
  if hold and name in autonomy.PAUSABLE:
   health[name]=dict(ok=True,checked_at=time.time(),paused=True);continue   # the owner paused everything self-starting
  try:callback();health[name]=dict(ok=True,checked_at=time.time())
  except Exception as exc:
   s.db.rollback();health[name]=dict(ok=False,checked_at=time.time(),error=str(exc)[:500]);print('scheduler '+name+': '+str(exc)[:500],flush=True)
 from youtube_runtime import atomic_json
 atomic_json(s.root/'scheduler-health.json',dict(observed_at=time.time(),services=health))
 # Means the scheduler is alive, not that every integration is healthy.
 (s.root/'worker.heartbeat').touch()
 return health
