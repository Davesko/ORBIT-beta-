/* Keep the operator's disclosure choices across polling-driven DOM replacement. */
(()=>{
 const choices=new Map();let modalSequence=0;
 const baseModal=showModal;showModal=function(...args){$('modalBody').dataset.disclosureScope=String(++modalSequence);return baseModal(...args);};
 function key(d){const turn=d.closest('[data-turn-id]'),auto=d.closest('#automationDetail'),work=d.closest('#agentWork'),modal=d.closest('#modalBody');const context=turn?'turn:'+turn.dataset.turnId:auto?'automation:'+project+':'+automationSelected:work?'work:'+project+':'+selected+':'+work.dataset.job:modal?'modal:'+modal.dataset.disclosureScope:'app:'+project+':'+selected;
  const parts=[];let node=d;while(node?.tagName==='DETAILS'){const label=node.querySelector(':scope > summary');parts.unshift(node.dataset.detailKey||node.id||label?.textContent.replace(/\s*·\s*\d+.*$/,'').trim()||'details');node=node.parentElement?.closest('details');}return context+'|'+parts.join('/');}
 document.addEventListener('click',e=>{if(e.target.closest?.('button,a,input,select,textarea'))return;const summary=e.target.closest?.('summary');if(!summary||summary.parentElement.tagName!=='DETAILS'||e.defaultPrevented)return;const d=summary.parentElement;choices.set(key(d),!d.open);if(choices.size>600)choices.delete(choices.keys().next().value);},true);
 function restore(node){if(!(node instanceof Element))return;const details=[...(node.matches('details')?[node]:[]),...node.querySelectorAll('details')];for(const d of details){const value=choices.get(key(d));if(value!==undefined&&d.open!==value)d.open=value;}}
 new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)restore(node);}).observe(document.body,{childList:true,subtree:true});
})();
