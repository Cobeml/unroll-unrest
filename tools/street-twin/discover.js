const $=id=>document.getElementById(id),href=p=>new URL(p,document.baseURI).href;
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,options={}){const r=await fetch(href(path),options);const d=await r.json();if(!r.ok)throw new Error(d.error||'Request unavailable. Try again.');return d;}
function error(e){$('error-banner').hidden=false;$('error-banner').textContent=e.message||'Request unavailable.';}
let page=0,total=0,selected=null,criteria=null,requestId=0,pollTimer=null;
let detections=null,yolo=false;
const video=$('preview-video'),canvas=$('preview-overlay');
function pane(preview){$('discovery-grid').classList.toggle('show-preview',preview);$('preview-tab').setAttribute('aria-pressed',preview);$('candidates-tab').setAttribute('aria-pressed',!preview);}
$('preview-tab').onclick=()=>pane(true);$('candidates-tab').onclick=()=>pane(false);
async function results(){
 const generation=++requestId;$('search-button').disabled=true;$('error-banner').hidden=true;
 $('candidates').innerHTML='<p class="loading-message">Searching indexed captions and visual embeddings…</p>';
 try{
  const d=await api('api/discover?'+new URLSearchParams({...criteria,page}));if(generation!==requestId)return;total=d.total;
  $('candidates').innerHTML=d.candidates.length?d.candidates.map((c,i)=>`<button class="candidate" data-choice="${i}" aria-pressed="false"><strong>${escape(c.location)}</strong><span>${escape(c.camera_id)} · ${c.start_sec.toFixed(1)}–${c.end_sec.toFixed(1)} s · Candidate</span><span class="snippet">${escape(c.caption)}</span></button>`).join(''):'<p class="loading-message">No matching candidates. Try another search or camera.</p>';
  $('page-label').textContent=total?`${page+1} / ${Math.ceil(total/4)} · ${total} parents`:'0 candidates';
  $('previous').disabled=page===0;$('next').disabled=(page+1)*4>=total;
  document.querySelectorAll('[data-choice]').forEach(b=>b.onclick=()=>choose(d.candidates[Number(b.dataset.choice)],b));
 }catch(e){error(e);$('candidates').innerHTML='<p class="loading-message">Search unavailable. Retry when the archive returns.</p>';}finally{$('search-button').disabled=false;}
}
function choose(c,button){
 selected=c;detections=null;yolo=false;canvas.hidden=true;
 document.querySelectorAll('[data-choice]').forEach(b=>b.setAttribute('aria-pressed',b===button));
 video.src=href('api/stream/'+c.id);video.hidden=false;$('preview-empty').hidden=true;
 $('preview-label').textContent=`${c.camera_id} · ${c.start_sec.toFixed(1)}–${c.end_sec.toFixed(1)} s matched. Full parent will run.`;
 $('analyze').disabled=false;$('preview-yolo').disabled=false;$('preview-yolo').textContent='YOLO objects';
 if(innerWidth<=700)pane(true);
}
$('filters').onsubmit=e=>{e.preventDefault();page=0;criteria={kind:$('kind').value,location:$('location').value,camera_id:$('camera_id').value};results();};
$('previous').onclick=()=>{page--;results();};$('next').onclick=()=>{page++;results();};
$('preview-yolo').onclick=async()=>{
 if(!selected)return;
 if(!detections){try{detections=await api('api/detections/'+selected.id);}catch(e){error(e);return;}}
 yolo=!yolo;canvas.hidden=!yolo;$('preview-yolo').textContent=yolo?'Hide objects':'YOLO objects';
 if(!detections.available)$('preview-label').textContent='No YOLO sidecar for this segment. Video remains available.';
};
function draw(){
 if(yolo&&detections?.available&&video.readyState>=1){
  const r=canvas.getBoundingClientRect();canvas.width=Math.round(r.width);canvas.height=Math.round(r.height);
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  const frame=(detections.frames||[]).reduce((best,f)=>Math.abs(f.time_sec-video.currentTime)<Math.abs((best?.time_sec??1e9)-video.currentTime)?f:best,null);
  if(frame&&Math.abs(frame.time_sec-video.currentTime)<.15){
   const shape=frame.shape||detections.video_shape||[1080,1920],scale=Math.min(canvas.width/shape[1],canvas.height/shape[0]);
   const ox=(canvas.width-shape[1]*scale)/2,oy=(canvas.height-shape[0]*scale)/2;ctx.font='13px Georgia, serif';ctx.strokeStyle='#92daee';ctx.fillStyle='#92daee';ctx.lineWidth=2;
   for(const d of frame.detections||[]){const b=d.bbox;if(!b||d.confidence<.5)continue;ctx.strokeRect(ox+b[0]*scale,oy+b[1]*scale,(b[2]-b[0])*scale,(b[3]-b[1])*scale);ctx.fillText(d.class_name||'object',ox+b[0]*scale,oy+b[1]*scale-4);}
  }
 }requestAnimationFrame(draw);
}requestAnimationFrame(draw);
$('analyze').onclick=async()=>{
 if(!selected)return;$('analyze').disabled=true;video.pause();
 try{const job=await api('api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({segment_id:selected.id})});location.href=href(job.result_url||'runs/'+job.id);}catch(e){error(e);$('analyze').disabled=false;}
};
const jobId=location.pathname.match(/\/runs\/([a-f0-9]{24})/)?.[1];
function runShell(){
 $('workspace').innerHTML='<div class="workspace-heading"><h1>Rebuilding the street</h1><p>Existing archive video → reconstructed approach → reviewed evidence</p></div><section class="run-layout" id="run-detail" aria-live="polite"><p>Loading the saved run…</p></section>';
}
async function poll(){
 try{
  const j=await api('api/runs/'+jobId);$('error-banner').hidden=true;
  const stages=['transfer','frames','geometry','detect','export','review','import','complete'],at=stages.indexOf(j.stage);
  $('run-detail').innerHTML=`<span class="eyebrow">${escape(j.status)}</span><h2>${escape(j.message)}</h2><div class="run-steps">${stages.slice(0,7).map((s,i)=>`<span class="${i===at?'active':i<at?'done':''}">${escape(({transfer:'Transfer',frames:'Frames',geometry:'3D map',detect:'Objects',export:'Export',review:'Review',import:'Import'})[s])}</span>`).join('')}</div><div class="run-progress"><i style="width:${j.status==='complete'?100:Math.max(3,(at+1)/8*100)}%"></i></div><p class="run-meta">${escape(j.source_filename)}<br>${escape(j.camera_id)} · ${escape(j.location)}<br>Selected segment ${escape(j.selected_segment_id)}</p><p class="run-meta">${j.source_bytes?`${(j.uploaded_bytes/1048576).toFixed(1)} / ${(j.source_bytes/1048576).toFixed(1)} MiB transferred`:'Full parent chunk'}${j.source_sha256?' · source SHA-256 recorded':''}<br>You can leave this page. The worker keeps processing.</p>${j.summary?`<p>${j.summary.objects} objects · ${j.summary.crossings_assessed} assessed crossings · ${j.summary.recommendations} supported recommendations</p>`:''}<div class="run-actions">${j.result_url?`<a class="primary" href="${href(j.result_url)}">Explore this street ↗</a>`:''}${j.status==='failed'?'<button id="retry" class="primary">Retry processing</button>':''}<a href="${href('discover')}">Find another clip</a></div>`;
  $('retry')?.addEventListener('click',async()=>{try{await api('api/runs/'+jobId+'/retry',{method:'POST'});poll();}catch(e){error(e);}});
  if(!['complete','failed'].includes(j.status))pollTimer=setTimeout(poll,5000);
 }catch(e){error(e);pollTimer=setTimeout(poll,10000);}
}
$('recent').onclick=async()=>{
 try{
  const d=await api('api/runs');let index=0;const runs=d.runs;
  $('workspace').innerHTML='<div class="workspace-heading"><h1>Recent runs</h1><a href="'+href('discover')+'">← Find clips</a></div><section id="runs-page"></section><div class="pager"><button id="runs-prev">Previous</button><span id="runs-label"></span><button id="runs-next">Next</button></div>';
  const render=()=>{$('runs-page').innerHTML=runs.slice(index*5,index*5+5).map(j=>`<div class="run-list-row"><a href="${href(j.result_url||'runs/'+j.id)}">${escape(j.source_filename)}</a><span>${escape(j.status)}</span></div>`).join('')||'<p>No runs yet.</p>';$('runs-label').textContent=`${index+1} / ${Math.max(1,Math.ceil(runs.length/5))}`;$('runs-prev').disabled=index===0;$('runs-next').disabled=(index+1)*5>=runs.length;};
  $('runs-prev').onclick=()=>{index--;render();};$('runs-next').onclick=()=>{index++;render();};render();
 }catch(e){error(e);}
};
if(jobId){runShell();poll();}else{
 api('api/metadata').then(m=>{for(const key of ['location','camera_id'])for(const value of m[key]||[]){const o=document.createElement('option');o.value=value;o.textContent=value;$(key).appendChild(o);}criteria={kind:'close-call'};results();}).catch(error);
}
addEventListener('pagehide',()=>clearTimeout(pollTimer));
