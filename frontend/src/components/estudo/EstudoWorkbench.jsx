import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/**
 * Visualizador de estudo comum aos motores LSF, CLT e construção tradicional.
 * Lê o «modelo de estudo» do backend (engines/estudo_modelo.py) e mostra-o em oito separadores:
 * 3D, alçados, mapa de quantidades, lista de corte, planos de corte, estudo, avisos e projeto.
 * Não calcula nada: tudo o que mostra vem medido do motor.
 */
const TABS = [["3d", "3D"], ["alcados", "Alçados"], ["quantidades", "Mapa de quantidades"], ["corte", "Lista de corte"], ["planos", "Planos de corte"],
  ["estudo", "Estudo"], ["avisos", "Avisos"], ["projeto", "Projeto"]];
const fmt = (x, d = 0) => (x == null || x === "" ? "—" : Number(x).toLocaleString("pt-PT", { minimumFractionDigits: d, maximumFractionDigits: d }));
const PAGINA = 24;

function contorno(p) {
  const { h, t } = p; const b = p.b || 0; const c = p.c || 0;
  if (p.tipo === "C" && c > 0) return [[b, c], [b, 0], [0, 0], [0, h], [b, h], [b, h - c], [b - t, h - c], [b - t, h - t], [t, h - t], [t, t], [b - t, t], [b - t, c]];
  if (p.tipo === "C" || p.tipo === "U") return [[b, 0], [0, 0], [0, h], [b, h], [b, h - t], [t, h - t], [t, t], [b, t]];
  return [[0, 0], [t, 0], [t, h], [0, h]];
}

