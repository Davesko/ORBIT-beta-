"""Check the actual export; a stationary source is not automatically a broken render."""
import re,subprocess


def verify_export(ffmpeg,output,duration):
    result=subprocess.run([ffmpeg,'-nostdin','-hide_banner','-v','info','-xerror',
        '-i',str(output),'-vf','scale=160:-2,freezedetect=n=-50dB:d=1.5',
        '-af','astats=metadata=0:reset=0','-f','null','-'],
        capture_output=True,text=True,timeout=max(90,round(duration*3)))
    if result.returncode:raise ValueError('A teljes render dekódolása hibát jelzett; a videót nem jelöljük késznek.')
    freezes=[float(x) for x in re.findall(r'freeze_duration: ([0-9.]+)',result.stderr)]
    starts=re.findall(r'freeze_start: ([0-9.]+)',result.stderr)
    if len(starts)>len(freezes):freezes.append(max(0,duration-float(starts[-1])))
    peaks=[float(x) for x in re.findall(r'Peak level dB: (-?[0-9.]+)',result.stderr)]
    return dict(full_decode='passed',freeze_intervals_observed=len(freezes),
        longest_stationary_seconds=max(freezes,default=0),
        audio_peak_db=max(peaks) if peaks else None,
        assessment='Stationary frames are observations, not proof of an editing error. Compare source before rejecting.')
