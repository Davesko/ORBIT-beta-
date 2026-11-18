/* Device-local panel sizes. Drag, keyboard arrows and double-click reset. */
(()=>{
 const root=document.documentElement,studio=document.getElementById('studioApp'),inspector=document.getElementById('inspector');
 const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
 function split(target,key,axis,min,max,apply){
  const handle=document.createElement('div');handle.className='resize-handle resize-'+axis;handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-label',axis==='x'?'Ügynökpanel szélessége':'Üzenetmező magassága');handle.setAttribute('aria-orientation',axis==='x'?'vertical':'horizontal');
  let size=Number(localStorage.getItem('orbitSize:'+key));
  const set=v=>{size=clamp(v,min(),max());apply(size);handle.setAttribute('aria-valuenow',Math.round(size));handle.setAttribute('aria-valuemin',min());handle.setAttribute('aria-valuemax',max());};
  if(Number.isFinite(size)&&size>0)set(size);
  let drag=null;
  handle.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();drag={pos:axis==='x'?e.clientX:e.clientY,size:axis==='x'?target.getBoundingClientRect().width:target.getBoundingClientRect().height};handle.setPointerCapture(e.pointerId);document.body.classList.add('resizing-panels');};
  handle.onpointermove=e=>{if(!drag)return;set(drag.size+drag.pos-(axis==='x'?e.clientX:e.clientY));};
  const end=()=>{if(!drag)return;drag=null;document.body.classList.remove('resizing-panels');localStorage.setItem('orbitSize:'+key,String(size));};
  handle.onpointerup=end;handle.onpointercancel=end;
  handle.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(e.key))return;e.preventDefault();if(e.key==='Home'){handle.ondblclick();return;}const current=axis==='x'?target.getBoundingClientRect().width:target.getBoundingClientRect().height;set(current+(['ArrowLeft','ArrowUp'].includes(e.key)?20:-20));localStorage.setItem('orbitSize:'+key,String(size));};
  handle.ondblclick=()=>{localStorage.removeItem('orbitSize:'+key);apply(null);};target.prepend(handle);
  window.addEventListener('resize',()=>{if(size>0)set(size);});
 }
 split(inspector,'inspector','x',()=>280,()=>Math.max(280,Math.min(800,window.innerWidth-440)),v=>root.style.setProperty('--inspector-width',v?v+'px':'354px'));
 const composer=inspector.querySelector('.composer');split(composer,'agentComposer','y',()=>100,()=>Math.max(100,Math.min(500,window.innerHeight*.55)),v=>{composer.style.height=v?v+'px':'';composer.classList.toggle('sized-composer',!!v);});
 document.querySelectorAll('dialog').forEach(d=>d.classList.add('resizable-dialog'));
})();
