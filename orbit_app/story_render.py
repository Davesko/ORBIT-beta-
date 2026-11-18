"""Local frame renderer for the Tiny Disasters cast and reusable sets."""
import array
import json
import math
import sys
import wave
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W,H,FPS=540,960,24
INK='#171c33'
PALETTES={
    'office':('#1d315a','#719cc9','#bad6f0'), 'home':('#493256','#a46987','#e2a5a4'),
    'park':('#174a54','#438b78','#9fd9ac'), 'cafe':('#633a39','#c8825e','#ffe0a6'),
    'station':('#3a3154','#7b8ba9','#d9edf8'), 'arcade':('#261546','#58408d','#e09aec'),
}
COLORS={'milo':('#64e0c5','#eeb589'), 'bea':('#ff995e','#ae735b')}


@lru_cache(maxsize=32)
def font(size):
    try:return ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',size)
    except OSError:return ImageFont.load_default(size=size)


def background(key):
    deep,mid,light=PALETTES[key]
    image=Image.new('RGB',(W,H),deep);d=ImageDraw.Draw(image)
    d.rounded_rectangle((25,102,515,697),35,fill=mid)
    d.rectangle((25,630,515,697),fill=deep)
    if key=='office':
        d.rounded_rectangle((86,160,453,374),22,fill=light,outline=INK,width=7)
        for x,height in ((105,44),(155,87),(213,60),(275,117),(335,75),(389,94)):
            d.rectangle((x,362-height,x+30,363),fill=mid)
        d.line((270,167,270,367),fill=INK,width=5)
        d.rounded_rectangle((69,460,470,509),16,fill='#baa082',outline=INK,width=6)
        for x in (101,414):d.rectangle((x,505,x+17,633),fill=INK)
    elif key=='home':
        d.rounded_rectangle((91,429,455,601),32,fill=light,outline=INK,width=7)
        d.rounded_rectangle((65,514,473,598),22,fill='#d98d96',outline=INK,width=7)
        d.line((419,279,419,415),fill=INK,width=7)
        d.polygon([(380,283),(457,283),(439,212),(399,212)],fill='#f7ce8b')
        d.rounded_rectangle((106,196,267,332),18,fill=deep,outline=INK,width=6)
        d.ellipse((146,229,225,305),fill='#e9bb99')
    elif key=='park':
        d.ellipse((341,156,438,251),fill='#ffdd89')
        for x,y in ((128,283),(340,347)):
            d.line((x,y,x,587),fill=deep,width=20)
            d.ellipse((x-88,y-80,x+88,y+64),fill=light,outline=INK,width=6)
        d.rounded_rectangle((115,484,420,545),15,fill='#b98966',outline=INK,width=6)
        d.line((141,544,141,621),fill=INK,width=10)
    elif key=='station':
        d.rounded_rectangle((45,223,498,500),26,fill=deep,outline=INK,width=7)
        for x in (61,214,367):
            d.rounded_rectangle((x,255,x+114,424),12,fill=light,outline=INK,width=5)
        d.rectangle((40,550,500,569),fill='#ffce68')
        d.line((106,186,438,186),fill=light,width=9)
    elif key=='arcade':
        for x,accent in ((65,'#f291b7'),(223,'#8df0db'),(373,'#ffd683')):
            d.rounded_rectangle((x,270,x+112,566),16,fill=deep,outline=accent,width=7)
            d.rounded_rectangle((x+13,299,x+99,400),8,fill=accent,outline=INK,width=5)
            d.ellipse((x+60,440,x+83,463),fill=accent)
    else:
        for x in (95,271,439):
            d.line((x,132,x,228),fill=INK,width=6)
            d.polygon([(x-43,247),(x+43,247),(x+23,200),(x-23,200)],fill=light)
        d.rounded_rectangle((68,390,472,513),18,fill=deep,outline=INK,width=7)
        d.rectangle((69,415,471,438),fill=light)
        for x in range(90,450,76):
            d.line((x,440,x,504),fill=mid,width=5)
        d.line((397,544,397,621),fill=INK,width=10)
    return image


def actor(draw,name,x,y,t,action,active):
    cloth,skin=COLORS[name]
    wave=math.sin(t*8)
    if active:
        x+=int(55*(1-min(t*2,1))) if action=='enter' else int(wave*6) if action=='shake' else 0
        y-=int(abs(wave)*32) if action=='celebrate' else int(5*wave)
    draw.ellipse((x-62,y+119,x+62,y+143),fill='#222743')
    for foot in (-25,25):
        draw.rounded_rectangle((x+foot-12,y+83,x+foot+12,y+131),11,fill=INK)
    draw.rounded_rectangle((x-47,y+21,x+47,y+111),22,fill=cloth,outline=INK,width=6)
    draw.line((x-39,y+44,x-69,y+(33 if active and action in ('point','react','celebrate') else 79)),fill=INK,width=12)
    draw.line((x+39,y+44,x+69,y+(22 if active and action in ('point','react','celebrate') else 74)),fill=INK,width=12)
    if name=='bea':draw.rounded_rectangle((x-61,y-83,x+61,y+37),34,fill=INK)
    draw.rounded_rectangle((x-53,y-72,x+53,y+24),38,fill=skin,outline=INK,width=6)
    if name=='bea':
        draw.polygon([(x-51,y-59),(x+50,y-75),(x+48,y-43),(x-40,y-37)],fill=INK)
    for eye in (-20,20):
        draw.ellipse((x+eye-5,y-32,x+eye+5,y-20),fill=INK)
        if name=='milo':draw.ellipse((x+eye-14,y-40,x+eye+14,y-12),outline=INK,width=4)
    if name=='milo':draw.line((x-6,y-28,x+6,y-28),fill=INK,width=4)
    if active and action in ('react','celebrate'):draw.ellipse((x-10,y-9,x+10,y+8),fill=INK)
    else:draw.arc((x-12,y-13,x+12,y+7),0,160,fill=INK,width=4)


