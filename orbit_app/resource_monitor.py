"""Measured process CPU/RSS, not guessed percentages or model throughput."""
import os,subprocess,time

def snapshot():
 try:
  raw=subprocess.run(['/bin/ps','-axo','pcpu=,rss=,args='],capture_output=True,text=True,timeout=2,check=True).stdout
  cpu=rss=0
  for line in raw.splitlines():
   parts=line.strip().split(None,2)
   if len(parts)==3 and any(x in parts[2].lower() for x in ('orbit','ollama','mlx','ffmpeg')):
    cpu+=float(parts[0]);rss+=int(parts[1])*1024
  total=int(subprocess.check_output(['/usr/sbin/sysctl','-n','hw.memsize'],text=True,timeout=2))
  cpu=min(100,round(cpu/max(1,os.cpu_count() or 1),1));mem=round(rss/total*100,1)
  return dict(cpu_percent=cpu,memory_bytes=rss,memory_percent=mem,level='red' if max(cpu,mem)>=85 else 'yellow' if max(cpu,mem)>=65 else 'green',observed_at=time.time(),scope='ORBIT, Ollama, MLX and FFmpeg process estimates')
 except (OSError,ValueError,subprocess.SubprocessError):return dict(level='unknown',observed_at=time.time())
