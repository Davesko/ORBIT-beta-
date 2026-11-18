/* ORBIT workshop life (2026-11-12, owner: "videójáték feeling", more actions, more rooms, easy delete).
   Rooms are redrawn with more detail and every piece of furniture leaves an activity spot. Idle characters pick
   spots by themselves (sit at the computer, on the sofa or the floor, play, solve a Rubik cube, smoke at the
   window, drink coffee, run a lap…). Only a real running job sends a character to a desk to type: the animation
   never implies AI work that is not happening. Geometry, handlers, links and agent data stay unchanged. */
const PixelLife=(()=>{
 const O=PixelOffice,INK='#151622';
 const px=O.px,F=O.F;
 Object.assign(F,{
  sofa:'1,11,27,2,#000,,.3;0,0,28,12,#151622;2,1,24,5,#3a5f8f;2,1,24,1,#6a92c5;1,5,4,6,#2c4a70;23,5,4,6,#2c4a70;5,6,18,4,#4f78ab;13,6,1,4,#2c4a70;6,7,6,1,#6a92c5;15,7,6,1,#6a92c5',
  tv:'0,0,26,15,#151622;1,1,24,12,#1b2a48;2,2,22,10,#2d4f8a,pl-tv;3,3,9,4,#7fb2ff,pl-tv2,.55;14,6,8,5,#ad8aee,pl-tv3,.55;11,15,4,2,#151622;7,16,12,1,#151622',
  tvstand:'0,0,30,8,#151622;1,1,28,6,#4a3a5e;2,2,12,4,#3a2d4c;16,2,12,4,#3a2d4c;19,3,5,2,#1b1d2b;23,3,1,1,#8fdc4a,po-led',
  beanbag:'1,2,12,7,#151622;0,4,14,5,#151622;2,3,10,5,{c};1,5,12,3,{d};3,3,4,1,#ffffff,,.25',
  arcade:'0,0,14,28,#151622;1,1,12,26,#5b2f99;2,2,10,3,#ff5c8f,pl-neon;2,6,10,8,#0f1424;3,7,8,6,#2fb3e0,pl-tv;4,9,3,2,#8fdc4a,pl-tv2;1,15,12,4,#47237a;3,16,2,2,#e9e6f0;8,16,2,2,#ff5c8f;10,16,2,2,#f2c76b;2,20,10,6,#3a1f66;4,22,6,1,#ad8aee',
  sidetable:'0,0,12,3,#151622;1,1,10,1,#b07a44;2,3,1,5,#151622;9,3,1,5,#151622;4,-2,3,2,#e9e6f0',
  bigwindow:'0,0,34,12,#151622;1,1,32,10,#1a2442;1,7,32,4,#22305a;3,5,3,5,#2a3560;7,3,4,7,#2a3560;13,6,3,4,#2a3560;18,2,5,8,#2a3560;25,4,4,6,#2a3560;30,6,2,4,#2a3560;4,6,1,1,#f2e3a6,po-led;8,4,1,1,#f2e3a6,po-led2;9,7,1,1,#f2e3a6;19,3,1,1,#f2e3a6,po-led;21,5,1,1,#f2e3a6;20,8,1,1,#f2e3a6,po-led2;26,5,1,1,#f2e3a6;27,8,1,1,#f2e3a6,po-led;5,2,1,1,#e9e6f0;28,2,1,1,#e9e6f0;16,0,2,12,#4a2f1f;0,11,34,2,#4a2f1f',
  ashtray:'0,0,5,2,#6e6c82;1,0,3,1,#2a2d3d;3,-1,2,1,#e9e6f0',
  fridge:'0,0,13,26,#151622;1,1,11,24,#d7dde9;1,9,11,1,#9b99b0;9,3,1,4,#6e6c82;9,12,1,6,#6e6c82;2,2,3,1,#ffffff;3,13,3,2,#f29a5c;6,14,2,2,#8fdc4a;2,19,2,2,#7fb2ff',
  counter:'0,2,40,11,#151622;1,3,38,3,#d4d0e2;1,6,38,6,#6e4630;3,7,8,4,#5e3c22;13,7,8,4,#5e3c22;23,7,8,4,#5e3c22;33,7,5,4,#5e3c22;7,9,1,1,#c9915a;17,9,1,1,#c9915a;27,9,1,1,#c9915a;14,3,8,2,#9b99b0;17,1,2,2,#9b99b0;28,0,3,3,#e9e6f0;32,0,3,3,#7fb2ff;3,-3,6,5,#151622;4,-2,4,3,#3b3d55;7,-2,1,1,#8fdc4a,po-led',
  table:'2,0,16,2,#151622;0,2,20,4,#151622;1,1,18,4,#c9915a;1,4,18,1,#9c6a46;9,6,2,4,#151622;6,9,8,1,#151622;4,0,3,2,#e9e6f0;12,0,3,2,#f2c76b;8,1,4,1,#d64b3a',
  stool:'0,0,6,2,#151622;1,0,4,1,#ad8aee;1,2,1,4,#151622;4,2,1,4,#151622',
  treadmill:'0,3,28,6,#151622;1,4,26,4,#9b99b0;2,5,24,2,#3b3d55,pl-belt;22,-6,2,10,#151622;19,-8,8,3,#151622;20,-7,6,1,#2fb3e0,po-led;0,9,3,2,#151622;25,9,3,2,#151622;1,4,26,1,#d7dde9',
  dumbbells:'0,2,18,7,#151622;1,3,16,5,#4b4f6a;2,0,2,3,#151622;14,0,2,3,#151622;3,4,3,2,#d64b3a;7,4,4,2,#2fb3e0;12,4,3,2,#8fdc4a',
  yogamat:'0,0,22,6,#151622;1,1,20,4,#2f7d6b;1,1,20,1,#3c8270;19,1,2,4,#25614f',
  neon:'0,0,22,7,#151622;1,1,20,5,#160d28;3,2,3,3,#ff5c8f,pl-neon;7,2,3,3,#3ff0e0,pl-neon2;11,2,3,3,#f2c76b,pl-neon;15,2,4,3,#ad8aee,pl-neon2',
  armchair:'0,2,14,11,#151622;1,3,12,6,#2f6b5a;1,3,12,1,#3c8270;0,6,3,7,#25564a;11,6,3,7,#25564a;3,8,8,4,#3c8270;1,13,2,1,#151622;11,13,2,1,#151622',
  armfront:'0,6,3,7,#25564a;11,6,3,7,#25564a;3,10,8,2,#3c8270',
  sofafront:'1,5,4,6,#2c4a70;23,5,4,6,#2c4a70;5,8,18,2,#4f78ab;0,11,28,1,#151622',
  monstera:'5,10,2,8,#3e6b34;1,0,5,4,#4d8240;6,1,5,4,#5f9a4c;0,4,6,4,#5f9a4c;6,5,6,4,#4d8240;2,8,4,3,#7fbf5a;7,9,4,3,#5f9a4c;2,17,8,5,#151622;3,17,6,4,#d7dde9;3,17,6,1,#ffffff',
  firepit:'0,4,16,5,#151622;1,5,14,3,#6e6c82;2,5,12,1,#9b99b0;4,3,8,2,#5e3c22;5,0,2,4,#f29a5c,pl-flame;8,-2,2,6,#f2c14e,pl-flame2;10,1,2,3,#d64b3a,pl-flame;7,2,2,2,#ffe7a6,pl-flame2',
  deckchair:'0,4,14,3,#151622;1,4,12,2,#e0a85a;1,0,2,5,#151622;2,1,1,3,#e0a85a;1,7,1,3,#151622;12,7,1,3,#151622;3,5,9,1,#b07a44',
  cat:'1,2,8,4,#151622;0,3,10,2,#151622;2,3,6,2,#e08a2e;7,1,3,3,#151622;8,2,1,1,#e08a2e;0,1,2,3,#e08a2e,pl-tail;3,4,1,1,#c4622d',
  globe:'2,0,5,5,#151622;3,1,3,3,#2f7d6b;3,1,1,1,#7fb2ff;4,5,1,3,#151622;2,8,5,2,#151622',
  dualmon:'0,0,12,9,#151622;1,1,10,7,#23395e;2,2,6,1,#7fb2ff,po-scr;2,4,8,1,#8fdc4a,po-scr;14,0,12,9,#151622;15,1,10,7,#1b1d2b;16,2,4,4,#ff5c8f,po-scr;21,2,3,5,#3ff0e0,po-scr;5,9,2,2,#151622;19,9,2,2,#151622;3,10,20,1,#151622',
  lapback:'0,0,8,5,#151622;1,1,6,3,#9b99b0;3,2,2,1,#e9e6f0',
  cooler:'1,0,6,7,#151622;2,1,4,5,#7fe0ff,,.7;0,7,8,11,#151622;1,8,6,9,#d7dde9;3,10,2,1,#2fb3e0',
  bag:'3,0,2,4,#6e6c82;1,4,6,16,#151622;2,5,4,14,#b0405a;2,5,4,1,#d65a6a;3,20,2,2,#151622',
  whiteboard:'0,0,30,14,#9b99b0;1,1,28,11,#f4f2f8;3,3,8,1,#2fb3e0;3,5,12,1,#3b3d55;3,8,6,1,#d64b3a;18,3,8,6,#f2c76b,,.7;18,3,8,1,#e0a85a;0,13,30,1,#6e6c82',
  bulbs:'0,0,1,1,#f2e3a6,po-led;6,1,1,1,#ffb26b,po-led2;12,0,1,1,#f2e3a6,po-led;18,1,1,1,#ffb26b,po-led2;24,0,1,1,#f2e3a6,po-led;30,1,1,1,#ffb26b,po-led2',
  books:'0,4,8,2,#b0405a;1,2,6,2,#2f7d6b;0,0,7,2,#f2c76b'
 });
 const item=(name,x,y,s=2,vars)=>{let a=F[name];if(vars)for(const k in vars)a=a.replaceAll('{'+k+'}',vars[k]);return `<g transform="translate(${Math.round(x)} ${Math.round(y)}) scale(${s})">${px(a)}</g>`;};
 const rug=O.rug;

 // ---------- Rooms: themes, detail and activity spots ----------
 const THEMES={...O.THEMES,
  gaming:{wall:'#1c1230',trim:'#ff5c8f',base:'#120a20',floor:'url(#plGrid)'},
  kitchen:{wall:'url(#plTileWall)',trim:'#d7dde9',base:'#3a3b51',floor:'url(#plChecker)'},
  gym:{wall:'#3a4152',trim:'#f29a5c',base:'#232835',floor:'url(#plGymFloor)'},
  terrace:{wall:'url(#plSky)',trim:'#6e4630',base:'#4a2f1f',floor:'url(#plDeck)'},
  library:{wall:'url(#poStripe)',trim:'#c9915a',base:'#24180f',floor:'url(#poWood)'},
  server:{wall:'#121a2a',trim:'#2fb3e0',base:'#0b111c',floor:'url(#poServer)'}};
 const SPOTS=new Map();
 function layout(kind,w,h){
  const cx=Math.round(w/2),big=w>=280,deep=h>=250;let o='';const spots=[];
  const spot=(type,x,y,extra={})=>spots.push({type,x:Math.round(x),y:Math.round(y),...extra});
  const pc=(x,y,screen='lapback')=>{o+=item('chair',x-10,y-34)+item('desk',x-32,y-20)+(screen==='dualmon'?item('dualmon',x-26,y-40):screen==='monitor'?item('monitor',x-12,y-38):item('lapback',x-8,y-25));spot('pc',x,y,{screen});};
  const sofa=(x,y)=>{o+=item('sofa',x,y);spot('sofa',x+16,y+20,{ox:-16,oy:-20});spot('sofa',x+40,y+20,{ox:-40,oy:-20});};
  const bean=(x,y,c='#d65a6a',d='#b8475a')=>{o+=item('beanbag',x-14,y-14,2,{c,d});spot('beanbag',x,y-2);};
  const floor=(x,y)=>spot('floor',x,y);
  const win=(x,y=6,big=false)=>{o+=big?item('bigwindow',x,y):item('window',x,y);spot('smoke',x+(big?34:20),y+62,{prop:'ashtray'});o+=item('ashtray',x+(big?44:30),y+66,1.5);};
  const coffee=(x,y)=>{o+=item('coffee',x,y);spot('coffee',x+8,y+40);};
  const read=(x,y)=>{o+=item('armchair',x,y);spot('read',x+14,y+24,{ox:-14,oy:-24});};
  switch(kind){
  case 'command':
   win(cx-34,4,true);o+=item('poster',18,6)+item('clock',w-34,10)+item('plant',8,40)+item('monstera',w-30,36);
   pc(cx-48,108,'monitor');pc(cx+48,108,'monitor');o+=item('trophy',cx+66,82);
   o+=rug(cx-62,h-64,124,46,'#6b3046','#8a4560');floor(cx-24,h-34);floor(cx+26,h-30);
   if(big||deep){sofa(w-76,h-58);o+=item('lamp',16,h-64);}else o+=item('lamp',14,h-60);
   break;
  case 'research':
   win(18,6);o+=item('shelf',w-42,22)+(big?item('shelf',w-80,22):'')+item('poster',big?w-104:w-66,6)+item('globe',w-64,h-40);
   pc(70,108,'monitor');o+=item('papers',92,86)+item('lamp',112,78);
   read(w-62,h-82);o+=rug(16,h-60,big?120:96,40,'#2f6b5a','#3c8270');floor(46,h-34);floor(88,h-30);
   if(big)pc(cx+40,108,'monitor');
   break;
  case 'workshop':
   o+=item('rack',10,28)+item('rack',34,28)+(big?item('rack',58,28):'')+item('neon',cx-6,6);
   o+=`<rect x="20" y="88" width="${Math.max(30,w-140)}" height="2" fill="#2f6a8a"/>`;
   pc(w-62,108,'dualmon');if(big)pc(w-138,108,'monitor');
   o+=item('crate',w-34,h-34)+item('crate',w-30,h-50);coffee(14,h-60);
   o+=rug(cx-56,h-58,100,38,'#24385a','#2f4a73');floor(cx-30,h-30);floor(cx+14,h-28);
   break;
  case 'editing':case 'media':
   o+=item('window',Math.round(w*.18),6)+item('poster',Math.round(w*.46),4)+(big?item('window',Math.round(w*.64),6):'');spot('smoke',Math.round(w*.18)+20,68);
   pc(cx-66,108,'monitor');pc(cx,108,'dualmon');pc(cx+66,108,'monitor');
   o+=item('plant',4,40)+item('plant',w-24,40)+item('coffee',w-30,h-58);spot('coffee',w-22,h-20);
   if(big||deep)sofa(12,h-56);else{o+=rug(16,h-56,96,40,'#3c4d7a','#536aa6');floor(44,h-28);floor(84,h-26);}
   bean(cx+30,h-24,'#536aa6','#3c4d7a');
   break;
  case 'audio':
   o+=item('onair',w-46,8)+item('speaker',12,32)+item('speaker',76,32)+item('poster',cx-10,6);
   pc(48,108,'monitor');
   o+=item('mic',w-52,72);spot('sing',w-44,118);
   o+=rug(18,h-56,100,38,'#3d3163','#5d4a8f');floor(46,h-28);floor(90,h-26);bean(w-44,h-24,'#5d4a8f','#3d3163');
   break;
  case 'office':case 'marketing':
   o+=item('whiteboard',w-78,4)+(kind==='marketing'?item('poster',22,6):'')+item('window',18,6);spot('smoke',38,68);spot('think',w-48,74);
   pc(52,112,'monitor');pc(cx+28,112,'monitor');if(big)pc(cx+96,112,'monitor');
   o+=item('cooler',w-24,h-74);spot('coffee',w-18,h-26);o+=item('plant',4,h-46);
   if(kind==='marketing'||big||deep)sofa(cx-40,h-52);else{o+=rug(30,h-50,110,34,'#2f5a4a','#3c7262');floor(60,h-24);floor(110,h-24);}
   break;
  case 'gaming':
   o+=item('neon',18,6)+item('tv',cx-26,4)+item('tvstand',cx-30,40);
   o+=`<rect x="4" y="33" width="${w-8}" height="2" class="pl-rgb"/>`;
   bean(cx-28,118,'#ff5c8f','#c23f6d');bean(cx+28,118,'#3ff0e0','#24a8a0');
   o+=item('arcade',w-34,30)+(big?item('arcade',w-64,30):'');spot('arcade',w-27,104);if(big)spot('arcade',w-57,104);
   pc(46,h-24,'dualmon');o+=rug(cx-40,h-58,108,40,'#2a1b46','#3d2766');floor(cx+0,h-30);floor(cx+44,h-28);
   break;
  case 'kitchen':
   o+=item('counter',10,26)+item('fridge',w-34,12)+item('window',96,4);spot('coffee',28,84);spot('coffee',w-26,96);spot('smoke',116,68);
   o+=item('table',cx-20,h-92);for(const [sx,sy] of [[cx-38,h-84],[cx+26,h-84],[cx-6,h-62]]){o+=item('stool',sx,sy);spot('stool',sx+6,sy+12);}
   o+=item('plant',w-24,h-44)+item('cat',14,h-28);floor(64,h-30);
   break;
  case 'gym':
   o+=item('window',cx-20,6)+item('poster',16,6);
   o+=item('treadmill',12,52)+item('treadmill',72,52);spot('treadmill',40,66);spot('treadmill',100,66);
   o+=item('dumbbells',w-46,40);spot('lift',w-36,94);o+=item('bag',w-26,96);spot('punch',w-40,140);
   o+=`<rect x="10" y="${h-62}" width="${w-20}" height="2" fill="#f4f2f8" opacity=".55"/><circle cx="${cx}" cy="${h-62}" r="18" fill="none" stroke="#f4f2f8" stroke-opacity=".45" stroke-width="2"/>`;
   o+=item('yogamat',16,h-46)+item('yogamat',70,h-46);floor(38,h-36);floor(92,h-36);o+=item('cooler',cx+12,h-72);spot('coffee',cx+20,h-28);
   break;
  case 'terrace':{
   o+=`<rect x="4" y="4" width="${w-8}" height="30" fill="url(#plSky)"/><circle cx="${w-40}" cy="14" r="6" fill="#f4ecc6"/><circle cx="${w-37}" cy="12" r="5" fill="#1b2444"/>`;
   for(let i=0;i<9;i++)o+=`<rect x="${14+i*((w-30)/9)|0}" y="${8+(i*7)%18}" width="1" height="1" fill="#fff" class="${i%2?'po-led':'po-led2'}"/>`;
   for(let x=10;x<w-10;x+=36)o+=item('bulbs',x,30,1.4);
   o+=`<rect x="4" y="36" width="${w-8}" height="3" fill="#6e4630"/>`;for(let x=8;x<w-8;x+=12)o+=`<rect x="${x}" y="39" width="2" height="12" fill="#4a2f1f"/>`;o+=`<rect x="4" y="50" width="${w-8}" height="2" fill="#6e4630"/>`;
   spot('smoke',34,72);spot('smoke',w-40,72);o+=item('ashtray',48,74,1.5);
   o+=item('firepit',cx-16,h-82);for(const [dx,dy] of [[-40,-4],[38,-2],[-20,34],[22,36]])spot('fire',cx+dx,h-66+dy);
   o+=item('deckchair',14,100)+item('deckchair',w-44,100);spot('lounge',30,118);spot('lounge',w-28,118);
   o+=item('monstera',6,h-50)+item('monstera',w-28,h-50);
   break;}
  case 'library':
   o+=item('shelf',8,22)+item('shelf',44,22)+(w>=250?item('shelf',80,22):'')+item('shelf',w-42,22)+item('lamp',w-62,40);
   read(cx-44,h-96);read(cx+16,h-96);o+=item('sidetable',cx-10,h-80)+item('books',cx-7,h-88);
   o+=rug(18,h-50,w-36,34,'#5a3a2a','#74503a');floor(46,h-26);floor(w-50,h-26);
   pc(cx,h-20,'monitor');o+=item('globe',12,h-42);
   break;
  case 'server':
   for(let x=10;x<w-40;x+=24)o+=item('rack',x,28);
   o+=`<rect x="8" y="88" width="${w-16}" height="2" fill="#2fb3e0" opacity=".6"/><rect x="8" y="92" width="${w-16}" height="1" fill="#8fdc4a" opacity=".4"/>`;
   pc(cx,h-36,'dualmon');spot('think',40,118);spot('think',w-46,118);o+=item('crate',w-30,h-34);floor(40,h-26);
   break;
  default: // lounge
   win(18,6);o+=item('tv',cx-6,4)+item('tvstand',cx-10,40)+item('poster',w-30,8);
   bean(cx+2,118);bean(cx+44,120,'#536aa6','#3c4d7a');
   o+=rug(cx-78,h-70,156,58,'#4c3b52','#79617c');sofa(cx-62,h-56);if(big)sofa(cx+4,h-56);else{floor(cx+30,h-30);}
   o+=item('sidetable',cx-40,h-84)+item('plant',4,h-46)+item('lamp',w-24,h-66)+item('cat',w-46,h-24);if(big)pc(w-44,h-90,'lapback');
  }
  return {art:o,spots};
 }
 function room(r){
  // The interior is designed for a compact room and scaled up with the room, so furniture keeps the characters' size.
  const p=SpaceMath.iso(r.x,r.y),w=Math.round(r.width*28),h=Math.round(r.height*28),k=Math.max(1,Math.min(1.45,w/224,h/196)),iw=Math.round(w/k),ih=Math.round(h/k);
  const t=THEMES[r.decor]||THEMES.lounge,{art,spots}=layout(r.decor,iw,ih);
  SPOTS.set(r.id,spots.map(s=>({...s,k,x:s.x*k,y:s.y*k,room:r.id,ux:r.x+s.x*k/28,uy:r.y+s.y*k/28,key:r.id+':'+s.type+':'+s.x+':'+s.y})));
  const accent=xml(r.accent||'#ad8aee');
  let o=`<g class="room-floor pixel-room po-room pl-room" data-room="${xml(r.id)}" data-decor="${xml(r.decor||'')}" role="button" tabindex="0" aria-label="${xml(r.name)} · szoba szerkesztése" transform="translate(${p[0]} ${p[1]})" shape-rendering="crispEdges">`;
  o+=`<rect class="pl-glow" x="-6" y="-6" width="${w+12}" height="${h+12}" rx="6" fill="none" stroke="${accent}" stroke-width="2" opacity="0"/>`;
  o+=`<rect x="-3" y="6" width="${w+6}" height="${h+8}" fill="#05070d" opacity=".75"/><rect width="${w}" height="${h}" fill="${INK}"/>`;
  o+=`<g transform="scale(${k.toFixed(4)})">`;
  o+=`<rect x="4" y="4" width="${iw-8}" height="26" fill="${t.wall}"/><rect x="4" y="4" width="${iw-8}" height="2" fill="#ffffff" opacity=".07"/>`;
  o+=`<rect x="4" y="24" width="${iw-8}" height="2" fill="${t.trim}" opacity="${['workshop','server','gaming'].includes(r.decor)?.6:1}"/><rect x="4" y="30" width="${iw-8}" height="5" fill="${t.base}"/>`;
  o+=`<rect x="4" y="35" width="${iw-8}" height="${ih-39}" fill="${t.floor}"/><rect x="4" y="35" width="${iw-8}" height="${ih-39}" fill="${xml(r.floor||'#000')}" opacity=".12"/>`;
  o+=`<rect x="4" y="35" width="${iw-8}" height="${ih-39}" fill="url(#plShade)"/>`;
  o+=art+`<rect x="4" y="35" width="${iw-8}" height="${ih-39}" fill="url(#plLight)" pointer-events="none"/></g>`;
  o+=`<rect x="${Math.round(w/2-16)}" y="${h-6}" width="32" height="6" fill="#8b654b"/><rect x="${Math.round(w/2-13)}" y="${h-6}" width="26" height="3" fill="#b78a5b"/>`;
  o+=`<rect x="14" y="${h-3}" width="${w-28}" height="2" fill="${accent}"/>`;
  return o+'</g>';
 }
 const ICON={command:'⌘',research:'🔬',workshop:'🛠',editing:'🎬',media:'🎬',audio:'🎙',office:'🗂',marketing:'📣',lounge:'🛋',gaming:'🎮',kitchen:'☕',gym:'🏋',terrace:'🔥',library:'📚',server:'🖧'};
 function label(r){
  const p=SpaceMath.iso(r.x+r.width/2,r.y),peers=roomPeers.get(r.id)||[],width=Math.min(Math.max(120,r.name.length*7.2+62),r.width*28-30,230),x=p[0]-width/2,y=p[1]-31;
  return `<g class="room-label pixel-room-label pl-label" data-room-label="${xml(r.id)}" role="button" tabindex="0" aria-label="${xml(r.name)} beállítása">`+
   `<rect class="pl-label-bg" x="${x}" y="${y}" width="${width}" height="24" rx="12"/>`+
   `<text class="pl-label-icon" x="${x+13}" y="${y+16.5}" text-anchor="middle">${ICON[r.decor]||'◆'}</text>`+
   `<text class="pl-label-name" x="${x+25}" y="${y+16}">${xml(r.name.slice(0,22))}</text>`+
   `<g class="pl-label-count"><rect x="${x+width-30}" y="${y+5}" width="22" height="14" rx="7"/><text x="${x+width-19}" y="${y+15.5}" text-anchor="middle">${peers.length}</text></g>`+
   `<g class="pl-room-del" data-room-del="${xml(r.id)}" role="button" tabindex="0" aria-label="${xml(r.name)} törlése" transform="translate(${x+width+6} ${y+1})"><title>Szoba törlése</title><rect width="22" height="22" rx="11"/><path d="M7 8h8M9 8V6.5h4V8M8 9.5l.6 6h4.8l.6-6" fill="none" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></g></g>`;
 }
 const DEFS=`<pattern id="plGrid" width="16" height="16" patternUnits="userSpaceOnUse">${px('0,0,16,16,#140c24;0,0,16,1,#2a1b46;0,0,1,16,#2a1b46')}</pattern>
<pattern id="plTileWall" width="12" height="12" patternUnits="userSpaceOnUse">${px('0,0,12,12,#cfd6df;0,0,12,1,#aab3c0;0,0,1,12,#aab3c0')}</pattern>
<pattern id="plChecker" width="16" height="16" patternUnits="userSpaceOnUse">${px('0,0,16,16,#cfc7b6;0,0,8,8,#b5ad9c;8,8,8,8,#b5ad9c;0,0,16,1,#a39b8a')}</pattern>
<pattern id="plGymFloor" width="40" height="24" patternUnits="userSpaceOnUse">${px('0,0,40,24,#b98a5a;0,11,40,1,#9c6f45;0,23,40,1,#9c6f45;26,0,1,11,#9c6f45;10,12,1,11,#9c6f45;2,3,14,1,#c99a68;14,15,12,1,#c99a68')}</pattern>
<pattern id="plRubber" width="20" height="20" patternUnits="userSpaceOnUse">${px('0,0,20,20,#262a35;2,2,2,2,#2e3340;12,11,2,2,#2e3340;0,19,20,1,#1e2129')}</pattern>
<pattern id="plDeck" width="28" height="10" patternUnits="userSpaceOnUse">${px('0,0,28,10,#a47450;0,4,28,1,#7d5236;0,9,28,1,#7d5236;14,0,1,4,#7d5236;5,5,1,4,#7d5236;2,1,8,1,#b88a60;17,6,7,1,#b88a60')}</pattern>
<linearGradient id="plSky" x2="0" y2="1"><stop stop-color="#0d1430"/><stop offset="1" stop-color="#3a2a5e"/></linearGradient>
<linearGradient id="plShade" x2="0" y2="1"><stop stop-color="#000" stop-opacity=".28"/><stop offset=".25" stop-color="#000" stop-opacity="0"/><stop offset=".85" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".18"/></linearGradient>
<radialGradient id="plLight" cx=".5" cy=".15" r=".8"><stop stop-color="#fff3d6" stop-opacity=".07"/><stop offset="1" stop-color="#fff3d6" stop-opacity="0"/></radialGradient>`;

 // ---------- Activities ----------
 const A={
  work:{pose:'chair',over:'desk',label:'Dolgozik a gépen',emo:'⌨️',glow:1},
  laptop_work:{pose:'floor',prop:'laptop',label:'Dolgozik laptopon',emo:'⌨️',glow:1},
  pc_game:{pose:'chair',over:'desk',label:'Játszik a gépen',emo:'🎮',glow:1},
  sofa:{pose:'sofa',over:'sofafront',label:'Pihen a kanapén',emo:'🛋️'},
  sofa_rubik:{pose:'sofa',over:'sofafront',prop:'cube',label:'Rubik-kockázik',emo:'🧩'},
  sofa_laptop:{pose:'sofa',over:'sofafront',prop:'laptop',label:'Laptopozik a kanapén',emo:'💻'},
  nap:{pose:'lie',label:'Szundít a kanapén',emo:'💤',fx:'z'},
  floor:{pose:'floor',label:'Ül a földön',emo:'🧘'},
  floor_rubik:{pose:'floor',prop:'cube',label:'Rubik-kockázik',emo:'🧩'},
  floor_phone:{pose:'floor',prop:'phone',label:'Telefonozik',emo:'📱'},
  game:{pose:'beanbag',prop:'pad',label:'Konzolozik',emo:'🎮'},
  bean_rubik:{pose:'beanbag',prop:'cube',label:'Rubik-kockázik',emo:'🧩'},
  arcade:{pose:'stand',prop:'hands',label:'Árkádgépezik',emo:'🕹️'},
  smoke:{pose:'stand',prop:'cig',label:'Cigizik az ablaknál',emo:'🚬'},
  coffee:{pose:'stand',prop:'mug',label:'Kávézik',emo:'☕'},
  stool:{pose:'stool',prop:'mug',label:'Uzsonnázik',emo:'🥪'},
  read:{pose:'armchair',over:'armfront',prop:'book',label:'Olvas',emo:'📖'},
  treadmill:{pose:'jog',label:'Fut a futópadon',emo:'🏃'},
  lift:{pose:'stand',prop:'dumbbell',label:'Súlyzózik',emo:'💪'},
  punch:{pose:'stand',prop:'gloves',label:'Bokszol',emo:'🥊'},
  sing:{pose:'stand',label:'Énekel',emo:'🎤',fx:'notes'},
  think:{pose:'stand',label:'Gondolkodik',emo:'💡'},
  fire:{pose:'floor',label:'Melegszik a tűznél',emo:'🔥'},
  fire_guitar:{pose:'floor',prop:'guitar',label:'Gitározik a tűznél',emo:'🎸',fx:'notes'},
  lounge:{pose:'sofa',label:'Napozószékben pihen',emo:'🌙'},
  run:{pose:'run',label:'Fut egy kört',emo:'🏃'},
  walk:{pose:'walk',label:'Sétál'},
  look:{pose:'stand',label:'Nézelődik'}
 };
 const BY_SPOT={pc:[['pc_game',1]],sofa:[['sofa',1.6],['sofa_rubik',1.2],['sofa_laptop',1],['nap',.8]],floor:[['floor',.8],['floor_rubik',1.4],['floor_phone',1]],
  beanbag:[['game',2],['bean_rubik',.7]],arcade:[['arcade',1.4]],smoke:[['smoke',1.3]],coffee:[['coffee',1.2]],stool:[['stool',1]],read:[['read',1.4]],
  treadmill:[['treadmill',1.5]],lift:[['lift',1.2]],punch:[['punch',1]],sing:[['sing',1]],think:[['think',.8]],fire:[['fire',1],['fire_guitar',.8]],lounge:[['lounge',1.2]]};
 const life=new Map(),taken=new Map();
 const hash=s=>{let h=2166136261;for(let i=0;i<s.length;i++)h=Math.imul(h^s.charCodeAt(i),16777619);return h>>>0;};
 const rand=(id,k,n=0)=>hash(id+':'+k+':'+n)/4294967296;
 function release(id){for(const [k,v]of taken)if(v===id)taken.delete(k);}
 function pick(id,v,L,working){
  const spots=SPOTS.get(v.room.id)||[],k=++L.k,free=s=>!taken.has(s.key)||taken.get(s.key)===id;release(id);
  let choice=null;
  if(working){const pcs=spots.filter(s=>s.type==='pc'&&free(s)).sort((a,b)=>Math.hypot(a.ux-L.pos.x,a.uy-L.pos.y)-Math.hypot(b.ux-L.pos.x,b.uy-L.pos.y));
   choice=pcs[0]?{act:'work',spot:pcs[0]}:{act:'laptop_work',spot:spots.find(s=>['floor','sofa'].includes(s.type)&&free(s))||null};}
  else{const options=[];for(const s of spots)if(free(s))for(const [act,wt] of BY_SPOT[s.type]||[])options.push({act,spot:s,wt:wt*(act===L.act?.25:1)});
   options.push({act:'run',spot:null,wt:L.act==='run'?.2:.9},{act:'walk',spot:null,wt:.35});
   let total=options.reduce((n,o)=>n+o.wt,0),r=rand(id,k)*total;choice=options.find(o=>(r-=o.wt)<0)||options[0];}
  const room=v.room;let target;
  if(choice.spot){taken.set(choice.spot.key,id);target={x:choice.spot.ux,y:choice.spot.uy};}
  else{const fx=.18+rand(id,k,1)*.64,fy=.45+rand(id,k,2)*.4;target={x:room.x+room.width*fx,y:room.y+room.height*fy};}
  const span=choice.act==='run'?11000:choice.act==='walk'?4000:choice.act==='nap'?26000:14000+rand(id,k,3)*14000;
  Object.assign(L,{act:choice.act,spot:choice.spot,target,phase:'walk',span,loop:0,working});
 }
 function loopPoint(room,s){const x0=room.x+1.3,y0=room.y+2.6,x1=room.x+room.width-1.3,y1=room.y+room.height-1.1,wd=x1-x0,ht=y1-y0,per=2*(wd+ht);let d=((s%per)+per)%per;
  if(d<wd)return {x:x0+d,y:y0};d-=wd;if(d<ht)return {x:x1,y:y0+d};d-=ht;if(d<wd)return {x:x1-d,y:y1};d-=wd;return {x:x0,y:y1-d};}

 // ---------- Drawing a pose ----------
 const PROP={
  cig:'<g class="pl-cig"><rect x="9" y="-27" width="7" height="2" fill="#e9e6f0"/><rect x="16" y="-27" width="2" height="2" fill="#f29a5c" class="pl-ember"/><circle class="pl-smoke s1" cx="17" cy="-31" r="2.4"/><circle class="pl-smoke s2" cx="17" cy="-31" r="2"/><circle class="pl-smoke s3" cx="17" cy="-31" r="1.6"/></g>',
  mug:'<g><rect x="8" y="-28" width="7" height="8" fill="#151622"/><rect x="9" y="-27" width="5" height="6" fill="#e9e6f0"/><rect x="9" y="-27" width="5" height="1" fill="#8a5a3b"/><rect x="15" y="-26" width="2" height="4" fill="#151622"/><path class="pl-steam" d="M10-31q2-3 0-6m3 6q2-3 0-6" fill="none" stroke="#e9e6f0" stroke-width="1" opacity=".6"/></g>',
  cube:'<g transform="translate(-4 -25)"><g class="pl-cube"><rect x="-1" y="-1" width="10" height="10" fill="#151622"/>'+[0,1,2].flatMap(i=>[0,1,2].map(j=>`<rect class="c${(i*3+j)%6}" x="${j*3}" y="${i*3}" width="2.4" height="2.4"/>`)).join('')+'</g></g>',
  pad:'<g class="pl-pad"><rect x="-9" y="-24" width="18" height="7" rx="2" fill="#151622"/><rect x="-8" y="-23" width="16" height="5" rx="2" fill="#3b3d55"/><rect x="-6" y="-21" width="3" height="1" fill="#e9e6f0"/><rect x="-5" y="-22" width="1" height="3" fill="#e9e6f0"/><rect x="3" y="-22" width="2" height="2" fill="#ff5c8f"/><rect x="5" y="-20" width="2" height="2" fill="#3ff0e0"/></g>',
  phone:'<g><rect x="-3" y="-27" width="6" height="9" fill="#151622"/><rect x="-2" y="-26" width="4" height="7" fill="#7fe0ff" class="pl-screen"/></g>',
  book:'<g><rect x="-10" y="-27" width="20" height="9" fill="#151622"/><rect x="-9" y="-26" width="9" height="7" fill="#e9e6f0"/><rect x="0" y="-26" width="9" height="7" fill="#d4d0e2"/><rect x="-7" y="-24" width="5" height="1" fill="#9b99b0"/><rect x="2" y="-24" width="5" height="1" fill="#9b99b0"/><rect x="2" y="-22" width="4" height="1" fill="#9b99b0"/></g>',
  laptop:'<g><rect x="-11" y="-21" width="22" height="3" fill="#151622"/><rect x="-10" y="-31" width="20" height="11" fill="#151622"/><rect x="-9" y="-30" width="18" height="9" fill="#9b99b0"/><rect x="-2" y="-27" width="4" height="3" fill="#e9e6f0" class="pl-screen"/></g>',
  dumbbell:'<g class="pl-curl"><rect x="-17" y="-26" width="8" height="3" fill="#151622"/><rect x="-18" y="-28" width="2" height="7" fill="#4b4f6a"/><rect x="-10" y="-28" width="2" height="7" fill="#4b4f6a"/><rect x="9" y="-26" width="8" height="3" fill="#151622"/><rect x="8" y="-28" width="2" height="7" fill="#4b4f6a"/><rect x="16" y="-28" width="2" height="7" fill="#4b4f6a"/></g>',
  gloves:'<g class="pl-punch"><rect x="10" y="-31" width="7" height="7" rx="2" fill="#d64b3a"/><rect x="-16" y="-27" width="7" height="7" rx="2" fill="#d64b3a"/></g>',
  hands:'<g class="pl-pad"><rect x="-10" y="-26" width="5" height="4" fill="#e8b48f"/><rect x="5" y="-26" width="5" height="4" fill="#e8b48f"/></g>',
  guitar:'<g transform="rotate(-25 0 -20)"><rect x="-14" y="-22" width="12" height="10" rx="4" fill="#b07a44"/><rect x="-10" y="-19" width="3" height="3" fill="#151622"/><rect x="-2" y="-19" width="18" height="3" fill="#5e3c22"/><rect x="15" y="-20" width="4" height="5" fill="#151622"/></g>'
 };
 const FX={z:'<g class="pl-fx pl-z"><text x="8" y="-40">z</text><text x="14" y="-50">z</text><text x="20" y="-60">Z</text></g>',
  notes:'<g class="pl-fx pl-notes"><text x="10" y="-44">♪</text><text x="-14" y="-52">♫</text></g>'};
 function over(L){const a=A[L.act]||{},s=L.spot||{};let o='',f='';
  if(L.phase==='do'){
   if(a.over==='desk')f=item('desk',-32,-20)+(s.screen==='lapback'?item('lapback',-8,-25):'');
   else if(a.over==='sofafront')f=item('sofafront',s.ox??-16,s.oy??-20);
   else if(a.over==='armfront')f=item('armfront',s.ox??-14,s.oy??-24);
   if(f)o+=`<g transform="scale(${(s.k||1).toFixed(4)})">${f}</g>`;
   if(a.prop)o+=PROP[a.prop]||'';if(a.fx)o+=FX[a.fx];
   if(a.glow)o+='<ellipse class="pl-face" cx="0" cy="-36" rx="13" ry="10" fill="#7fb2ff"/>';
  }
  return o;}
 const POSE={stand:'',chair:'translate(0 4) scale(1 .9)',sofa:'translate(0 3) scale(1 .86)',floor:'translate(0 8) scale(1.05 .72)',beanbag:'translate(0 5) scale(1.02 .8)',
  stool:'translate(0 3) scale(1 .9)',armchair:'translate(0 3) scale(1 .86)',lie:'translate(27 -10) rotate(-90) scale(.92)'};
 function bubble(v,text){let b=v.el.querySelector('.pl-bubble');if(!b){b=document.createElementNS('http://www.w3.org/2000/svg','g');b.setAttribute('class','pl-bubble');v.el.append(b);}
  if(!text){b.style.display='none';return;}b.innerHTML=`<g transform="translate(0 -76)"><rect x="-12" y="-13" width="24" height="20" rx="6"/><path d="M-3 7l3 4 3-4z"/><text y="2" text-anchor="middle">${text}</text></g>`;b.style.display='';b.classList.remove('pop');requestAnimationFrame(()=>b.classList.add('pop'));}
 function parts(v){let under=v.el.querySelector('.pl-over');if(!under){under=document.createElementNS('http://www.w3.org/2000/svg','g');under.setAttribute('class','pl-over');under.setAttribute('shape-rendering','crispEdges');v.el.insertBefore(under,v.el.querySelector('.figure').nextSibling);
   const t=document.createElementNS('http://www.w3.org/2000/svg','title');v.el.prepend(t);v.title=t;}
  v.el.querySelector('.pixel-seat')?.remove();return under;}

 // ---------- The frame loop ----------
 function frame(t){
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches||document.documentElement.dataset.motion==='off';
  const working=new Set((state?.jobs||[]).filter(j=>j.status==='running').map(j=>j.agent));
  const counts={};
  for(const [id,v]of spriteElements){
   if(!SPOTS.has(v.room.id))continue;
   let L=life.get(id);const busy=working.has(id),type=characterFor(id),floating=['jellyfish','hologram'].includes(type);
   if(!L||L.room!==v.room.id){release(id);L={k:hash(id)%97,pos:{x:v.seat.x,y:v.seat.y},face:1,room:v.room.id,t};life.set(id,L);pick(id,v,L,busy);L.pos={...L.target};L.phase='do';L.until=t+L.span*rand(id,'start');}
   const overG=parts(v);
   if(L.stale){L.stale=false;v.drawn='';if(L.spot&&!(SPOTS.get(v.room.id)||[]).some(s=>s.key===L.spot.key))L.until=0;}
   if(L.working!==busy||(L.phase==='do'&&t>L.until))pick(id,v,L,busy);
   const dt=Math.min(.2,Math.max(0,(t-(L.t||t))/1000));L.t=t;
   if(reduced&&L.phase==='walk'){L.pos={...L.target};L.phase='do';L.until=t+L.span;}
   if(L.phase==='walk'){const dx=L.target.x-L.pos.x,dy=L.target.y-L.pos.y,d=Math.hypot(dx,dy),speed=L.act==='run'?3.4:1.8,step=speed*dt;
    if(Math.abs(dx)>.03)L.face=dx<0?-1:1;
    if(d<=step||d<.02){L.pos={...L.target};L.phase='do';L.until=t+L.span;if(A[L.act]?.emo&&!reduced)bubble(v,A[L.act].emo);L.bubbleAt=t;}else L.pos={x:L.pos.x+dx/d*step,y:L.pos.y+dy/d*step};}
   else if(L.act==='run'&&!reduced){L.loop+=dt*3.2;const p=loopPoint(v.room,L.loop+hash(id)%9);if(Math.abs(p.x-L.pos.x)>.002)L.face=p.x<L.pos.x?-1:1;L.pos=p;}
   if(L.bubbleAt&&t-L.bubbleAt>3400){bubble(v,null);L.bubbleAt=0;}
   const doing=L.phase==='do',act=doing?(L.act==='walk'?'look':L.act):(L.act==='run'?'run':'walk'),a=A[act]||A.walk,key=act+'|'+L.phase+'|'+(L.spot?.key||'');
   if(v.drawn!==key){v.drawn=key;overG.innerHTML=over(L);if(v.title)v.title.textContent=v.agent.name+' · '+(busy?'Dolgozik: valódi feladat fut':(doing?a.label:'Úton: '+(A[L.act]?.label||'sétál').toLowerCase()));}
   const p=iso(L.pos.x,L.pos.y);v.el.setAttribute('transform',`translate(${p[0].toFixed(1)} ${p[1].toFixed(1)})`);agentPositions.set(id,p);
   let pose=a.pose;if(floating&&pose!=='run'&&pose!=='walk'&&pose!=='jog')pose='float';
   const moving=pose==='walk'||pose==='run'||pose==='jog';
   const bob=reduced?0:pose==='float'?Math.sin(t/520+v.index)*2.2:pose==='run'||pose==='jog'?-Math.abs(Math.sin(t/95+v.index))*4:pose==='walk'?-Math.abs(Math.sin(t/150+v.index))*2.4:act==='work'?-Math.abs(Math.sin(t/120))*1.1:Math.sin(t/900+v.index)*.5;
   const lean=pose==='run'||pose==='jog'?` skewX(${(-9*L.face).toFixed(1)})`:'';
   const base=POSE[pose]||'',flip=L.face<0?' scale(-1 1)':'';
   v.el.querySelector('.figure').setAttribute('transform',`translate(0 ${bob.toFixed(2)})${flip}${lean} ${base}`);
   overG.setAttribute('transform',L.face<0&&!(A[L.act]?.over)?'scale(-1 1)':'');
   v.el.classList.toggle('walking',moving&&!floating);v.el.classList.toggle('sitting',!!POSE[pose]&&pose!=='lie');v.el.classList.toggle('pl-working',busy);
   v.el.querySelector('.work-light').style.display=busy?'':'none';
   const label=busy?'work':doing?act:'walk';counts[label]=(counts[label]||0)+1;
  }
  hud(counts);
 }
 let hudKey='';
 function hud(counts){const host=$('plHud');if(!host)return;const keyNow=JSON.stringify(counts);if(keyNow===hudKey)return;hudKey=keyNow;host.replaceChildren();
  const work=counts.work||0;const lead=el('span','pl-chip'+(work?' live':''));lead.append(el('i','pl-dot'),document.createTextNode(work?work+' dolgozik':'Mindenki pihen'));host.append(lead);
  const groups={};for(const [act,n] of Object.entries(counts)){if(act==='work')continue;const e=(A[act]||{}).emo||'🚶';groups[e]=(groups[e]||0)+n;}
  for(const [e,n] of Object.entries(groups)){const c=el('span','pl-chip');c.textContent=e+' '+n;host.append(c);}}
 return {room,label,DEFS,SPOTS,A,frame,layout,life};
})();

