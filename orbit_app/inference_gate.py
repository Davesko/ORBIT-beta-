"""One local-model memory owner across the control, worker and bridge processes."""
import contextlib,fcntl,sqlite3,threading,time
from pathlib import Path
from execution_queue import DeferredExecution
_local=threading.local()

def interactive_pending(root):
 """Read-only admission check at boundaries where background work can yield."""
 path=Path(root)/'studio.sqlite'
 if not path.is_file():return False
 try:
  db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=.2)
  try:
   return db.execute("""SELECT 1 FROM jobs WHERE kind IN ('command','control_apply')
                        AND status IN ('queued','running') AND created>? LIMIT 1""",(time.time()-600,)).fetchone() is not None
  finally:db.close()
 except sqlite3.Error:return False

def chat_waiting(root,grace=1.5):
 """A chat request queued for the model (a busy model defers it to 'queued'), not one answered without a model,
 or a running chat task (the computer operator) waiting for the model right now."""
 try:
  if time.time()-(Path(root)/'chat-waiting').stat().st_mtime<4:return True
 except OSError:pass
 path=Path(root)/'studio.sqlite'
 if not path.is_file():return False
 try:
  db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=.2)
  try:
   now=time.time()
   # An automation's run is a chat job nobody is waiting on: it does not push other work off the model.
   return db.execute("""SELECT 1 FROM jobs WHERE kind IN ('command','command_apply','control_apply') AND status='queued'
                        AND created BETWEEN ? AND ? AND coalesce(json_extract(payload,'$.retry_at'),0)<=?
                        AND prompt NOT LIKE '[ORBIT-RUN]%' LIMIT 1""",(now-600,now-grace,now+5)).fetchone() is not None
  finally:db.close()
 except sqlite3.Error:return False

INTERACTIVE=('command','command_apply','control_apply','chat')

def set_background(kind,automated=False):
 """Marks this thread's current job: a background job's model call yields to a waiting chat. An automation's chat run
 counts as background: it yields to the owner and does not interrupt other work."""
 _local.background=bool(kind) and (kind not in INTERACTIVE or automated)
 _local.interactive=kind in INTERACTIVE and not automated

def is_background():
 return getattr(_local,'background',False)

def yield_for_chat(root):
 if interactive_pending(root):
  raise DeferredExecution('A videó a következő snitt előtt átadja a helyi modellt a chatnek.',3)

@contextlib.contextmanager
def lease(root,wait=0):
 """wait>0 queues in-process for up to `wait` seconds (helpers that cannot be deferred);
 otherwise a busy model defers the job. Every local model call must hold this: the SSD server
 keeps one model loaded, so an unleased call evicts the model another job is using."""
 path=str(Path(root).resolve()/'model-session.lock');held=getattr(_local,'held',{})
 if path in held:
  yield;return
 Path(root).mkdir(parents=True,exist_ok=True)
 with open(path,'a') as f:
  deadline=time.monotonic()+wait
  while True:
   try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:
    # An interactive caller waiting here tells background model calls to hand over.
    if getattr(_local,'interactive',False) and wait>0:
     try:(Path(root)/'chat-waiting').touch()
     except OSError:pass
    if time.monotonic()>=deadline:raise DeferredExecution('A háttérfeladat átadja a modellt a chatnek; néhány másodperc.' if getattr(_local,'interactive',False) else 'A helyi modell másik feladaton dolgozik; a kérésed sorban áll.',3) from None
    time.sleep(.5)
  held[path]=f;_local.held=held
  try:yield
  finally:held.pop(path,None);fcntl.flock(f,fcntl.LOCK_UN)
