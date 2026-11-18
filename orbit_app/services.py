"""On a new Mac nothing starts ORBIT's background worker: the original install set its LaunchAgent up by hand.
The first request from the app installs it once, for this user only, when ORBIT runs from its installed core."""
import os,plistlib,subprocess
from pathlib import Path
HOME=Path.home();ROOT=HOME/'Library/Application Support/Orbit'
WORKER='hu.orbit.studio-worker'

def installed_core():
 return Path(__file__).resolve().parent==(ROOT/'core').resolve()

def ensure_worker():
 """Writes and loads the worker LaunchAgent if it is missing. Never touches an existing one."""
 plist=HOME/'Library/LaunchAgents'/(WORKER+'.plist');core=ROOT/'core'
 if plist.exists() or not installed_core() or not (core/'worker.py').is_file():return False
 (ROOT/'logs').mkdir(parents=True,exist_ok=True);plist.parent.mkdir(parents=True,exist_ok=True)
 plist.write_bytes(plistlib.dumps(dict(Label=WORKER,ProgramArguments=['/usr/bin/python3',str(core/'worker.py')],WorkingDirectory=str(core),
  RunAtLoad=True,KeepAlive=True,ThrottleInterval=15,EnvironmentVariables=dict(PYTHONDONTWRITEBYTECODE='1'),
  StandardOutPath=str(ROOT/'logs/worker.stdout.log'),StandardErrorPath=str(ROOT/'logs/worker.stderr.log'))))
 subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(plist)],capture_output=True)
 return True
