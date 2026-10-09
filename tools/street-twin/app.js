'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {clips:[], recommendations:[], selected:null, metadata:null, detection:null, generation:0};
const locationName = value => ({new_york:'New York',san_francisco:'San Francisco',nashville:'Nashville / I-24',neighborhood:'Neighborhood',toronto:'Toronto'}[value] || value);
const time = seconds => `${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
const apiURL = path => new URL('api/'+path, document.baseURI).href;
const streamURL = id => apiURL('stream/'+encodeURIComponent(id));
function status(message, error=false) { $('status').textContent=message; $('status').classList.toggle('error',error); }
async function api(path, options={}) {
  const response=await fetch(apiURL(path),options);
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || 'Archive temporarily unavailable.');
  return data;
}
function showTab(name) {
  document.querySelectorAll('.tab').forEach(button => {
    const active = button.dataset.tab === name;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  ['analytics','evidence','spatial'].forEach(tab => $(tab+'-panel').hidden = tab !== name);
  if(name !== 'analytics') $('hero-video').pause();
}
function filterParams() {
  const p=new URLSearchParams();
  [['location','location'],['camera_id','camera'],['start','start-date'],['end','end-date']].forEach(([key,id])=>{if($(id).value)p.set(key,$(id).value);});
  return p;
}
function populateSelect(id, values, defaultText, chosen='') {
  $(id).innerHTML=`<option value="">${escapeHTML(defaultText)}</option>`+values.map(v=>`<option value="${escapeHTML(v)}">${escapeHTML(id==='location'?locationName(v):v)}</option>`).join('');
  $(id).value=values.includes(chosen)?chosen:'';
}
function renderAnalytics(data) {
  state.clips=data.clips;state.recommendations=data.recommendations;state.activeRecommendation=null;
  renderEvidenceList();
  $('sample-label').textContent=`${data.sample_count} SAMPLED / ${data.available_clips ?? '—'} AVAILABLE CLIPS`;
  $('metrics').innerHTML=[[data.sample_count,'Sampled clips'],[data.recommendations.length,'Planning reviews'],[data.camera_count,'Cameras sampled']].map(([n,label])=>`<div><strong>${n}</strong><span>${label}</span></div>`).join('');
  const max=Math.max(...data.object_chart.map(x=>x.clip_count),1);
  $('object-chart').innerHTML=data.object_chart.length?data.object_chart.map(x=>`<div class="bar-row"><span>${escapeHTML(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${x.clip_count/max*100}%"></div></div><span class="count">${x.clip_count}</span></div>`).join(''):'<p class="muted">No detections in this sample.</p>';
  $('condition-chart').innerHTML=data.conditions.map(x=>`<span class="condition"><i></i>${escapeHTML(x.label)} <b>${x.clip_count}</b></span>`).join('');
  $('review-count').textContent='CAPTION-SUPPORTED OBSERVATIONS';
  renderRecommendations();
  const hero=data.clips.find(c=>c.filename.includes('GOPR0130_chunk_0004_segment_005')) || data.clips[0];
  if(hero) {
    state.hero=hero;
    $('hero-video').src=streamURL(hero.id);
    if(!matchMedia('(prefers-reduced-motion: reduce)').matches) $('hero-video').play().catch(()=>{});
    $('hero-title').textContent=hero.observation_tags.includes('Cyclist passage')?'Delivery vehicles narrow cyclist passage.':'A recorded view of the street.';
    $('hero-camera').textContent=hero.camera_id;
    $('hero-location').textContent=locationName(hero.location);
    $('hero-time').textContent=`Segment ${hero.segment_number} · ${time(hero.start_sec)}–${time(hero.end_sec)}`;
    $('hero-duration').textContent=`${hero.duration}s CLIP`;
  } else {
    state.hero=null;$('hero-video').removeAttribute('src');$('hero-video').load();
    $('hero-title').textContent='No clips in this view.';$('hero-camera').textContent='VIDEO EVIDENCE';
    $('hero-location').textContent='Adjust the filters';$('hero-time').textContent='';$('hero-duration').textContent='';
  }
}
async function loadAnalytics() {
  const generation=++state.generation;
  status('Sampling recorded street footage…');
  document.querySelector('.apply').disabled=true;
  try {
    const data=await api('analytics?'+filterParams());
    if(generation!==state.generation)return;
    clearPlayer();renderAnalytics(data);
    if(data.clips.length)selectClip(data.clips[0].id);
    status(`${data.sample_count} sampled clips across ${data.camera_count} cameras. Dates refer to indexing; observations refer to recorded footage.`);
  } catch(error) { if(generation===state.generation)status(error.message,true); }
  finally {if(generation===state.generation)document.querySelector('.apply').disabled=false;}
}
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => showTab(button.dataset.tab)));
$('hero-open').addEventListener('click',()=>{if(state.hero) {showTab('evidence');selectClip(state.hero.id);}});
$('filters').addEventListener('submit', event => {event.preventDefault();loadAnalytics();});
async function start() {
  try {
    state.metadata=await api('metadata');
    populateSelect('location',state.metadata.location,'All street locations','new_york');
    populateSelect('camera',state.metadata.camera_id.filter(c=>!c.includes('warehouse')&&!c.includes('smartspace')),'All street cameras','nyc_bike_gopro-1');
    await loadAnalytics();
  } catch(error) {status(error.message,true);}
}


