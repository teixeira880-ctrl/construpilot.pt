// Visualizador 3D ConstruPilot CLT — lê window.CLT (resultado do motor Python) e extrude cada painel com o seu contorno real e recortes.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const D = window.CLT || { paineis: [], vigas: [] };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (x, d = 1) => Number(x).toLocaleString(D.locale || 'pt-PT', { minimumFractionDigits: d, maximumFractionDigits: d });
document.documentElement.style.setProperty('--acc', D.accent || '#203B2D');
const COR = { parede: 0xd2a467, laje: 0xc08e52, cobertura: 0xa97543, empena: 0xe0bb84, viga: 0x9a6a35 };

const host = $('#v3d');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.localClippingEnabled = true;
host.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf3f5f7);
const camera = new THREE.PerspectiveCamera(40, 1, 50, 500000);
camera.up.set(0, 0, 1);
scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.5));
const sun = new THREE.DirectionalLight(0xffffff, 1.7);
sun.position.set(-8000, -14000, 20000);
scene.add(sun);
const grid = new THREE.GridHelper(60000, 60, 0xc9d1d9, 0xe1e6ea);
grid.rotation.x = Math.PI / 2;
scene.add(grid);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
const clip = new THREE.Plane(new THREE.Vector3(0, 0, -1), 1e9);
const root = new THREE.Group();
scene.add(root);
const L = {};
for (const k of ['paredes', 'lajes', 'cobertura', 'vigas']) { L[k] = new THREE.Group(); root.add(L[k]); }
const mats = new Map();
const mat = (cor) => {
  if (!mats.has(cor)) mats.set(cor, new THREE.MeshStandardMaterial({ color: cor, metalness: 0, roughness: 0.78, side: THREE.DoubleSide, clippingPlanes: [clip] }));
  return mats.get(cor);
};
const edge = new THREE.LineBasicMaterial({ color: 0x5a3d1e, clippingPlanes: [clip] });
const bb = new THREE.Box3();
const place = (obj, u, v, w, o) => {
  obj.matrixAutoUpdate = false;
  obj.matrix.set(u[0], v[0], w[0], o[0], u[1], v[1], w[1], o[1], u[2], v[2], w[2], o[2], 0, 0, 0, 1);
};
for (const p of D.paineis) {
  const sh = new THREE.Shape(p.contorno.map(([a, b]) => new THREE.Vector2(a, b)));
  for (const r of p.recortes || []) {
    const h = new THREE.Path();
    h.moveTo(r.x0, r.z0); h.lineTo(r.x1, r.z0); h.lineTo(r.x1, r.z1); h.lineTo(r.x0, r.z1); h.closePath();
    sh.holes.push(h);
  }
  const g = new THREE.ExtrudeGeometry(sh, { depth: p.esp, bevelEnabled: false });
  const mesh = new THREE.Mesh(g, mat(COR[p.tipo] || 0xc99a5b));
  place(mesh, p.u, p.v, p.w, p.o);
  mesh.userData = { p, mat: mesh.material };
  const ln = new THREE.LineSegments(new THREE.EdgesGeometry(g, 20), edge);
  place(ln, p.u, p.v, p.w, p.o);
  const grp = p.tipo === 'parede' ? L.paredes : p.tipo === 'laje' ? L.lajes : L.cobertura;
  grp.add(mesh); grp.add(ln);
  mesh.updateMatrixWorld(true);
  g.computeBoundingBox();
  bb.union(g.boundingBox.clone().applyMatrix4(mesh.matrix));
}
const box = new THREE.BoxGeometry(1, 1, 1).translate(0.5, 0.5, 0.5);
for (const v of D.vigas || []) {
  const mesh = new THREE.Mesh(box, mat(COR.viga));
  const z = [0, 0, 1];
  place(mesh, v.eixo.map((x) => x * v.L), v.lado.map((x) => x * v.b), z.map((x) => x * v.h), v.o);
  mesh.userData = { v, mat: mesh.material };
  L.vigas.add(mesh);
}
function vista(t) {
  const ctr = bb.getCenter(new THREE.Vector3());
  const r = bb.getSize(new THREE.Vector3()).length() * 0.62;
  const dirs = { iso: [-1, -1.25, 0.9], frente: [0, -1, 0.12], lado: [1, 0, 0.12], topo: [0, -0.02, 1] };
  const d = new THREE.Vector3(...dirs[t]).normalize();
  const fit = r / Math.tan((camera.fov * Math.PI) / 360) / Math.min(1, camera.aspect || 1);
  camera.position.copy(ctr.clone().add(d.multiplyScalar(fit * 0.8)));
  controls.target.copy(ctr); controls.update();
}
const resize = () => {
  const r = host.getBoundingClientRect();
  if (!r.width || !r.height) return;
  renderer.setSize(r.width, r.height, false);
  renderer.domElement.style.width = r.width + 'px'; renderer.domElement.style.height = r.height + 'px';
  camera.aspect = r.width / r.height; camera.updateProjectionMatrix();
};
new ResizeObserver(resize).observe(host); resize();
const camadas = () => { for (const k in L) L[k].visible = $('#cam-' + k)?.checked ?? true; };
camadas();
const corte = $('#corte');
const mx = Math.ceil((bb.max.z + 200) / 50) * 50;
corte.max = mx; corte.value = mx;
const aplicaCorte = () => { const v = +corte.value; clip.constant = v >= mx ? 1e9 : v; $('#corteVal').textContent = v >= mx ? (D.txt?.semCorte || 'sem corte') : `z = ${fmt(v, 0)} mm`; };
corte.oninput = aplicaCorte; aplicaCorte();
if (innerWidth < 760) $('#ctrl').open = false;
vista('iso');
document.addEventListener('change', (e) => { if (e.target.matches('.camadas input')) camadas(); });
document.addEventListener('click', (e) => { const b = e.target.closest('[data-vista]'); if (b) vista(b.dataset.vista); });
const ray = new THREE.Raycaster();
let down = null, sel = null;
renderer.domElement.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', (e) => {
  if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
  const r = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
  const vis = []; root.traverse((o) => { if (o.isMesh && o.parent.visible) vis.push(o); });
  const hit = ray.intersectObjects(vis, false).find((h) => clip.distanceToPoint(h.point) >= 0);
  if (sel) { sel.material = sel.userData.mat; sel = null; }
  const info = $('#info');
  if (!hit) { info.hidden = true; return; }
  sel = hit.object; sel.material = sel.userData.mat.clone(); sel.material.emissive = new THREE.Color(0xff6a00); sel.material.emissiveIntensity = 0.5;
  const p = sel.userData.p, v = sel.userData.v;
  info.hidden = false;
  info.innerHTML = p ? `<b>${esc(p.id)}</b> · ${esc(p.tipoNome)}<br>${esc(p.painel)} (${esc(p.camadasTxt)} mm) — <b>${fmt(p.L, 0)} × ${fmt(p.H, 0)} mm</b><br>${fmt(p.volLiq, 3)} m³ · ${fmt(p.kg, 0)} kg${p.recortes?.length ? ` · ${p.recortes.length} recorte(s)` : ''}${p.nota ? `<br><small>${esc(p.nota)}</small>` : ''}`
    : `<b>${esc(v.nome)}</b><br>${fmt(v.L, 0)} mm · ${fmt(v.m3, 3)} m³`;
});
const loop = () => { controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop); };
loop();
window.__cltReady = true;
