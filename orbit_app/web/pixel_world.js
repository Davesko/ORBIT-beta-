/* ORBIT pixel workshop. Original tile and sprite artwork; saved room geometry stays editable. */
const PixelWorld=(()=>{
 const rect=(x,y,w,h,c,extra='')=>`<rect x="${Math.round(x)}" y="${Math.round(y)}" width="${Math.max(1,Math.round(w))}" height="${Math.max(1,Math.round(h))}" fill="${xml(c)}" ${extra}/>`;
 const path=(d,c)=>`<path d="${d}" fill="${xml(c)}"/>`;
 const ink='#151622',wood='#775240',lightwood='#ab7b52',metal='#37394d';
 function pot(x,y){return `<g transform="translate(${x} ${y})">`+rect(-7,0,14,13,'#795441')+rect(-9,-2,18,5,'#ac7650')+rect(-2,-19,4,19,'#52774f')+path('M-2-13h-9v-6h-5v-6h10v5h4M2-6h9v-6h5v-6H6v6H2','#648b55')+rect(-10,-23,5,5,'#93a66b')+'</g>';}
 function lamp(x,y){return `<g transform="translate(${x} ${y})">`+rect(-2,0,4,27,'#56433c')+rect(-10,26,20,4,'#332d36')+path('M-9-13h18l6 16h-30z','#d6a66a')+rect(-9,-10,18,10,'#f5cf8c')+rect(-5,-8,5,6,'#ffe7b4')+'</g>';}
 function desk(x,y,w=76,editing=false){return AtelierArt.image(editing?'desk-editing':'desk-research',x,y-14,w,editing?w*.49:w*.64);}
 function shelf(x,y){return AtelierArt.image('bookshelf',x,y,45,70);}
 function board(x,y,w=76,sub=''){let out=`<g transform="translate(${x} ${y})">`+rect(0,0,w,44,ink)+rect(3,3,w-6,38,'#a68a69')+rect(7,7,w-14,30,'#c4ae89');for(let i=0;i<5;i++)out+=rect(12+i*10,11+(i%2)*12,7,8,['#e1cfac','#b3b9ad','#b4a0bf'][i%3]);if(sub)out+=`<text x="8" y="34" fill="#4b4244" font-size="6" font-family="system-ui">${xml(sub.slice(0,17))}</text>`;return out+'</g>';}
 function sofa(x,y,w=66){return `<g transform="translate(${x} ${y})">`+rect(0,0,w,32,ink)+rect(4,0,w-8,21,'#594867')+rect(5,3,w-10,3,'#786286')+rect(7,20,w-14,13,'#6c577c')+rect(0,13,8,22,'#443b56')+rect(w-8,13,8,22,'#443b56')+rect(w/2,20,2,12,'#43394d')+rect(4,35,6,4,'#292634')+rect(w-10,35,6,4,'#292634')+'</g>';}
 function audio(x,y){let out=desk(x,y,92,false);out+=`<g transform="translate(${x+5} ${y+8})">`;for(let i=0;i<12;i++)out+=rect(6+i*6,0,4,7,['#806899','#71a29b','#a59a80'][i%3]);out+='</g>';return out;}
 function mic(x,y){return `<g transform="translate(${x} ${y})">`+rect(-2,-24,4,34,'#777988')+rect(-5,-35,10,17,ink)+rect(-3,-33,6,11,'#9d9aa6')+rect(-2,-33,2,10,'#d2c5b4')+rect(-9,9,18,3,'#272936')+'</g>';}
 function rug(x,y,w,h){return rect(x,y,w,h,'#4c3b52')+rect(x+3,y+3,w-6,h-6,'#79617c')+rect(x+5,y+5,w-10,h-10,'#56415a')+rect(x+10,y+10,w-20,h-20,'#634d63');}
 function room(r){const p=SpaceMath.iso(r.x,r.y),w=Math.round(r.width*28),h=Math.round(r.height*28),cut=10;let out=`<g class="room-floor pixel-room" data-room="${xml(r.id)}" role="button" tabindex="0" aria-label="${xml(r.name)} · szoba szerkesztése" transform="translate(${p[0]} ${p[1]})" shape-rendering="crispEdges">`;
 out+=path(`M${cut} 8H${w-cut}L${w+3} 22V${h+4}L${w-cut} ${h+16}H${cut}L-3 ${h+4}V22Z`,'#080b14');
 out+=path(`M${cut} 0H${w-cut}L${w} ${cut}V${h-cut}L${w-cut} ${h}H${cut}L0 ${h-cut}V${cut}Z`,r.wall);
 out+=rect(8,10,w-16,h-20,r.floor)+`<rect x="8" y="10" width="${w-16}" height="${h-20}" fill="url(#atelierWoodFloor)"/><rect x="8" y="10" width="${w-16}" height="${h-20}" fill="${xml(r.floor)}" opacity=".18"/>`;
 out+=rect(8,10,w-16,33,'#4a3737');for(let by=13;by<43;by+=10)for(let bx=10+((by-13)/10%2)*14;bx<w-13;bx+=29)out+=rect(bx,by,26,1,'#765443')+rect(bx,by,1,9,'#191c29');
 // Deliberate low walls with a finite reusable brick pattern, not procedural clutter.
 out+=rect(8,0,w-16,12,'#51516a')+rect(10,2,w-20,3,'#777187')+rect(0,10,8,h-20,'#3f4058')+rect(w-8,10,8,h-20,'#3a3b51')+rect(8,h-12,w-16,12,'#33354a')+rect(10,h-11,w-20,3,'#68617b');
 for(let i=28;i<w-10;i+=28)out+=rect(i,0,2,12,'#303245')+rect(i,h-10,2,10,'#202536');
 for(let i=25;i<h-10;i+=25)out+=rect(0,i,8,2,'#292b3d')+rect(w-8,i,8,2,'#242739');
 // Four door thresholds also make every newly positioned room connectable.
 out+=rect(w/2-14,h-13,28,13,'#8b654b')+rect(w/2-11,h-13,22,9,'#b78a5b')+rect(w/2-13,0,26,12,'#6d5244');
 const kind=r.decor,editing=['editing','media'].includes(kind),research=['research','command','office'].includes(kind);
 if(editing){out+=desk(24,65,Math.min(w-108,154),true)+desk(w-91,112,60,false)+shelf(w-52,44)+rug(58,h-69,w-116,38);}
 else if(kind==='audio'){out+=audio(25,54)+mic(w-48,103);for(let i=0;i<3;i++){out+=rect(23+i*34,17,28,21,'#252535')+rect(25+i*34,19,24,2,'#57506c');}out+=rug(32,h-67,w-70,35);}
 else if(research){out+=desk(22,56,76)+board(115,49,Math.min(78,w-143),r.sub)+shelf(w-54,70);}
 else{out+=board(25,46,Math.min(w-84,100),r.sub)+sofa(23,h-66,Math.min(84,w/2-20))+desk(w-97,53,70);}
 if(research)out+=rug(34,h-65,w-105,34)+rect(36,h-76,32,18,wood)+rect(39,h-73,10,7,'#cbb895')+rect(59,h-73,4,5,'#9e8c80');
 out+=rect(15,h-7,w-30,2,r.accent);out+=lamp(20,28)+pot(w-23,h-30)+pot(w-26,35);
 return out+'</g>';}
 function label(r){const p=SpaceMath.iso(r.x+r.width/2,r.y),peers=roomPeers.get(r.id)||[];const width=Math.min(r.width*28-42,205);return `<g class="room-label pixel-room-label" data-room-label="${xml(r.id)}" role="button" tabindex="0" aria-label="${xml(r.name)} beállítása"><rect x="${p[0]-width/2}" y="${p[1]+14}" width="${width}" height="25" rx="3" fill="#151827" stroke="#696077"/><text x="${p[0]-width/2+10}" y="${p[1]+31}" fill="#e0dce9" font-family="system-ui,sans-serif" font-size="12" font-weight="600">${xml(r.name.slice(0,23))}</text><text x="${p[0]+width/2-9}" y="${p[1]+30}" fill="#a89bbd" font-family="system-ui" font-size="9" text-anchor="end">${peers.length}</text></g>`;}
 function corridors(list){if(list.length<2)return '';const reached=[list[0]],left=list.slice(1);let out='';while(left.length){let best=null;for(const a of reached)for(const b of left){const ax=a.x+a.width/2,ay=a.y+a.height/2,bx=b.x+b.width/2,by=b.y+b.height/2,d=Math.abs(ax-bx)+Math.abs(ay-by);if(!best||d<best.d)best={a,b,d,ax,ay,bx,by};}const {a,b,ax,ay,bx,by}=best,p=SpaceMath.iso(ax,ay),q=SpaceMath.iso(bx,by);const d=`M${p}L${q[0]},${p[1]}L${q}`;out+=`<path d="${d}" fill="none" stroke="#10131e" stroke-width="54"/><path d="${d}" fill="none" stroke="#3a394c" stroke-width="45"/><path d="${d}" fill="none" stroke="#555064" stroke-width="2" stroke-dasharray="2 24"/>`;reached.push(b);left.splice(left.indexOf(b),1);}return `<g class="pixel-corridors" pointer-events="none" shape-rendering="crispEdges">${out}</g>`;}
 function character(color,type){const c=/^#[0-9a-f]{6}$/i.test(color)?color:'#a78bdb';let out=rect(-10,3,20,4,'#090c16')+rect(-8,-3,6,7,'#242839')+rect(3,-3,6,7,'#242839');
 const eyes=(a='#f8d878')=>rect(-7,-27,4,4,a)+rect(4,-27,4,4,a)+rect(-6,-27,1,2,'#fff1c9')+rect(5,-27,1,2,'#fff1c9');
 if(['hacker','goblin','operator'].includes(type)){
 out+=path('M-12 1v-14h-4v-14h4v-8h5v-5H7v5h6v8h4v15h-5V1Z',ink)+path('M-10-33h4v-6H6v6h5v17h-21Z',type==='hacker'?'#39354b':'#6c448b')+rect(-9,-29,18,15,'#131b23')+rect(-9,-13,19,13,'#343044')+rect(-11,-3,6,5,'#51435d')+rect(6,-3,6,5,'#51435d');
 if(type==='goblin'){out+=path('M-10-27h-8v-5h-7v8h6v6h9M10-27h8v-5h7v8h-6v6h-9','#6b9a49')+rect(-9,-29,19,15,'#75a853')+rect(-6,-15,12,3,'#4e753b')+rect(-11,-28,10,8,'#252637')+rect(2,-28,10,8,'#252637')+rect(-8,-26,5,4,'#e6cc75')+rect(5,-26,5,4,'#e6cc75')+rect(-1,-25,3,2,'#c59454')+rect(-3,-19,7,3,'#91b965');}else out+=eyes(type==='operator'?'#e2bb9b':'#edce7f');out+=rect(-3,-8,6,4,'#b39b65');
 }else if(type==='wizard'){
 out+=path('M-13 2l5-21H8L14 2Z','#6f478e')+rect(-9,-29,18,15,'#d7ae85')+path('M-10-18h20v4H6v6H-5v-5h-5Z','#ddd6c2')+path('M-17-30v-4h5v-6h5v-7h5v-9H4v6h8v4H6v6h5v6h7v4Z','#754b9c')+rect(-15,-34,29,4,'#ac7bb7')+eyes('#282b3b')+rect(17,-30,3,35,'#a27a4f')+rect(14,-35,9,7,'#c2a1dd');
 }else if(['cyberfox','dragon','raven','jellyfish','pikachu','hologram'].includes(type)){
 const fur={cyberfox:'#8cb8e0',dragon:'#87a477',raven:'#696b88',jellyfish:'#aa91cf',pikachu:'#dcc65e',hologram:'#83c6c7'}[type];out+=rect(-9,-13,19,15,fur)+path('M-13-19v-16h-4v-10h7l7 7h6l8-7h7v12h-4v16Z',fur)+rect(-9,-30,18,15,fur)+rect(-8,-19,16,6,'#d9e5df')+rect(-4,-19,8,4,'#333b52')+eyes('#222a3a')+path('M10-7h10v-6h5v-11h6v16h-6v8H10Z',fur)+rect(-6,-7,13,6,'#bdd3d5');if(type==='pikachu')out+=rect(-12,-52,5,17,fur)+rect(8,-52,5,17,fur);
 }else{
 out+=rect(-12,-18,25,19,'#202939')+rect(-9,-17,19,15,type==='samurai'?'#5b586f':'#b4bbc8')+rect(-16,-14,5,11,'#7f8a9e')+rect(12,-14,5,11,'#7f8a9e')+path('M-14-21v-15h5v-6H9v6h6v15h-5v5H-9v-5Z',type==='samurai'?'#55586a':'#bbc4cf')+rect(-10,-34,21,15,'#141e2c')+rect(-8,-32,17,3,'#25384a')+eyes(type==='astronaut'?'#f1d084':'#8bd4e4')+rect(-4,-11,9,5,c)+rect(-2,-10,3,2,'#d4e6df');if(type==='samurai')out+=path('M-17-34v-7h4v7h26v-7h4v7l-6 5h-22Z','#c4a05b');
 }
 return `<g class="pixel-character" shape-rendering="crispEdges">${out}</g>`;
 }
 return {rect,room,label,corridors,character,desk,pot};
})();
roomMarkup=PixelWorld.room;roomLabel=PixelWorld.label;characterMarkup=PixelWorld.character;
buildStation=function(){const svg=$('station');svg.innerHTML=`<defs><pattern id="pixelTiles" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#080c1827" stroke-width="1"/><path d="M2 2h23" stroke="#ffffff07" stroke-width="1"/></pattern><marker id="handoffArrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="var(--accent)"/></marker></defs><g id="roomArt">${PixelWorld.corridors(rooms)}${rooms.map(roomMarkup).join('')}</g><g id="links"></g><g id="labels">${rooms.map(roomLabel).join('')}</g><g id="sprites"></g><g id="draftLink" pointer-events="none"></g>`;
 svg.querySelectorAll('[data-room],[data-room-label]').forEach(node=>{const open=()=>roomClick(node.dataset.room||node.dataset.roomLabel);node.addEventListener('click',e=>{if(suppressClick||(!editLayout&&node.hasAttribute('data-room')))return;e.stopPropagation();open();});node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});});spriteSignature='';linkSignature='';spriteElements.clear();agentPositions.clear();setCamera(camera,false);};
// Routed elbows read as a handoff, rather than decorative arcs over every desk.
curve=function(a,b){const ay=a[1]-13,by=b[1]-13,middle=Math.round((ay+by)/2);return `M${a[0]},${ay}L${a[0]},${middle}L${b[0]},${middle}L${b[0]},${by}`;};
