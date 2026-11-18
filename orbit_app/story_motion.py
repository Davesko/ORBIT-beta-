"""Measure motion left after compensating for a global camera transform."""
import json
import subprocess
import sys

import cv2
import numpy as np


def measure(frames):
    if len(frames)<2:
        return dict(passed=False,reason='Too few decoded motion samples.')
    height,width=frames[0].shape
    yy,xx=np.mgrid[0:height:8,0:width:8]
    grid=np.column_stack((xx.ravel(),yy.ravel())).astype(np.float32)
    outer=(grid[:,0]<width*.2)|(grid[:,0]>width*.8)|(grid[:,1]<height*.17)|(grid[:,1]>height*.83)
    yy,xx=np.mgrid[:height,:width]
    peaks=[];fractions=[];unstable=0
    border=(xx<width*.12)|(xx>width*.88)|(yy<height*.12)|(yy>height*.88)
    for before,after in zip(frames,frames[1:]):
        flow=cv2.calcOpticalFlowFarneback(before,after,None,.5,3,15,3,5,1.2,0)
        moving=grid+flow[grid[:,1].astype(int),grid[:,0].astype(int)]
        affine,_=cv2.estimateAffinePartial2D(grid[outer],moving[outer],method=cv2.RANSAC,ransacReprojThreshold=.7)
        if affine is None:
            global_flow=np.median(flow.reshape(-1,2),axis=0)
        else:
            global_flow=np.stack((affine[0,0]*xx+affine[0,1]*yy+affine[0,2]-xx,
                                  affine[1,0]*xx+affine[1,1]*yy+affine[1,2]-yy),axis=-1)
        residual=np.linalg.norm(flow-global_flow,axis=-1)
        center=residual[round(height*.16):round(height*.88),round(width*.1):round(width*.9)]
        peaks.append(float(np.percentile(center,99)))
        fractions.append(float(np.mean(center>.8)))
        if peaks[-1]>width*.20 and fractions[-1]>.55 and np.mean(residual[border]>4)>.35:
            unstable+=1
    active=sum(peak>1.0 and fraction>.01 for peak,fraction in zip(peaks,fractions))
    distorted=unstable>=max(2,int(np.ceil(len(peaks)*.4)))
    return dict(passed=active>=min(2,len(peaks)) and not distorted,active_pairs=active,sample_pairs=len(peaks),
                unstable_pairs=unstable,unstable_image=distorted,
                peak_residual_pixels=round(max(peaks),3),peak_active_fraction=round(max(fractions),4),
                method='Optical-flow residual in the central image after background camera compensation; not semantic pose verification.')


DRIFT_LIMIT=14.0
STAYS=.6


def presence(frame, background):
    """Share of the central image that differs clearly from the background colour: the drawn cast and props."""
    height,width=frame.shape
    center=frame[round(height*.12):round(height*.9),round(width*.08):round(width*.92)].astype(np.float32)
    return float(np.mean(np.abs(center-background)>40))


def drift(frames, reference):
    """Mean grey-level change of the frame border against the clean start image, per sample.

    With a fixed camera and background the border barely changes; Wan's low-resolution failure mode (horizontal
    streaks, colour bands, a melting background) changes it by 30-80 levels."""
    height,width=reference.shape
    yy,xx=np.mgrid[:height,:width]
    border=(xx<width*.12)|(xx>width*.88)|(yy<height*.12)|(yy>height*.88)
    return [float(np.mean(np.abs(frame.astype(np.float32)-reference.astype(np.float32))[border])) for frame in frames]


def decode(ffmpeg,path,count,still=False,colour=False):
    depth=3 if colour else 1
    result=subprocess.run([ffmpeg,'-nostdin','-v','error','-i',path,'-vf',('' if still else 'fps=6,')+'scale=160:288,format='+('bgr24' if colour else 'gray'),
                           '-frames:v',str(count),'-f','rawvideo','-'],capture_output=True,timeout=90,check=True)
    raw=np.frombuffer(result.stdout,dtype=np.uint8)
    if raw.size%(160*288*depth) or not raw.size:
        raise ValueError('Incomplete video motion samples.')
    return raw.reshape(-1,288,160,depth) if colour else raw.reshape(-1,288,160)


def cast_presence(frame,names):
    """Share of the central image in the cast's own identity colours; props and background are not counted."""
    from story_identity import mask
    height,width=frame.shape[:2]
    center=frame[round(height*.12):round(height*.9),round(width*.08):round(width*.92)]
    return float(np.mean(np.any([mask(center,n) for n in names],axis=0)))


def inspect(ffmpeg,path,reference=None,names=()):
    frames=decode(ffmpeg,path,36)
    result=measure(frames)
    if reference:
        values=drift(frames,decode(ffmpeg,reference,1,still=True)[0])
        mean=float(np.mean(values))
        result.update(border_drift_mean=round(mean,2),border_drift_max=round(max(values),2))
        if mean>DRIFT_LIMIT:
            result.update(passed=False,unstable_image=True,glitch='background drifts from the clean start frame')
        start=decode(ffmpeg,reference,1,still=True)[0]
        height,width=start.shape
        yy,xx=np.mgrid[:height,:width]
        edge=(xx<width*.06)|(xx>width*.94)|(yy<height*.05)
        background=float(np.median(start[edge]))
        first,last=presence(start,background),presence(frames[-1],background)
        floor=.01
        if names:
            # The drawn props also differ from the background; with known identity colours only the cast is counted.
            from story_identity import usable
            start_colour=decode(ffmpeg,reference,1,still=True,colour=True)[0]
            names=usable(start_colour,list(names))
            if names:
                first=cast_presence(start_colour,names)
                last=cast_presence(decode(ffmpeg,path,36,colour=True)[-1],names)
                result.update(presence_by='identity colours: '+', '.join(names));floor=.002
        result.update(cast_presence_start=round(first,4),cast_presence_end=round(last,4))
        # The last pose is held for the rest of the shot: a character that walked or fell out of frame leaves an empty stage.
        if first>floor and last<first*STAYS:
            result.update(passed=False,left_frame=True)
    return result


if __name__=='__main__':
    print(json.dumps(inspect(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else None,
                             json.loads(sys.argv[4]) if len(sys.argv)>4 else ())))