roomMarkup=PixelWorld.room=PixelLife.room;roomLabel=PixelWorld.label=PixelLife.label;
{
 const buildBeforeLife=buildStation;
 buildStation=function(){
  buildBeforeLife();
  $('station').querySelector('defs').insertAdjacentHTML('beforeend',PixelLife.DEFS);
  $('station').querySelectorAll('[data-room-del]').forEach(node=>{const go=e=>{e.stopPropagation();e.preventDefault();const r=rooms.find(x=>x.id===node.dataset.roomDel);if(r)quickDeleteRoom(r);};
   node.addEventListener('click',go);node.addEventListener('pointerdown',e=>e.stopPropagation());node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' ')go(e);});});
  // Owner 12 Nov: no text bar on the map about who does what; the characters' own animation shows it.
  $('plHud')?.remove();
  for(const L of PixelLife.life.values())L.stale=true;
 };
}
animateStation=function(t){requestAnimationFrame(animateStation);if(document.hidden||$('studioApp').hidden||t-lastFrame<33)return;lastFrame=t;
 if(!gesture&&!$('modal').open)PixelLife.frame(t);
 if(t-linkFrame>120){linkFrame=t;updateLinks();}
};

// ---------- Easy room delete: one click for an empty room, one choice for a full one, always undoable ----------
function undoBar(text,undo){let bar=document.querySelector('.pl-undo');if(!bar){bar=el('div','pl-undo');document.body.append(bar);}
 bar.replaceChildren(el('span','',text),button('Visszavonás',async()=>{bar.classList.remove('visible');await undo();},'secondary'));bar.classList.add('visible');clearTimeout(undoBar.timer);undoBar.timer=setTimeout(()=>bar.classList.remove('visible'),9000);}
