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
  state.clips=data.clips;state.recommendations=data.recommendations;
  $('sample-label').textContent=`${data.sample_count} SAMPLED / ${data.available_clips ?? '—'} AVAILABLE CLIPS`;
  $('metrics').innerHTML=[[data.sample_count,'Sampled clips'],[data.recommendations.length,'Planning reviews'],[data.camera_count,'Cameras sampled']].map(([n,label])=>`<div><strong>${n}</strong><span>${label}</span></div>`).join('');
  const max=Math.max(...data.object_chart.map(x=>x.clip_count),1);
  $('object-chart').innerHTML=data.object_chart.length?data.object_chart.map(x=>`<div class="bar-row"><span>${escapeHTML(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${x.clip_count/max*100}%"></div></div><span class="count">${x.clip_count}</span></div>`).join(''):'<p class="muted">No detections in this sample.</p>';
  $('condition-chart').innerHTML=data.conditions.map(x=>`<span class="condition"><i></i>${escapeHTML(x.label)} <b>${x.clip_count}</b></span>`).join('');
  $('review-count').textContent='CAPTION-SUPPORTED OBSERVATIONS';
  $('recommendations').innerHTML='<p class="muted">Select Evidence / Clips to explore the sampled observations. Structured planning reviews are the next slice.</p>';
  const hero=data.clips.find(c=>c.filename.includes('GOPR0130_chunk_0004_segment_005')) || data.clips[0];
  if(hero) {
    state.hero=hero;
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
    renderAnalytics(data);
    status(`${data.sample_count} sampled clips across ${data.camera_count} cameras. Dates refer to indexing; observations refer to recorded footage.`);
  } catch(error) { if(generation===state.generation)status(error.message,true); }
  finally {if(generation===state.generation)document.querySelector('.apply').disabled=false;}
}
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => showTab(button.dataset.tab)));
$('filters').addEventListener('submit', event => {event.preventDefault();loadAnalytics();});
async function start() {
  try {
    state.metadata=await api('metadata');
    populateSelect('location',state.metadata.location,'All street locations','new_york');
    populateSelect('camera',state.metadata.camera_id.filter(c=>!c.includes('warehouse')&&!c.includes('smartspace')),'All street cameras','nyc_bike_gopro-1');
    await loadAnalytics();
  } catch(error) {status(error.message,true);}
}
start();
