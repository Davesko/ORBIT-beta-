/* Jarvis: talk to the main assistant in Hungarian. The microphone is recorded natively, local Whisper
   writes it down, the normal command flow answers, and the answer is spoken.
   Conversation mode listens again after each spoken answer until you stop it. */
(()=>{
 const BUSY=['queued','running','queued_apply','applying'];
 const SPEECH_DB=-38,SILENCE_DB=-46,SILENCE_MS=1300,MAX_MS=60000,NOTHING_MS=7000;
 let state='idle',stopFlag=false;
 const mic=el('button','command-mic','🎙');mic.id='commandMic';mic.title='Beszélj magyarul (kattints, majd mondd)';mic.setAttribute('aria-label','Hangos üzenet a fő asszisztensnek');
 const talk=el('button','command-talk','Beszélgetés');talk.id='commandTalk';talk.title='Beszélgetés mód: a válasz után újra figyel';
 let conversation=false;try{conversation=localStorage.getItem('orbitVoiceConversation')==='1';}catch(e){}
 const tools=document.querySelector('.command-composer-tools');tools.insertBefore(talk,$('commandSend'));tools.insertBefore(mic,$('commandSend'));
 function setTalk(){talk.classList.toggle('on',conversation);talk.setAttribute('aria-pressed',String(conversation));}
 setTalk();
 function live(text){const l=$('commandLive');if(!text){if(l.dataset.voice){l.hidden=true;l.textContent='';delete l.dataset.voice;}return;}l.hidden=false;l.dataset.voice='1';l.textContent=text;}
 function setState(s,text){state=s;mic.dataset.state=s;mic.textContent=s==='listening'?'■':s==='speaking'?'🔊':s==='thinking'?'…':'🎙';
  mic.title=s==='listening'?'Leállítás (vagy csak hallgass el)':s==='speaking'?'Felolvasás leállítása':'Beszélj magyarul';
  $('guardianTrigger').classList.toggle('voice-'+'listening',s==='listening');$('guardianTrigger').classList.toggle('voice-speaking',s==='speaking');live(text||'');}
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));

 async function listen(){
  stopFlag=false;await call('voice_listen_start');setState('listening','Figyelek… beszélj magyarul. Ha elhallgatsz, elküldöm.');
  const t0=Date.now();let heard=false,quietSince=0;
  while(!stopFlag){
   await sleep(180);
   const lv=await call('voice_level').catch(()=>({recording:false}));
   if(!lv.recording)break;
   const now=Date.now();
   if(lv.level>SPEECH_DB){heard=true;quietSince=0;}
   else if(heard&&lv.level<SILENCE_DB){quietSince=quietSince||now;if(now-quietSince>SILENCE_MS)break;}
   if(!heard&&now-t0>NOTHING_MS){await call('voice_listen_stop',{cancel:true});setState('idle','Nem hallottam semmit – kattints újra a 🎙 gombra.');setTimeout(()=>state==='idle'&&live(''),3500);return null;}
   if(now-t0>MAX_MS)break;
  }
  const cancel=stopFlag==='cancel';
  setState('thinking',cancel?'':'Leírom, amit mondtál…');
  const r=await call('voice_listen_stop',{cancel});
  return cancel?null:(r.text||'').trim();
 }

 async function waitForAnswer(before){
  for(let i=0;i<900;i++){ // up to ~30 minutes
   await sleep(2000);
   if(stopFlag)return null;
   await pollCommand();
   const turn=(commandState?.turns||[]).find(t=>!before.has(t.id));
   if(turn&&!BUSY.includes(turn.status))return turn;
   if(turn)live('Az ORBIT dolgozik a válaszon…');
  }
  return null;
 }

 async function speak(text){
  if(!text||stopFlag)return;
  setState('speaking','Válaszolok… (a 🔊 gombbal leállíthatod)');
  try{await call('voice_speak',{text});}catch(e){toast(e.message,true);}
 }

 async function round(){
  const text=await listen();
  if(!text){if(state!=='idle')setState('idle');return false;}
  stopFlag=false; // a click that ended the recording must not cancel the answer
  $('commandInput').value=text;
  const before=new Set((commandState?.turns||[]).map(t=>t.id));
  live('„'+text+'”');
  await sendCommand(true);
  setState('thinking','Az ORBIT gondolkodik…');
  const turn=await waitForAnswer(before);
  if(!turn){setState('idle');return false;}
  const answer=turn.status==='failed'?'Ez most nem sikerült. '+(turn.error||''):turn.status==='review'?(turn.response||'')+' A végrehajtáshoz jóváhagyás kell a képernyőn.':(turn.response||'Kész.');
  await speak(answer);
  setState('idle');
  return !stopFlag;
 }

 async function run(){
  try{
   do{if(!await round())break;}while(conversation&&!stopFlag&&assistantOpen);
  }catch(e){toast(e.message,true);}
  finally{if(state!=='idle')setState('idle');}
 }

 mic.onclick=()=>{
  if(state==='listening'){stopFlag=true;return;}            // finish now and send
  if(state==='speaking'){stopFlag=true;call('voice_stop_speaking').catch(()=>{});return;}
  if(state==='thinking')return;
  openAssistant(true);run();
 };
 talk.onclick=()=>{conversation=!conversation;try{localStorage.setItem('orbitVoiceConversation',conversation?'1':'0');}catch(e){}setTalk();
  toast(conversation?'Beszélgetés mód: a válasz után újra figyelek.':'Beszélgetés mód kikapcsolva.');};
 document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&state!=='idle'){stopFlag='cancel';if(state==='speaking')call('voice_stop_speaking').catch(()=>{});}
  // Option+Space: talk from anywhere in the app
  if(e.code==='Space'&&e.altKey&&!e.metaKey&&!e.ctrlKey){e.preventDefault();mic.click();}
 });
})();
