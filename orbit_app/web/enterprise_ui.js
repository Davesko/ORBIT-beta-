/* Persistent business experiments; UI never claims verified income from views. */
let enterpriseMission=null,enterpriseBusy=false,enterpriseSignature='';
const enterpriseLabels={measure:'Eredmények áttekintése',research:'Friss témák kutatása',plan:'Üzleti és szerkesztési terv',produce:'Videógyártás és ellenőrzés',assess:'Eredmény rögzítése'};
async function loadEnterprise(){
 // The panel moved to the Autopilot page; without it there is nothing to load.
 if(currentApp!=='automations'||enterpriseBusy||!$('enterprisePanel'))return;
 enterpriseBusy=true;const pid=project;
 try{const d=await call('enterprise_status');if(pid!==project)return;const signature=JSON.stringify([pid,d.mission]);enterpriseMission=d.mission;if(signature!==enterpriseSignature){enterpriseSignature=signature;renderEnterprise();}}
 catch(e){const n=$('enterprisePanel');if(n)n.textContent='ORBIT-küldetés: '+e.message;}
 finally{enterpriseBusy=false;}
}
function renderEnterprise(){
 const pane=$('enterprisePanel');if(!pane)return;const openIds=[...pane.querySelectorAll('details[open]')].map(x=>x.id);pane.replaceChildren();pane.className='enterprise-panel';
 const m=enterpriseMission,active=m?.status==='active';const head=el('div','automation-detail-head'),intro=el('div');intro.append(el('span','eyebrow','ORBIT / FOLYAMATOS KÜLDETÉS'),el('h2','','Ötlet → terv → alkotás → mérés'));head.append(intro,button(active?'Ⅱ Szüneteltetés':m?'▶ Küldetés folytatása':'▶ Küldetés bekapcsolása',()=>act(async()=>{if(!m){showEnterpriseSetup();return;}await call('enterprise_save',{settings:{enabled:!active}});enterpriseSignature='';await loadEnterprise();}),'secondary'));pane.append(head);
 pane.append(el('p','hint','Helyi AI · határozatlan ideig, amíg ki nem kapcsolod. A Mac legyen ébren. Kutat, terveket ment, videót gyárt és az eredményekből tanul. A meglévő publikálási szabályaid érvényesek.'));
 if(!m){pane.append(el('p','hint','Jelenleg a Shorts-csapat hajtja végre a videós terveket. Más üzleti ötleteket javaslatként ment; a bevétel lehetőség, nem garantált eredmény.'));return;}
 const latest=m.run,done=m.steps.filter(x=>x.state==='done').length;
 pane.append(el('p','',active?(latest?.status==='running'?'Dolgozik · '+done+'/'+m.steps.length+' lépés':m.waiting_reason==='daily_goal'?'A mai cél teljesült. Holnap automatikusan folytatja.':m.waiting_reason==='daily_attempt_limit'?'A mai próbálkozási keret elfogyott. Holnap új tervvel folytatja.':'Új tervre vár · következő: '+autoTime(m.next_run)):'Szünetel · a mentett terv és eredmények megmaradtak.'),el('p','hint',m.goal+' · Napi cél: '+m.spec.daily_cycles+' sikeres ciklus · Csak helyi modellek'));
 const stages=el('div','enterprise-stages');for(const st of m.steps){const item=el('div','enterprise-stage '+st.state);item.append(el('strong','',(st.state==='done'?'✓ ':['waiting','dispatching'].includes(st.state)?'◉ ':'○ ')+(enterpriseLabels[st.node]||st.node)),el('small','',(st.result?.available===false?'Nem elérhető; ezt a terv figyelembe veszi.':st.error)||({planned:'Tervezve',pending:st.retry_at?'Újrapróbálás: '+autoTime(st.retry_at):'Várakozik',waiting:'Feldolgozás',dispatching:'Indítás',done:'Elkészült',blocked:'Újratervezésre vár',attention:'Újratervezésre vár'}[st.state]||st.state)));stages.append(item);}pane.append(stages);
 if(latest?.error)pane.append(el('p','hint','Az előző ciklus tanulsága: '+latest.error+' A küldetés új tervvel folytatja; hibás videót nem jelöl késznek.'));
 const plan=m.steps.find(x=>x.node==='plan')?.result?.content;
 if(plan?.topic){const details=el('details','work-detail');details.id='enterprisePlan';details.append(el('summary','','Aktuális üzleti terv'),el('p','',plan.topic),el('p','hint',plan.hypothesis),el('p','hint','Következő teszt: '+plan.experiment),el('p','hint','Bevételi feltevés: '+plan.revenue_path));for(const idea of plan.other_business_ideas||[])details.append(el('p','hint',idea.name+' · '+idea.validation));pane.append(details);}
 const events=el('details','work-detail');events.id='enterpriseEvents';events.append(el('summary','','Küldetésnapló'));for(const e of (m.events||[]).slice(0,8))events.append(el('p','hint',autoTime(e.created)+' · '+(enterpriseLabels[e.node]||'ORBIT')+' · '+({replan_scheduled:'Újratervezés ütemezve',cycle_started:'Új ciklus',verified:'Eredmény ellenőrizve',accepted:'Feladat átvéve',dispatch:'Lépés indítása',done:'Ciklus elkészült',attention:'Hiba rögzítve',started:'Bekapcsolva',paused:'Szüneteltetve'}[e.kind]||e.kind)));pane.append(events);
 for(const id of openIds){const d=pane.querySelector('#'+id);if(d)d.open=true;}
 if(active||latest?.status==='running')pane.append(button('Küldetés és aktuális munkája leállítása',()=>act(async()=>{await call('enterprise_save',{settings:{enabled:false,cancel:true}});enterpriseSignature='';await loadEnterprise();}),'text-button'));
}
function showEnterpriseSetup(){
 if(!state.auto_short_available){toast('Ehhez a projekthez előbb teljes Shorts-csapat szükséges.');return;}
 const body=el('div');body.append(el('p','','Az ORBIT folyamatos kísérleteket végez: valódi témát kutat, helyi AI-val tervet készít, videót gyárt, ellenőriz és újratervez. Egy hibás ciklus után késleltetve folytatja; nem ismétli korlátlanul ugyanazt a hibát.'),field('Mi legyen a vállalkozási cél?','enterpriseGoal','textarea','Építs fenntartható YouTube Shorts vállalkozást releváns, ellenőrzött források értelmes szerkesztésével. A mért eredményekből tanulj, és dolgozz ki további életképes üzleti ötleteket.'),field('Napi sikeres videóciklus célja','enterpriseDaily','input',3));const input=body.querySelector('#enterpriseDaily');Object.assign(input,{type:'number',min:1,max:12});body.append(el('p','hint','Csak helyi AI. Nincs végdátum. A napi próbálkozások és a várakozási idők korlátozzák a gép és az adatforrások terhelését. A jelenlegi YouTube-publikálási beállítás megmarad. Bevételt csak valós mérés igazolhat.'));
 body.append(button('Folyamatos küldetés indítása',()=>act(async()=>{await call('enterprise_save',{settings:{enabled:true,goal:$('enterpriseGoal').value,daily_goal:Number($('enterpriseDaily').value)}});$('modal').close();enterpriseSignature='';await loadEnterprise();toast('ORBIT-küldetés bekapcsolva.');})));showModal('ORBIT · Folyamatos küldetés',body);
}
const beforeEnterpriseLoad=loadAutomations;
loadAutomations=async function(){await beforeEnterpriseLoad();await loadEnterprise();};
$('navAutomations').addEventListener('click',loadEnterprise);setInterval(loadEnterprise,5000);