function Vista3D({ modelo }) {
  const host = useRef(null);
  const cena = useRef(null);
  const [visiveis, setVisiveis] = useState(() => Object.fromEntries((modelo.camadas || []).map((c) => [c.id, c.visivel])));
  const [info, setInfo] = useState(null);
  const [corte, setCorte] = useState(null);
  const [zMax, setZMax] = useState(0);

  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.localClippingEnabled = true;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf3f5f7);
    const camera = new THREE.PerspectiveCamera(40, 1, 50, 500000);
    camera.up.set(0, 0, 1);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
    const sol = new THREE.DirectionalLight(0xffffff, 1.6);
    sol.position.set(-8000, -14000, 20000);
    scene.add(sol);
    const grelha = new THREE.GridHelper(60000, 60, 0xc9d1d9, 0xe1e6ea);
    grelha.rotation.x = Math.PI / 2;
    scene.add(grelha);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    const plano = new THREE.Plane(new THREE.Vector3(0, 0, -1), 1e9);
    const grupos = {};
    for (const c of modelo.camadas || []) { grupos[c.id] = new THREE.Group(); scene.add(grupos[c.id]); }
    const mats = new Map();
    const mat = (cor, op) => {
      const k = `${cor}|${op}`;
      if (!mats.has(k)) {
        mats.set(k, new THREE.MeshStandardMaterial({ color: cor, metalness: op < 1 ? 0 : 0.3, roughness: op < 1 ? 0.9 : 0.5, transparent: op < 1, opacity: op,
          side: THREE.DoubleSide, clippingPlanes: [plano], depthWrite: op === 1 }));
      }
      return mats.get(k);
    };
    const geos = new Map();
    const cubo = new THREE.BoxGeometry(1, 1, 1).translate(0.5, 0.5, 0.5);
    const bb = new THREE.Box3();
    for (const s of modelo.solidos || []) {
      const g = grupos[s.camada];
      if (!g) continue;
      let mesh;
      if (s.t === "perfil") {
        const k = `${JSON.stringify(s.sec)}|${s.L}`;
        if (!geos.has(k)) geos.set(k, new THREE.ExtrudeGeometry(new THREE.Shape(contorno(s.sec).map(([u, v]) => new THREE.Vector2(u, v))), { depth: s.L, bevelEnabled: false }));
        mesh = new THREE.Mesh(geos.get(k), mat(s.cor, s.op ?? 1));
        mesh.matrix.set(s.u[0], s.v[0], s.w[0], s.o[0], s.u[1], s.v[1], s.w[1], s.o[1], s.u[2], s.v[2], s.w[2], s.o[2], 0, 0, 0, 1);
        bb.expandByPoint(new THREE.Vector3(...s.o));
        bb.expandByPoint(new THREE.Vector3(s.o[0] + s.w[0] * s.L, s.o[1] + s.w[1] * s.L, s.o[2] + s.w[2] * s.L));
      } else {
        mesh = new THREE.Mesh(cubo, mat(s.cor, s.op ?? 1));
        mesh.matrix.set(s.a[0], s.b[0], s.c[0], s.o[0], s.a[1], s.b[1], s.c[1], s.o[1], s.a[2], s.b[2], s.c[2], s.o[2], 0, 0, 0, 1);
        bb.expandByPoint(new THREE.Vector3(...s.o));
        bb.expandByPoint(new THREE.Vector3(s.o[0] + s.a[0] + s.b[0] + s.c[0], s.o[1] + s.a[1] + s.b[1] + s.c[1], s.o[2] + s.a[2] + s.b[2] + s.c[2]));
      }
      mesh.matrixAutoUpdate = false;
      mesh.userData = { info: s.info, mat: mesh.material };
      g.add(mesh);
    }
    if (bb.isEmpty()) bb.set(new THREE.Vector3(0, 0, 0), new THREE.Vector3(1000, 1000, 1000));
    const vista = (t) => {
      const ctr = bb.getCenter(new THREE.Vector3());
      const r = bb.getSize(new THREE.Vector3()).length() * 0.62;
      const dirs = { iso: [-1, -1.25, 0.9], frente: [0, -1, 0.12], lado: [1, 0, 0.12], topo: [0, -0.02, 1] };
      const d = new THREE.Vector3(...dirs[t]).normalize();
      const fit = r / Math.tan((camera.fov * Math.PI) / 360) / Math.min(1, camera.aspect || 1);
      camera.position.copy(ctr.clone().add(d.multiplyScalar(fit * 0.8)));
      controls.target.copy(ctr);
      controls.update();
    };
    const resize = () => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      renderer.setSize(r.width, r.height, false);
      renderer.domElement.style.width = `${r.width}px`;
      renderer.domElement.style.height = `${r.height}px`;
      camera.aspect = r.width / r.height;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();
    vista("iso");
    const raio = new THREE.Raycaster();
    let baixo = null;
    let sel = null;
    const onDown = (e) => { baixo = [e.clientX, e.clientY]; };
    const onUp = (e) => {
      if (!baixo || Math.hypot(e.clientX - baixo[0], e.clientY - baixo[1]) > 5) return;
      const r = renderer.domElement.getBoundingClientRect();
      raio.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
      const alvos = [];
      Object.values(grupos).forEach((g) => { if (g.visible) alvos.push(...g.children); });
      const hit = raio.intersectObjects(alvos, false).find((h) => plano.distanceToPoint(h.point) >= 0);
      if (sel) { sel.material = sel.userData.mat; sel = null; }
      if (!hit) { setInfo(null); return; }
      sel = hit.object;
      sel.material = sel.userData.mat.clone();
      sel.material.emissive = new THREE.Color(0xff6a00);
      sel.material.emissiveIntensity = 0.6;
      setInfo(sel.userData.info);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    let vivo = true;
    const ciclo = () => { if (!vivo) return; controls.update(); renderer.render(scene, camera); requestAnimationFrame(ciclo); };
    ciclo();
    const topo = Math.ceil((bb.max.z + 200) / 50) * 50;
    setZMax(topo);
    setCorte(topo);
    cena.current = { grupos, plano, vista, topo };
    return () => {
      vivo = false;
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      controls.dispose();
      geos.forEach((g) => g.dispose());
      mats.forEach((m) => m.dispose());
      cubo.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === el) el.removeChild(renderer.domElement);
      cena.current = null;
    };
  }, [modelo]);

  useEffect(() => {
    const c = cena.current;
    if (!c) return;
    Object.entries(c.grupos).forEach(([id, g]) => { g.visible = !!visiveis[id]; });
  }, [visiveis, zMax]);
  useEffect(() => {
    const c = cena.current;
    if (!c || corte == null) return;
    c.plano.constant = corte >= c.topo ? 1e9 : corte;
  }, [corte]);

  return (
    <div className="relative rounded-lg border overflow-hidden bg-[#f3f5f7]" style={{ height: "70vh", minHeight: 420 }} data-testid="estudo-3d">
      <div ref={host} className="absolute inset-0" style={{ touchAction: "none" }} />
      <details className="absolute left-3 top-3 rounded-lg border bg-white/95 px-3 py-2 text-xs max-w-[260px]" open>
        <summary className="cursor-pointer font-semibold text-muted-foreground">Camadas e vistas</summary>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 my-2">
          {(modelo.camadas || []).map((c) => (
            <label key={c.id} className="flex items-center gap-1.5">
              <input type="checkbox" checked={!!visiveis[c.id]} onChange={(e) => setVisiveis({ ...visiveis, [c.id]: e.target.checked })} />{c.nome}
            </label>
          ))}
        </div>
        <div className="text-muted-foreground">Corte · {corte == null || corte >= zMax ? "sem corte" : `z = ${fmt(corte)} mm`}</div>
        <input type="range" className="w-full" min={0} max={zMax || 1} step={50} value={corte ?? 0} onChange={(e) => setCorte(Number(e.target.value))} />
        <div className="flex flex-wrap gap-1 mt-1">
          {[["iso", "Iso"], ["frente", "Frente"], ["lado", "Lado"], ["topo", "Topo"]].map(([k, n]) => (
            <button key={k} type="button" className="rounded border bg-white px-2 py-1" onClick={() => cena.current?.vista(k)}>{n}</button>
          ))}
        </div>
      </details>
      {info && (
        <div className="absolute right-3 bottom-3 rounded-lg bg-slate-900/90 text-white px-3 py-2 text-[13px] max-w-xs" data-testid="estudo-3d-info">
          <b>{info.titulo}</b>
          {(info.linhas || []).map((l, i) => <div key={i} className="text-slate-200">{l}</div>)}
        </div>
      )}
    </div>
  );
}

