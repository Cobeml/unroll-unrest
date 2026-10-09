/* Adapted from UnfoldUnrest viewer/ride.html @ 98703a5. Archive video, YOLO and same-origin assets run on VSS. */

import * as THREE from './vendor/three.module.min.js';
import { OrbitControls } from './vendor/OrbitControls.js';

async function run(){
const $ = id => document.getElementById(id);
const href = p => new URL(p,document.baseURI).href;
const escape = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function read(p,options={}) { const r=await fetch(href(p),options); if(!r.ok)throw new Error('Demo data unavailable. Refresh to retry.'); return r.json(); }
const sceneId=location.pathname.match(/\/rides\/([A-Za-z0-9_-]+)/)?.[1];
const D = await read(sceneId?'api/rides/'+sceneId:'api/ride');
const ridePath='rides/'+D.scene_id;
const analysisPath=sceneId?'api/rides/'+sceneId+'/analysis':'api/ride/analysis';
const base = '';
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
const vid=$('vid'),ov=$('ov'),mini=$('mini'),scrub=$('scrub');
vid.src=href(D.video);vid.poster=href('assets/ride-preview.jpg');
vid.addEventListener('error',()=>{ $('error-banner').hidden=false;$('error-banner').textContent='Archive video unavailable. The saved map and evidence remain available; refresh to retry.'; });
const ortho = new Image();ortho.src=href(D.ortho);
await new Promise((resolve,reject)=>{ortho.onload=resolve;ortho.onerror=()=>reject(new Error('Saved map image unavailable. Refresh to retry.'));});
const byId = Object.fromEntries(D.objects.map(o => [o.id, o]));
const cws = D.objects.filter(o => o.group === 'crosswalk' && o.ends).sort((a, b) => a.t_pass - b.t_pass);
cws.forEach((c, i) => c.n = i + 1);
const S = D.stats, E = D.extent, CAM_H = D.cam_h || 1.1, RULES = D.rules || {};
const WIN = RULES.window_m ?? 12, TH = RULES.target_h ?? 1, CLEAR = RULES.clear ?? .9;
// a side of a crossing: hidden (under half of it in view where stopping must start), part hidden, in view, not judged
const level = e => !e.covered ? 'none' : e.seen_at_stop >= CLEAR ? 'clear' : e.review?.claim === 'rejected' ? 'disputed'
                 : e.seen_at_stop >= .5 ? 'part' : 'hidden';
const RANK = { hidden: 3, part: 2, clear: 1, disputed: .5, none: 0 };
const worst = c => c.ends.reduce((w, e) => RANK[level(e)] > RANK[level(w)] ? e : w, c.ends[0]);
const verdict = c => 'v-' + level(worst(c));
const judged = c => c.ends.some(e => e.covered);
const COL = { hidden: css('--curb'), part: css('--line'), clear: css('--lane'), disputed: '#9aa0a3', none: '#7d8285' };
const vcol = c => COL[level(worst(c))];
const seenCol = s => s >= CLEAR ? COL.clear : s >= .5 ? COL.part : COL.hidden;
const NAME = { hedge: 'hedge', planter: 'planter', 'bus shelter': 'bus shelter', kiosk: 'kiosk', 'utility box': 'utility box', tree: 'tree', pole: 'lamp post', person: 'person', bicycle: 'bike' };
const list = a => a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1];
const cap = s => {s=String(s ?? '');return s ? s[0].toUpperCase()+s.slice(1):'';};
const pct = x => `${Math.round(100 * x)}%`, mm = x => `${Math.round(x)} m`;
const nameOf = o => escape(o?.group === 'vehicle' ? o.label : (NAME[o?.group] || o?.group || 'unidentified object'));
function hiders(e) {                        // "a hedge", "3 hedges", "4 lamp posts and things the detector did not name"
  const n = {};
  for (const b of e.blockers) { const k = nameOf(byId[b.id]); n[k] = (n[k] || 0) + 1; }
  const parts = Object.entries(n).map(([k, c]) => c === 1 ? `a ${k}` : `${c} ${k}s`);
  if (e.unnamed > e.blockers.reduce((s, b) => s + b.n, 0)) parts.push('things the detector did not name');
  return list(parts) || 'something the detector did not name';
}
const TAIL = 1.0;                           // s past the crossing the inspection lasts

// The story leads with the action; detail stays on its own page.
$('headline').textContent=D.findings?.length?'A clearer crossing.':'The street, reconstructed.';
$('sub').textContent=`${S.crosswalks ?? cws.length} crossings · ${S.crossings_judged ?? 0} assessed · ${Math.round(S.duration)} seconds`;
function title(c) {
 const w=worst(c),lv=level(w);
 if(lv==='none')return 'Approach not assessed';
 if(lv==='disputed')return 'Checks disagree';
 if(lv==='clear')return 'Waiting area in view';
 return `${cap(w.side)} waiting area · ${pct(1-w.seen_at_stop)} hidden`;
}
function strip(e) {                          // the way in, WIN m out on the left to the crossing on the right
  const F = e.frames.filter(f => f.counted && f.seen != null).sort((a, b) => b.d - a.d);
  const X = d => `${((WIN - Math.min(WIN, Math.max(0, d))) / WIN * 100).toFixed(1)}%`;
  const segs = F.map((f, i) => {
    const a = i ? (F[i - 1].d + f.d) / 2 : Math.min(WIN, f.d + .5), b = i < F.length - 1 ? (f.d + F[i + 1].d) / 2 : Math.max(0, f.d - .5);
    return `<i style="left:${X(a)};width:calc(${X(b)} - ${X(a)});background:${seenCol(f.seen)}"></i>`;
  }).join('');
  const label = `${cap(e.side)} side on the way in: ${F.map(f => `${pct(f.seen)} in view at ${mm(f.d)}`).join(', ')}`;
  return `<div class="meter strip" role="img" aria-label="${label}">${segs}<b class="stop" style="left:${X(e.needed_m)}"></b></div>` +
         `<div class="scale"><span>${WIN} m out</span><span>white mark: stopping must start</span><span>crossing</span></div>`;
}
function cardHTML(c) {
 return `<div class="ch"><span class="disc">${c.n}</span><div><h2>${title(c)}</h2><p>Crossing ${c.n} · spatial estimate</p></div></div><div class="aps">${c.ends.map(e=>`<div><div class="ap-h"><span>${cap(e.side)}</span><span>${!e.covered?'Not assessed':level(e)==='disputed'?'Review disagrees':pct(e.seen_at_stop)+' in view'}</span></div>${e.covered?strip(e):'<div class="meter off"></div>'}</div>`).join('')}</div>`;
}

