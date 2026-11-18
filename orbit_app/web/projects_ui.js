// A projektlista kezelése: új projekt, átnevezés, törlés (kuka), visszaállítás. Csak a tulajdonos ablakából érhető el.
async function projectsCall(op,args){return (await call('project_app',{op,args:args||{}})).result;}
function projectBytes(n){return n>=1e9?(n/1e9).toFixed(1).replace('.',',')+' GB':n>=1e6?Math.round(n/1e6)+' MB':Math.round(n/1e3)+' kB';}
function projectFacts(p){const parts=[p.agents+' ügynök'];if(p.scheduled)parts.push(p.scheduled+' bekapcsolt automatizáció');if(p.busy)parts.push(p.busy+' munka fut vagy vár');return parts.join(' · ');}
async function projectsDone(r,target){if(target&&target===project)await changeProject('universe');else await refresh();toast(r.message);await showProjects();}
function editProject(p){const form=el('div');form.append(field('Projekt neve','projectEditName','input',p.name),field('Miről szól?','projectEditDescription','textarea',p.description||''));
 const row=el('div','pm-actions');row.append(button('Mentés',async()=>{const r=await projectsCall('project_edit',{target:p.id,name:$('projectEditName').value,description:$('projectEditDescription').value});await projectsDone(r);}),button('Vissza',showProjects,'secondary'));
 form.append(row);showModal('Projekt szerkesztése',form);$('projectEditName').focus();}
function trashProject(p){const form=el('div');form.append(el('p','','„'+p.name+'” a kukába kerül: eltűnik a listából, az időzítései leállnak, a fájljai megmaradnak. Innen bármikor visszaállítható.'));
 const row=el('div','pm-actions');row.append(button('Áthelyezés a kukába',async()=>{await projectsDone(await projectsCall('project_trash',{target:p.id}),p.id);},'pm-danger'),button('Mégse',showProjects,'secondary'));
 form.append(row);showModal('Projekt törlése',form);}
function purgeProject(p){const form=el('div');form.append(el('p','','Ez végleges: „'+p.name+'” beszélgetései, munkái és mappája ('+projectBytes(p.size)+') törlődnek, és nem hozhatók vissza. A megerősítéshez írd be a projekt nevét.'),field('Projekt neve','projectPurgeName','input',''));
 const go=button('Végleges törlés',async()=>{await projectsDone(await projectsCall('project_purge',{target:p.id,confirm:$('projectPurgeName').value}));},'pm-danger');go.disabled=true;
 const row=el('div','pm-actions');row.append(go,button('Mégse',showProjects,'secondary'));form.append(row);showModal('Végleges törlés',form);
 $('projectPurgeName').oninput=()=>{go.disabled=$('projectPurgeName').value.trim()!==p.name;};$('projectPurgeName').focus();}
async function showProjects(){const data=await projectsCall('project_list'),box=el('div','pm');
 const add=el('div','pm-actions');add.append(button('＋ Új projekt',async()=>newProject()));box.append(add);
 for(const p of data.projects){const row=el('div','pm-row'),info=el('div','pm-info');info.append(el('strong','',p.name));if(p.description)info.append(el('p','pm-description',p.description));info.append(el('small','',projectFacts(p)));
  const acts=el('div','pm-row-actions');acts.append(button('Szerkesztés',async()=>editProject(p),'secondary'));
  if(p.protected)info.append(el('small','pm-note',p.protected));else acts.append(button('Törlés',async()=>trashProject(p),'secondary'));
  row.append(info,acts);box.append(row);}
 if(data.trash.length){box.append(el('h3','pm-heading','Kuka'));
  for(const p of data.trash){const row=el('div','pm-row pm-trashed'),info=el('div','pm-info');info.append(el('strong','',p.name),el('small','',projectBytes(p.size)+' · törölve: '+new Date(p.deleted*1000).toLocaleDateString('hu-HU')));
   const acts=el('div','pm-row-actions');acts.append(button('Visszaállítás',async()=>projectsDone(await projectsCall('project_restore',{target:p.id})),'secondary'),button('Végleges törlés',async()=>purgeProject(p),'secondary'));
   row.append(info,acts);box.append(row);}}
 showModal('Projektek',box);}
$('manageProjects').onclick=()=>act(showProjects);
