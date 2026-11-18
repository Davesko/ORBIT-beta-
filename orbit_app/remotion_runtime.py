"""Bounded local Remotion finish. FFmpeg owns source edits and continuous audio."""
import json,os,shutil,subprocess,sys
from pathlib import Path


def location():
    return Path(__file__).resolve().parent/'remotion'


def node_binary():
    explicit=os.environ.get('ORBIT_NODE')
    candidates=[explicit,shutil.which('node'),str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')]
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()),None)


def ready():
    base=location()
    return bool(node_binary() and (base/'node_modules/@remotion/renderer/package.json').is_file() and (base/'dist/index.html').is_file())


def finish(base_video,output,contract,progress,ffmpeg,tmp):
    if not ready():raise RuntimeError('A helyi Remotion futtató nincs előkészítve.')
    props=tmp/'motion.json';motion=tmp/'motion.mp4'
    props.write_text(json.dumps(dict(contract=contract,base=str(base_video),output=str(motion),progress=str(progress))))
    subprocess.run([node_binary(),str(location()/'render.cjs'),str(props)],check=True,
                   timeout=1200,cwd=location(),stdout=sys.stderr,stderr=sys.stderr)
    # Copy the original continuous mixed audio; Chromium never re-times speech.
    subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(motion),'-i',str(base_video),
                    '-map','0:v:0','-map','1:a:0?','-c','copy','-movflags','+faststart',
                    '-n',str(output)],check=True,timeout=120,stdout=subprocess.DEVNULL)
