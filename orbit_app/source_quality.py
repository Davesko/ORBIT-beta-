"""Measured source black intervals for editorial exclusion, separate from model opinion."""
import json,re,subprocess,sys
from pathlib import Path

def black_intervals(log):
 return [dict(start=float(a),end=float(b)) for a,b in re.findall(r'black_start:([\d.]+)\s+black_end:([\d.]+)',log) if float(b)>float(a)]

def scan(source,duration):
 import imageio_ffmpeg
 result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-hide_banner','-v','info','-protocol_whitelist','file,pipe','-i',str(source),'-t',str(min(180,float(duration))),'-an','-vf','scale=320:-2,blackdetect=d=0.35:pix_th=0.05:pic_th=0.98','-f','null','-'],capture_output=True,text=True,timeout=90)
 if result.returncode:raise ValueError('A forrás képkockái nem dekódolhatók a minőségellenőrzéshez.')
 return dict(version=1,black_intervals=black_intervals(result.stderr))

def annotate(s,job,tracks,data):
 cache=data.setdefault('source_quality',{})
 for track in tracks:
  name=track['source']['source_video'];path=s.safe_path(job['project'],name);stat=path.stat();fingerprint=[stat.st_size,stat.st_mtime_ns]
  saved=cache.get(name,{})
  if saved.get('fingerprint')!=fingerprint or saved.get('version')!=1:
   s.job_stage(job['id'],'source_quality','Forrásképek ellenőrzése · üres nyitóképek kizárása')
   result=subprocess.run([str(s.root/'media-runtime/bin/python'),str(Path(__file__).resolve()),str(path),str(track['source']['duration'])],capture_output=True,text=True,timeout=100)
   if result.returncode:raise ValueError('A forrás minőségellenőrzése nem fejeződött be. A mentett forrás megmaradt.')
   saved=json.loads(result.stdout);saved['fingerprint']=fingerprint;cache[name]=saved
  track['quality']=saved

if __name__=='__main__':
 try:print(json.dumps(scan(sys.argv[1],float(sys.argv[2]))))
 except Exception as e:print(json.dumps(dict(error=str(e))));sys.exit(1)
