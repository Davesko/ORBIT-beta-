"""The files of one Etsy listing, made from a finished design. Runs in ORBIT's image runtime (it has Pillow); the
worker's own Python does not.

    python etsy_files.py preview SOURCE.png OUT.jpg
    python etsy_files.py pdf SOURCE.png OUT.pdf

preview  what shoppers see: at most 2000 px with MINTA across it, so the picture is not the product itself.
pdf      the file the buyer downloads: one printable page at 300 dpi.
"""
import sys
from PIL import Image,ImageDraw,ImageFont

def font(size):
 for path in ('/System/Library/Fonts/Helvetica.ttc','/System/Library/Fonts/Supplemental/Arial.ttf'):
  try:return ImageFont.truetype(path,size)
  except OSError:pass
 return ImageFont.load_default()

def preview(source,out):
 page=Image.open(source).convert('RGB');page.thumbnail((2000,2000))
 size=max(page.size)//7;mark=Image.new('RGBA',(int(max(page.size)*1.5),)*2,(0,0,0,0));draw=ImageDraw.Draw(mark);type_=font(size)
 for y in range(0,mark.size[1],int(size*2.6)):
  draw.text((size*(y//size%3),y),'MINTA   MINTA   MINTA',font=type_,fill=(120,120,120,70))
 mark=mark.rotate(32)
 left,top=(mark.size[0]-page.size[0])//2,(mark.size[1]-page.size[1])//2
 page.paste(mark.crop((left,top,left+page.size[0],top+page.size[1])),(0,0),mark.crop((left,top,left+page.size[0],top+page.size[1])))
 page.save(out,'JPEG',quality=88)

def pdf(source,out):
 Image.open(source).convert('L').save(out,'PDF',resolution=300)

if __name__=='__main__':
 {'preview':preview,'pdf':pdf}[sys.argv[1]](sys.argv[2],sys.argv[3])
