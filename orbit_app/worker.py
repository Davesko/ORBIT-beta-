"""Persistent local scheduler; one generation lane and a separate model download lane."""
import fcntl
import signal
import threading
import time
from studio import ROOT,Studio,now

if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    lock=(ROOT/'worker.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit(0)
    stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    db=Studio()
    from assistant_resilience import recover_interrupted
    recover_interrupted(db)
    def lane(kinds,yield_to_production=False):
        s=Studio()
        from missions import production_active
        from inference_gate import interactive_pending
        while not stop.is_set():
            try:
                # Background analysis waits (still queued, nothing lost) while a video is produced.
                if yield_to_production and (production_active(s) or interactive_pending(s.root)):stop.wait(1);continue
                if not s.run_next(kinds):stop.wait(1)
            except Exception as exc:
                # An open transaction left behind here would lock out every other lane and the app.
                s.db.rollback();print('worker:',str(exc),flush=True);stop.wait(3)
    for kinds in [('command','control_apply'),('chat','scheduled','pipeline','graph','media','media_analysis','youtube_upload','short_request','command_apply','model_evaluation'),('model_pull',),('growth_research','growth_metrics'),('mission_dispatch',)]:
        threading.Thread(target=lane,args=(kinds,),daemon=True).start()
    threading.Thread(target=lane,args=(('mission_agent',),True),daemon=True).start()
    def video_fallback():
        # Story sound and render steps belong to the desktop app's video lane. The app starts that lane once: when it
        # ended (10 Nov) those steps waited forever with nothing running. While no lane holds the lock, they run here.
        import fcntl
        s=Studio()
        while not stop.is_set():
            stop.wait(5)
            try:
                if not s.db.execute("SELECT 1 FROM jobs WHERE kind IN ('command_apply','graph') AND status='queued' AND json_extract(payload,'$.foreground_video')=1 LIMIT 1").fetchone():continue
                with (s.root/'video-worker.lock').open('a') as lock:
                    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:continue
                    while not stop.is_set() and s.run_next(('command_apply','graph'),foreground_video=True):pass
            except Exception as exc:
                s.db.rollback();print('video fallback:',str(exc)[:300],flush=True)
    threading.Thread(target=video_fallback,daemon=True).start()
    threading.Thread(target=lane,args=(('assist',),True),daemon=True).start()
    from telegram_control import loop as telegram_loop
    threading.Thread(target=telegram_loop,args=(stop,),daemon=True).start()
    def feedback_lane():
        from short_feedback import poll_all
        while not stop.is_set():
            try:poll_all()
            except Exception:pass
            stop.wait(3600)
    threading.Thread(target=feedback_lane,daemon=True).start()
    def email_lane():
        s=Studio()
        from email_hub import pass_all
        while not stop.is_set():
            try:pass_all(s)
            except Exception as exc:
                s.db.rollback();print('email:',str(exc)[:300],flush=True)
            stop.wait(20)
    threading.Thread(target=email_lane,daemon=True).start()
    def design_lane():
        # Digital products' designs, rendered with the local image model while the Autopilot does not use it.
        s=Studio()
        from design_studio import work
        import autonomy
        while not stop.is_set():
            if autonomy.paused(s):
                stop.wait(30);continue
            try:done=work(s)
            except Exception as exc:
                s.db.rollback();print('design:',str(exc)[:300],flush=True);done=None
            stop.wait(5 if done else 30)
    threading.Thread(target=design_lane,daemon=True).start()
    while not stop.is_set():
        from scheduler_services import tick
        try:tick(db)
        except Exception as exc:
            db.db.rollback();print('scheduler health: '+str(exc)[:500],flush=True)
        stop.wait(3)
