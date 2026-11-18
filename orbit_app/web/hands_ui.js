/* Gépvezérlés: ORBIT Hands (the assistant's own mouse and keyboard) and the two macOS permissions it needs.
   Each button shows the system prompt and opens the exact Settings pane where ORBIT Hands is switched on. */
(()=>{
async function handsOp(op,args){return (await call('project_app',{op,args:args||{}})).result;}
const ORBITCUR='<svg viewBox="0 0 120 70" width="120" height="70" aria-hidden="true"><defs><radialGradient id="oc" cx="35%" cy="35%"><stop offset="0" stop-color="#fff"/><stop offset=".5" stop-color="#35f2c5"/><stop offset="1" stop-color="#8c6bff"/></radialGradient><linearGradient id="tail" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8c6bff" stop-opacity="0"/><stop offset="1" stop-color="#35f2c5" stop-opacity=".7"/></linearGradient></defs><path d="M118 2 L96 20" stroke="url(#tail)" stroke-width="9" stroke-linecap="round"/><path d="M92 24 C70 30 46 40 26 52" fill="none" stroke="#35f2c5" stroke-width="2.6" stroke-linecap="round"/><path d="M92 24 C70 30 46 40 26 52" fill="none" stroke="#fff" stroke-width="1.2" stroke-dasharray="4 7"/><circle cx="26" cy="52" r="10" fill="none" stroke="#fa739e" stroke-width="2" stroke-dasharray="7 6"/><circle cx="26" cy="52" r="2.5" fill="#fff"/><ellipse cx="96" cy="20" rx="20" ry="7" fill="none" stroke="#35f2c5" stroke-opacity=".8" stroke-width="1.4" transform="rotate(28 96 20)"/><circle cx="96" cy="20" r="10" fill="url(#oc)"/><circle cx="111" cy="27" r="3" fill="#fa739e"/></svg>';
const YARN='<svg viewBox="0 0 120 70" width="120" height="70" aria-hidden="true"><path d="M86 22 C62 30 44 44 26 52" fill="none" stroke="#fa739e" stroke-width="2.2" stroke-linecap="round"/><circle cx="26" cy="52" r="4" fill="#35f2c5"/><circle cx="26" cy="52" r="10" fill="none" stroke="#35f2c5" stroke-opacity=".6" stroke-width="2"/><circle cx="96" cy="20" r="15" fill="#fa739e"/><g fill="none" stroke-width="1.2"><ellipse cx="96" cy="20" rx="15" ry="6" stroke="#c7386e" transform="rotate(25 96 20)"/><ellipse cx="96" cy="20" rx="15" ry="6" stroke="#ffb8d1" transform="rotate(-35 96 20)"/><ellipse cx="96" cy="20" rx="15" ry="6" stroke="#c7386e" transform="rotate(85 96 20)"/></g><circle cx="96" cy="20" r="15" fill="none" stroke="#8c1f4d" stroke-width="1.2"/></svg>';
async function showHands(restart){
 const st=await handsOp('hands_status',{restart:restart===true});const body=el('div','hands-panel');
 const head=el('div','hands-head');const art=el('div','hands-yarn');art.innerHTML=YARN;
 head.append(art,el('p','','Az ORBIT saját egérrel és billentyűzettel dolgozik a gépeden: megnyit, kattint, gépel, kitölt. Munka közben egy fonalgombolyag jelenik meg a képernyőn, és egy szál fut belőle oda, ahová éppen kattint. A te egered közben a helyén marad.'));
 body.append(head);
 const rows=[['accessibility',st.accessibility],['screen',st.screen]];
 for(const [key,ok] of rows){
  const p=st.permissions[key];const row=el('div','hands-row'+(ok?' ok':''));
  row.append(el('span','hands-dot',ok?'✓':'!'));const text=el('div','hands-text');text.append(el('strong','',p.label),el('span','',p.why));row.append(text);
  if(!ok){row.append(button('Engedély megadása',async()=>{await handsOp('hands_request',{which:key});toast('Megnyitottam a Rendszerbeállításokat: kapcsold be az „ORBIT Hands” kapcsolót, majd gyere vissza.');}));
   row.append(button('Be van kapcsolva, mégsem megy',async()=>{await handsOp('hands_reset',{which:key});toast('Az ORBIT Hands régi bejegyzését töröltem. A felugró ablakban engedélyezd újra, és kapcsold be a listában.');},'secondary'));}
  else row.append(el('span','hands-ok','Megadva'));
  body.append(row);
 }
 if(!st.running)body.append(el('p','hands-warn','Az ORBIT Hands most nem fut. '+(st.error||'')));
 // Cursor style: the ORBIT core (default) or the yarn ball; a click switches and shows it on screen.
 const styles=el('div','hands-styles');styles.append(el('strong','','Az ORBIT egere'));
 const grid=el('div','hands-style-grid');
 for(const [key,label,art,desc] of [['orbit','ORBIT mag',ORBITCUR,'Izzó mag keringő holddal, üstököscsóva és fénysugár a kattintás helyéig.'],['yarn','Fonalgombolyag',YARN,'Gombolyag, amelyből fonal fut oda, ahová kattint.']]){
  const card=el('button','hands-style'+((st.style||'orbit')===key?' active':''));card.type='button';const pic=el('div','hands-style-art');pic.innerHTML=art;card.append(pic,el('strong','',label),el('span','',desc));
  card.onclick=()=>act(async()=>{await handsOp('hands_style',{name:key});grid.querySelectorAll('.hands-style').forEach(b=>b.classList.remove('active'));card.classList.add('active');toast(label+' kiválasztva – nézd a képernyőt.');});
  grid.append(card);
 }
 styles.append(grid,el('span','hands-note','Amikor az ORBIT vezérli a gépet, jobb fent a menüsorban „◉ ORBIT vezérel” látszik; az Esc billentyűvel vagy a menüből bármikor leállíthatod.'));
 body.append(styles);
 const actions=el('div','hands-actions');
 actions.append(button('Állapot frissítése',async()=>{$('modal').close();showHands(true);},'secondary'));
 actions.append(button('Kurzor kipróbálása',async()=>{await handsOp('hands_test');toast('Nézd a képernyőt: megjelenik a fonalgombolyag.');},'secondary'));
 body.append(actions);
 body.append(el('p','hands-note','A macOS az engedélyt az „ORBIT Hands” nevű segédappnak adja (a saját Programok mappádban). Ha a kapcsoló be van kapcsolva, de itt mégis felkiáltójel látszik, a bejegyzés egy régebbi változathoz tartozik: nyomd meg a „Be van kapcsolva, mégsem megy” gombot. Jelszót, kártyaszámot nem gépel, és végleges vásárlás, küldés, közzététel vagy törlés gombot nem nyom meg: azt mindig te teszed.'));
 showModal('Gépvezérlés és engedélyek',body);
}
window.showHands=showHands;
// On start: if a permission is missing, say so once per day, with the buttons that open the right window.
setTimeout(async()=>{try{const st=await handsOp('hands_status');if(st.accessibility&&st.screen)return;const key='orbitHandsAsked';const day=new Date().toDateString();if(localStorage.getItem(key)===day)return;localStorage.setItem(key,day);showHands();}catch(e){}},2500);
})();