def prop(draw,key,x,y):
    if key=='none':return
    if key=='phone':
        draw.rounded_rectangle((x-16,y-30,x+16,y+30),7,fill='#9bedff',outline=INK,width=5)
        draw.line((x-7,y+21,x+7,y+21),fill=INK,width=3)
    elif key=='clock':
        draw.ellipse((x-28,y-28,x+28,y+28),fill='#f9edc4',outline=INK,width=5)
        draw.line((x,y-14,x,y,x+13,y+7),fill=INK,width=4)
    elif key=='laptop':
        draw.rounded_rectangle((x-32,y-29,x+32,y+17),5,fill='#9bedff',outline=INK,width=5)
        draw.line((x-41,y+19,x+41,y+19),fill=INK,width=7)
    else:
        draw.rounded_rectangle((x-24,y-19,x+24,y+24),6,fill='#ffdf8c',outline=INK,width=5)
        if key=='coffee':draw.arc((x+19,y-15,x+41,y+13),270,90,fill=INK,width=5)
        else:draw.line((x-13,y,x+13,y),fill=INK,width=4)


def lines(draw,value,face,limit):
    result=['']
    for word in value.split():
        test=(result[-1]+' '+word).strip()
        if result[-1] and draw.textlength(test,font=face)>limit:result.append(word)
        else:result[-1]=test
    return result


def reference(scene, subshot):
    image=background(scene['set'])
    draw=ImageDraw.Draw(image)
    focus=scene['actor'];other='bea' if focus=='milo' else 'milo'
    actor_x={'left':152,'center':270,'right':390}[scene['blocking']]
    framing=scene['framing']
    if framing=='detail':
        draw.rounded_rectangle((70,378,470,680),35,fill=PALETTES[scene['set']][1],outline=INK,width=8)
        prop(draw,scene['prop'],actor_x,540)
        area=(actor_x-90,380,actor_x+90,700)
    else:
        if framing in ('wide','two-shot'):
            if actor_x==270:actor_x=170
            actor(draw,other,385 if actor_x<270 else 155,500,0,'hold',False)
        actor(draw,focus,actor_x,500,0,scene['action'],True)
        prop(draw,scene['prop'],actor_x+75 if actor_x<340 else actor_x-75,545)
        if framing=='close':
            area=(actor_x-135,290,actor_x+135,770)
        elif framing=='two-shot':
            area=(36,90,504,922)
        else:
            area=(0,0,W,H)
    if subshot%2:
        x1,y1,x2,y2=area
        area=(x1+12,y1+21,x2-12,y2-21)
    return image.crop(area).resize((W,H),Image.Resampling.LANCZOS)


def caption_image(scene,meme=False):
    image=Image.new('RGBA',(W,H))
    if not scene['caption'].strip():
        return image
    draw=ImageDraw.Draw(image);face=font(38 if meme else 34)
    caption=lines(draw,scene['caption'],face,440)
    while (len(caption)>3 or max(draw.textlength(line,font=face) for line in caption)>440) and face.size>14:
        face=font(face.size-2);caption=lines(draw,scene['caption'],face,440)
    top=146 if meme and scene['beat']=='hook' else 670 if meme else 690
    bottom=top+126
    draw.rounded_rectangle((38,top,502,bottom),12 if meme else 22,
                           fill=(255,219,54,255) if meme else (20,23,43,230))
    for i,line in enumerate(caption):
        draw.text((270,top+63+(i-(len(caption)-1)/2)*37),line,anchor='mm',font=face,
                  fill='#14131b' if meme else '#ffc17d' if scene['beat']=='payoff' else '#ffffff')
    return image


def effects(path,scenes,total):
    rate=24000;sample=array.array('h',[0])*(total*rate//FPS);offset=0
    for i,scene in enumerate(scenes):
        for j in range(2300):
            sample[offset+j]=int(3100*(1-j/2300)**2*math.sin(j*(.07+i*.025)))
        offset+=scene['frames']*rate//FPS
    with wave.open(str(path),'wb') as out:
        out.setparams((1,2,rate,0,'NONE','not compressed'));out.writeframes(sample.tobytes())


def main(plan,output):
    for index,shot in enumerate(plan['shots'],1):
        if plan.get('engine')!='original-episode-v2':
            reference(shot,shot['part']).save(output/f'reference-{index}.png')
        caption_image(shot,plan.get('profile',{}).get('arc')=='meme').save(output/f'caption-{index}.png')
    if plan.get('engine')!='original-episode-v2':
        effects(output/'effects.wav',plan['scenes'],plan['frames'])


if __name__=='__main__':
    main(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
