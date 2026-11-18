"""Small background jobs of the local model: learning the user's memory, summarising and answering email. A failure here
stays quiet: the next round tries again, and nothing the owner is waiting for depends on it silently."""
import json

def chat_model():
 """The model for a background text job. "auto" would judge the task from the text's own words: a letter about pictures
 got the vision model, which answered with nothing. A text model already in memory is used as it is: loading the
 utility model for a memory note unloaded the chat's model and the next chat answer waited for a reload."""
 try:
  import model_hub
  current=model_hub.loaded_chat_model()
  if current:return current
  from model_router import choose
  return choose('Foglald össze ezt a szöveget.',model_hub.models(),purpose='utility')['model']
 except Exception:return 'auto'

def run(s,job):
 """Every task here calls the local model, so it holds the shared model lease like the agents do. Without it a memory
 or mail job loaded its own model and unloaded the one a running agent or chat was using on the other server."""
 from inference_gate import lease
 from execution_queue import DeferredExecution
 if json.loads(job['payload']).get('task')=='trading_agents_install':
  import trading_agents
  return trading_agents.install(s,job)   # pip only, no model: it does not hold the model lease
 if str(json.loads(job['payload']).get('task') or '')=='szim_make':
  import szim_app
  return szim_app.run_job(s,job)   # recipes + physics engine, no model
 if str(json.loads(job['payload']).get('task') or '').startswith('watch_'):
  if json.loads(job['payload'])['task']=='watch_radar':
   import trend_radar
   return 'Trendradar frissítve · '+str(len(trend_radar.refresh(s,force=True)['items']))+' trend'
  import stream_watch
  return stream_watch.run_job(s,job)   # a download, no model
 try:
  with lease(s.root):return _run(s,job)
 except DeferredExecution as error:
  # Background work: no need to knock every few seconds while an agent holds the model for minutes.
  raise DeferredExecution(str(error),max(error.seconds,30)) from None

def _run(s,job):
 task=json.loads(job['payload']).get('task')
 if task=='memory_graph':
  import memory_graph
  return memory_graph.run_job(s,job)
 if task in ('memory_learn','memory_index'):
  import memory_brain
  return memory_brain.index_vectors(s) if task=='memory_index' else memory_brain.learn(s,job)
 if task in ('email_summary','email_reply','email_auto'):
  import email_hub
  return email_hub.run_job(s,job,task)
 if task=='scheduled_email_review':
  import email_brief
  return email_brief.scheduled_review(s,job)
 if task=='email_briefing':
  import email_brief
  return email_brief.run(s,job)
 if task=='self_improve':
  import self_improve
  return self_improve.run_job(s,job)
 if task=='kobold_learn':
  import kobold_link
  return kobold_link.learn_job(s,job)
 if task=='kobold_answer':
  import kobold_link
  return kobold_link.answer_job(s,job)
 if task=='autopilot_tune':
  import autopilot_hub
  return autopilot_hub.tune_job(s,job)
 if task and task.startswith('clip_'):
  import musicvideo
  return musicvideo.run_job(s,job)
 if task=='trading_agents_run':
  import trading_agents
  return trading_agents.run(s,job)
 if task=='model_benchmark':
  import model_finder
  return model_finder.benchmark(s,job)
 raise ValueError('Ismeretlen háttérfeladat.')
