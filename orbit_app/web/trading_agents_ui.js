/* TradingAgents as a research tool in Settings (owner, 12 Nov): local models, public data, reports only — never an order. */
{
 const taOp=async(name,args)=>(await call('project_app',{op:name,args:args||{}})).result;
 const decisionTone=d=>/\b(buy|overweight)\b/i.test(d)?'buy':/\b(sell|underweight)\b/i.test(d)?'sell':'hold';
 async function taSection(host){
  host.replaceChildren(el('label','','TradingAgents · kutatás'));
  let st;try{st=await taOp('trading_agents_status');}catch(e){host.append(el('p','error-text',e.message));return;}
  host.append(el('p','hint','Elemzőcsapat (piac, hírek, fundamentumok, bika–medve vita, kockázatkezelők) a helyi modelleken, nyilvános adatokból. '+st.disclaimer));
  if(st.running.length)host.append(el('p','',st.running.map(r=>(r.task==='trading_agents_install'?'Telepítés':'Elemzés · '+(r.ticker||''))+' · '+(r.status==='running'?'fut':'sorban vár')).join(' · ')));
  if(!st.installed){
   if(!st.running.some(r=>r.task==='trading_agents_install'))host.append(button('TradingAgents '+st.version+' telepítése',()=>act(async()=>{await taOp('trading_agents_install');toast('A telepítés elindult a háttérben.');taSection(host);}),'secondary'));
   return;
  }
  const row=el('div','row ta-row'),input=el('input');input.placeholder='Tőzsdei jel, pl. NVDA';input.maxLength=15;input.setAttribute('aria-label','Tőzsdei jel');
  row.append(input,button('Elemzés indítása',()=>act(async()=>{await taOp('trading_agents_run',{ticker:input.value});toast('Az elemzés sorba került; a helyi modellel akár egy óráig is tarthat, közben a modell foglalt.');taSection(host);})));
  host.append(row);
  for(const r of st.reports){const card=el('button','item-card ta-report ta-'+decisionTone(r.decision||''));card.type='button';
   card.append(el('strong','',r.ticker+' · '+r.date),el('small','',(r.decision||'').slice(0,140)));card.onclick=()=>act(()=>showTaReport(r.id));host.append(card);}
 }
 async function showTaReport(id){
  const r=await taOp('trading_agents_report',{id});const body=el('div','ta-report-body');
  body.append(el('p','hint',r.disclaimer+' · '+r.source+' · '+r.models.quick+' / '+r.models.deep));
  const names={final_trade_decision:'Végső döntés',trader_investment_plan:'Kereskedő terve',investment_plan:'Kutatási vezető terve',market_report:'Piaci elemzés',news_report:'Hírek',fundamentals_report:'Fundamentumok'};
  for(const [key,name] of Object.entries(names)){const text=(r.sections||{})[key];if(!text)continue;const d=el('details');if(key==='final_trade_decision')d.open=true;d.append(el('summary','',name),el('pre','ta-text',text));body.append(d);}
  showModal('TradingAgents · '+r.ticker+' · '+r.date,body);
 }
 const settingsBeforeTa=showSettings;
 showSettings=function(){settingsBeforeTa();const body=document.querySelector('#modal .personal-settings');if(!body)return;const host=el('div','ta-settings');body.append(host);taSection(host);};
}