async function archiveRoom(room,target){const moved=(roomPeers.get(room.id)||[]).map(a=>a.id);await call('room_archive',{id:room.id,move_to:target});await refresh();
 undoBar(`„${room.name}” törölve.`,async()=>{await call('room_restore',{id:room.id});
  // The agents that moved out go back home as well.
  for(const id of moved){const a=state.agents.find(x=>x.id===id);if(a&&a.room!==room.id)await call('agent_save',{agent:{...a,room:room.id}});}
  await refresh();toast('A szoba és a csapata visszakerült.');});}
function quickDeleteRoom(room){
 const others=rooms.filter(r=>r.id!==room.id);if(!others.length){toast('Ez az utolsó szobád; előbb hozz létre másikat.',true);return;}
 const members=roomPeers.get(room.id)||[],roomy=[...others].sort((a,b)=>(roomPeers.get(a.id)||[]).length-(roomPeers.get(b.id)||[]).length)[0];
 if(!members.length){act(()=>archiveRoom(room,roomy.id));return;}
 const form=el('div','pl-delete');form.append(el('p','',`${members.length} ügynök van itt (${members.map(a=>a.name).join(', ')}). Ők átköltöznek, minden beállításuk megmarad.`));
 const target=field('Ide költöznek','plDeleteTarget','select');options(target.querySelector('select'),others.map(r=>({value:r.id,label:r.name+' · '+(roomPeers.get(r.id)||[]).length+' ügynök'})),roomy.id);form.append(target);
 form.append(button('Szoba törlése',()=>act(async()=>{const to=$('plDeleteTarget').value;$('modal').close();await archiveRoom(room,to);}),'danger'));
 showModal(`„${room.name}” törlése`,form);
}
showRoomDelete=quickDeleteRoom;
{
 const roomsBeforeLife=showRooms;
 showRooms=function(){roomsBeforeLife();const cards=document.querySelectorAll('#modal .room-card');cards.forEach((card,i)=>{const room=rooms[i];if(!room)return;const row=card.querySelector('.row');if(row&&!row.querySelector('.pl-card-del')){const b=button('Törlés',()=>{$('modal').close();quickDeleteRoom(room);},'danger-link pl-card-del');row.append(b);}});};
}
// The map may already be drawn when this file arrives (the first state can land between two script loads): redraw it.
if(typeof state!=='undefined'&&state&&typeof syncStation==='function'){layoutSignature='';syncStation();}

