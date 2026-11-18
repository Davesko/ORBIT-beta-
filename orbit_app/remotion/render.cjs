// Fixed composition, local media only. Never evaluate model-provided JS or URLs.
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {randomUUID}=require('node:crypto');
const {selectComposition,renderMedia}=require('@remotion/renderer');

async function main(){
  const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
  if(data.contract.schema_version!=='orbit.edit.v1')throw new Error('Unsupported edit contract');
  const file=fs.realpathSync(data.base),size=fs.statSync(file).size,token='/'+randomUUID()+'.mp4';
  const server=http.createServer((req,res)=>{
    if(req.url!==token||!['GET','HEAD'].includes(req.method)){res.writeHead(404);res.end();return;}
    const match=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');
    let start=match?Number(match[1]):0,end=match&&match[2]?Number(match[2]):size-1;
    if(start>end||end>=size){res.writeHead(416);res.end();return;}
    const headers={'Content-Type':'video/mp4','Content-Length':end-start+1,'Accept-Ranges':'bytes','Access-Control-Allow-Origin':'*'};
    if(match)headers['Content-Range']=`bytes ${start}-${end}/${size}`;
    res.writeHead(match?206:200,headers);
    if(req.method==='HEAD')res.end();else {const stream=fs.createReadStream(file,{start,end});stream.on('error',()=>res.destroy());stream.pipe(res);req.on('close',()=>stream.destroy());}
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const inputProps={contract:data.contract,src:`http://127.0.0.1:${server.address().port}${token}`};
  const opts={serveUrl:path.join(__dirname,'dist'),inputProps,
    concurrency:2,offthreadVideoThreads:1,offthreadVideoCacheSizeInBytes:128*1024*1024,
    chromiumOptions:{disableWebSecurity:false}};
  try {
    const composition=await selectComposition({...opts,id:'OrbitShort'});
    await renderMedia({...opts,composition,codec:'h264',crf:18,pixelFormat:'yuv420p',
      outputLocation:data.output,overwrite:false,muted:true,
      onProgress:({progress})=>{
        const elapsed=data.contract.output.duration_frames/30*(.65+.30*progress);
        fs.writeFileSync(data.progress,`out_time_us=${Math.round(elapsed*1e6)}\nprogress=continue\n`);
      }});
  } finally {await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