function Paginas({ total, pagina, setPagina }) {
  const n = Math.ceil(total / PAGINA);
  if (n <= 1) return null;
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <button type="button" className="rounded border px-2 py-1 disabled:opacity-40" disabled={pagina === 0} onClick={() => setPagina(pagina - 1)}>Anterior</button>
      <span>{pagina + 1} de {n} · {fmt(total)} no total</span>
      <button type="button" className="rounded border px-2 py-1 disabled:opacity-40" disabled={pagina >= n - 1} onClick={() => setPagina(pagina + 1)}>Seguinte</button>
    </div>
  );
}

function Alcado({ a }) {
  const m = Math.max(a.L, a.H) * 0.02;
  return (
    <figure className="rounded-lg border bg-card p-3">
      <figcaption className="text-xs font-semibold mb-2">{a.titulo}</figcaption>
      <svg viewBox={`${-m} ${-m} ${a.L + 2 * m} ${a.H + 2 * m}`} className="w-full" style={{ maxHeight: 320 }} role="img" aria-label={a.titulo}>
        <g transform={`translate(0 ${a.H}) scale(1 -1)`}>
          <rect x={0} y={0} width={a.L} height={a.H} fill="#fafbfc" stroke="#94a3b8" strokeWidth={m * 0.12} />
          {(a.rects || []).map((r, i) => (
            <rect key={i} x={r.x} y={r.y} width={Math.max(r.w, m * 0.08)} height={Math.max(r.h, m * 0.08)} fill={r.cor || "#5b84ad"} stroke="#334155" strokeWidth={m * 0.04}>
              {r.rotulo ? <title>{r.rotulo}</title> : null}
            </rect>
          ))}
          {(a.vaos || []).map((v, i) => (
            <g key={`v${i}`} stroke="#c2410c" strokeWidth={m * 0.1} fill="none">
              <rect x={v.x} y={v.y} width={v.w} height={v.h} strokeDasharray={`${m * 0.5} ${m * 0.3}`} />
              <line x1={v.x} y1={v.y} x2={v.x + v.w} y2={v.y + v.h} /><line x1={v.x} y1={v.y + v.h} x2={v.x + v.w} y2={v.y} />
            </g>
          ))}
        </g>
      </svg>
    </figure>
  );
}

