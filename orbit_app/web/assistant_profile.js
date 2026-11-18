/* Shared app preferences and user-visible persistent personal memory. */
let assistantPreferenceVersion=0,assistantPreferenceBootstrapped=false;
function saveAssistantPreferences(settings){assistantPreferenceVersion=Date.now()/1000;return call('command_preferences_save',{settings}).catch(e=>toast(e.message));}
function syncAssistantPreferences(rows){
 if(!rows.length){if(!assistantPreferenceBootstrapped){assistantPreferenceBootstrapped=true;saveAssistantPreferences({...personalSettings,...appearance});}return;}
 const version=Math.max(...rows.map(r=>r.updated));if(version<=assistantPreferenceVersion)return;assistantPreferenceVersion=version;assistantPreferenceBootstrapped=true;
 const values=Object.fromEntries(rows.map(r=>[r.key,JSON.parse(r.value)]));
 if(values.theme)personalSettings.theme=values.theme;if(typeof values.motion==='boolean')personalSettings.motion=values.motion;applyPersonalSettings();
 if(values.background)appearance.background=values.background;if(values.characters)appearance.characters=values.characters;
 localStorage.setItem('orbitAppearance',JSON.stringify(appearance));applyAppearance();spriteSignature='';if(state)updateSprites();
}
async function showAssistantProfile(){
 const [data,personal]=await Promise.all([call('command_overview'),call('command_state',{global:true})]);const body=el('div','personal-settings');
 body.append(el('p','','Egy személyes asszisztens az összes projekt felett. Látja a csapatokat, a kapcsolatokat, a munkák állapotát és a hibákat. Egyes ügynököknek és teljes csapatoknak is adhatsz feladatot a fő chatből.'));
 const summary=el('div','auto-summary');summary.append(el('h3','',data.projects.length+' projekt · '+data.agents.length+' ügynök'),el('p','','A háttérfeladatok angolul futnak, veled magyarul beszélget.'));body.append(summary);
 for(const project of data.projects){const d=el('details','item-card');d.append(el('summary','',project.name));const agents=data.agents.filter(a=>a.project===project.id);for(const a of agents){const jobs=data.recent_jobs.filter(j=>j.agent===a.id),running=jobs.find(j=>['queued','running'].includes(j.status));d.append(el('p','',a.name+' · '+a.role+(running?' · dolgozik':'')));}body.append(d);}
 body.append(el('label','','Személyes memória'),el('p','','A tartósan megjegyzett preferenciákat itt láthatod, javíthatod és elfelejtetheted. Új emléket a chatben is kérhetsz.'));
 for(const item of personal.memory||[]){const card=el('div','item-card'),input=el('textarea');input.value=item.display||item.content;input.rows=3;input.setAttribute('aria-label','Megjegyzett preferencia');card.append(input,button('Mentés',async()=>{await call('command_memory_save',{key:item.key,content:input.value,display:input.value});toast('Személyes memória frissítve.');}),button('Elfelejtés',async()=>{await call('command_memory_forget',{key:item.key});await showAssistantProfile();},'secondary'));body.append(card);}
 const input=el('textarea');input.rows=2;input.placeholder='Például: rövid, magyar válaszokat kérek.';input.setAttribute('aria-label','Új személyes preferencia');body.append(input,button('Preferencia megjegyzése',async()=>{if(!input.value.trim())return;await call('command_memory_save',{key:'preference-'+Date.now(),content:input.value,display:input.value});await showAssistantProfile();}));
 showModal('Személyes asszisztens',body);
}
