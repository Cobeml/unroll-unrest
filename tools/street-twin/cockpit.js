/* Street geometry and cockpit adapted from UnfoldUnrest viewer/ride.html @ 7a3163c.
   Imported estimates remain separate from archive YOLO and measured traffic flow. */
import * as THREE from './vendor/three.module.min.js';
import {OrbitControls} from './vendor/OrbitControls.js';
const {api,url,state,selectClip,loadView,filterParams}=window.StreetTwin;
const $=id=>document.getElementById(id),still=matchMedia('(prefers-reduced-motion: reduce)').matches;
let D=null,engine=null,selected=null,view='director',mapTime=0,playing=false,last=0,pendingSeek=null,loading=0,clipsLoading=false,detached=false;
const color=o=>o.group==='vehicle'?({standing:'#e45a48',moving:'#c9cdcf',unknown:'#719bb2'}[o.motion]):o.group==='crosswalk'?'#f2f1ec':'#f0c75a';
function boundClip(){return detached?null:D?.bindings.find(b=>b.segment_id===state.selected?.id);}
function timeAtVideo(){const b=boundClip();return b?Math.min(b.scene_end_sec,Math.max(b.scene_start_sec,b.scene_start_sec+$('video').currentTime-b.clip_start_sec)):null;}
function linkage(){
 const b=boundClip();$('scene-link-state').textContent=!D?'':b?'Video linked to this map':'Archive video separate from this map';
 $('footer-context').textContent=D?'Spatial geometry estimated from saved reconstruction':'Saved-map import ready';
}
async function seek(t){
 mapTime=Math.max(0,Math.min(D.duration,t));
 const b=D.bindings.find(b=>mapTime>=b.scene_start_sec&&mapTime<b.scene_end_sec)||D.bindings.find(b=>mapTime===D.duration&&b.scene_end_sec===D.duration);
 if(!b){detached=true;$('video').pause();linkage();return;}
 detached=false;const local=b.clip_start_sec+mapTime-b.scene_start_sec;
 if(state.selected?.id!==b.segment_id){
  playing=false;
  pendingSeek={id:b.segment_id,time:local,play:false};
  try{const clip=b.clip||await api('evidence/'+b.segment_id);if(!state.clips.some(c=>c.id===clip.id))state.clips.push(clip);selectClip(clip);}catch{pendingSeek=null;$('scene-link-state').textContent='Linked clip unavailable';}
 }else if($('video').readyState>=1)$('video').currentTime=local;
 else pendingSeek={id:b.segment_id,time:local,play:false};
}
$('video').addEventListener('loadedmetadata',()=>{if(pendingSeek?.id===state.selected?.id){$('video').currentTime=pendingSeek.time;if(pendingSeek.play)$('video').play().catch(()=>{});pendingSeek=null;}});
window.addEventListener('streettwin:clip',e=>{detached=false;const b=D?.bindings.find(b=>b.segment_id===e.detail.id);if(b)mapTime=b.scene_start_sec;linkage();});
$('video').addEventListener('play',()=>{if(boundClip())playing=true;});
$('video').addEventListener('pause',()=>{if(boundClip()&&!$('video').ended)playing=false;});
$('video').addEventListener('ended',async()=>{
 const b=boundClip();if(!b||!playing||clipsLoading)return;
 const next=D.bindings.find(n=>Math.abs(n.scene_start_sec-b.scene_end_sec)<.02);
 if(!next){playing=false;return;}
 clipsLoading=true;
 try{const c=next.clip||await api('evidence/'+next.segment_id);if(!state.clips.some(v=>v.id===c.id))state.clips.push(c);pendingSeek={id:c.id,time:next.clip_start_sec,play:true};selectClip(c);}catch{playing=false;$('scene-link-state').textContent='Next clip unavailable';}finally{clipsLoading=false;}
});
$('scene-scrub').addEventListener('input',e=>seek(Number(e.target.value)));
$('scene-play').onclick=()=>{
 if(!D)return;
 if(boundClip()){
  if(!$('video').paused){$('video').pause();playing=false;}else{playing=true;$('video').play().catch(()=>{playing=false;});}
 }else playing=!playing;
};
$('clear-object').onclick=()=>{selected=null;describe();};
$('cloud-toggle').onclick=()=>{if(engine?.cloud){engine.cloud.visible=!engine.cloud.visible;$('cloud-toggle').setAttribute('aria-pressed',String(engine.cloud.visible));}};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;document.querySelectorAll('[data-view]').forEach(k=>k.setAttribute('aria-pressed',String(k===b)));if(engine){engine.orbit.enabled=view==='free';engine.orbit.target.copy(engine.look);engine.orbit.update();}});
function describe(){
 $('scene-insight').hidden=!selected;
 if(!selected)return;
 $('object-title').textContent=selected.label;
 $('object-detail').textContent=`${selected.group==='vehicle'?selected.motion+' · ':''}${selected.t0.toFixed(1)}–${selected.t1.toFixed(1)}s · ${selected.seen} observations. ${selected.group==='crosswalk'?'Sightlines are imported estimates.':'Position and footprint are estimated.'}`;
}
function pose(t){
 const P=D.path;let i=0;while(i<P.length-2&&P[i+1].t<t)i++;
 const a=P[i],b=P[Math.min(i+1,P.length-1)],u=Math.max(0,Math.min(1,(t-a.t)/Math.max(.0001,b.t-a.t)));
 let dh=((b.h-a.h+540)%360)-180;
 return {x:a.x+(b.x-a.x)*u,y:a.y+(b.y-a.y)*u,h:(a.h+dh*u)*Math.PI/180};
}
function dispose(){if(!engine)return;engine.resize.disconnect();engine.orbit.dispose();engine.scene.traverse(o=>{o.geometry?.dispose();for(const m of [o.material].flat().filter(Boolean)){m.map?.dispose();m.dispose();}});engine.renderer.dispose();engine.renderer.domElement.remove();engine=null;}
async function build(data,token){
 const E=data.extent,cx=(E.x0+E.x1)/2,cy=(E.y0+E.y1)/2;
 const image=new Image();image.src=url(data.assets.ortho.url).href;
 await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;});
 if(token!==loading)return;
 $('ortho-fallback').src=image.src;
 let renderer;
 try{renderer=new THREE.WebGLRenderer({antialias:innerWidth>700,alpha:true});}
 catch{$('ortho-fallback').hidden=false;$('scene-link-state').textContent='Overhead view · 3D unavailable';$('cloud-toggle').disabled=true;document.querySelectorAll('[data-view]').forEach(b=>b.disabled=true);return;}
 renderer.setPixelRatio(Math.min(devicePixelRatio||1,innerWidth>700?2:1));renderer.setClearColor(0,0);$('stage').appendChild(renderer.domElement);
 renderer.domElement.setAttribute('aria-label','Saved street map. Choose Explore to orbit, then click an object.');renderer.domElement.tabIndex=0;
 const scene=new THREE.Scene();scene.fog=new THREE.Fog('#262d3a',80,Math.max(300,E.x1-E.x0));
 const cam=new THREE.PerspectiveCamera(48,1,.1,2000);cam.up.set(0,0,1);
 const orbit=new OrbitControls(cam,renderer.domElement);orbit.enabled=view==='free';orbit.enableDamping=true;orbit.maxPolarAngle=Math.PI*.48;
 scene.add(new THREE.HemisphereLight('#a9bddb','#2b2724',1.9));const sun=new THREE.DirectionalLight('#ffd3a3',1);sun.position.set(-30,25,50);scene.add(sun);
 const ground=new THREE.Mesh(new THREE.PlaneGeometry(2000,2000),new THREE.MeshLambertMaterial({color:'#1a1d20'}));ground.position.set(cx,cy,-.08);scene.add(ground);
 const grid=new THREE.GridHelper(1000,200,'#3a4250','#2a313b');grid.rotation.x=Math.PI/2;grid.position.set(cx,cy,-.07);grid.material.transparent=true;grid.material.opacity=.45;scene.add(grid);
 const tex=new THREE.Texture(image);tex.needsUpdate=true;tex.colorSpace=THREE.SRGBColorSpace;
 const road=new THREE.Mesh(new THREE.PlaneGeometry(E.x1-E.x0,E.y1-E.y0),new THREE.MeshBasicMaterial({map:tex,transparent:true}));road.position.set(cx,cy,-.03);scene.add(road);
 const route=new THREE.BufferGeometry().setFromPoints(data.path.map(p=>new THREE.Vector3(p.x,p.y,.06)));
 const ribbon=new THREE.Line(route,new THREE.LineBasicMaterial({color:'#63bd91',transparent:true,opacity:.75}));scene.add(ribbon);
 const boxes=[];const unit=new THREE.BoxGeometry(1,1,1);unit.translate(0,0,.5);
 for(const o of data.objects){
  let mesh;
  if(o.footprint){
   const F=o.footprint,L=Math.hypot(F[1][0]-F[0][0],F[1][1]-F[0][1]),W=Math.hypot(F[2][0]-F[1][0],F[2][1]-F[1][1]);
   const h=o.group==='crosswalk'?.06:Math.max(.3,Math.min(o.height||1.45,5));
   mesh=new THREE.Mesh(unit,new THREE.MeshLambertMaterial({color:color(o),transparent:true,opacity:o.motion==='moving'?.2:.55,emissive:'#000000'}));
   mesh.scale.set(L,W,h);mesh.position.set((F[0][0]+F[2][0])/2,(F[0][1]+F[2][1])/2,0);mesh.rotation.z=Math.atan2(F[1][1]-F[0][1],F[1][0]-F[0][0]);
   const edge=new THREE.LineSegments(new THREE.EdgesGeometry(unit),new THREE.LineBasicMaterial({color:color(o),transparent:true,opacity:.9}));mesh.add(edge);
  }else{mesh=new THREE.Mesh(new THREE.SphereGeometry(.3,12,8),new THREE.MeshLambertMaterial({color:color(o),transparent:true,opacity:.7}));mesh.position.set(o.xy[0],o.xy[1],.4);}
  mesh.userData.object=o;boxes.push(mesh);scene.add(mesh);
 }
 const rider=new THREE.Group();const body=new THREE.Mesh(new THREE.ConeGeometry(.42,1.3,4),new THREE.MeshLambertMaterial({color:'#f0c75a',emissive:'#5a4600'}));body.rotation.z=-Math.PI/2;body.position.z=data.cam_h;rider.add(body);
 const half=data.hfov/2*Math.PI/180,shape=new THREE.Shape();shape.moveTo(0,0);shape.absarc(0,0,14,-half,half,false);shape.lineTo(0,0);
 const cone=new THREE.Mesh(new THREE.ShapeGeometry(shape,24),new THREE.MeshBasicMaterial({color:'#f0c75a',transparent:true,opacity:.12,depthWrite:false}));cone.position.z=.05;rider.add(cone);scene.add(rider);
 const rays=new THREE.Group();scene.add(rays);
 for(const o of data.objects.filter(o=>o.group==='crosswalk'))for(const a of o.approaches||[]){
  const positions=[],colors=[];
  for(const ray of a.rays||[]){positions.push(a.waiting[0],a.waiting[1],1,ray.to[0],ray.to[1],1.05);const c=new THREE.Color(ray.clear?'#f2f1ec':'#e45a48');colors.push(c.r,c.g,c.b,c.r,c.g,c.b);}
  if(!positions.length)continue;const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
  const lines=new THREE.LineSegments(g,new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.55}));lines.userData.object=o;scene.add(lines);rays.add(lines);
 }
 const cloud=new THREE.Points(new THREE.BufferGeometry(),new THREE.PointsMaterial({size:.07,vertexColors:true}));scene.add(cloud);
 const eye=new THREE.Vector3(),look=new THREE.Vector3(cx,cy,0);
 const resize=new ResizeObserver(()=>{const w=$('stage').clientWidth,h=$('stage').clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);cam.aspect=w/h;cam.updateProjectionMatrix();});resize.observe($('stage'));
 engine={renderer,scene,cam,orbit,cloud,boxes,rays,rider,eye,look,resize,image,cx,cy};
 const raycaster=new THREE.Raycaster();let down=null;
 renderer.domElement.addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);
 renderer.domElement.addEventListener('pointerup',e=>{if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>6)return;const r=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),cam);selected=raycaster.intersectObjects(boxes,false)[0]?.object.userData.object||null;describe();});
 if(data.assets.points){
  try{
   const buffers=await Promise.all(['points','colours'].map(async k=>{const r=await fetch(url(data.assets[k].url));if(!r.ok)throw new Error();return r.arrayBuffer();}));
   if(token!==loading)return;
   const pos=new Float32Array(buffers[0]),rgb=new Uint8Array(buffers[1]),step=Math.max(1,Math.ceil(pos.length/3/(innerWidth<700?80000:200000))),P=[],C=[];
   for(let i=0;i<pos.length/3;i+=step){if(pos[i*3+2]<.25)continue;P.push(pos[i*3],pos[i*3+1],pos[i*3+2]);C.push(rgb[i*3],rgb[i*3+1],rgb[i*3+2]);}
   cloud.geometry.setAttribute('position',new THREE.Float32BufferAttribute(P,3));cloud.geometry.setAttribute('color',new THREE.BufferAttribute(new Uint8Array(C),3,true));
  }catch{$('scene-link-state').textContent='Point cloud unavailable · street surface loaded';}
 }
}
function minimap(){
 if(!engine||!$('mini').offsetParent)return;
 const canvas=$('mini'),w=460,h=300;canvas.width=w;canvas.height=h;const c=canvas.getContext('2d'),E=D.extent,s=Math.min(w/(E.x1-E.x0),h/(E.y1-E.y0))*.9,px=x=>w/2+(x-engine.cx)*s,py=y=>h/2-(y-engine.cy)*s;
 c.drawImage(engine.image,px(E.x0),py(E.y1),(E.x1-E.x0)*s,(E.y1-E.y0)*s);
 c.strokeStyle='#63bd91';c.lineWidth=3;c.beginPath();D.path.forEach((p,i)=>{if(i)c.lineTo(px(p.x),py(p.y));else c.moveTo(px(p.x),py(p.y));});c.stroke();
 for(const o of D.objects){c.fillStyle=color(o);c.fillRect(px(o.xy[0])-2,py(o.xy[1])-2,4,4);}const r=pose(mapTime);c.fillStyle='#f0c75a';c.beginPath();c.arc(px(r.x),py(r.y),5,0,7);c.fill();
}
function frame(now){
 const dt=Math.min(.1,(now-(last||now))/1000);last=now;
 if(D){
  const synced=timeAtVideo();if(synced!==null)mapTime=synced;else if(playing){mapTime=Math.min(D.duration,mapTime+dt);if(mapTime===D.duration)playing=false;}
  $('scene-clock').textContent=`${mapTime.toFixed(1)} / ${D.duration.toFixed(1)}s`;$('scene-scrub').value=mapTime;
  $('scene-play').textContent=boundClip()?(!$('video').paused?'Pause':'Play'):(playing?'Pause':'Play');
  if(engine){
   const e=engine,r=pose(mapTime),fx=Math.cos(r.h),fy=Math.sin(r.h);e.rider.position.set(r.x,r.y,0);e.rider.rotation.z=r.h;
   for(const mesh of e.boxes){const q=mesh.userData.object;mesh.material.emissive.set(selected?.id===q.id?'#705419':'#000000');mesh.material.opacity=q.t0<=mapTime&&q.t1>=mapTime?.65:.2;}
   for(const l of e.rays.children)l.visible=selected?.id===l.userData.object.id||(view==='director'&&Math.abs((l.userData.object.t_pass??-100)-mapTime)<3.5);
   if(view==='free')e.orbit.update();else{
    const target=new THREE.Vector3(r.x+10*fx,r.y+10*fy,0),eye=new THREE.Vector3(r.x-9*fx,r.y-9*fy,6);
    if(view==='overview'){const span=Math.max(D.extent.x1-D.extent.x0,D.extent.y1-D.extent.y0,30);eye.set(e.cx-span*.4,e.cy-span*.7,span*.7);target.set(e.cx,e.cy,0);}
    else if(view==='director'){const o=selected||D.objects.find(o=>o.group==='crosswalk'&&Math.abs(o.t_pass-mapTime)<3.5);if(o){target.set(o.xy[0],o.xy[1],0);eye.set(o.xy[0]-15*fx-8*fy,o.xy[1]-15*fy+8*fx,18);}}
    const a=still?1:1-Math.exp(-dt*2.2);if(!e.eye.lengthSq())e.eye.copy(eye);e.eye.lerp(eye,a);e.look.lerp(target,a);e.cam.position.copy(e.eye);e.cam.lookAt(e.look);
   }
   e.renderer.render(e.scene,e.cam);minimap();
  }
 }
 requestAnimationFrame(frame);
}
async function loadScene(id){
 const token=++loading;playing=false;detached=false;selected=null;dispose();D=null;describe();$('ortho-fallback').hidden=true;
 $('cloud-toggle').disabled=false;document.querySelectorAll('[data-view]').forEach(b=>b.disabled=false);
 if(!id){$('cockpit').classList.add('map-pending');$('map-empty').hidden=false;for(const k of ['scene-bar','scene-legend','mini'])$(k).hidden=true;linkage();return;}
 try{
  const data=await api('spatial/scenes/'+id);if(token!==loading)return;D=data;mapTime=0;
  $('cockpit').classList.remove('map-pending');$('map-empty').hidden=true;for(const k of ['scene-bar','scene-legend','mini'])$(k).hidden=false;$('scene-scrub').max=D.duration;
  linkage();await build(data,token);if(token!==loading)return;const b=boundClip();if(b)mapTime=b.scene_start_sec;
  const initial=new URLSearchParams(location.search).get('scene_time');if(initial!=null&&Number.isFinite(Number(initial)))await seek(Number(initial));
 }catch{if(token!==loading)return;dispose();D=null;$('map-empty').hidden=false;$('map-empty').querySelector('h2').textContent='Saved map unavailable';$('scene-link-state').textContent='Re-import this scene to retry';for(const k of ['scene-bar','scene-legend','mini'])$(k).hidden=true;$('cockpit').classList.add('map-pending');}
}
$('scene-select').onchange=async()=>{await loadScene($('scene-select').value);loadView(filterParams());};
try{const list=await api('spatial/scenes');for(const s of list.scenes){const o=document.createElement('option');o.value=s.id;o.textContent=s.name;$('scene-select').appendChild(o);}const id=new URLSearchParams(location.search).get('scene_id')||'';if(list.scenes.some(s=>s.id===id)){$('scene-select').value=id;await loadScene(id);}else if(list.scenes.length===1){$('scene-select').value=list.scenes[0].id;await loadScene(list.scenes[0].id);}linkage();if($('scene-select').value&&state.context.get('scene_id')!==$('scene-select').value)loadView(filterParams());}
catch{$('scene-link-state').textContent='Saved-map import ready';}
requestAnimationFrame(frame);