function Plano({ p }) {
  const m = Math.max(p.W, p.H) * 0.015;
  const fs = Math.max(p.W, p.H) * 0.018;
  return (
    <figure className="rounded-lg border bg-card p-3">
      <figcaption className="text-xs font-semibold mb-2 flex justify-between gap-2">
        <span>{p.titulo} · {fmt(p.W)} × {fmt(p.H)} mm</span>
        {p.aproveitamento != null && <span className="text-muted-foreground font-normal">{fmt(p.aproveitamento, 1)} % aproveitado</span>}
      </figcaption>
      <svg viewBox={`${-m} ${-m} ${p.W + 2 * m} ${p.H + 2 * m}`} className="w-full" style={{ maxHeight: 260 }} role="img" aria-label={p.titulo}>
        <rect x={0} y={0} width={p.W} height={p.H} fill="#f1f5f9" stroke="#64748b" strokeWidth={m * 0.15} />
        {p.pecas.map((q, i) => (
          <g key={i}>
            <rect x={q.x} y={q.y} width={q.w} height={q.h} fill="#d8b475" fillOpacity={0.75} stroke="#7c5a1e" strokeWidth={m * 0.1}><title>{`${q.rotulo} · ${fmt(q.w)} × ${fmt(q.h)} mm`}</title></rect>
            {q.w > fs * 4 && q.h > fs * 1.4 && <text x={q.x + q.w / 2} y={q.y + q.h / 2 + fs * 0.35} fontSize={fs} textAnchor="middle" fill="#3f2d0c">{String(q.rotulo).slice(0, 22)}</text>}
          </g>
        ))}
      </svg>
    </figure>
  );
}