// ---- the ride: pose at time t, distance along it ----
const PATH = D.path, arc = [0];
for (let i = 1; i < PATH.length; i++) arc.push(arc[i - 1] + Math.hypot(PATH[i].x - PATH[i - 1].x, PATH[i].y - PATH[i - 1].y));
function rider(t) {
  let i = Math.min(PATH.length - 2, Math.max(0, Math.floor(t * D.fps)));
  while (i > 0 && PATH[i].t > t) i--;
  while (i < PATH.length - 2 && PATH[i + 1].t < t) i++;
  const a = PATH[i], b = PATH[i + 1], u = Math.min(1, Math.max(0, (t - a.t) / Math.max(b.t - a.t, 1e-6)));
  let dh = b.h - a.h; if (dh > 180) dh -= 360; if (dh < -180) dh += 360;
  return { x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u, h: (a.h + dh * u) * Math.PI / 180, s: arc[i] + (arc[i + 1] - arc[i]) * u };
}
const sAt = xy => { let best = 0, bd = 1e9; PATH.forEach((p, i) => { const d = Math.hypot(p.x - xy[0], p.y - xy[1]); if (d < bd) { bd = d; best = i; } }); return arc[best]; };
const tAtS = s => { const i = Math.max(1, arc.findIndex(v => v >= s)); if (i < 1 || arc[i] === undefined) return PATH[PATH.length - 1].t;
  const u = (s - arc[i - 1]) / Math.max(arc[i] - arc[i - 1], 1e-6); return PATH[i - 1].t + (PATH[i].t - PATH[i - 1].t) * Math.min(1, Math.max(0, u)); };
function riderAtS(s) { return rider(tAtS(Math.max(0, s))); }
cws.forEach(c => {
  c.s = sAt(c.xy); c.s_edge = sAt(c.edge); c.t_edge = tAtS(c.s_edge);
  const ks = c.ends.flatMap(e => e.frames.map(f => f.k));
  c.tw0 = ks.length ? PATH[Math.min(...ks)].t : c.t_edge - 1.5;      // from WIN m out
  c.tw1 = c.t_edge + TAIL;                                           // to just past the crossing
});
const inWindow = (c, t) => judged(c) && t >= c.tw0 && t <= c.tw1;
const inspecting = t => cws.find(c => inWindow(c, t)) || null;


// ---- the street in 3D (plan metres, z up) ----
const stage = $('stage');
const renderer = new THREE.WebGLRenderer({ antialias: innerWidth > 700, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, innerWidth > 700 ? 2 : 1)); renderer.setClearColor(0x000000, 0);
stage.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.fog = new THREE.Fog('#262d3a', 45, 150);
const cam = new THREE.PerspectiveCamera(48, 2, .1, 600); cam.up.set(0, 0, 1);
const orbit = new OrbitControls(cam, renderer.domElement); orbit.enabled = false; orbit.enableDamping = true; orbit.maxPolarAngle = Math.PI * .48;
scene.add(new THREE.HemisphereLight('#a9bddb', '#2b2724', 1.9));
const sun = new THREE.DirectionalLight('#ffd3a3', 1.0); sun.position.set(-30, 25, 50); scene.add(sun);
const C3 = { red: new THREE.Color(css('--curb')), green: new THREE.Color(css('--lane')), yellow: new THREE.Color(css('--line')), paint: new THREE.Color(css('--paint')) };
const cx0 = (E.x0 + E.x1) / 2, cy0 = (E.y0 + E.y1) / 2;
{ // the ground beyond what we saw, with a survey grid, then the road from above
  const g = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), new THREE.MeshLambertMaterial({ color: '#1a1d20' }));
  g.position.set(cx0, cy0, -.08); scene.add(g);
  const grid = new THREE.GridHelper(600, 120, '#3a4250', '#2a313b'); grid.rotation.x = Math.PI / 2; grid.position.set(cx0, cy0, -.07);
  grid.material.transparent = true; grid.material.opacity = .55; scene.add(grid);
  const cv = document.createElement('canvas'); cv.width = ortho.width; cv.height = ortho.height;
  const x = cv.getContext('2d'); x.drawImage(ortho, 0, 0);
  const im = x.getImageData(0, 0, cv.width, cv.height), a = im.data;
  for (let i = 0; i < a.length; i += 4) if (a[i] + a[i + 1] + a[i + 2] < 12) a[i + 3] = 0;    // never seen: see-through
  x.putImageData(im, 0, 0);
  // keep the street we rode: the photo fades out ~12 m either side of the ride, where it is seen too obliquely to trust
  const mk = document.createElement('canvas'); mk.width = cv.width; mk.height = cv.height; const m = mk.getContext('2d');
  m.filter = `blur(${Math.round(4 / E.res)}px)`; m.strokeStyle = '#fff'; m.lineCap = m.lineJoin = 'round'; m.lineWidth = 20 / E.res;
  m.beginPath(); D.path.forEach((p, i) => { const px = (p.x - E.x0) / E.res, py = (E.y1 - p.y) / E.res; i ? m.lineTo(px, py) : m.moveTo(px, py); }); m.stroke();
  x.globalCompositeOperation = 'destination-in'; x.drawImage(mk, 0, 0); x.globalCompositeOperation = 'source-over';
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
  const road = new THREE.Mesh(new THREE.PlaneGeometry(E.x1 - E.x0, E.y1 - E.y0), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
  road.position.set(cx0, cy0, -.03); scene.add(road);
}
const cloudPts = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ size: .07, vertexColors: true }));
if (D.cloud) {
  const [pb, cb] = await Promise.all([D.cloud.points, D.cloud.colours].map(f => fetch(href(f)).then(r => {if(!r.ok)throw new Error('Point cloud unavailable.');return r.arrayBuffer();})));
  const pa = new Float32Array(pb), ca = new Uint8Array(cb), keep = [];
  const step=Math.max(1,Math.ceil(pa.length/3/(innerWidth<700?80000:200000)));
  for (let i = 0; i < pa.length / 3; i+=step) if (pa[3 * i + 2] > .25) keep.push(i);         // the road is the photo; points add what stands on it
  const P3 = new Float32Array(keep.length * 3), Cb = new Uint8Array(keep.length * 3);
  keep.forEach((i, j) => { for (let k = 0; k < 3; k++) { P3[3 * j + k] = pa[3 * i + k]; Cb[3 * j + k] = ca[3 * i + k]; } });
  cloudPts.geometry.setAttribute('position', new THREE.BufferAttribute(P3, 3));
  cloudPts.geometry.setAttribute('color', new THREE.BufferAttribute(Cb, 3, true));
  scene.add(cloudPts);
}
// the ride as a painted ribbon: dim ahead, green where we have been
const ribbon = (() => {
  const pos = [], idx = [], w = .22;
  PATH.forEach((p, i) => {
    const q = PATH[Math.min(i + 1, PATH.length - 1)], r = PATH[Math.max(i - 1, 0)];
    let dx = q.x - r.x, dy = q.y - r.y; const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
    pos.push(p.x - dy * w, p.y + dx * w, .05, p.x + dy * w, p.y - dx * w, .05);
    if (i) { const a = 2 * (i - 1); idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  });
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setIndex(idx);
  const all = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: C3.green, transparent: true, opacity: .28, depthWrite: false }));
  const done = new THREE.Mesh(geo.clone(), new THREE.MeshBasicMaterial({ color: C3.green, transparent: true, opacity: .95, depthWrite: false }));
  scene.add(all, done); return done;
})();