function clipTitle(clip) {
  const first=clip.caption.split(/(?<=[.!?])\s/)[0] || 'Recorded street segment';
  return first.length>145?first.slice(0,142)+'…':first;
}
function tagsHTML(clip) {
  const reviews=state.recommendations.filter(r=>r.segment_refs.some(ref=>ref.segment_id===clip.id));
  const labels=reviews.length?reviews.map(r=>r.label):(clip.observation_tags||[]);
  return [...new Set(labels)].map(t=>`<span>${escapeHTML(t)}</span>`).join('');
}
function renderEvidenceList(clips=null) {
  if(clips===null) {
    const ids=state.activeRecommendation?.segment_refs.map(r=>r.segment_id);
    clips=ids?state.clips.filter(c=>ids.includes(c.id)):state.clips;
  }
  $('evidence-count').textContent=`${clips.length} RECORDED SEGMENTS`;
  $('clip-list').innerHTML=clips.length?clips.map(c=>`<button class="evidence-card ${state.selected===c.id?'selected':''}" data-clip="${c.id}"><div class="meta"><span>${escapeHTML(locationName(c.location))}</span><span>${time(c.start_sec)}–${time(c.end_sec)}</span></div><h4>${escapeHTML(clipTitle(c))}</h4><div class="meta"><span>${escapeHTML(c.camera_id)}</span><span>SEG ${c.segment_number}</span></div><div class="tags">${tagsHTML(c)}</div></button>`).join(''):'<p class="muted">No matching clips. Adjust the filters or description.</p>';
  $('clip-list').querySelectorAll('[data-clip]').forEach(b=>b.addEventListener('click',()=>selectClip(b.dataset.clip)));
}
let selectionGeneration=0;
async function selectClip(id) {
  const generation=++selectionGeneration;
  state.selected=id;state.detection=null;
  $('reasoning').textContent='';$('reason-button').disabled=false;
  renderEvidenceList();
  const known=state.clips.find(c=>c.id===id);
  if(known)renderPlayer(known);
  $('evidence-video').src=streamURL(id);
  $('detection-summary').textContent='Loading detection context…';
  try {
    const clip=await api('evidence/'+id);
    if(generation!==selectionGeneration)return;
    const merged={...known,...clip,observation_tags:known?.observation_tags||[]};
    renderPlayer(merged);
    const detections=await api('detections/'+id);
    if(generation!==selectionGeneration)return;
    state.detection=detections;
    $('detection-summary').textContent=detections.available?
      `YOLO context · ${detections.frame_count} frames · Peak detections per clip: `+Object.entries(clip.object_counts).filter(([k])=>['car','person','bicycle','truck','bus','motorcycle'].includes(k)).map(([k,n])=>`${k} ${n}`).join(' / '):'No YOLO frame detections available for this segment.';
    drawDetections();
  } catch(error) {if(generation===selectionGeneration)$('detection-summary').textContent=error.message;}
}
function renderPlayer(clip) {
  state.selectedClip=clip;
  $('player-title').textContent=clipTitle(clip);
  $('player-timing').textContent=`Parent ${time(clip.start_sec)}–${time(clip.end_sec)} · ${clip.duration}s clip`;
  $('player-tags').innerHTML=tagsHTML(clip)+(state.activeRecommendation?`<span>REVIEW ${escapeHTML(state.activeRecommendation.id.slice(0,6))}</span>`:'');
  $('player-details').innerHTML=[['CAMERA',clip.camera_id],['LOCATION',locationName(clip.location)],['INDEXED AT',(clip.indexed_at||'Unknown').replace('T',' ').slice(0,19)],['SEGMENT',clip.segment_number]].map(([k,v])=>`<div><span>${k}</span>${escapeHTML(v)}</div>`).join('')+`<div class="segment-id"><span>SEGMENT ID / SOURCE</span>${escapeHTML(clip.source)}</div>`;
  $('player-caption').textContent=clip.caption;
}
function drawDetections() {
  const canvas=$('overlay'),video=$('evidence-video');
  canvas.width=video.clientWidth;canvas.height=video.clientHeight;
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  if(!$('show-detections').checked||!state.detection?.available||!video.videoWidth)return;
  const frames=state.detection.frames;
  const frame=frames.reduce((best,f)=>Math.abs(f.time_sec-video.currentTime)<Math.abs((best?.time_sec??Infinity)-video.currentTime)?f:best,null);
  if(!frame||Math.abs(frame.time_sec-video.currentTime)>.12)return;
  const [h,w]=frame.shape||state.detection.video_shape;
  const scale=Math.min(canvas.width/video.videoWidth,canvas.height/video.videoHeight);
  const displayW=video.videoWidth*scale,displayH=video.videoHeight*scale;
  const offsetX=(canvas.width-displayW)/2,offsetY=(canvas.height-displayH)/2;
  const sx=displayW/w,sy=displayH/h;
  ctx.font='11px monospace';ctx.lineWidth=1.4;
  for(const d of frame.detections) {
    if(d.confidence<.5||!['car','person','bicycle','truck','bus','motorcycle'].includes(d.label))continue;
    const [x1,y1,x2,y2]=d.bbox;
    const x=offsetX+x1*sx,y=offsetY+y1*sy;
    ctx.strokeStyle=d.label==='bicycle'?'#d7ee75':'#7cc7b6';
    ctx.strokeRect(x,y,(x2-x1)*sx,(y2-y1)*sy);
    const text=`${d.label} ${Math.round(d.confidence*100)}%`;
    const ty=Math.max(y-17,0);
    ctx.fillStyle='#101b18dd';ctx.fillRect(x,ty,ctx.measureText(text).width+8,17);
    ctx.fillStyle=ctx.strokeStyle;ctx.fillText(text,x+4,ty+12);
  }
}
function frameLoop() { if(!$('evidence-panel').hidden)drawDetections();requestAnimationFrame(frameLoop); }
requestAnimationFrame(frameLoop);
$('show-detections').addEventListener('change',drawDetections);
$('evidence-video').addEventListener('error',()=>{if(state.selected)$('detection-summary').textContent='Playback unavailable. The indexed caption and segment reference remain visible.';});
$('reason-button').addEventListener('click',async()=>{
  if(!state.selected)return;
  const id=state.selected;
  $('reason-button').disabled=true;$('reasoning').textContent='Reading this parent video’s indexed captions…';
  try {const x=await api('reason/'+id,{method:'POST'});if(state.selected===id)$('reasoning').textContent='Parent video description · '+x.answer;}
  catch(error){if(state.selected===id)$('reasoning').textContent=error.message;}
  finally{if(state.selected===id)$('reason-button').disabled=false;}
});
$('search-form').addEventListener('submit',async event=>{
  event.preventDefault();const query=$('query').value.trim();
  if(!query)return;
  const generation=++state.generation;
  status('Searching indexed street descriptions…');
  try {
    const p=filterParams();p.set('query',query);
    const data=await api('search?'+p);
    if(generation!==state.generation)return;
    renderAnalytics(data);showTab('evidence');
    status(`${data.sample_count} retrieved clips. Search results may include routine activity; planning reviews require caption evidence.`);
    if(data.clips.length)selectClip(data.clips[0].id);else clearPlayer();
  }catch(error){if(generation===state.generation)status(error.message,true);}
});
function clearPlayer() {
  ++selectionGeneration;state.activeRecommendation=null;state.selected=null;state.detection=null;state.selectedClip=null;
  $('evidence-video').removeAttribute('src');$('evidence-video').load();
  $('player-title').textContent='No segment selected';$('player-timing').textContent='';
  ['player-tags','player-details','player-caption','detection-summary','reasoning'].forEach(id=>$(id).textContent='');
}
$('reset-search').addEventListener('click',()=>{$('query').value='';clearPlayer();loadAnalytics();});
function renderRecommendations() {
  const recommendations=state.recommendations;
  $('review-count').textContent=`${recommendations.length} CAPTION-SUPPORTED REVIEWS`;
  $('recommendations').innerHTML=recommendations.length?recommendations.map(r=>`<button class="recommendation" data-review="${r.id}"><div class="card-top"><span>${escapeHTML(r.label.toUpperCase())}</span><span class="severity">${escapeHTML(r.severity.toUpperCase())}</span></div><h3>${escapeHTML(r.title)}</h3><p>${escapeHTML(r.observation)}</p><p class="action">${escapeHTML(r.action)}</p><div class="card-bottom"><span>${escapeHTML(locationName(r.location))} · ${r.metrics.evidence_clips} clips</span><span>View evidence ↗</span></div></button>`).join(''):'<p class="muted">No supported planning reviews in this sample. Routine activity remains available in Evidence / Clips.</p>';
  $('recommendations').querySelectorAll('[data-review]').forEach(b=>b.addEventListener('click',()=>{
    state.activeRecommendation=state.recommendations.find(r=>r.id===b.dataset.review);
    showTab('evidence');renderEvidenceList();
    selectClip(state.activeRecommendation.segment_refs[0].segment_id);
    status(`${state.activeRecommendation.title} ${state.activeRecommendation.metrics.evidence_clips} referenced clips.`);
  }));
}
document.querySelectorAll('[data-demo]').forEach(button=>button.addEventListener('click',async()=>{
  const generation=++state.generation;
  status('Opening a verified archive example…');
  try {
    const data=await api('demo/'+button.dataset.demo);
    if(generation!==state.generation)return;
    $('location').value='new_york';$('camera').value='nyc_bike_gopro-1';
    $('start-date').value='';$('end-date').value='';$('query').value=data.demo.query;
    clearPlayer();renderAnalytics(data);showTab('evidence');
    await selectClip(data.clips[0].id);
    status(`Verified archive example · ${data.demo.query}`);
  }catch(error){if(generation===state.generation)status(error.message,true);}
}));
start();
