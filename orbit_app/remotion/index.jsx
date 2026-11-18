import React,{useLayoutEffect,useMemo,useState} from 'react';
import {AbsoluteFill,Composition,OffthreadVideo,registerRoot,useCurrentFrame,delayRender,continueRender,cancelRender} from 'remotion';

export const CaptionLayer=({captions,frame})=>{
  const p=captions.preset,box=p.box||[108,880,864,1220],anchor=p.anchor||[486,1200];
  const [ready]=useState(()=>delayRender('Measure caption fonts'));
  const [sizes,setSizes]=useState({});
  useLayoutEffect(()=>{
    let cancelled=false;
    const font=p.font||'Arial';
    document.fonts.load(`800 ${p.font_size||76}px "${font}"`).then(()=>{
      if(cancelled)return;
      const ctx=document.createElement('canvas').getContext('2d');
      const measured={};
      for(const page of captions.pages){
        const width=Math.min(680,box[2]-box[0]-32),height=anchor[1]-box[1]-12;
        let size=p.font_size||76;
        // Exact browser font metrics, with padding and maximum active-word scale.
        for(;size>24;size--){
          ctx.font=`800 ${size}px "${font}"`;
          let lines=1,used=0,wide=false;
          for(const w of page.words){
            const n=ctx.measureText(w.text).width*1.08+20;
            if(n>width){wide=true;break;}
            if(used&&used+n+12>width){lines++;used=0;}
            used+=n+12;
          }
          if(!wide&&lines<=2&&lines*size*1.25<=height)break;
        }
        if(size<=24)throw Error('Caption cannot fit saved safe area');
        measured[page.start_frame]=size;
      }
      setSizes(measured);continueRender(ready);
    }).catch(cancelRender);
    return ()=>{cancelled=true;};
  },[captions,ready]);
  const page=captions.pages.find(p=>p.start_frame<=frame&&frame<p.end_frame);
  if(!page)return null;
  const active=page.words.find(w=>w.start_frame<=frame&&frame<w.end_frame);
  const age=active?frame-active.start_frame:10;
  const pop=p.animation==='word-pop'?1+0.08*Math.max(0,1-age/3):1;
  const opacity=p.animation==='fade'?Math.min(1,(frame-page.start_frame+1)/2):1;
  return <div style={{position:'absolute',left:box[0],top:box[1],width:box[2]-box[0],height:box[3]-box[1],overflow:'hidden'}}>
    <div style={{position:'absolute',bottom:box[3]-anchor[1],left:0,width:'100%',display:'flex',justifyContent:'center'}}>
      <div style={{maxWidth:Math.min(680,box[2]-box[0]-32),display:'flex',flexWrap:'wrap',justifyContent:'center',alignItems:'baseline',gap:12,
        fontFamily:`"${p.font||'Arial'}",Arial,sans-serif`,fontSize:sizes[page.start_frame]||p.font_size||76,fontWeight:800,lineHeight:1.16,
        color:'white',textAlign:'center',opacity,WebkitTextStroke:'1.5px #101010',paintOrder:'stroke fill',
        textShadow:'0 3px 5px rgba(0,0,0,.85)'}}>
        {page.words.map((w,i)=><span key={i} style={{display:'inline-block',padding:'0 10px',borderRadius:12,
          background:p.treatment==='pill'&&w===active?'#17212ee8':'transparent',
          borderBottom:p.treatment==='impact'&&w===active?`4px solid ${p.highlight}`:'4px solid transparent',
          color:w===active?(p.highlight||'#BFA3FF'):'white',transform:`scale(${w===active?pop:1})`}}>{w.text}</span>)}
      </div>
    </div>
  </div>;
};
const Short=({contract,src})=>{
  const frame=useCurrentFrame();
  const wipes=(contract.effects||[]).filter(e=>e.type==='wipe'&&e.start_frame<=frame&&frame<e.end_frame);
  return <AbsoluteFill style={{backgroundColor:'#101010'}}>
    <OffthreadVideo src={src} muted style={{width:'100%',height:'100%',objectFit:'cover'}}/>
    {wipes.map((e,i)=>{const t=(frame-e.start_frame)/(e.end_frame-e.start_frame);return <AbsoluteFill key={i} style={{background:e.parameters.color,transform:`translateX(${(t*2-1)*115}%) skewX(-12deg)`}}/>;})}
    <CaptionLayer captions={contract.captions} frame={frame}/>
  </AbsoluteFill>;
};
const Root=()=> <Composition id="OrbitShort" component={Short} width={1080} height={1920} fps={30}
  durationInFrames={30} defaultProps={{contract:{output:{duration_frames:30},captions:{pages:[],preset:{}}},src:''}}
  calculateMetadata={({props})=>({durationInFrames:props.contract.output.duration_frames})}/>;
registerRoot(Root);
