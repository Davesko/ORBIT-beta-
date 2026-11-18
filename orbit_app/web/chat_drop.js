/* macOS hands over one-use tokens for user-selected files, never arbitrary file paths. */
let commandAttachments=[],chatAttachmentBusy=0,chatAttachmentEpoch=0;
function pendingChatAttachments(){return [...(commandImage?[commandImage]:[]),...commandAttachments];}
function clearChatAttachments(){commandImage=null;commandAttachments=[];chatAttachmentEpoch++;updateAttachment();}
function attachmentScope(){return {project,session:chatSession,epoch:chatAttachmentEpoch};}
function sameAttachmentScope(scope){return scope.project===project&&scope.session===chatSession&&scope.epoch===chatAttachmentEpoch;}
async function pickChatAttachment(){
 if(pendingChatAttachments().length+chatAttachmentBusy>=8)throw Error('Egy üzenethez legfeljebb 8 fájlt csatolj.');
 const scope=attachmentScope();chatAttachmentBusy++;updateAttachment();$('commandSend').disabled=true;
 try{const result=await call('command_pick_image',{requestProject:scope.project});if(!result.cancelled&&sameAttachmentScope(scope))commandAttachments.push(result);}
 finally{chatAttachmentBusy--;updateAttachment();$('commandSend').disabled=commandSending||!!chatAttachmentBusy;}
}
function dropTarget(x,y){const target=document.elementFromPoint(x,y);return !!target?.closest('#commandApp')&&!target.closest('#canvasPanel');}
function dropHint(){let hint=$('chatDropHint');if(!hint){hint=el('div','chat-drop-hint');hint.id='chatDropHint';hint.hidden=true;hint.append(el('strong','','Engedd ide a fájlokat'),el('small','','Dokumentum · kép · videó · hang · legfeljebb 8 fájl, egyenként 2 GB'));$('commandApp').append(hint);}return hint;}
window.orbitDropHover=(x,y)=>{dropHint().hidden=!dropTarget(x,y);};
window.orbitDropLeave=()=>{dropHint().hidden=true;};
window.orbitReceiveDroppedFiles=(items,x,y)=>{
 window.orbitDropLeave();if(!dropTarget(x,y)){toast('A csatoláshoz a chat területére húzd a fájlt.');return false;}
 if(!Array.isArray(items)||pendingChatAttachments().length+chatAttachmentBusy+items.length>8){toast('Egy üzenethez legfeljebb 8 fájlt csatolj.',true);return false;}
 const scope=attachmentScope();chatAttachmentBusy+=items.length;updateAttachment();$('commandSend').disabled=true;
 act(async()=>{for(const item of items){try{const result=await call('command_import_drop',{token:item.token,requestProject:scope.project});
   if(sameAttachmentScope(scope))commandAttachments.push(result);else toast('A fájl az eredeti projekt Alkotások gyűjteményébe került.');
  }catch(error){toast(item.label+': '+error.message,true);}
  finally{chatAttachmentBusy--;updateAttachment();$('commandSend').disabled=commandSending||!!chatAttachmentBusy;}
 }});return true;
};
// The native view owns file drops; prevent WebKit navigating to a dropped local document.
function filePart(blob){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('A fájlrészlet nem olvasható.'));reader.readAsDataURL(blob);});}
async function importWebFile(file,scope){
 const start=await call('command_file_begin',{name:file.name,size:file.size,requestProject:scope.project});
 try{
  for(let offset=0;offset<file.size;offset+=512*1024){const data=await filePart(file.slice(offset,offset+512*1024));await call('command_file_chunk',{token:start.token,offset,data,requestProject:scope.project});}
  return await call('command_file_end',{token:start.token,requestProject:scope.project});
 }catch(error){await call('command_file_abort',{token:start.token,requestProject:scope.project}).catch(()=>{});throw error;}
}
document.addEventListener('dragover',event=>{if([...event.dataTransfer?.types||[]].includes('Files')){event.preventDefault();window.orbitDropHover(event.clientX,event.clientY);}});
document.addEventListener('dragleave',event=>{if(!event.relatedTarget)window.orbitDropLeave();});
document.addEventListener('drop',event=>{
 const files=[...event.dataTransfer?.files||[]];if(!files.length)return;event.preventDefault();window.orbitDropLeave();
 if(!dropTarget(event.clientX,event.clientY))return;
 if(files.length+pendingChatAttachments().length+chatAttachmentBusy>8||files.some(file=>!file.size||file.size>2*1024**3)){toast('Legfeljebb 8 fájl, egyenként legfeljebb 2 GB csatolható.',true);return;}
 const scope=attachmentScope();chatAttachmentBusy+=files.length;updateAttachment();$('commandSend').disabled=true;
 act(async()=>{for(const file of files){try{const result=await importWebFile(file,scope);if(sameAttachmentScope(scope))commandAttachments.push(result);else toast('A fájl az eredeti projekt Alkotások gyűjteményébe került.');}
  catch(error){toast(file.name+': '+error.message,true);}finally{chatAttachmentBusy--;updateAttachment();$('commandSend').disabled=commandSending||!!chatAttachmentBusy;}
 }});
});
$('projectSelect').addEventListener('change',clearChatAttachments);
