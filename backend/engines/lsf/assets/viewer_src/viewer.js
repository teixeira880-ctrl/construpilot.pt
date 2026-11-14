// Visualizador 3D ConstruPilot LSF — lê window.LSF (resultado do motor Python) e desenha cada perfil com a sua secção real.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const D = window.LSF || { membros: [], placas: [] };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (x, d = 1) => Number(x).toLocaleString(D.locale || 'pt-PT', { minimumFractionDigits: d, maximumFractionDigits: d });
const ACC = D.accent || '#203B2D';
document.documentElement.style.setProperty('--acc', ACC);

const COR = (tp) => {
  if (/rei|apoio/.test(tp)) return 0x2f5f8f;
  if (/curto/.test(tp)) return 0x86a9cc;
  if (/^Montante/.test(tp)) return 0x5b84ad;
  if (/Guia de verga|Verga/.test(tp)) return 0xc9772b;
  if (/peitoril/.test(tp)) return 0xb08a5a;
  if (/^Guia/.test(tp)) return 0xa9b6c3;
  if (/Bloqueador de piso/.test(tp)) return 0x7aa585;
  if (/^Bloqueador/.test(tp)) return 0x8c9aa6;
  if (/Fita/.test(tp)) return 0xc0392b;
  if (/Viga de piso/.test(tp)) return 0x4f8a5f;
  if (/bordadura/.test(tp)) return 0x96bf9d;
  if (/Banzo/.test(tp)) return 0x7a5ea8;
  if (/Diagonal/.test(tp)) return 0xa98fcf;
  return 0x888888;
};
function outline(p) {
  const { h, t } = p; const b = p.b || 0; const c = p.c || 0;
  if (p.tipo === 'C' && c > 0) return [[b, c], [b, 0], [0, 0], [0, h], [b, h], [b, h - c], [b - t, h - c], [b - t, h - t], [t, h - t], [t, t], [b - t, t], [b - t, c]];
  if (p.tipo === 'C' || p.tipo === 'U') return [[b, 0], [0, 0], [0, h], [b, h], [b, h - t], [t, h - t], [t, t], [b, t]];
  return [[0, 0], [t, 0], [t, h], [0, h]];
}

