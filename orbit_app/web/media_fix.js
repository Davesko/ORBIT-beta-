/* Videos (owner, 12 Nov): a video that is closed stops, and every video shows itself at once — a still right away,
   the playable file as soon as the card is on screen — instead of waiting behind a "Videó lejátszása" button. */
{
 // 1. Closing stops the sound: a detached or hidden <video> kept playing in the background (WebKit does that).
 const stopIn=node=>{if(!node||node.nodeType!==1)return;for(const m of node.matches?.('video,audio')?[node]:node.querySelectorAll('video,audio'))try{if(!m.isConnected||m.closest('dialog:not([open])'))m.pause();}catch{}};
 new MutationObserver(list=>{for(const r of list)for(const n of r.removedNodes)stopIn(n);}).observe(document.body,{childList:true,subtree:true});
 const modal=document.getElementById('modal');
 if(modal){modal.addEventListener('close',()=>{for(const m of modal.querySelectorAll('video,audio'))try{m.pause();}catch{}});modal.addEventListener('cancel',()=>stopIn(modal));}

 // 2. A still for each video, fetched once and cached in the page.
 const posters=new Map();
 window.videoPoster=function(a){const key=a.id;if(!posters.has(key))posters.set(key,call('project_app',{op:'poster_get',args:{id:a.id,project:a.project||project}}).then(r=>r.result?.poster||null).catch(()=>null));return posters.get(key);};

 // 3. The playable file loads by itself when the card scrolls into view (one at a time keeps memory calm).
 const queue=[];let busy=false;
 const pump=async()=>{if(busy)return;const job=queue.shift();if(!job)return;busy=true;try{await job();}finally{busy=false;pump();}};
 const seen=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){seen.unobserve(e.target);const go=e.target._orbitLoad;if(go){queue.push(go);pump();}}},{rootMargin:'300px'});

 mediaCard=function(a,preview=false){
  const card=el('figure','inline-media-card');
  const media=el(a.kind==='image'?'img':a.kind==='audio'?'audio':'video');
  function showError(){card.classList.add('media-error');if(!card.querySelector('.media-error-label'))card.append(el('p','media-error-label','Az előnézet nem olvasható. A Megnyitás gombbal megnyithatod a Macen.'));}
  media.addEventListener('error',()=>{if(media.getAttribute('src'))showError();});
  if(a.kind==='image'){media.alt=a.name;media.loading='lazy';media.src=mediaURL(a);}
  else{
   media.controls=true;media.preload='metadata';media.setAttribute('playsinline','');
   if(a.kind==='video')videoPoster(a).then(p=>{if(p&&!media.poster)media.poster=p;});
   card.classList.add('media-loading');
   const attach=async()=>{try{media.src=await playableMedia(a);card.classList.remove('media-error');card.querySelector('.media-error-label')?.remove();}
    catch{showError();const retry=button('Előnézet újrapróbálása',()=>{retry.remove();queue.push(attach);pump();},'secondary');card.append(retry);}
    finally{card.classList.remove('media-loading');}};
   card._orbitLoad=attach;
   if(preview){queue.unshift(attach);pump();}else seen.observe(card);
  }
  const caption=el('figcaption');
  caption.append(el('span','',a.kind==='image'?'Elkészült kép':a.kind==='video'?'Elkészült videó':'Elkészült hang'),
   button('Megnyitás ↗',()=>call('open_artifact',{id:a.id,requestProject:a.project||project}),'media-open'));
  card.append(media,caption);
  return card;
 };

}
