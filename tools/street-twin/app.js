'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=s=>`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
const locationName=s=>({new_york:'New York',san_francisco:'San Francisco',nashville:'Nashville / I-24',neighborhood:'Neighborhood',toronto:'Toronto'}[s]||s);
const titles={cyclist_passage_review:'Review cyclist passage',curb_use_review:'Review curb allocation',crossing_review:'Review crossing clearance',queue_review:'Review intersection approaches'};
const colors={person:'#7bcbb7',bicycle:'#d6ed7c',car:'#90b9df',truck:'#e6c88b',bus:'#dfa6c4',motorcycle:'#b7cba5'};
const state={clips:[],recommendations:[],selected:null,metadata:null,detections:null,highlight:'all',context:new URLSearchParams(location.search),operation:0,selection:0,policy:null};
const policyId=location.pathname.match(/\/policy\/([a-f0-9]{16})\/?$/)?.[1];
function url(path){return new URL(path,document.baseURI);}
function apiURL(path){return url('api/'+path).href;}
function status(message='',error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
async function api(path,options={}){const response=await fetch(apiURL(path),options);const data=await response.json();if(!response.ok)throw new Error(data.error||'Archive unavailable');return data;}
function choose(id,values,placeholder,selected=''){$(id).innerHTML=`<option value="">${esc(placeholder)}</option>`+values.map(v=>`<option value="${esc(v)}">${esc(id==='location'?locationName(v):v)}</option>`).join('');$(id).value=values.includes(selected)?selected:'';}
function filterParams(){const p=new URLSearchParams({view:'archive'});[['location','location'],['camera_id','camera'],['start','start'],['end','end']].forEach(([k,id])=>{if($(id).value)p.set(k,$(id).value);});if($('query').value.trim())p.set('query',$('query').value.trim());return p;}
function policyURL(id){const href=url('policy/'+id);href.search=state.context;return href.href;}
function renderWorkspace(data){
 state.clips=data.clips;state.recommendations=data.recommendations;state.policy=null;
 $('view-location').textContent=locationName($('location').value)||'Street archive';
 $('sample-summary').textContent=`${data.sample_count} SAMPLED CLIPS${data.available_clips!=null?' / '+data.available_clips+' AVAILABLE':''}`;
 $('policy-count').textContent=data.recommendations.length?`${data.recommendations.length} REVIEWS`:'';
 $('policies').innerHTML=data.recommendations.length?data.recommendations.map(r=>`<a class="policy-card" href="${esc(policyURL(r.id))}"><div class="category"><span>${esc(r.label.toUpperCase())}</span><span>↗</span></div><h3>${esc(titles[r.type])}</h3><div class="bottom"><span>${r.metrics.evidence_clips} supporting clips</span><span>Open policy →</span></div></a>`).join(''):'<p class="muted">No supported policy reviews in this sample.</p>';
 const selected=data.clips.find(c=>c.filename.includes('GOPR0130_chunk_0004_segment_005'))||data.clips[0];
 if(selected)selectClip(selected);else clearVideo();
 status('');
}
async function loadView(p=filterParams()){
 const operation=++state.operation;status('Loading street footage…');
 try{
  let data;
  if(p.has('demo'))data=await api('demo/'+encodeURIComponent(p.get('demo')));
  else data=await api((p.get('query')?'search':'analytics')+'?'+p);
  if(operation!==state.operation)return;
  state.context=p;const href=url('./');href.search=p;history.replaceState(null,'',href);
  renderWorkspace(data);
 }catch(e){if(operation===state.operation)status(e.message,true);}
}
function clearVideo(){++state.selection;state.selected=null;state.detections=null;$('video').removeAttribute('src');$('video').load();$('video-empty').hidden=false;$('object-chips').innerHTML='';$('clip-time').textContent='—';$('clip-index').textContent='0 / 0';$('camera-label').textContent='No footage';$('clip-detail-content').textContent='';$('previous').disabled=true;$('next').disabled=true;$('detection-status').textContent='NO CLIP';drawDetections();}
function renderClipDetails(clip){
 $('camera-label').textContent=clip.camera_id;
 $('clip-time').textContent=`${time(clip.start_sec)}–${time(clip.end_sec)} · Segment ${clip.segment_number}`;
 $('spatial-ref').textContent='SEG '+clip.id.slice(0,10);
 $('clip-detail-content').innerHTML=`<p>${esc(clip.caption)}</p><p>${esc(locationName(clip.location))} · Indexed ${esc((clip.indexed_at||'').slice(0,10))}</p><code>${esc(clip.source)}</code>`;
}
async function selectClip(clip){
 const selection=++state.selection;state.selected=clip;state.detections=null;state.highlight='all';
 $('video-empty').hidden=true;$('video').src=apiURL('stream/'+clip.id);$('detection-status').textContent='LOADING OBJECTS';renderClipDetails(clip);renderObjects();
 const index=state.clips.findIndex(c=>c.id===clip.id);
 $('clip-index').textContent=`${index+1} / ${state.clips.length}`;$('previous').disabled=index<=0;$('next').disabled=index>=state.clips.length-1;
 document.querySelectorAll('.citation').forEach(c=>c.classList.toggle('selected',c.dataset.id===clip.id));
 if(!matchMedia('(prefers-reduced-motion: reduce)').matches)$('video').play().catch(()=>{});
 const results=await Promise.allSettled([api('evidence/'+clip.id),api('detections/'+clip.id)]);
 if(selection!==state.selection)return;
 if(results[0].status==='fulfilled'){state.selected={...clip,...results[0].value};renderClipDetails(state.selected);}
 if(results[1].status==='fulfilled'){state.detections=results[1].value;$('detection-status').textContent=state.detections.available?'YOLO OBJECTS':'NO FRAME DATA';}
 else $('detection-status').textContent='OBJECT DATA UNAVAILABLE';
 renderObjects();drawDetections();
}
function renderObjects(){
 const clip=state.selected;
 if(!clip)return;
 const labels=Object.keys(colors).filter(l=>clip.object_classes.includes(l));
 $('object-chips').innerHTML=`<button class="object-chip active" data-object="all" aria-pressed="true">All objects</button>`+labels.map(l=>`<button class="object-chip" data-object="${l}" aria-pressed="false"><span style="color:${colors[l]}">●</span> ${l}</button>`).join('');
 $('object-chips').querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{
  state.highlight=button.dataset.object;
  $('object-chips').querySelectorAll('button').forEach(b=>{const active=b.dataset.object===state.highlight;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  drawDetections();
 }));
}
function currentFrame(){
 if(!state.detections?.available)return null;
 const frames=state.detections.frames;
 let low=0,high=frames.length-1;const t=$('video').currentTime;
 while(low<high){const mid=Math.floor((low+high)/2);if(frames[mid].time_sec<t)low=mid+1;else high=mid;}
 const candidates=[frames[low],frames[Math.max(0,low-1)]].filter(Boolean);
 const frame=candidates.sort((a,b)=>Math.abs(a.time_sec-t)-Math.abs(b.time_sec-t))[0];
 return frame&&Math.abs(frame.time_sec-t)<.12?frame:null;
}
function drawDetections(){
 const video=$('video'),canvas=$('detections'),ctx=canvas.getContext('2d');
 const w=video.clientWidth,h=video.clientHeight;
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 ctx.clearRect(0,0,w,h);
 if(!$('show-detections').checked||!video.videoWidth)return;
 const frame=currentFrame();if(!frame)return;
 const [fh,fw]=frame.shape||state.detections.video_shape;
 const scale=Math.min(w/video.videoWidth,h/video.videoHeight),dw=video.videoWidth*scale,dh=video.videoHeight*scale;
 const ox=(w-dw)/2,oy=(h-dh)/2,sx=dw/fw,sy=dh/fh;
 ctx.font='10px monospace';ctx.lineWidth=1.6;
 for(const d of frame.detections){
  if(d.confidence<.5||!colors[d.label]||(state.highlight!=='all'&&state.highlight!==d.label))continue;
  const [x1,y1,x2,y2]=d.bbox,x=ox+x1*sx,y=oy+y1*sy;
  ctx.strokeStyle=colors[d.label];ctx.strokeRect(x,y,(x2-x1)*sx,(y2-y1)*sy);
  const text=`${d.label} ${Math.round(d.confidence*100)}%`,ty=Math.max(oy,y-16);
  ctx.fillStyle='#0d1c16d9';ctx.fillRect(x,ty,ctx.measureText(text).width+8,16);ctx.fillStyle=colors[d.label];ctx.fillText(text,x+4,ty+11);
 }
}
function navigateClip(delta){const index=state.clips.findIndex(c=>c.id===state.selected?.id);const clip=state.clips[index+delta];if(clip)selectClip(clip);}
$('previous').addEventListener('click',()=>navigateClip(-1));$('next').addEventListener('click',()=>navigateClip(1));
$('show-detections').addEventListener('change',drawDetections);
$('video').addEventListener('error',()=>{if(state.selected)status('Playback unavailable. Clip references remain available.',true);});
$('filter-toggle').addEventListener('click',()=>{$('filter-drawer').hidden=!$('filter-drawer').hidden;$('filter-toggle').setAttribute('aria-expanded',String(!$('filter-drawer').hidden));});
$('filter-drawer').addEventListener('submit',e=>{e.preventDefault();loadView();});
$('reset').addEventListener('click',()=>{$('start').value='';$('end').value='';$('query').value='';loadView();});
function updateCameras(){const region=$('location').value;choose('camera',state.metadata.camera_id.filter(c=>!region||(state.metadata.camera_locations[c]||[]).includes(region)),'All cameras',$('camera').value);}
$('location').addEventListener('change',()=>{updateCameras();loadView();});
$('camera').addEventListener('change',()=>loadView());
document.querySelectorAll('[data-demo]').forEach(button=>button.addEventListener('click',()=>{
 $('location').value='new_york';updateCameras();$('camera').value='nyc_bike_gopro-1';$('start').value='';$('end').value='';$('query').value='';
 const p=filterParams();p.set('demo',button.dataset.demo);loadView(p);
}));
async function loadPolicy(){
 $('explorer').hidden=true;$('policy-page').hidden=false;$('view-tools').hidden=true;$('back').hidden=false;$('filter-drawer').hidden=true;
 const back=url('./');back.search=state.context;$('back').href=back.href;

 try{
  const report=await api('policy/'+policyId+'?'+state.context);state.policy=report;state.clips=report.clips;
  document.title=report.title+' — StreetTwin';$('policy-title').textContent=report.title;
  $('policy-category').textContent=report.recommendation.label.toUpperCase()+' / POLICY REVIEW';
  $('policy-location').textContent=`${locationName(report.recommendation.location)} · ${report.recommendation.camera_id}`;
  const s=report.statistics;
  $('policy-statistics').innerHTML=[[s.evidence_clips,'Supporting clips'],[s.sampled_clips,'Clips in camera sample'],[s.support_percent+'%','Sampled clips with observation'],[s.evidence_seconds+'s','Referenced footage']].map(([n,label])=>`<div class="stat"><strong>${n}</strong><span>${label}</span></div>`).join('');
  $('policy-action').textContent=report.recommendation.action;$('policy-observation').textContent=report.recommendation.observation;$('policy-analysis').textContent=report.analysis;
  $('sampling-note').textContent=report.sampling_note+' Dates refer to indexing; seconds are relative to each parent video.';
  $('citation-links').innerHTML=report.clips.map(c=>`<a href="#clip-${c.id}" data-cite="${c.id}" aria-label="Open clip citation ${c.citation_number}">[${c.citation_number}]</a>`).join('');
  const max=Math.max(...s.detected_classes.map(c=>c.clip_count),1);
  $('detection-chart').innerHTML=s.detected_classes.map(c=>`<div class="detection-row"><span>${esc(c.label)}</span><div class="detection-bar"><span style="width:${c.clip_count/max*100}%"></span></div><span>${c.clip_count}</span></div>`).join('')||'<p class="note">No detection context available.</p>';
  $('policy-video-slot').appendChild(document.querySelector('.video-view'));
  $('citations').innerHTML=report.clips.map(c=>`<article class="citation" id="clip-${c.id}" data-id="${c.id}"><div class="citation-header"><span>[${c.citation_number}] ${esc(c.camera_id)} · ${time(c.start_sec)}–${time(c.end_sec)}</span><button class="play-citation" data-play="${c.id}">Play clip ↗</button></div><blockquote>${esc(c.caption_evidence)}</blockquote><details><summary>Source & full caption</summary><code>${esc(c.source)}</code><p>${esc(locationName(c.location))} · Indexed ${esc((c.indexed_at||'').slice(0,10))}</p><p>${esc(c.caption)}</p></details></article>`).join('');
  document.querySelectorAll('[data-cite],[data-play]').forEach(link=>link.addEventListener('click',()=>selectClip(state.clips.find(c=>c.id===(link.dataset.cite||link.dataset.play)))));
  $('footer-context').textContent='Statistics from cited archive observations';
  if(report.clips.length)selectClip(report.clips[0]);status('');
 }catch(e){status(e.message,true);$('policy-title').textContent='Policy unavailable';$('reason-button').hidden=true;}
}
$('reason-button').addEventListener('click',async()=>{
 if(!state.selected)return;const id=state.selected.id;
 $('reason-button').disabled=true;$('reasoning').textContent='Reading parent video…';
 try{const r=await api('reason/'+id,{method:'POST'});if(state.selected?.id===id)$('reasoning').textContent=r.answer;}
 catch(e){$('reasoning').textContent=e.message;}
 finally{$('reason-button').disabled=false;}
});
// Empty viewer scaffold only. It contains no inferred street or object geometry.
const orbit={yaw:.5,pitch:.6,distance:30,drag:null};
function drawSpatial(){
 const canvas=$('spatial-canvas');if(!canvas.clientWidth)return;
 const w=canvas.clientWidth,h=canvas.clientHeight;
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 const ctx=canvas.getContext('2d');ctx.clearRect(0,0,w,h);
 function project(x,z){
  const rx=x*Math.cos(orbit.yaw)-z*Math.sin(orbit.yaw),rz=x*Math.sin(orbit.yaw)+z*Math.cos(orbit.yaw);
  const depth=orbit.distance+rz*Math.cos(orbit.pitch);if(depth<2)return null;
  const f=Math.min(w,h)*.8;
  return [w/2+rx*f/depth,h*.68+rz*Math.sin(orbit.pitch)*f/depth];
 }
 ctx.strokeStyle='#64836138';ctx.lineWidth=.6;
 for(let n=-24;n<=24;n+=2){for(const line of [[[n,-24],[n,24]],[[-24,n],[24,n]]]){const a=project(...line[0]),b=project(...line[1]);if(a&&b){ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();}}}
}
$('spatial-canvas').addEventListener('pointerdown',e=>{orbit.drag={x:e.clientX,y:e.clientY};e.currentTarget.setPointerCapture(e.pointerId);});
$('spatial-canvas').addEventListener('pointermove',e=>{if(!orbit.drag)return;orbit.yaw+=(e.clientX-orbit.drag.x)*.008;orbit.pitch=Math.max(.2,Math.min(1.3,orbit.pitch+(e.clientY-orbit.drag.y)*.006));orbit.drag={x:e.clientX,y:e.clientY};drawSpatial();});
$('spatial-canvas').addEventListener('pointerup',()=>orbit.drag=null);
$('spatial-canvas').addEventListener('pointercancel',()=>orbit.drag=null);
$('spatial-canvas').addEventListener('wheel',e=>{e.preventDefault();orbit.distance=Math.max(16,Math.min(60,orbit.distance+e.deltaY*.03));drawSpatial();},{passive:false});
$('spatial-canvas').addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-'].includes(e.key)){e.preventDefault();if(e.key==='ArrowLeft')orbit.yaw-=.1;if(e.key==='ArrowRight')orbit.yaw+=.1;if(e.key==='ArrowUp')orbit.pitch=Math.min(1.3,orbit.pitch+.1);if(e.key==='ArrowDown')orbit.pitch=Math.max(.2,orbit.pitch-.1);if(e.key==='+')orbit.distance=Math.max(16,orbit.distance-2);if(e.key==='-')orbit.distance=Math.min(60,orbit.distance+2);drawSpatial();}});
$('reset-orbit').addEventListener('click',()=>{orbit.yaw=.5;orbit.pitch=.6;orbit.distance=30;drawSpatial();});
window.addEventListener('resize',()=>{drawSpatial();drawDetections();});
function frameLoop(){drawDetections();requestAnimationFrame(frameLoop);}requestAnimationFrame(frameLoop);
async function start(){
 if(policyId){loadPolicy();return;}
 try{
  state.metadata=await api('metadata');
  const p=state.context,hasContext=p.has('view')||p.has('demo');
  choose('location',state.metadata.location,'All locations',hasContext?(p.get('location')||''):'new_york');
  choose('camera',state.metadata.camera_id,'All cameras',hasContext?(p.get('camera_id')||''):'nyc_bike_gopro-1');updateCameras();
  $('start').value=p.get('start')||'';$('end').value=p.get('end')||'';$('query').value=p.get('query')||'';
  drawSpatial();await loadView(p.has('demo')?p:filterParams());
 }catch(e){status(e.message,true);}
}
start();