function Tabela({ colunas, linhas, vazio }) {
  if (!linhas.length) return <p className="text-sm text-muted-foreground">{vazio}</p>;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-xs text-muted-foreground">
          <tr>{colunas.map((c) => <th key={c.k} className={`px-3 py-2 font-semibold ${c.num ? "text-right" : "text-left"}`}>{c.n}</th>)}</tr>
        </thead>
        <tbody>
          {linhas.map((l, i) => (
            <tr key={i} className="border-t">
              {colunas.map((c) => <td key={c.k} className={`px-3 py-1.5 ${c.num ? "text-right tabular-nums" : ""} ${c.fraco ? "text-xs text-muted-foreground" : ""}`}>{c.f ? c.f(l[c.k], l) : l[c.k]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EstudoWorkbench({ modelo }) {
  const [tab, setTab] = useState("3d");
  const [pagA, setPagA] = useState(0);
  const [pagP, setPagP] = useState(0);
  const [filtro, setFiltro] = useState("");
  const capitulos = useMemo(() => {
    const out = [];
    for (const q of modelo?.quantidades || []) {
      let g = out.find((x) => x.nome === q.capitulo);
      if (!g) { g = { nome: q.capitulo, linhas: [] }; out.push(g); }
      g.linhas.push(q);
    }
    return out;
  }, [modelo]);
  const planos = useMemo(() => (modelo?.planos_corte || []).filter((p) => !filtro || p.titulo.toLowerCase().includes(filtro.toLowerCase())), [modelo, filtro]);
  useEffect(() => { setPagP(0); }, [filtro]);
  if (!modelo) return null;
  const conta = { alcados: modelo.alcados?.length, quantidades: modelo.quantidades?.length, corte: modelo.lista_corte?.length, planos: modelo.planos_corte?.length, avisos: modelo.avisos?.length };

  return (
    <section className="rounded-xl border bg-background overflow-hidden" data-testid="estudo-workbench">
      <header className="bg-slate-900 text-white px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <b className="text-base">{modelo.titulo}</b>
          <span className="text-sm text-slate-300">{modelo.subtitulo}</span>
        </div>
        <div className="text-sm text-slate-300 tabular-nums">{(modelo.kpi || []).join(" · ")}</div>
      </header>
      <nav className="flex gap-1 overflow-x-auto border-b px-2" role="tablist">
        {TABS.map(([k, n]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`estudo-tab-${k}`}
            className={`whitespace-nowrap px-3 py-2.5 text-sm border-b-2 -mb-px ${tab === k ? "border-orange-600 font-semibold" : "border-transparent text-muted-foreground"}`}>
            {n}{conta[k] ? <span className="ml-1 text-xs text-muted-foreground">{fmt(conta[k])}</span> : null}
          </button>
        ))}
      </nav>
      <div className="p-3 space-y-3">
        {tab === "3d" && <Vista3D modelo={modelo} />}
        {tab === "alcados" && (
          <>
            {!(modelo.alcados || []).length && <p className="text-sm text-muted-foreground">Este estudo não tem alçados.</p>}
            <div className="grid gap-3 lg:grid-cols-2">{(modelo.alcados || []).slice(pagA * PAGINA, (pagA + 1) * PAGINA).map((a, i) => <Alcado key={`${pagA}-${i}`} a={a} />)}</div>
            <Paginas total={(modelo.alcados || []).length} pagina={pagA} setPagina={setPagA} />
          </>
        )}
        {tab === "quantidades" && (capitulos.length ? capitulos.map((g) => (
          <div key={g.nome} className="space-y-1">
            <h3 className="text-sm font-semibold">{g.nome}</h3>
            <Tabela vazio="" linhas={g.linhas} colunas={[{ k: "item", n: "Designação" }, { k: "qtd", n: "Quantidade", num: true, f: (v, l) => fmt(v, l.un === "un" ? 0 : 2) },
              { k: "un", n: "Un." }, { k: "nota", n: "Como foi contado", fraco: true }]} />
          </div>
        )) : <p className="text-sm text-muted-foreground">Sem quantidades.</p>)}
        {tab === "corte" && (
          <Tabela vazio="Sem lista de corte." linhas={modelo.lista_corte || []} colunas={[{ k: "grupo", n: "Material" }, { k: "peca", n: "Peça" },
            { k: "comprimento", n: "Comprimento (mm)", num: true, f: (v) => fmt(v, 0) }, { k: "largura", n: "Largura (mm)", num: true, f: (v) => fmt(v, 0) },
            { k: "espessura", n: "Espessura (mm)", num: true, f: (v) => fmt(v, 0) }, { k: "n", n: "Qtd.", num: true }]} />
        )}
        {tab === "planos" && (
          <>
            {(modelo.planos_corte || []).length > PAGINA && (
              <input className="h-9 w-full max-w-sm rounded-md border px-2 text-sm" placeholder="Filtrar por material ou chapa" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
            )}
            {!planos.length && <p className="text-sm text-muted-foreground">Sem planos de corte.</p>}
            <div className="grid gap-3 lg:grid-cols-2">{planos.slice(pagP * PAGINA, (pagP + 1) * PAGINA).map((p, i) => <Plano key={`${pagP}-${i}`} p={p} />)}</div>
            <Paginas total={planos.length} pagina={pagP} setPagina={setPagP} />
          </>
        )}
        {tab === "estudo" && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            {(modelo.estudo || []).map(([k, v]) => (
              <div key={k} className="rounded-lg border bg-card p-3"><div className="text-xs text-muted-foreground">{k}</div><div className="text-lg font-bold tabular-nums">{v}</div></div>
            ))}
          </div>
        )}
        {tab === "avisos" && ((modelo.avisos || []).length
          ? <ul className="space-y-1.5 text-sm">{modelo.avisos.map((a, i) => <li key={i} className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900">{a}</li>)}</ul>
          : <p className="text-sm text-muted-foreground">Sem avisos.</p>)}
        {tab === "projeto" && <pre className="max-h-[70vh] overflow-auto rounded-lg border bg-muted/40 p-3 text-xs">{JSON.stringify(modelo.projeto || {}, null, 2)}</pre>}
      </div>
    </section>
  );
}