const flat = (pts, z) => { const sh = new THREE.Shape(); pts.forEach((p, i) => i ? sh.lineTo(p[0], p[1]) : sh.moveTo(p[0], p[1])); const g = new THREE.ShapeGeometry(sh); g.translate(0, 0, z); return g; };
function textSprite(text, fg, bg, h = .9) {
  const cv = document.createElement('canvas'), x = cv.getContext('2d'), f = '700 44px Georgia, serif';
  x.font = f; const w = Math.ceil(x.measureText(text).width) + 36; cv.width = w; cv.height = 72;
  x.font = f; x.fillStyle = bg; x.beginPath(); x.roundRect(0, 6, w, 60, 30); x.fill();
  x.fillStyle = fg; x.textBaseline = 'middle'; x.fillText(text, 18, 40);
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  sp.scale.set(h * w / 72, h, 1); sp.renderOrder = 10; return sp;
}
// road text, painted the way "PEDS TO YIELD" is: tall letters, first word nearest the traffic reading it
function roadText(lines, color) {
  const cv = document.createElement('canvas'); cv.width = 512; cv.height = 256 * lines.length;
  const x = cv.getContext('2d'); x.fillStyle = color; x.font = '800 190px Georgia, serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
  [...lines].reverse().forEach((l, i) => { x.save(); x.translate(256, 128 + 256 * i + 14); x.scale(.58, 1); x.fillText(l, 0, 0); x.restore(); });
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 1.9 * lines.length * 1.25), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }));
  m.renderOrder = 3; return m;
}

// vehicles and street furniture
const unitBox = new THREE.BoxGeometry(1, 1, 1); unitBox.translate(0, 0, .5);
const meshOf = {};
function block(o, color, opacity, h) {
  const F = o.footprint, L = Math.hypot(F[1][0] - F[0][0], F[1][1] - F[0][1]), W = Math.hypot(F[2][0] - F[1][0], F[2][1] - F[1][1]);
  const g = new THREE.Group();
  const m = new THREE.Mesh(unitBox, new THREE.MeshLambertMaterial({ color, transparent: true, opacity, depthWrite: opacity > .9, emissive: '#000000' }));
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(unitBox), new THREE.LineBasicMaterial({ color: new THREE.Color(color).lerp(new THREE.Color('#ffffff'), .45), transparent: true, opacity: Math.min(1, opacity + .25) }));
  for (const k of [m, e]) { k.scale.set(L, W, h); g.add(k); }
  g.position.set((F[0][0] + F[2][0]) / 2, (F[0][1] + F[2][1]) / 2, 0); g.rotation.z = Math.atan2(F[1][1] - F[0][1], F[1][0] - F[0][0]);
  scene.add(g); meshOf[o.id] = m; return g;
}
for (const o of D.objects) {
  if (o.group === 'vehicle') block(o, o.motion==='standing' ? C3.red : new THREE.Color(o.motion==='unknown'?'#719bb2':'#8a8f92'), o.motion==='standing' ? .62 : .16, o.height || 1.45);
  else if (o.footprint) block(o, C3.yellow, o.blocks ? .55 : .14, Math.max(.3, Math.min(o.height || 1, 3.5)));
  else if (o.group !== 'crosswalk') {
    const spec = { bollard: [new THREE.CylinderGeometry(.1, .1, .9, 12), C3.yellow, .45], person: [new THREE.CapsuleGeometry(.23, 1.1, 4, 10), C3.paint, .8],
                   bicycle: [new THREE.BoxGeometry(.45, .45, 1), new THREE.Color('#6fc3ff'), .5], 'fire hydrant': [new THREE.CylinderGeometry(.16, .2, .7, 12), C3.red, .35],
                   pole: [new THREE.CylinderGeometry(.07, .07, 4, 8), new THREE.Color('#6c7176'), 2], tree: [new THREE.CylinderGeometry(.14, .18, 3, 8), new THREE.Color('#5b5148'), 1.5] }[o.group];
    if (!spec) continue;
    const m = new THREE.Mesh(spec[0], new THREE.MeshLambertMaterial({ color: spec[1] }));
    if (o.group !== 'bicycle') m.rotation.x = Math.PI / 2;
    m.position.set(o.xy[0], o.xy[1], spec[2]); scene.add(m);
  }
}