// Agent chat opens at the newest message (owner 12 Nov: "mindig a chat elejétől kell legörgetnem"). The log is drawn while
// the Munka tab hides it, so its scroll stayed at the top; showing the Chat tab now jumps to the end, and media that loads
// later keeps the view at the end unless the owner scrolled up to read.
{
 const log=$('chatLog');let stick=true;
 const toEnd=()=>{if(log&&stick)log.scrollTop=log.scrollHeight;};
 if(log){
  log.addEventListener('scroll',()=>{if(log.clientHeight)stick=log.scrollHeight-log.scrollTop-log.clientHeight<120;},{passive:true});
  log.addEventListener('load',()=>requestAnimationFrame(toEnd),true);
  log.addEventListener('loadedmetadata',()=>requestAnimationFrame(toEnd),true);
 }
 if(typeof setInspectorView==='function'){
  const viewBeforeLife=setInspectorView;
  setInspectorView=function(view){viewBeforeLife(view);if(view==='chat'){stick=true;requestAnimationFrame(()=>requestAnimationFrame(toEnd));}};
  $('chatTab')&&($('chatTab').onclick=()=>setInspectorView('chat'));
 }
 if(typeof selectAgent==='function'){const selectBeforeLife=selectAgent;selectAgent=function(...args){stick=true;const out=selectBeforeLife(...args);requestAnimationFrame(toEnd);return out;};}
}
