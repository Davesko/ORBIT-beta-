/* ORBIT 3 office: one pixel grid and palette for rooms, furniture and characters.
   Presentation only — room geometry, handlers, links and agent data are unchanged. */
const PixelOffice=(()=>{
 const INK='#151622';
 // Compact pixel art: "x,y,w,h,color[,class[,opacity]];…" in art units.
 const px=(spec)=>spec.split(';').filter(Boolean).map(s=>{const [x,y,w,h,c,cls,op]=s.split(',');return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${c}"${cls?` class="${cls}"`:''}${op?` opacity="${op}"`:''}/>`;}).join('');

 // ---------- Furniture (art units, drawn at 2× in rooms) ----------
 const F={
  desk:'1,12,31,2,#000,,.25;0,2,32,11,#151622;1,3,30,3,#b07a44;1,3,30,1,#c9915a;1,6,30,6,#7d5230;2,6,2,6,#5e3c22;28,6,2,6,#5e3c22;12,7,8,3,#6a4428;15,8,2,1,#d9b27a',
  monitor:'5,8,2,3,#2a2d3d;3,10,6,1,#2a2d3d;0,0,12,9,#151622;1,1,10,7,#23395e;2,2,6,1,#7fb2ff,po-scr;2,4,8,1,#4f7fc0,po-scr;2,6,4,1,#8fdc4a,po-scr',
  timeline:'5,8,2,3,#2a2d3d;3,10,6,1,#2a2d3d;0,0,14,9,#151622;1,1,12,7,#1b1d2b;2,2,4,1,#f29a5c;6,2,5,1,#7fb2ff;2,4,7,1,#8fdc4a;9,4,3,1,#ad8aee;2,6,10,1,#3b3d55;7,1,1,7,#e9e6f0,po-blink',
  shelf:'1,29,17,2,#000,,.25;0,0,18,30,#151622;1,1,16,28,#6e4630;1,9,16,1,#4a2f1f;1,18,16,1,#4a2f1f;2,3,2,6,#b0405a;4,2,2,7,#7fb2ff;6,4,3,5,#f2c76b;10,3,2,6,#8fdc4a;12,5,4,4,#ad8aee;2,12,3,6,#e08a2e;5,11,2,7,#5d4a8f;8,13,5,5,#d4d0e2;13,11,2,7,#2f7d6b;2,21,6,6,#a0603d;9,20,2,7,#7fb2ff;11,21,2,6,#b0405a;13,22,3,5,#f2c76b;1,27,16,2,#4a2f1f',
  plant:'2,13,7,1,#000,,.25;3,0,4,2,#7fbf5a;1,2,8,3,#5f9a4c;0,4,3,3,#4d8240;7,4,3,3,#4d8240;3,2,2,1,#9bd673;4,5,2,3,#3e6b34;1,8,8,5,#151622;2,8,6,4,#a0603d;2,8,6,1,#c07a4f',
  lamp:'0,0,7,5,#151622;1,1,5,3,#f5cf8c;2,1,2,1,#ffe7b4;3,5,1,11,#56433c;1,16,5,2,#332d36',
  rack:'0,0,10,26,#151622;1,1,8,24,#2b3044;2,3,6,2,#1b1f2d;2,7,6,2,#1b1f2d;2,11,6,2,#1b1f2d;2,15,6,2,#1b1f2d;2,19,6,2,#1b1f2d;7,3,1,1,#2f6a8a,po-led;7,7,1,1,#2f6a8a,po-led2;7,11,1,1,#8fdc4a,po-led;7,15,1,1,#2f6a8a,po-led2;7,19,1,1,#f2c76b,po-led',
  sofa:'1,11,27,2,#000,,.25;0,0,28,12,#151622;2,1,24,5,#594867;2,1,24,1,#786286;1,5,4,6,#443b56;23,5,4,6,#443b56;5,6,18,4,#6c577c;13,6,1,4,#43394d',
  window:'0,0,20,10,#151622;1,1,18,8,#2d3f6a;1,6,18,3,#3e5a8a;4,2,1,1,#e9e6f0;13,3,1,1,#e9e6f0;15,2,2,2,#f2e3a6;9,1,2,8,#6e4630;1,5,18,1,#6e4630;0,9,20,2,#4a2f1f',
  poster:'0,0,10,12,#151622;1,1,8,10,#ad8aee;3,3,4,4,#160d28;4,4,2,2,#8fdc4a;2,8,6,1,#160d28',
  board:'0,0,30,12,#9b99b0;1,1,28,10,#e9e6f0;3,3,2,1,#2f7d6b;4,4,2,1,#2f7d6b;6,3,1,1,#2f7d6b;9,3,10,1,#3b3d55;3,7,2,1,#b0405a;9,7,14,1,#3b3d55;22,3,5,3,#f2c76b',
  coffee:'0,0,8,10,#151622;1,1,6,8,#3b3d55;2,2,4,2,#1b1d2b;5,2,1,1,#8fdc4a,po-led;3,6,2,2,#e9e6f0',
  mic:'2,0,4,5,#151622;3,1,2,3,#d8d4e6;3,5,2,16,#6e6c82;0,21,8,2,#151622',
  mixer:'0,0,16,6,#151622;1,1,14,4,#2a2d3d;2,2,1,2,#f29a5c;4,2,1,2,#8fdc4a;6,2,1,2,#7fb2ff;8,2,1,2,#ad8aee;11,2,3,1,#8fdc4a,po-led;11,3,2,1,#f2c76b,po-led2',
  speaker:'0,0,5,8,#151622;1,1,3,6,#2a2d3d;1,4,3,2,#4b4f6a',
  clock:'1,0,5,7,#151622;0,1,7,5,#151622;1,1,5,5,#e9e6f0;3,2,1,2,#151622;4,3,1,1,#151622',
  crate:'0,0,12,9,#151622;1,1,10,7,#a0603d;1,4,10,1,#7d4a2c;5,1,2,7,#7d4a2c',
  trophy:'0,0,5,3,#f2c14e;1,3,3,1,#d9a53a;2,4,1,1,#d9a53a;1,5,3,1,#6e4630',
  papers:'0,0,6,3,#e9e6f0;1,1,4,1,#9b99b0;4,-1,4,3,#d4d0e2',
  onair:'0,0,17,6,#151622;1,1,15,4,#d64b3a,po-onair;3,2,11,2,#ffd3c8,,.8',
  chair:'2,0,6,6,#151622;3,1,4,4,#4b4f6a;1,5,8,3,#151622;2,5,6,2,#5a5f80;4,8,2,2,#151622;2,9,6,1,#151622'
 };
 const item=(name,x,y,s=2)=>`<g transform="translate(${Math.round(x)} ${Math.round(y)}) scale(${s})">${px(F[name])}</g>`;
 const rug=(x,y,w,h,a,b)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${INK}"/><rect x="${x+2}" y="${y+2}" width="${w-4}" height="${h-4}" fill="${a}"/><rect x="${x+6}" y="${y+6}" width="${w-12}" height="${h-12}" fill="${b}"/><rect x="${x+10}" y="${y+10}" width="${w-20}" height="${h-20}" fill="${a}"/>`;

 // ---------- Room themes ----------
 const THEMES={
  command:{wall:'#4a2a3a',trim:'#5a3448',base:'#2e1a26',floor:'url(#poCarpet)'},
  research:{wall:'url(#poStripe)',trim:'#5a4834',base:'#2a2018',floor:'url(#poWood)'},
  workshop:{wall:'#18223a',trim:'#7fe0ff',base:'#0e1524',floor:'url(#poServer)'},
  editing:{wall:'#2f3550',trim:'#3a4263',base:'#1e2238',floor:'url(#poWoodL)'},
  media:{wall:'#2f3550',trim:'#3a4263',base:'#1e2238',floor:'url(#poWoodL)'},
  audio:{wall:'url(#poPanel)',trim:'#544287',base:'#1f1833',floor:'url(#poFoam)'},
  office:{wall:'#2a3a33',trim:'#34483f',base:'#1b2620',floor:'url(#poTile)'},
  marketing:{wall:'#2a3a33',trim:'#34483f',base:'#1b2620',floor:'url(#poTile)'},
  lounge:{wall:'#3a2f46',trim:'#4a3c5a',base:'#241c2e',floor:'url(#poWood)'}
 };
 function furniture(kind,w,h){
  const cx=w/2,big=w>=230;let o='';
  if(kind==='command'){
   o+=item('window',w-64,6)+item('clock',w-92,10)+item('poster',22,6)+item('shelf',10,30);
   o+=rug(cx-62,h-84,124,50,'#6b3046','#8a4560')+item('chair',cx-10,46)+item('desk',cx-32,58)+item('monitor',cx-12,42)+item('trophy',cx+16,56)+item('papers',cx-26,60);
   o+=item('lamp',w-28,h-70)+item('plant',w-30,h-42);
  }else if(kind==='research'){
   o+=item('shelf',w-42,22)+(big?item('shelf',w-80,22):'')+item('poster',big?w-104:w-66,6);
   o+=item('chair',30,46)+item('desk',14,58)+item('monitor',30,42)+item('papers',54,58)+item('lamp',84,52);
   o+=rug(18,h-78,big?120:84,42,'#2f6b5a','#3c8270')+(big?item('sofa',w-76,h-44):'')+item('plant',w-28,h-40);
  }else if(kind==='workshop'){
   o+=item('rack',10,28)+item('rack',34,28)+(big?item('rack',58,28):'');
   o+=`<rect x="20" y="84" width="${Math.max(30,w-120)}" height="2" fill="#2f6a8a"/><rect x="${w-110}" y="84" width="2" height="14" fill="#2f6a8a"/>`;
   o+=item('chair',w-70,46)+item('desk',w-86,58)+item('monitor',w-82,42)+item('timeline',w-56,42)+item('crate',w-32,h-32);
  }else if(kind==='editing'||kind==='media'){
   o+=item('window',Math.round(w*.22),6)+item('poster',Math.round(w*.46),4)+(big?item('window',Math.round(w*.62),6):'');
   o+=rug(cx-78,h-86,156,58,'#3c4d7a','#536aa6')+item('chair',cx-10,46)+item('desk',cx-64,58)+item('desk',cx,58);
   o+=item('timeline',cx-56,40)+item('timeline',cx-14,36)+item('timeline',cx+28,40);
   o+=item('plant',8,32)+item('plant',w-28,32)+(big?item('sofa',12,h-40):'')+item('crate',w-34,h-34)+item('coffee',w-30,h-54);
  }else if(kind==='audio'){
   o+=item('onair',w-46,8)+item('speaker',12,32)+item('speaker',70,32)+item('desk',12,52)+item('mixer',28,46)+item('monitor',46,34);
   o+=item('mic',w-52,60)+rug(w-104,h-44,80,24,'#3d3163','#5d4a8f');
  }else if(kind==='office'||kind==='marketing'){
   o+=item('board',w-76,4)+(kind==='marketing'?item('poster',22,6):'')+item('chair',30,46)+item('desk',14,58)+item('monitor',30,42)+item('papers',58,58);
   if(big)o+=item('chair',cx+18,46)+item('desk',cx+2,58)+item('timeline',cx+16,42)+item('trophy',cx+40,54);
   o+=item('shelf',w-42,30)+item('crate',w-38,h-32)+item('crate',w-32,h-48)+item('plant',10,h-40)+(kind==='marketing'&&big?item('sofa',cx-28,h-42):'');
  }else{
   o+=item('window',cx-20,6)+item('poster',22,6)+rug(cx-70,h-84,140,54,'#4c3b52','#79617c')+item('sofa',cx-60,h-60)+item('sofa',cx+4,h-60)+item('crate',cx-12,h-90)+item('coffee',cx-8,h-100)+item('plant',10,32)+item('plant',w-28,32)+item('lamp',w-26,h-60);
  }
  return o;
 }
 function room(r){
  const p=SpaceMath.iso(r.x,r.y),w=Math.round(r.width*28),h=Math.round(r.height*28),t=THEMES[r.decor]||THEMES.lounge;
  let o=`<g class="room-floor pixel-room po-room" data-room="${xml(r.id)}" role="button" tabindex="0" aria-label="${xml(r.name)} · szoba szerkesztése" transform="translate(${p[0]} ${p[1]})" shape-rendering="crispEdges">`;
  o+=`<rect x="-3" y="5" width="${w+6}" height="${h+8}" fill="#080b14"/><rect width="${w}" height="${h}" fill="${INK}"/>`;
  o+=`<rect x="4" y="4" width="${w-8}" height="26" fill="${t.wall}"/><rect x="4" y="24" width="${w-8}" height="2" fill="${t.trim}" opacity="${r.decor==='workshop'?.55:1}"/><rect x="4" y="30" width="${w-8}" height="5" fill="${t.base}"/>`;
  o+=`<rect x="4" y="35" width="${w-8}" height="${h-39}" fill="${t.floor}"/><rect x="4" y="35" width="${w-8}" height="${h-39}" fill="${xml(r.floor||'#000')}" opacity=".12"/>`;
  o+=`<rect x="4" y="35" width="${w-8}" height="3" fill="#000" opacity=".22"/>`;
  o+=furniture(r.decor,w,h);
  o+=`<rect x="${Math.round(w/2-16)}" y="${h-6}" width="32" height="6" fill="#8b654b"/><rect x="${Math.round(w/2-13)}" y="${h-6}" width="26" height="3" fill="#b78a5b"/>`;
  o+=`<rect x="14" y="${h-3}" width="${w-28}" height="2" fill="${xml(r.accent||'#ad8aee')}"/>`;
  return o+'</g>';
 }
 const DEFS=`<pattern id="poWood" width="32" height="24" patternUnits="userSpaceOnUse">${px('0,0,32,24,#8a5a3b;0,10,32,2,#6e4630;0,22,32,2,#6e4630;20,0,2,10,#6e4630;8,12,2,10,#6e4630;2,2,12,2,#9c6a46;12,14,14,2,#9c6a46')}</pattern>
<pattern id="poWoodL" width="32" height="24" patternUnits="userSpaceOnUse">${px('0,0,32,24,#a8774c;0,10,32,2,#875b38;0,22,32,2,#875b38;24,0,2,10,#875b38;10,12,2,10,#875b38;2,2,14,2,#bb8a5b;14,14,12,2,#bb8a5b')}</pattern>
<pattern id="poCarpet" width="8" height="8" patternUnits="userSpaceOnUse">${px('0,0,8,8,#4e2236;0,0,4,4,#5a2a3e;4,4,4,4,#5a2a3e')}</pattern>
<pattern id="poServer" width="16" height="16" patternUnits="userSpaceOnUse">${px('0,0,16,16,#121a2a;0,0,16,2,#1d2c44;0,0,2,16,#1d2c44;8,8,2,2,#24385a')}</pattern>
<pattern id="poFoam" width="12" height="12" patternUnits="userSpaceOnUse">${px('0,0,12,12,#2c2346;2,2,4,4,#3a2f5e;8,8,2,2,#3a2f5e')}</pattern>
<pattern id="poPanel" width="16" height="26" patternUnits="userSpaceOnUse">${px('0,0,16,26,#3a2f5e;2,2,12,22,#463873;4,4,2,18,#544287;8,4,2,18,#544287')}</pattern>
<pattern id="poTile" width="16" height="16" patternUnits="userSpaceOnUse">${px('0,0,16,16,#2b3b33;0,0,8,8,#33473d;8,8,8,8,#33473d;0,0,16,1,#24322b;0,0,1,16,#24322b')}</pattern>
<pattern id="poStripe" width="12" height="26" patternUnits="userSpaceOnUse">${px('0,0,12,26,#3f3326;0,0,6,26,#47392b;2,10,2,2,#5a4834')}</pattern>`;

 // ---------- Characters: one style, own silhouettes (art units, feet at the bottom) ----------
 const S={
  king:[18,22,'3,2,12,9,#151622;1,10,16,11,#151622;16,7,2,13,#151622;4,1,10,2,#151622;5,1,8,1,#f2c14e;5,0,1,1,#f2c14e;8,0,2,1,#f2c14e;12,0,1,1,#f2c14e;8,1,2,1,#d64b6a;4,3,10,2,#3b2a3a;5,5,8,4,#f1c7a1;7,6,1,2,#151622;10,6,1,2,#151622;7,6,1,1,#fff,,.85;10,6,1,1,#fff,,.85;5,8,8,3,#6b4a36;8,8,2,1,#b0405a;2,11,14,9,#b0405a;2,11,2,9,#8a2f45;14,11,2,9,#8a2f45;5,12,8,6,#3a2c44;8,12,2,6,#f2c14e;4,10,10,2,#e9e6f0;6,10,1,1,#151622;11,11,1,1,#151622;6,18,2,2,#2a2433;10,18,2,2,#2a2433;16,8,1,10,#d4d0e2;15,15,3,1,#f2c14e'],
  cyberfox:[20,18,'3,0,4,4,#151622;10,0,4,4,#151622;2,3,13,8,#151622;3,9,12,9,#151622;13,7,7,9,#151622;4,1,2,3,#e07a2e;11,1,2,3,#e07a2e;5,2,1,2,#f2c7a1;11,2,1,2,#f2c7a1;3,4,11,6,#e07a2e;5,7,7,3,#f3e6d8;8,8,1,1,#151622;5,5,1,2,#151622;11,5,1,2,#151622;5,5,1,1,#7fe0ff;11,5,1,1,#7fe0ff;4,10,10,1,#2f7d6b;12,10,2,3,#2f7d6b;4,11,9,5,#e07a2e;6,11,5,4,#f3e6d8;14,8,5,7,#e07a2e;16,8,3,2,#f3e6d8;14,13,5,2,#c4622d;4,16,3,1,#4a2f1f;10,16,3,1,#4a2f1f'],
  pikachu:[16,18,'6,0,4,3,#151622;7,2,2,3,#151622;3,4,10,13,#151622;2,6,12,9,#151622;12,8,4,8,#151622;7,0,2,2,#7fe0ff,po-led;7,2,1,3,#2a2433;4,5,8,11,#f2c76b;3,7,10,7,#f2c76b;4,5,3,1,#ffe7a6;6,10,4,4,#fff0c4;5,7,2,2,#151622;9,7,2,2,#151622;5,7,1,1,#fff;9,7,1,1,#fff;4,10,1,1,#f29a5c;11,10,1,1,#f29a5c;7,9,2,1,#151622,,.6;13,9,2,2,#7fe0ff;13,11,2,2,#a6e4ff;13,13,2,2,#7fe0ff;5,16,2,1,#b8862f;9,16,2,1,#b8862f'],
  jellyfish:[16,20,'3,0,10,2,#151622;2,1,12,8,#151622;1,8,14,3,#151622;3,10,3,7,#151622;6,10,2,9,#151622;9,10,2,8,#151622;11,10,2,6,#151622;3,1,10,8,#9a81c3;5,2,3,1,#d8c9ff;4,3,1,2,#d8c9ff;6,5,1,2,#151622;9,5,1,2,#151622;7,7,2,1,#151622,,.6;2,9,12,1,#7b62a8;4,11,1,5,#bc9fe1;6,11,1,7,#bc9fe1;9,11,1,6,#bc9fe1;11,11,1,4,#bc9fe1;6,17,1,1,#7fe0ff;9,16,1,1,#7fe0ff'],
  hacker:[18,22,'4,0,10,1,#151622;3,1,12,11,#151622;2,11,14,8,#151622;4,18,10,4,#151622;4,1,10,10,#39354b;12,2,2,8,#2a2738;5,1,4,1,#4b4766;6,4,6,6,#151622;7,6,1,1,#7fe0ff;10,6,1,1,#7fe0ff;6,9,6,1,#7fe0ff,,.25;3,12,12,6,#39354b;4,13,10,5,#151622;5,13,8,4,#9b99b0;8,15,2,1,#8fdc4a;3,17,12,1,#6e6c82;3,16,1,1,#c98b67;14,16,1,1,#c98b67;5,19,3,2,#23253a;10,19,3,2,#23253a'],
  robot:[18,20,'7,0,4,4,#151622;3,3,12,9,#151622;0,11,18,7,#151622;5,16,8,4,#151622;8,0,2,1,#ff6b6b,po-onair;8,1,2,2,#6e6c82;4,4,10,7,#b9c3d6;4,4,10,1,#d7dde9;5,5,8,5,#151622;6,6,2,2,#2fb3e0;10,6,2,2,#2fb3e0;7,9,4,1,#2fb3e0,,.6;3,6,1,3,#6e6c82;14,6,1,3,#6e6c82;3,12,12,4,#6c7aa0;6,13,6,2,#23395e;7,13,1,1,#8fdc4a,po-led;9,13,1,1,#f2c76b,po-led2;1,12,2,4,#8a95ad;15,12,2,4,#8a95ad;6,17,6,2,#2a2d3d;8,18,2,1,#8a95ad'],
  wizard:[16,28,'6,0,4,3,#151622;5,2,6,4,#151622;4,5,8,4,#151622;1,8,14,3,#151622;2,10,12,17,#151622;13,3,3,24,#151622;7,0,2,2,#754b9c;6,2,4,3,#754b9c;5,5,6,3,#754b9c;7,3,1,1,#f2c76b;9,6,1,1,#f2c76b;5,7,6,1,#ac7bb7;2,9,12,1,#754b9c;5,10,6,4,#d7ae85;6,11,1,1,#151622;9,11,1,1,#151622;4,13,8,4,#e9e6f0;5,17,6,2,#e9e6f0;7,19,2,1,#e9e6f0;3,15,10,11,#6f478e;5,15,6,4,#e9e6f0;3,25,10,1,#ac7bb7;11,16,2,9,#57367a;14,7,1,19,#a27a4f;13,4,3,3,#c2a1dd,po-led'],
  dragon:[22,18,'0,2,8,8,#151622;13,0,8,8,#151622;20,3,2,4,#151622;5,6,13,9,#151622;0,11,7,4,#151622;6,14,11,4,#151622;1,3,6,6,#64517a;3,4,1,4,#4a3c5c;5,4,1,4,#4a3c5c;14,2,6,5,#87a477;20,4,1,2,#87a477;15,0,1,2,#c1a266;18,0,1,2,#c1a266;17,3,2,2,#151622;17,3,1,1,#fff;20,5,1,1,#151622;14,6,7,1,#6b8a5c;6,7,11,7,#87a477;9,10,7,4,#c9d9b6;8,7,1,1,#64517a;11,7,1,1,#64517a;14,7,1,1,#64517a;1,12,5,2,#87a477;0,11,2,2,#64517a;7,14,3,3,#6b8a5c;13,14,3,3,#6b8a5c'],
  goblin:[18,20,'4,0,10,11,#151622;0,4,5,4,#151622;13,4,5,4,#151622;2,10,14,8,#151622;4,17,10,3,#151622;6,1,6,2,#7a3fc0;5,2,8,8,#7a3fc0;11,3,2,7,#5b2f99;6,1,2,1,#9a62e0;6,4,6,5,#7cc04a;1,5,4,2,#7cc04a;13,5,4,2,#7cc04a;2,6,2,1,#5f9a4c;14,6,2,1,#5f9a4c;7,5,1,2,#f2a33a;10,5,1,2,#f2a33a;7,5,1,1,#ffe7a6;10,5,1,1,#ffe7a6;7,8,4,1,#151622;4,11,10,6,#5b2f99;12,11,2,6,#47237a;7,11,5,5,#151622;8,12,3,3,#e9e6f0;8,13,1,1,#2f7d6b;9,14,1,1,#2f7d6b;10,12,1,1,#2f7d6b;3,14,2,2,#7cc04a;12,14,2,2,#7cc04a;6,17,2,2,#2b2140;10,17,2,2,#2b2140;5,19,3,1,#7cc04a;10,19,3,1,#7cc04a'],
  astronaut:[16,22,'3,0,10,1,#151622;2,1,12,10,#151622;1,10,14,8,#151622;3,17,10,5,#151622;3,1,10,9,#e9e6f0;4,3,8,5,#2f6a8a;5,3,2,1,#a6e4ff;9,6,2,1,#a6e4ff,,.6;12,0,1,1,#f29a5c,po-led;2,11,12,6,#d7dbe6;1,11,1,5,#9b99b0;14,11,1,5,#9b99b0;6,12,4,3,#b0405a;7,13,1,1,#8fdc4a,po-led;4,17,3,3,#d7dbe6;9,17,3,3,#d7dbe6;4,20,3,1,#6e6c82;9,20,3,1,#6e6c82'],
  samurai:[18,22,'2,0,14,5,#151622;3,4,12,7,#151622;1,10,16,8,#151622;4,17,10,5,#151622;16,5,2,13,#151622;2,0,2,2,#f2c14e;14,0,2,2,#f2c14e;8,0,2,2,#f2c14e;3,1,12,4,#8a2f45;5,5,8,4,#f1c7a1;7,6,1,1,#151622;10,6,1,1,#151622;5,8,8,2,#2a2433;2,11,14,6,#b0405a;2,11,3,3,#8a2f45;13,11,3,3,#8a2f45;5,13,8,1,#8a2f45;5,15,8,1,#8a2f45;4,16,10,1,#f2c14e;5,18,3,3,#2a2433;10,18,3,3,#2a2433;16,6,1,11,#7fe0ff,po-led;15,14,3,1,#f2c14e'],
  raven:[18,20,'5,1,8,8,#151622;13,3,4,4,#151622;3,7,12,10,#151622;0,8,4,7,#151622;14,8,4,7,#151622;6,16,6,4,#151622;6,2,6,6,#44445e;9,4,2,2,#f2c76b;10,4,1,1,#151622;13,4,3,2,#b88c55;16,5,1,1,#b88c55;4,8,10,8,#383a51;6,10,6,5,#53506b;1,9,3,5,#2c2d40;14,9,3,5,#2c2d40;1,13,3,1,#595571;14,13,3,1,#595571;7,16,4,2,#2c2d40;6,18,2,2,#b88c55;10,18,2,2,#b88c55'],
  operator:[16,22,'3,2,10,10,#151622;2,3,12,8,#151622;1,11,14,7,#151622;3,17,10,5,#151622;3,3,10,2,#3b2a3a;3,5,1,4,#3b2a3a;12,5,1,4,#3b2a3a;4,5,8,6,#e8b48f;4,5,3,1,#3b2a3a;10,5,2,1,#3b2a3a;6,7,1,2,#151622;9,7,1,2,#151622;6,7,1,1,#fff,,.85;9,7,1,1,#fff,,.85;7,10,2,1,#151622,,.55;4,11,8,5,{c};2,12,2,4,{c};12,12,2,4,{c};10,11,2,5,#000,,.18;2,16,2,1,#e8b48f;12,16,2,1,#e8b48f;4,16,8,1,#2a2433;4,17,3,3,#2c3550;9,17,3,3,#2c3550;4,20,3,1,#2a2433;9,20,3,1,#2a2433;2,6,2,3,#151622;12,6,2,3,#151622;4,9,2,1,#151622;4,9,1,1,#7fe0ff'],
 };
 S.hologram=S.robot;
 function character(color,type){
  const c=/^#[0-9a-f]{6}$/i.test(color)?color:'#ad8aee';
  const [w,h,art]=S[type]||S.operator,scale=2.5;
  const body=px(art.replaceAll('{c}',c));
  const holo=type==='hologram';
  return `<g class="pixel-character po-character" shape-rendering="crispEdges"><rect x="-13" y="2" width="26" height="4" fill="#090c16" opacity=".45"/><g transform="translate(${-w*scale/2} ${4-h*scale}) scale(${scale})"${holo?' opacity=".7"':''}>${holo?body.replace(/fill="#[0-9a-f]{6}"/gi,m=>m):body}${holo?`<rect x="0" y="4" width="${w}" height="1" fill="#a6e4ff" opacity=".35"/><rect x="0" y="10" width="${w}" height="1" fill="#a6e4ff" opacity=".35"/><rect x="0" y="15" width="${w}" height="1" fill="#a6e4ff" opacity=".35"/>`:''}</g></g>`;
 }
 return {room,character,DEFS,F,px,item,rug,THEMES,S};
})();

// Characters: one unified style; keys stay identical so saved appearance choices keep working.
characterMarkup=PixelWorld.character=PixelOffice.character;
for(const look of looks)if(look[0]==='pikachu')look[1]='Szikra · elektromos lény';
if(!looks.some(l=>l[0]==='king'))looks.splice(1,0,['king','Király']);
{
 const characterBeforeOffice=characterFor;
 const defaults={KING:'king',Atlas:'cyberfox',Pulse:'pikachu',Echo:'jellyfish',Scout:'hacker',Pixel:'robot',Lex:'wizard',Reach:'dragon',Vega:'goblin'};
 characterFor=function(id){
  if(appearance.characters[id]&&looks.some(l=>l[0]===appearance.characters[id]))return appearance.characters[id];
  const name=typeof state!=='undefined'?state?.agents.find(a=>a.id===id)?.name:null;
  return defaults[name]||characterBeforeOffice(id);
 };
}

// Rooms: themed interiors by the room's saved "Berendezés" (decor); geometry and handlers unchanged.
roomMarkup=PixelWorld.room=PixelOffice.room;
{
 const buildBeforeOffice=buildStation;
 buildStation=function(){
  buildBeforeOffice();
  $('station').querySelector('defs').insertAdjacentHTML('beforeend',PixelOffice.DEFS);
 };
}

// Motion: eased walking (no linear jumps), smooth footstep bob, 30 fps.
PixelMotion.pose=function(room,seat,index,t,working,reduced){
 const home={x:seat.x,y:seat.y},left={x:room.x+room.width*.3,y:room.y+room.height-2.2},right={x:room.x+room.width*.7,y:room.y+room.height-2.4},mid={x:room.x+room.width*.5,y:room.y+room.height-1.8};
 if(reduced||working)return {...home,sitting:working,walking:false};
 const target=[left,right,mid][index%3],phase=(t+index*3719)%32000;
 const ease=n=>n<.5?4*n*n*n:1-Math.pow(-2*n+2,3)/2,lerp=(a,b,n)=>{n=ease(Math.min(1,Math.max(0,n)));return {x:a.x+(b.x-a.x)*n,y:a.y+(b.y-a.y)*n};};
 if(phase<7000)return {...home,sitting:true,walking:false};
 if(phase<14000)return {...lerp(home,target,(phase-7000)/7000),walking:true,sitting:false};
 if(phase<19000)return {...target,walking:false,sitting:false};
 if(phase<27000)return {...lerp(target,home,(phase-19000)/8000),walking:true,sitting:false};
 return {...home,sitting:true,walking:false};
};
animateStation=function(t){requestAnimationFrame(animateStation);if(document.hidden||$('studioApp').hidden||t-lastFrame<33)return;lastFrame=t;const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches||document.documentElement.dataset.motion==='off';
 if(!gesture&&!$('modal').open){const working=new Set((state?.jobs||[]).filter(j=>j.status==='running').map(j=>j.agent));for(const [id,v]of spriteElements){const pose=PixelMotion.pose(v.room,v.seat,v.index+id.charCodeAt(0),t,working.has(id),reduced),type=characterFor(id),floating=['jellyfish','hologram'].includes(type);const before=v.motionPosition||{x:v.seat.x,y:v.seat.y},dt=Math.min(.2,Math.max(0,(t-(v.motionTime||t))/1000)),distance=Math.hypot(pose.x-before.x,pose.y-before.y),step=Math.min(distance,dt*2.4);const position=distance>0?{x:before.x+(pose.x-before.x)*step/distance,y:before.y+(pose.y-before.y)*step/distance}:before;v.motionPosition=reduced?{x:pose.x,y:pose.y}:position;v.motionTime=t;if(working.has(id)&&distance>.12){pose.sitting=false;pose.walking=true;}const p=iso(v.motionPosition.x,v.motionPosition.y);v.el.setAttribute('transform',`translate(${p[0].toFixed(1)} ${p[1].toFixed(1)})`);agentPositions.set(id,p);v.el.classList.toggle('walking',pose.walking&&!floating);v.el.classList.toggle('sitting',pose.sitting&&!floating);
  let chair=v.el.querySelector('.pixel-seat');if(!chair){chair=document.createElementNS('http://www.w3.org/2000/svg','g');chair.classList.add('pixel-seat');chair.setAttribute('shape-rendering','crispEdges');chair.innerHTML='<rect x="-12" y="-6" width="24" height="12" fill="#151622"/><rect x="-10" y="-5" width="20" height="8" fill="#5a5f80"/><rect x="-10" y="-5" width="20" height="2" fill="#6f7599"/><rect x="-2" y="6" width="4" height="5" fill="#151622"/><rect x="-8" y="10" width="16" height="2" fill="#151622"/>';v.el.insertBefore(chair,v.el.querySelector('.figure'));}chair.style.display=pose.sitting&&!floating?'':'none';
  const bounce=reduced?0:floating?Math.sin(t/520+v.index)*2.2:pose.walking?-Math.abs(Math.sin(t/150+v.index))*2.4:working.has(id)?-Math.abs(Math.sin(t/120))*1.2:Math.sin(t/900+v.index)*.5;
  v.el.querySelector('.figure').setAttribute('transform',pose.sitting&&!floating?`translate(0 ${(4+bounce).toFixed(2)}) scale(1 .9)`:`translate(0 ${bounce.toFixed(2)})`);v.el.querySelector('.work-light').style.display=working.has(id)?'':'none';}}
 if(t-linkFrame>120){linkFrame=t;updateLinks();}
};

// Data path: a pipe for every handoff; delivered paths glow, live deliveries carry moving packets.
{
 const linksBeforeOffice=updateLinks;
 updateLinks=function(force=false){
  linksBeforeOffice(force);
  const root=$('links');if(!root||!state)return;
  for(const node of root.querySelectorAll('[data-connection]')){
   const visible=node.querySelector('.connection-visible');if(!visible)continue;
   const id='po-path-'+node.dataset.connection.replace(/[^a-zA-Z0-9_-]/g,'');
   if(!visible.id)visible.id=id;
   let under=node.querySelector('.po-pipe');
   if(!under){
    under=document.createElementNS('http://www.w3.org/2000/svg','path');under.classList.add('po-pipe');under.setAttribute('fill','none');under.setAttribute('pointer-events','none');node.insertBefore(under,visible);
    const flow=document.createElementNS('http://www.w3.org/2000/svg','path');flow.classList.add('po-flow');flow.setAttribute('fill','none');flow.setAttribute('pointer-events','none');node.insertBefore(flow,visible.nextSibling);
    const packets=document.createElementNS('http://www.w3.org/2000/svg','g');packets.classList.add('po-packets');packets.setAttribute('pointer-events','none');
    packets.innerHTML=[0,1.6].map((delay,i)=>`<rect x="-4" y="-4" width="8" height="8" fill="${i?'#c7b0ff':'#8fdc4a'}" stroke="#151622" stroke-width="1.5"><animateMotion dur="3.2s" begin="${delay}s" repeatCount="indefinite" calcMode="spline" keyTimes="0;1" keySplines=".45 0 .55 1"><mpath href="#${id}"/></animateMotion></rect>`).join('');
    node.append(packets);
   }
   const d=visible.getAttribute('d')||'';
   node.querySelector('.po-pipe').setAttribute('d',d);node.querySelector('.po-flow').setAttribute('d',d);
   const flowing=node.classList.contains('flowing'),received=node.classList.contains('has-receipt');
   node.classList.toggle('po-received',received&&!flowing);node.classList.toggle('po-live',flowing);
  }
 };
}

// Step bar: who works on which stage; a click opens that agent on that exact job.
{
 const STAGE={research:'Trend',producer:'Tervezés',source:'Források',transcript:'Átirat',selection:'Történet',layout:'Képkivágás',render:'Vágás',metadata:'Csomagolás',verify:'Ellenőrzés'};
 const STATUS={done:'✓ kész',running:'● dolgozik',failed:'! hiba',blocked:'⊘ blokkolt',cancelled:'■ leállítva',queued:'○ vár'};
 const progressBeforeOffice=renderProgress;
 renderProgress=function(){
  progressBeforeOffice();
  const host=$('workflowSteps'),runs=state?.workflow_runs||[],run=runs.find(r=>r.id===viewRun)||runs[0];if(!host||!run)return;
  const key='po:'+JSON.stringify(run.jobs.map(j=>[j.id,j.status,j.agent,characterFor(j.agent)]));if(host.dataset.poKey===key&&host.querySelector('.po-step'))return;host.dataset.poKey=key;
  host.replaceChildren(...run.jobs.map((j,i)=>{
   let payload={};try{payload=JSON.parse(j.payload||'{}');}catch{}
   const a=state.agents.find(x=>x.id===j.agent),b=el('button','po-step '+j.status);
   b.innerHTML=`<svg viewBox="-20 -62 40 70" width="24" height="42" aria-hidden="true">${characterMarkup(a?.color||'#ad8aee',characterFor(j.agent))}</svg>`;
   const text=el('span','po-step-text');text.append(el('small','',(i+1)+' · '+(STAGE[payload.auto_step]||payload.step||'Lépés')),el('strong','',a?.name||agentName(j.agent)||'Ügynök'),el('em','',STATUS[j.status]||j.status));b.append(text);
   b.title=(a?.name||'Ügynök')+' · '+jobLabel(j)+' · kattints a részletekért';b.setAttribute('aria-label',b.title);
   b.onclick=()=>openJob(j.agent,j.id);return b;
  }));
 };
}