// crossings: zebra bars, each side's watch area (a 1 m tall box), the sightline from the rider, road paint, labels
for (const c of cws) {
  const r = rider(c.t_edge), v = [Math.cos(r.h), Math.sin(r.h)], u = [-v[1], v[0]];
  const R = c.rect, ctr = [R.reduce((s, p) => s + p[0], 0) / 4, R.reduce((s, p) => s + p[1], 0) / 4];
  const hu = Math.max(...R.map(p => Math.abs((p[0] - ctr[0]) * u[0] + (p[1] - ctr[1]) * u[1])));
  const hv = Math.max(...R.map(p => Math.abs((p[0] - ctr[0]) * v[0] + (p[1] - ctr[1]) * v[1])));
  for (let k = -hu + .4; k <= hu - .3; k += 1.0) {
    const bar = new THREE.Mesh(new THREE.PlaneGeometry(Math.max(.6, 2 * hv - .6), .5), new THREE.MeshBasicMaterial({ color: C3.paint, transparent: true, opacity: .82, depthWrite: false }));
    bar.position.set(ctr[0] + u[0] * k, ctr[1] + u[1] * k, .04); bar.rotation.z = Math.atan2(v[1], v[0]); scene.add(bar);
  }
  const disc = textSprite(String(c.n), verdict(c) === 'v-part' ? '#1e2022' : '#ffffff', vcol(c), 1.5); disc.position.set(c.xy[0], c.xy[1], 7.5); scene.add(disc);
  c.fx = { ends: [], labels: [] };
  for (const e of c.ends) {
    const A = e.area, mid = [A.reduce((s, p) => s + p[0], 0) / 4, A.reduce((s, p) => s + p[1], 0) / 4];
    const box = new THREE.Mesh(new THREE.ExtrudeGeometry((() => { const sh = new THREE.Shape(); A.forEach((p, i) => i ? sh.lineTo(p[0], p[1]) : sh.moveTo(p[0], p[1])); return sh; })(), { depth: TH, bevelEnabled: false }),
                               new THREE.MeshBasicMaterial({ color: '#9aa0a3', transparent: true, opacity: .12, depthWrite: false }));
    box.renderOrder = 3; scene.add(box);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry), new THREE.LineBasicMaterial({ color: '#9aa0a3', transparent: true, opacity: .9 }));
    scene.add(edges);
    const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    const line = new THREE.Line(lg, new THREE.LineBasicMaterial({ color: '#ffffff', transparent: true, opacity: .95, depthTest: false }));
    line.renderOrder = 6; line.frustumCulled = false; line.visible = false; scene.add(line);
    const paints = [];
    if (e.covered) {                                   // painted on the ride, reading toward the rider
      const put = (m, d) => { const p = riderAtS(c.s_edge - d); m.position.set(p.x, p.y, .07); m.rotation.z = p.h - Math.PI / 2; m.visible = false; scene.add(m); paints.push(m); };
      if (!c.fx.stop) { put(roadText(['STOP', `${Math.round(e.needed_m)} M`], '#f2f1ec'), e.needed_m); c.fx.stop = true; }
      if (e.exposed && e.clear_from_m != null && level(e) === 'hidden')
        put(roadText([`${e.side.toUpperCase()}`, `SEEN ${Math.round(e.clear_from_m)} M`], css('--curb')), Math.max(e.clear_from_m, 1.6));
    }
    c.fx.ends.push({ e, box, edges, line, mid, paints });
  }
  for (const id of new Set(c.ends.filter(e => level(e) === 'hidden').flatMap(e => e.blockers.slice(0, 2).map(b => b.id)))) {
    const o = byId[id]; if (!o.footprint) continue;
    const txt = o.group === 'vehicle' ? cap(o.label) : o.height ? `${cap(NAME[o.group] || o.group)}, ${o.height.toFixed(1)} m tall` : cap(NAME[o.group] || o.group);
    const sp = textSprite(txt, o.group === 'vehicle' ? '#ffffff' : '#1e2022', o.group === 'vehicle' ? css('--curb') : css('--line'), .55);
    sp.position.set(o.xy[0], o.xy[1], (o.height || 1.45) + .7 + .7 * c.fx.labels.length); scene.add(sp); c.fx.labels.push({ sp, id });
  }
}
// what the rider could see: per frame, the street within WIN m, light where it was in view and red where it was hidden
let viewMesh = null, viewTex = null, viewData = null, viewK = -2;
if (D.view) {
  const V = D.view;
  viewData = new Uint8Array(await (await fetch(href(V.file))).arrayBuffer());
  viewTex = new THREE.DataTexture(new Uint8Array(V.nx * V.ny * 4), V.nx, V.ny, THREE.RGBAFormat);
  viewTex.magFilter = viewTex.minFilter = THREE.LinearFilter;
  viewMesh = new THREE.Mesh(new THREE.PlaneGeometry(V.nx * V.res, V.ny * V.res), new THREE.MeshBasicMaterial({ map: viewTex, transparent: true, depthWrite: false }));
  viewMesh.position.set(V.x0 + V.nx * V.res / 2, V.y0 + V.ny * V.res / 2, .015); viewMesh.renderOrder = 2; scene.add(viewMesh);
}
function setView(k) {
  if (!viewTex || k === viewK) return;
  viewK = k;
  const V = D.view, n = V.nx * V.ny, off = Math.min(V.frames - 1, Math.max(0, k)) * n, px = viewTex.image.data;
  for (let i = 0; i < n; i++) {
    const s = viewData[off + i], j = 4 * i;
    if (s === 1) { px[j] = 255; px[j + 1] = 236; px[j + 2] = 180; px[j + 3] = 105; }
    else if (s === 2) { px[j] = 236; px[j + 1] = 40; px[j + 2] = 32; px[j + 3] = 200; }
    else px[j + 3] = 0;
  }
  viewTex.needsUpdate = true;
}
// the rider
const riderM = new THREE.Group();
{ const body = new THREE.Mesh(new THREE.ConeGeometry(.42, 1.3, 4), new THREE.MeshLambertMaterial({ color: C3.yellow, emissive: '#5a4600' }));
  body.rotation.z = -Math.PI / 2; body.position.z = CAM_H; riderM.add(body);
  const half = D.hfov / 2 * Math.PI / 180, sh = new THREE.Shape(); sh.moveTo(0, 0); sh.absarc(0, 0, WIN, -half, half, false); sh.lineTo(0, 0);
  const cone = new THREE.Mesh(new THREE.ShapeGeometry(sh, 24), new THREE.MeshBasicMaterial({ color: C3.yellow, transparent: true, opacity: .07, depthWrite: false }));
  cone.position.z = .05; riderM.add(cone); }
scene.add(riderM);

// ---- the director: where the camera goes ----
let view = 'director', started = false;
const eye = new THREE.Vector3(), look = new THREE.Vector3(), wantEye = new THREE.Vector3(), wantLook = new THREE.Vector3();
let last = performance.now();
function shot(t, now) {
  const R = rider(t), fx = Math.cos(R.h), fy = Math.sin(R.h);
  const behind = () => { wantEye.set(R.x - 9 * fx, R.y - 9 * fy, 6); wantLook.set(R.x + 10 * fx, R.y + 10 * fy, 0); };
  if (view === 'chase') return behind();
  if (view === 'overview') { wantEye.set(cx0 - 22, cy0 - 50, 46); wantLook.set(cx0 + 4, cy0, 0); return; }
  if (!started) {                                      // the opening: a slow flight down the street we rode
    const total = arc[arc.length - 1], s = still ? total * .35 : (now * .005) % total;
    const i = Math.max(0, arc.findIndex(v => v >= s)), p = PATH[i], q = PATH[Math.min(i + 6, PATH.length - 1)];
    let dx = q.x - p.x, dy = q.y - p.y; const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
    wantEye.set(p.x - dx * 14 - dy * 16, p.y - dy * 14 + dx * 16, 17); wantLook.set(p.x + dx * 16, p.y + dy * 16, 0); return;
  }
  const c = inspecting(t);
  if (!c) return behind();
  // raised behind the rider, looking past them at the side of the crossing they cannot see
  const e = worst(c), mid = c.fx.ends.find(f => f.e === e).mid;
  let dx = mid[0] - R.x, dy = mid[1] - R.y; const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
  const side = (fx * (mid[1] - R.y) - fy * (mid[0] - R.x)) > 0 ? -1 : 1;    // stand off to the other side
  const aside = innerWidth > 900 ? 2.5 : 0;
  wantLook.set((R.x + mid[0]) / 2 + fx * 1.5 - fy * aside, (R.y + mid[1]) / 2 + fy * 1.5 + fx * aside, .4);
  wantEye.set(R.x - fx * 11 + side * -fy * 4.5, R.y - fy * 11 + side * fx * 4.5, 9.5);
}