const host = $('#v3d');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.localClippingEnabled = true;
host.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf3f5f7);
const camera = new THREE.PerspectiveCamera(40, 1, 50, 500000);
camera.up.set(0, 0, 1);
scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
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
for (const k of ['estrutura', 'osb', 'gesso', 'etics', 'piso', 'cobertura']) { L[k] = new THREE.Group(); root.add(L[k]); }
const mats = new Map();
const mat = (cor, op = 1) => {
  const k = cor + '|' + op;
  if (!mats.has(k)) mats.set(k, new THREE.MeshStandardMaterial({ color: cor, metalness: op < 1 ? 0 : 0.35, roughness: op < 1 ? 0.9 : 0.45, transparent: op < 1, opacity: op, side: THREE.DoubleSide, clippingPlanes: [clip], depthWrite: op === 1 }));
  return mats.get(k);
};
const geo = new Map();
const bb = new THREE.Box3();
for (const m of D.membros) {
  const k = m.perfilNome + '|' + m.L;
  if (!geo.has(k)) geo.set(k, new THREE.ExtrudeGeometry(new THREE.Shape(outline(m.sec).map(([u, v]) => new THREE.Vector2(u, v))), { depth: m.L, bevelEnabled: false }));
  const mesh = new THREE.Mesh(geo.get(k), mat(COR(m.tipoPeca)));
  mesh.matrixAutoUpdate = false;
  mesh.matrix.set(m.u[0], m.v[0], m.w[0], m.o[0], m.u[1], m.v[1], m.w[1], m.o[1], m.u[2], m.v[2], m.w[2], m.o[2], 0, 0, 0, 1);
  mesh.userData = { m, mat: mesh.material };
  L.estrutura.add(mesh);
  bb.expandByPoint(new THREE.Vector3(...m.bbox.min)); bb.expandByPoint(new THREE.Vector3(...m.bbox.max));
}
const box = new THREE.BoxGeometry(1, 1, 1).translate(0.5, 0.5, 0.5);
for (const p of D.placas) {
  const op = p.placa === 'ETICS' ? 0.55 : /^GC/.test(p.placa) ? 0.8 : 0.88;
  const cor = p.placa === 'ETICS' ? 0xeeeeea : /^GC/.test(p.placa) ? 0xf4f1e8 : p.grupo === 'Pisos' ? 0xc79f5c : 0xd8b475;
  const g = p.placa === 'ETICS' ? L.etics : p.grupo === 'Pisos' ? L.piso : p.grupo === 'Cobertura' ? L.cobertura : /^GC/.test(p.placa) ? L.gesso : L.osb;
  const pl = p.plano;
  for (const r of p.pecas) {
    const dx = r.x1 - r.x0, dz = r.z1 - r.z0;
    let o, a, b, c;
    if (pl.tipo === 'parede') {
      o = [pl.A[0] + pl.d[0] * r.x0 + pl.n[0] * pl.y, pl.A[1] + pl.d[1] * r.x0 + pl.n[1] * pl.y, pl.z0 + r.z0];
      a = pl.d.map((x) => x * dx); b = pl.n.map((x) => x * pl.esp); c = [0, 0, dz];
    } else if (pl.tipo === 'piso') {
      o = [pl.O[0] + pl.Pd[0] * r.x0 + pl.Sd[0] * r.z0, pl.O[1] + pl.Pd[1] * r.x0 + pl.Sd[1] * r.z0, pl.z];
      a = pl.Pd.map((x) => x * dx); b = pl.Sd.map((x) => x * dz); c = [0, 0, pl.esp];
    } else {
      o = [0, 1, 2].map((i) => pl.O[i] + pl.U[i] * r.x0 + pl.Vv[i] * r.z0);
      a = pl.U.map((x) => x * dx); b = pl.Vv.map((x) => x * dz); c = pl.N.map((x) => x * pl.esp);
    }
    const mesh = new THREE.Mesh(box, mat(cor, op));
    mesh.matrixAutoUpdate = false;
    mesh.matrix.set(a[0], b[0], c[0], o[0], a[1], b[1], c[1], o[1], a[2], b[2], c[2], o[2], 0, 0, 0, 1);
    mesh.userData = { p, mat: mesh.material };
    g.add(mesh);
  }
}
function vista(t) {
  const ctr = bb.getCenter(new THREE.Vector3());
  const r = bb.getSize(new THREE.Vector3()).length() * 0.62;
  const dirs = { iso: [-1, -1.25, 0.9], frente: [0, -1, 0.12], lado: [1, 0, 0.12], topo: [0, -0.02, 1], tras: [0, 1, 0.12] };
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
// seleção
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
  sel = hit.object; sel.material = sel.userData.mat.clone(); sel.material.emissive = new THREE.Color(0xff6a00); sel.material.emissiveIntensity = 0.6;
  const m = sel.userData.m, p = sel.userData.p;
  info.hidden = false;
  info.innerHTML = m ? `<b>${esc(m.id)}</b> · ${esc(m.tipoPeca)}<br>${esc(m.perfilNome)} — <b>${fmt(m.L)} mm</b> · ${fmt(m.kg, 2)} kg${m.nota ? `<br><small>${esc(m.nota)}</small>` : ''}`
    : `<b>${esc(p.nome)}</b><br>${esc(p.ref)} · ${esc(p.face)}<br>${fmt(p.cell.x1 - p.cell.x0, 0)} × ${fmt(p.cell.z1 - p.cell.z0, 0)} mm · ${p.parafusos || 0} paraf.`;
});
const loop = () => { controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop); };
loop();
window.__lsfReady = true;
