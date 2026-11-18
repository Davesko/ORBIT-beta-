/* One persistent app-wide inference policy; keys and privacy consent stay in Connections. */
let aiPolicySaving=false,aiPolicyMode=null;
function syncAiPolicy(policy){
 if(!policy||!['local','local_first','hybrid'].includes(policy.mode))return;
 aiPolicyMode=policy.mode;
 if(policy.mode!=='local')localStorage.setItem('orbitNonLocalMode',policy.mode);
 const b=$('assistantLocal'),local=policy.mode==='local';
 b.disabled=aiPolicySaving;b.setAttribute('aria-busy',String(aiPolicySaving));b.setAttribute('aria-pressed',String(local));
 b.querySelector('.ai-policy-state').textContent=local?'BE':'KI';
 b.title=local?'Az összes új AI-modellhívás a Macen fut, a korábbi kézi felhős választások helyett is. A webes adatforrások továbbra is elérhetők.':'A helyi modellek és a Kapcsolatok oldalon engedélyezett API-modellek is használhatók. Az automatikus választás a mentett AI-üzemmódot követi.';
}
const commandBeforeAiPolicy=renderCommand;
renderCommand=function(){commandBeforeAiPolicy();if(!aiPolicySaving)syncAiPolicy(commandState?.ai_policy);};
$('assistantLocal').onclick=()=>act(async()=>{
 if(aiPolicySaving||!aiPolicyMode)return;
 const oldMode=aiPolicyMode,local=oldMode!=='local',saved=localStorage.getItem('orbitNonLocalMode');
 const next=local?'local':(['local_first','hybrid'].includes(saved)?saved:'hybrid');
 aiPolicySaving=true;if(assistantOpen)assistantPinned=true;syncAiPolicy({mode:oldMode});
 try{
  const info=await call('connections_save',{settings:{mode:next}});
  const policy={mode:info.mode,local_only:info.mode==='local'};
  if(commandState)commandState.ai_policy=policy;
  if(policy.local_only&&/^(groq|gemini|openrouter|deepseek)\//.test(localStorage.getItem('orbitPersonalModel')||''))localStorage.setItem('orbitPersonalModel','auto');
  $('commandModel').dataset.models='';syncAiPolicy(policy);
  try{await loadModels();renderCommand();}catch{toast('Az AI-üzemmód mentve; a modelllista később frissül.');return;}
  toast(policy.local_only?'Csak helyi AI · minden új modellhívás helyben fut.':'Helyi és engedélyezett API-modellek is használhatók.');
 }catch(error){aiPolicySaving=false;syncAiPolicy({mode:oldMode});throw error;}
 finally{aiPolicySaving=false;syncAiPolicy({mode:aiPolicyMode});}
});

// Separate icon and label geometry without replacing existing navigation handlers.
for(const b of document.querySelectorAll('.app-rail .rail-button')){
 const nodes=[...b.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim());
 if(!nodes.length)continue;
 const label=nodes.map(n=>n.textContent.trim()).join(' '),icon=b.querySelector(':scope > span');
 if(icon)icon.classList.add('rail-icon');
 for(const n of nodes)n.remove();
 const text=el('span','rail-label',label);b.append(text);b.setAttribute('aria-label',label);b.title=label;
 if(b.id==='navAutomations'||b.id==='navGrowth'){
  b.classList.add('has-short-label');b.append(el('span','rail-short-label',b.id==='navAutomations'?'Folyamatok':'Elérés'));
 }
}