// ---- per frame: the scene's moving parts ----
function update3d(t, now) {
  const R = rider(t);
  riderM.position.set(R.x, R.y, 0); riderM.rotation.z = R.h;
  let k = 0; while (k < PATH.length - 1 && PATH[k + 1].t <= t) k++;
  ribbon.geometry.setDrawRange(0, 6 * k);
  const pulse = still ? .5 : .5 + .5 * Math.sin(now * .006);
  setView(Math.round(t * D.fps));
  const lit = new Set(), kf = Math.round(t * D.fps), act = inspecting(t);
  for (const c of cws) {
    const on = c === act || view === 'overview' || view === 'free';
    for (const f of c.fx.ends) {
      const fr = f.e.frames.find(q => q.k === kf), live = c === act && fr && fr.seen != null && f.e.covered && level(f.e) !== 'disputed';
      const col = live ? new THREE.Color(seenCol(fr.seen)) : f.e.covered ? new THREE.Color(COL[level(f.e)]) : new THREE.Color('#9aa0a3');
      f.box.material.color.copy(col); f.edges.material.color.copy(col);
      f.box.material.opacity = live ? .42 + .2 * pulse : on ? .3 : .12;
      f.line.visible = !!live;
      if (live) {
        const p = f.line.geometry.attributes.position; p.setXYZ(0, R.x, R.y, CAM_H); p.setXYZ(1, f.mid[0], f.mid[1], TH); p.needsUpdate = true;
        f.line.material.color.copy(col);
      }
      f.paints.forEach(m => m.visible = on);
    }
    for (const L of c.fx.labels) { L.sp.visible = c === act && view !== 'overview'; if (c === act) lit.add(L.id); }
  }
  for (const [id, m] of Object.entries(meshOf)) { const q = lit.has(+id) ? pulse : 0; m.material.emissive.setRGB(.55 * q, .45 * q, .1 * q); }
  if (view === 'free') orbit.update();
  else {
    shot(t, now);
    const dt = Math.min(.1, (now - last) / 1000), a = still ? 1 : 1 - Math.exp(-dt * 2.2);
    if (!eye.lengthSq()) { eye.copy(wantEye); look.copy(wantLook); }
    eye.lerp(wantEye, a); look.lerp(wantLook, a); cam.position.copy(eye); cam.lookAt(look);
  }
  renderer.render(scene, cam);
}
function size3() { const w = stage.clientWidth, h = stage.clientHeight; renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); }
new ResizeObserver(size3).observe(stage); size3();

// ---- the card: the crossing being inspected, else the next one ----
let shown = null;
function updateCard(t) {
  const c = cws.find(c => t >= c.tw0 - .4 && t <= c.tw1 + 1.2) || null;
  const nx = cws.find(c => c.tw0 > t);
  const key = c ? `c${c.id}` : `n${nx ? nx.id : 'end'}`;
  if (key === shown) {
    const el = $('card').querySelector('.next');
    if (!c && nx && el) el.textContent = `Crossing ${nx.n} in ${Math.max(0, Math.round(nx.s_edge - rider(t).s))} m`;
    return;
  }
  shown = key;
  const card = $('card');
  card.className = 'card ' + (c ? verdict(c) : '');
  card.innerHTML = c ? cardHTML(c)
    : nx ? `<p class="next">Crossing ${nx.n} in ${Math.max(0, Math.round(nx.s_edge - rider(t).s))} m</p><p class="hint">Light: in view · Red: hidden · Yellow: obstruction</p>`
         : `<p class="next">End of the ride</p><p class="hint">${S.crosswalks} crossings over ${Math.round(S.distance)} m; ${S.crossings_judged} could be judged.</p>`;
  void card.offsetWidth; card.classList.add('fresh');
}

