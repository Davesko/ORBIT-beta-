"""CPU-only, bounded visual samples from a file the user attached."""
import json
import math
import sys
from pathlib import Path
import cv2

def preview(source,folder):
    capture=cv2.VideoCapture(str(source))
    try:
        fps=capture.get(cv2.CAP_PROP_FPS);frames=capture.get(cv2.CAP_PROP_FRAME_COUNT)
        duration=frames/fps if math.isfinite(fps) and fps>0 and math.isfinite(frames) else 0
        info=dict(width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),seconds=duration,sampled_seconds=[])
        for index,fraction in enumerate((.10,.5,.9),1):
            at=max(0,duration*fraction);capture.set(cv2.CAP_PROP_POS_MSEC,at*1000)
            ok,image=capture.read()
            if not ok:continue
            h,w=image.shape[:2];scale=min(1,768/max(w,h));image=cv2.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))))
            if cv2.imwrite(str(folder/f'sample-{index}.jpg'),image,[cv2.IMWRITE_JPEG_QUALITY,80]):info['sampled_seconds'].append(round(at,2))
        (folder/'video-info.json').write_text(json.dumps(info))
    finally:capture.release()

if __name__=='__main__':preview(Path(sys.argv[1]),Path(sys.argv[2]))