// ---- the minimap ----
const MS = { s: 0, x: 0, y: 0 };
function drawMini(t) {
  if (!mini.offsetParent) return;
  const r = devicePixelRatio || 1, W = Math.round(mini.clientWidth * r), H = Math.round(mini.clientHeight * r);
  if (mini.width !== W || mini.height !== H) { mini.width = W; mini.height = H; }
  const ctx = mini.getContext('2d'), R = rider(t);
  const fit = Math.min(W / (E.x1 - E.x0), H / (E.y1 - E.y0)) * 2.6;
  const a = still || !MS.s ? 1 : .15, ax = R.x + Math.cos(R.h) * 10, ay = R.y + Math.sin(R.h) * 10;   // what is coming up
  MS.s += (fit - MS.s) * a; MS.x += (ax - MS.x) * a; MS.y += (ay - MS.y) * a;
  const P = (x, y) => [W / 2 + (x - MS.x) * MS.s, H / 2 - (y - MS.y) * MS.s];
  const poly = pts => { ctx.beginPath(); pts.forEach((p, i) => { const [x, y] = P(p[0], p[1]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.closePath(); };
  ctx.clearRect(0, 0, W, H);
  const [ix, iy] = P(E.x0, E.y1); ctx.globalAlpha = .9; ctx.drawImage(ortho, ix, iy, (E.x1 - E.x0) * MS.s, (E.y1 - E.y0) * MS.s); ctx.globalAlpha = 1;
  for (const c of cws) for (const e of c.ends) { poly(e.area); ctx.fillStyle = COL[level(e)] + '99'; ctx.fill(); }
  for (const o of D.objects) if (o.footprint) {
    poly(o.footprint);
    ctx.fillStyle = o.group === 'vehicle' ? (o.parked ? 'rgba(224,54,44,.75)' : 'rgba(201,205,207,.25)') : (o.blocks ? 'rgba(245,197,24,.85)' : 'rgba(245,197,24,.25)'); ctx.fill();
  }
  ctx.strokeStyle = css('--lane'); ctx.lineWidth = 3 * r; ctx.lineCap = 'round'; ctx.beginPath();
  PATH.filter(p => p.t <= t).forEach((p, i) => { const [x, y] = P(p.x, p.y); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
  for (const c of cws) {
    const [x, y] = P(...c.xy); ctx.fillStyle = vcol(c); ctx.beginPath(); ctx.arc(x, y, 9 * r, 0, 7); ctx.fill();
    ctx.fillStyle = verdict(c) === 'v-part' ? '#1e2022' : '#fff'; ctx.font = `800 ${11 * r}px Georgia`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(c.n, x, y + r);
  }
  const [rx, ry] = P(R.x, R.y), half = D.hfov / 2 * Math.PI / 180;
  const g = ctx.createRadialGradient(rx, ry, 0, rx, ry, 16 * MS.s); g.addColorStop(0, 'rgba(245,197,24,.4)'); g.addColorStop(1, 'rgba(245,197,24,0)');
  ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(rx, ry); ctx.arc(rx, ry, 16 * MS.s, -R.h - half, -R.h + half); ctx.closePath(); ctx.fill();
  ctx.fillStyle = css('--line'); ctx.strokeStyle = '#1e2022'; ctx.lineWidth = 2 * r; ctx.beginPath(); ctx.arc(rx, ry, 6 * r, 0, 7); ctx.fill(); ctx.stroke();
}

// ---- the scrubber ----
function drawScrub(t) {
  const r = devicePixelRatio || 1, W = Math.round(scrub.clientWidth * r), H = Math.round(scrub.clientHeight * r), dur = S.duration;
  if (scrub.width !== W || scrub.height !== H) { scrub.width = W; scrub.height = H; }
  const ctx = scrub.getContext('2d'), X = s => 12 * r + (W - 24 * r) * Math.min(1, Math.max(0, s / dur));
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(242,241,236,.16)'; ctx.fillRect(X(0), H / 2 - 3 * r, X(dur) - X(0), 6 * r);
  for (const c of cws) { ctx.fillStyle = 'rgba(245,197,24,.16)'; ctx.fillRect(X(c.tw0), H / 2 - 9 * r, X(c.tw1) - X(c.tw0), 18 * r); }
  ctx.fillStyle = css('--lane'); ctx.fillRect(X(0), H / 2 - 3 * r, X(t) - X(0), 6 * r);
  for (const c of cws) {
    const x = X(c.t_edge); ctx.fillStyle = vcol(c); ctx.beginPath(); ctx.arc(x, H / 2, 10 * r, 0, 7); ctx.fill();
    ctx.fillStyle = verdict(c) === 'v-part' ? '#1e2022' : '#fff'; ctx.font = `800 ${11 * r}px Georgia`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(c.n, x, H / 2 + r);
  }
  ctx.fillStyle = css('--paint'); ctx.fillRect(X(t) - 1.5 * r, 4 * r, 3 * r, H - 8 * r);
}
let dragging = false;
const scrubTo = e => { const b = scrub.getBoundingClientRect(); seek(Math.min(1, Math.max(0, (e.clientX - b.left - 12) / (b.width - 24))) * S.duration); begin(); };
scrub.onpointerdown = e => { dragging = true; scrub.setPointerCapture(e.pointerId); scrubTo(e); };
scrub.onpointermove = e => { if (dragging) scrubTo(e); };
scrub.onpointerup = () => { dragging = false; };

// ---- the video and its boxes ----
function drawOverlay(t) {
  const r = devicePixelRatio || 1, b = ov.getBoundingClientRect(), W = Math.round(b.width * r), H = Math.round(b.height * r);
  if (ov.width !== W || ov.height !== H) { ov.width = W; ov.height = H; }
  const ctx = ov.getContext('2d'); ctx.clearRect(0, 0, W, H);
  const k = Math.round(t * D.fps), boxes = D.overlays[k] || [], sx = W / D.frame_size[0], sy = H / D.frame_size[1];
  if(overlayMode==='yolo'){drawYOLO(ctx,t,W,H);return;}
  if(overlayMode==='none')return;
  const act = inspecting(t), key = new Set(act ? act.ends.flatMap(e => e.blockers.map(b => b.id)) : []);
  ctx.font = `700 ${11 * r}px Georgia`; ctx.textBaseline = 'bottom';
  for (const [id, x0, y0, x1, y1] of boxes) {
    const o = byId[id]; let col, label = '';
    if (o.group === 'vehicle') { col = o.motion==='standing' ? css('--curb') : o.motion==='unknown'?'#719bb2':'#c9cdcf'; label = key.has(id) ? o.label : ''; }
    else if (o.footprint) { col = css('--line'); label = key.has(id) ? o.label : ''; }
    else continue;
    if (act && !key.has(id)) continue;                 // at a crossing, only what screens its sides
    ctx.globalAlpha = act ? 1 : .5;
    ctx.strokeStyle = col; ctx.lineWidth = 1.8 * r; ctx.strokeRect(x0 * sx, y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy);
    if (label) { const w = ctx.measureText(label).width + 8 * r; ctx.fillStyle = col; ctx.fillRect(x0 * sx, y0 * sy - 14 * r, w, 14 * r);
      ctx.fillStyle = col === css('--line') || col === '#c9cdcf' ? '#1e2022' : '#fff'; ctx.fillText(label, x0 * sx + 4 * r, y0 * sy - r); }
  }
  ctx.globalAlpha = 1;
  // each side of the crossing ahead, as a 1 m tall box where someone about to cross would stand
  if (act) for (const e of act.ends) {
    const f = e.frames.find(f => f.k === k);
    if (!f || !f.poly) continue;
    const col = e.covered && f.seen != null && level(e) !== 'disputed' ? seenCol(f.seen) : '#c9cdcf', P = f.poly.map(([x, y]) => [x * sx, y * sy]);
    const path = pts => { ctx.beginPath(); pts.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); };
    ctx.globalAlpha = .3; ctx.fillStyle = col; path(P.slice(4)); ctx.fill(); ctx.globalAlpha = 1;
    ctx.strokeStyle = col; ctx.lineWidth = 2.2 * r; path(P.slice(0, 4)); ctx.stroke(); path(P.slice(4)); ctx.stroke();
    for (let i = 0; i < 4; i++) { ctx.beginPath(); ctx.moveTo(...P[i]); ctx.lineTo(...P[i + 4]); ctx.stroke(); }
    if (e.covered && f.seen != null && level(e) !== 'disputed') {
      const txt = `${e.side} side: ${f.seen >= CLEAR ? 'in view' : `${pct(1 - f.seen)} hidden`}`, top = P.slice(0, 4).reduce((a, p) => p[1] < a[1] ? p : a);
      const w = ctx.measureText(txt).width + 8 * r; ctx.fillStyle = col; ctx.fillRect(top[0] - w / 2, top[1] - 18 * r, w, 14 * r);
      ctx.fillStyle = f.seen >= CLEAR ? '#fff' : f.seen >= .5 ? '#1e2022' : '#fff'; ctx.fillText(txt, top[0] - w / 2 + 4 * r, top[1] - 5 * r);
    }
  }
}

// ---- controls ----
function seek(t) { vid.currentTime = Math.min(S.duration, Math.max(0, t)); }
function begin() { started = true; $('go').hidden = true; document.querySelector('.cockpit').classList.add('playing'); }
function start() { begin(); vid.play().catch(()=>{ $('error-banner').hidden=false;$('error-banner').textContent='Playback unavailable. The map and recommendation evidence remain available.'; }); }
$('go').onclick = start;
$('play').onclick = () => { if (!started || vid.paused) start(); else vid.pause(); };
vid.onplay = () => { begin(); $('play').textContent = 'Pause'; };
vid.onpause = () => $('play').textContent = 'Play';
document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => {
  view = b.dataset.view; orbit.enabled = view === 'free';
  document.querySelectorAll('[data-view]').forEach(x => x.setAttribute('aria-pressed', x === b));
  if (view === 'free') { orbit.target.copy(look); orbit.update(); }
});
$('cloud').onclick = () => { cloudPts.visible = !cloudPts.visible; $('cloud').setAttribute('aria-pressed', cloudPts.visible); };
$('seen').onclick = () => { if (viewMesh) { viewMesh.visible = !viewMesh.visible; $('seen').setAttribute('aria-pressed', viewMesh.visible); } };
addEventListener('keydown', e => {
  if (e.target.closest('button, input, select, textarea, a, .xi')) return;
  const t = vid.currentTime || 0;
  if (e.key === ' ') { e.preventDefault(); $('play').click(); }
  else if (e.key === 'ArrowRight') { const c = cws.find(c => c.tw0 - .3 > t + .05); if (c) { seek(c.tw0 - .3); begin(); } }
  else if (e.key === 'ArrowLeft') { const c = [...cws].reverse().find(c => c.tw0 - .3 < t - .6); seek(c ? c.tw0 - .3 : 0); }
});

function frame(now) {
  const t = vid.currentTime || 0;
  // the story slows down while a crossing is inspected
  const slow = view === 'director' && started && !vid.paused && !!inspecting(t) && !still;
  const rate = slow ? .4 : 1; if (vid.playbackRate !== rate) vid.playbackRate = rate;
  $('speed').classList.toggle('on', slow);
  $('clock').textContent = `${t.toFixed(1)} s of ${S.duration.toFixed(1)} s`;
  update3d(t, now); updateCard(t); drawMini(t); drawScrub(t); drawOverlay(t);
  last = now;
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ---- archive detections, linked crossing maintenance proposals and Cosmos evidence ----
let overlayMode='spatial';const detectionCache=new Map();let detectionClip=null;
function currentClip(t){return D.clips.find(c=>c.start_sec<=t&&c.end_sec>t)||D.clips.at(-1);}
function warmDetections(t){const clip=currentClip(t);if(!clip||clip.id===detectionClip)return;detectionClip=clip.id;if(!detectionCache.has(clip.id)){detectionCache.set(clip.id,null);read('api/detections/'+clip.id).then(d=>detectionCache.set(clip.id,d)).catch(()=>detectionCache.set(clip.id,{available:false,frames:[]}));}}
function drawYOLO(ctx,t,W,H){warmDetections(t);const clip=currentClip(t),data=detectionCache.get(clip?.id);if(!data?.available)return;const local=t-clip.start_sec,frames=data.frames||[];const f=frames.reduce((best,f)=>Math.abs((f.time_sec??f.timestamp_sec??f.frame_index/(data.fps||30))-local)<Math.abs((best?.time_sec??best?.timestamp_sec??best?.frame_index/(data.fps||30)??1e9)-local)?f:best,null);if(!f||Math.abs((f.time_sec??f.timestamp_sec??0)-local)>.15)return;const shape=f.shape||data.video_shape||[1080,1920],sx=W/(shape[1]||1920),sy=H/(shape[0]||1080);ctx.font='13px Georgia, serif';for(const o of f.detections||[]){if((o.confidence??0)<.5)continue;const b=o.bbox||o.box;if(!b||b.length!==4)continue;ctx.strokeStyle='#90cfe3';ctx.fillStyle='#90cfe3';ctx.lineWidth=2;ctx.strokeRect(b[0]*sx,b[1]*sy,(b[2]-b[0])*sx,(b[3]-b[1])*sy);ctx.fillText(o.class_name||o.label||'object',b[0]*sx,b[1]*sy-4);}}
$('overlay-mode').onclick=()=>{overlayMode=overlayMode==='spatial'?'yolo':overlayMode==='yolo'?'none':'spatial';$('overlay-mode').textContent=overlayMode==='spatial'?'Sightlines':overlayMode==='yolo'?'YOLO objects':'No overlays';if(overlayMode==='yolo')warmDetections(vid.currentTime);};
const findings=D.findings||[];
$('recommendations').innerHTML=findings.length?findings.map(f=>`<a class="recommendation" href="${href(ridePath+'/recommendations/'+f.id)}"><span>${escape(f.title)}</span><span aria-hidden="true">↗</span></a>`).join(''):'<p class="empty-insight">No supported maintenance action found.</p>';
const findingId=location.pathname.match(/\/(?:finding|recommendations)\/(crossing-[0-9]+-(?:left|right))/)?.[1];
const finding=findings.find(f=>f.id===findingId);
function paginateText(container,text){
 const words=String(text).split(/\s+/),pages=[],size=innerHeight<700?40:65;for(let i=0;i<words.length;i+=size)pages.push(words.slice(i,i+size).join(' '));
 let page=0;const render=()=>{container.innerHTML=`<p class="analysis-copy">${escape(pages[page]||'No analysis available.')}</p><div class="pager"><button id="analysis-prev" ${page===0?'disabled':''}>Previous</button><span>${page+1} / ${Math.max(1,pages.length)}</span><button id="analysis-next" ${page>=pages.length-1?'disabled':''}>Next</button></div>`;container.querySelector('#analysis-prev').onclick=()=>{page--;render();};container.querySelector('#analysis-next').onclick=()=>{page++;render();};};render();
}
function renderReport(f){
 document.body.classList.add('detail');$('policy-report').hidden=false;
 $('policy-report').innerHTML=`<header class="report-head"><a href="${href(ridePath)}?t=${f.scene_time_sec}">← Street story</a><span class="eyebrow">Crossing ${f.crossing} · ${escape(f.side)}</span><h1>${escape(f.title)}</h1></header><div class="report-tabs" role="tablist" aria-label="Recommendation evidence">${['Action','Statistics','Frames','Video','Review','Cosmos','Source'].map((label,i)=>`<button role="tab" id="tab-${label.toLowerCase()}" aria-controls="report-content" aria-selected="${i===0}" data-tab="${label.toLowerCase()}">${label}</button>`).join('')}</div><div class="report-content" id="report-content" role="tabpanel" aria-labelledby="tab-action"></div>`;
 const content=$('report-content');let sourcePage=0,reviewPage=0;
 const reviews=cws.find(c=>c.id===f.object_id)?.ends.filter(e=>e.review)||[];
 function tab(which){
  const figure=$('evidence-video');document.body.appendChild(figure);
  figure.hidden=which!=='video';vid.pause();
  document.querySelectorAll('[data-tab]').forEach(b=>{b.setAttribute('aria-selected',b.dataset.tab===which);b.tabIndex=b.dataset.tab===which?0:-1;});
  content.setAttribute('aria-labelledby','tab-'+which);
  if(which==='action')content.innerHTML=`<span class="eyebrow">Maintenance proposal</span><h2>Clear the waiting area from view obstructions.</h2><p class="large-copy">${escape(f.action)}</p><p class="small-note">${escape(f.limitations)}</p><button class="primary" id="show-frames">See the supporting frames ↗</button>`;
  if(which==='statistics')content.innerHTML=`<p class="eyebrow">Imported spatial estimates</p><div class="policy-metrics">${[[pct(f.metrics.hidden_fraction),'waiting area hidden'],[mm(f.metrics.estimated_stop_m),'modeled stopping distance'],[f.metrics.estimated_clear_m==null?'—':mm(f.metrics.estimated_clear_m),'fully in view']].map(([v,l])=>`<div><strong>${v}</strong><span>${l}</span></div>`).join('')}</div><p>From the ${escape(f.side)} approach at ${f.scene_time_sec.toFixed(1)} s. These values use an assumed camera height, not a calibrated survey.</p><p class="small-note">${S.stopped ?? 0} standing vehicle footprints · ${D.objects.filter(o=>o.motion==='moving').length} moving · ${D.objects.filter(o=>o.group==='vehicle'&&o.motion==='unknown').length} uncertain. Standing does not distinguish parking from queuing.</p>`;
  if(which==='frames')content.innerHTML=`<figure class="review-image">${f.evidence_url?`<img src="${href(f.evidence_url)}" alt="${escape(f.side)} waiting area at modeled stopping distance, compared with the later approach">`:'<p>No frame export available.</p>'}<figcaption>At modeled stopping distance / later on the approach · imported review ${escape(f.review.claim)}</figcaption></figure>`;
  if(which==='video'){
   content.innerHTML=`<div class="video-slot"></div><div class="evidence-links">${f.segment_refs.map(r=>`<button class="evidence-link" data-seek="${r.start_sec}">${r.start_sec.toFixed(1)}–${r.end_sec.toFixed(1)} s · ${escape(r.camera_id)}</button>`).join('')}</div>`;
   content.querySelector('.video-slot').appendChild($('evidence-video'));seekWhenReady(f.scene_time_sec);vid.controls=true;
   content.querySelectorAll('[data-seek]').forEach(b=>b.onclick=()=>{seek(Number(b.dataset.seek));vid.play().catch(()=>{});});
  }else{document.body.appendChild($('evidence-video'));vid.controls=false;}
  if(which==='review'){
   const e=reviews[reviewPage],review=e?.review;
   content.innerHTML=`<span class="eyebrow">Independent frame review</span><h2>${cap(e?.side||f.side)} side · ${escape(review?.claim||'Not reviewed')}</h2><div id="review-copy"></div><p class="small-note">Rejected claims are retained and excluded from maintenance actions.</p><div class="pager"><button id="review-prev" ${reviewPage===0?'disabled':''}>Previous side</button><span>${reviewPage+1} / ${Math.max(1,reviews.length)}</span><button id="review-next" ${reviewPage>=reviews.length-1?'disabled':''}>Next side</button></div>`;
   paginateText($('review-copy'),review?.reason||'No independent review available.');
   $('review-prev').onclick=()=>{reviewPage--;tab('review');};$('review-next').onclick=()=>{reviewPage++;tab('review');};
  }
  if(which==='cosmos'){
   content.innerHTML=`<span class="eyebrow">Indexed captions + spatial evidence</span><button id="cosmos-analysis" class="primary">Generate Cosmos analysis</button><div id="cosmos-result" role="status"></div>`;
   $('cosmos-analysis').onclick=async()=>{const b=$('cosmos-analysis');b.disabled=true;$('cosmos-result').textContent='Reading indexed footage and imported reviews…';try{const d=await read(analysisPath,{method:'POST'});paginateText($('cosmos-result'),d.answer);}catch{$('cosmos-result').textContent='Analysis unavailable. Saved evidence remains available.';}finally{b.disabled=false;}};
  }
  if(which==='source'){
   const r=f.segment_refs[sourcePage];
   content.innerHTML=`<span class="eyebrow">Canonical archive evidence</span><dl class="source-list"><dt>Video</dt><dd>${escape(D.source_filename)}</dd><dt>Camera / location</dt><dd>${escape(r?.camera_id)} / ${escape(r?.location)}</dd><dt>Segment</dt><dd>${escape(r?.segment_id)}</dd><dt>Parent interval</dt><dd>${r?.start_sec.toFixed(2)}–${r?.end_sec.toFixed(2)} s</dd><dt>Map</dt><dd>${escape(D.scene_id)}</dd><dt>Source linkage</dt><dd>${D.source_verification?.method==='authenticated_transfer_sha256'?'Authenticated transfer, SHA-256 verified':'Verified matching archive frame'}</dd></dl><div class="pager"><button id="source-prev" ${sourcePage===0?'disabled':''}>Previous clip</button><span>${sourcePage+1} / ${f.segment_refs.length}</span><button id="source-next" ${sourcePage>=f.segment_refs.length-1?'disabled':''}>Next clip</button></div>`;
   $('source-prev').onclick=()=>{sourcePage--;tab('source');};$('source-next').onclick=()=>{sourcePage++;tab('source');};
  }
  content.querySelector('#show-frames')?.addEventListener('click',()=>tab('frames'));
 }
 document.querySelectorAll('[data-tab]').forEach(b=>{b.onclick=()=>tab(b.dataset.tab);b.onkeydown=e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();const tabs=[...document.querySelectorAll('[data-tab]')],i=tabs.indexOf(b),next=tabs[(i+(e.key==='ArrowRight'?1:tabs.length-1))%tabs.length];tab(next.dataset.tab);next.focus();}};});tab('action');
}
if(findingId&&!finding)throw new Error('This recommendation is unavailable. Return to the street story.');
function seekWhenReady(t){if(vid.readyState>=1)seek(t);else vid.addEventListener('loadedmetadata',()=>seek(t),{once:true});}
if(finding){renderReport(finding);seekWhenReady(finding.scene_time_sec);}
const initial=Number(new URLSearchParams(location.search).get('t'));if(Number.isFinite(initial)&&initial>0)seekWhenReady(initial);
window.UnfoldDemo={seek,start,sceneId:D.scene_id,findings};

} // run
run().catch(error=>{const b=document.getElementById('error-banner');b.hidden=false;b.textContent=error.message||'Demo unavailable. Refresh to retry.';document.getElementById('headline').textContent='Saved ride unavailable';});
