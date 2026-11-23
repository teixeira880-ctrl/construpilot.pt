import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Armchair, Car, Copy, DoorOpen, Download, Eraser, Layers, Loader2, Maximize2, Minimize2, MousePointer2, PenLine, RectangleHorizontal, Redo2, RotateCcw, Ruler, Save, Square, StickyNote, Trash2, TrendingUp, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import Estudio3D from "@/components/licenciamento/Estudio3D";
import * as G from "@/components/licenciamento/estudioGeo";

/**
 * Estúdio de Projeto — um único modelo do edifício (paredes multicamada, vãos ligados às paredes, pisos, cobertura).
 * Desenha-se em planta; o 3D, os alçados, os cortes e as medições são calculados pelo servidor a partir do mesmo modelo.
 */

const FERRAMENTAS = [
  ["selecionar", "Selecionar", MousePointer2], ["parede", "Parede", PenLine], ["sala", "Sala", RectangleHorizontal], ["porta", "Porta", DoorOpen],
  ["janela", "Janela", Square], ["portada", "Portada", Layers], ["portao", "Portão", Car], ["escada", "Escada", TrendingUp],
  ["objeto", "Mobiliário", Armchair], ["cota", "Cota", Ruler], ["nota", "Nota", StickyNote], ["apagar", "Apagar", Eraser],
];
const COB = { plana: "Plana", uma_agua: "Uma água", duas_aguas: "Duas águas", quatro_aguas: "Quatro águas" };
const LADOS = { frente: "Frente", tardoz: "Tardoz", esquerda: "Esquerda", direita: "Direita" };
const ALTURA_2D = 470;
const DICA = {
  parede: "Clique para marcar pontos; escreva o comprimento e Enter para uma medida exata; Esc termina. O cursor cola a pontas, eixos e à grelha de 5 cm.",
  sala: "Clique num canto e depois no canto oposto: as quatro paredes são criadas de uma vez.",
  objeto: "Escolha a peça no painel e clique na planta para a colocar. R roda 90°; as setas deslocam 5 cm.",
  cota: "Clique em dois pontos para os cotar. A cota aparece nas plantas, no PDF e no DXF.",
  nota: "Clique no sítio da nota e escreva o texto.",
};

function Campo({ rotulo, children }) {
  return <label className="block text-xs text-muted-foreground">{rotulo}<div className="mt-0.5">{children}</div></label>;
}

function Num({ valor, onChange, passo = 0.05, min = 0, ...resto }) {
  const [txt, setTxt] = useState(String(valor ?? ""));
  useEffect(() => { setTxt(String(valor ?? "")); }, [valor]);
  const confirmar = () => {
    const v = Number(String(txt).replace(",", "."));
    if (Number.isFinite(v) && v >= min) onChange(v); else setTxt(String(valor ?? ""));
  };
  return <Input className="h-8" inputMode="decimal" step={passo} value={txt} onChange={(e) => setTxt(e.target.value)} onBlur={confirmar}
    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); confirmar(); } }} {...resto} />;
}

// Texto confirmado ao sair do campo ou com Enter (não grava a cada letra)
function Texto({ valor, onChange, ...resto }) {
  const [txt, setTxt] = useState(valor ?? "");
  useEffect(() => { setTxt(valor ?? ""); }, [valor]);
  const confirmar = () => { const v = txt.trim(); if (v && v !== valor) onChange(v); else setTxt(valor ?? ""); };
  return <Input className="h-8" maxLength={40} value={txt} onChange={(e) => setTxt(e.target.value)} onBlur={confirmar}
    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.currentTarget.blur(); } }} {...resto} />;
}

function Sel({ valor, onChange, opcoes, ...resto }) {
  return (
    <select className="w-full border rounded h-8 px-2 bg-background text-sm text-foreground" value={valor} onChange={(e) => onChange(e.target.value)} {...resto}>
      {opcoes.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
    </select>
  );
}

// Lista de acabamentos agrupada (fachadas, coberturas, caixilharias, pavimentos…), com a cor de cada opção ao lado.
function SelAcabamento({ valor, onChange, lista, herdado = null, ...resto }) {
  // `herdado` (acabamento da casa) acrescenta a opção vazia «como a casa» — usada nas escolhas divisão a divisão
  const grupos = [...new Set(lista.map((x) => x.grupo))];
  const atual = lista.find((x) => x.id === valor);
  return (
    <div className="flex items-center gap-2">
      <span className="h-6 w-6 rounded border shrink-0" style={{ background: atual?.cor || herdado?.cor || "#fff" }} />
      <select className="w-full border rounded h-8 px-2 bg-background text-sm text-foreground min-w-0" value={atual ? valor : ""} onChange={(e) => onChange(e.target.value)} {...resto}>
        {herdado ? <option value="">Como a casa — {herdado.nome}</option> : !atual && <option value="">—</option>}
        {grupos.map((g) => <optgroup key={g} label={g}>{lista.filter((x) => x.grupo === g).map((x) => <option key={x.id} value={x.id}>{x.nome}</option>)}</optgroup>)}
      </select>
    </div>
  );
}

// Biblioteca de materiais para as camadas: pesquisa por nome, filtro por categoria, espessuras de catálogo de cada um.
function SeletorMaterial({ biblioteca, categorias, onEscolher, onFechar }) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const limpa = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const termo = limpa(q.trim());
  const lista = biblioteca.filter((m) => (!cat || m.categoria === cat) && (!termo || limpa(m.nome).includes(termo)));
  return (
    <div className="border rounded p-2 space-y-2 bg-background" data-testid="estudio-materiais">
      <div className="flex gap-2">
        <Input className="h-8" placeholder="Procurar material…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus data-testid="estudio-materiais-pesquisa" />
        <Button size="sm" variant="ghost" onClick={onFechar}>Fechar</Button>
      </div>
      <Sel valor={cat} onChange={setCat} opcoes={[["", `Todas as categorias (${biblioteca.length} materiais)`], ...categorias.map((c) => [c, c])]} />
      <div className="max-h-64 overflow-auto divide-y">
        {lista.map((m) => (
          <button type="button" key={m.id} className="w-full text-left py-1.5 px-1 hover:bg-muted flex items-center gap-2" onClick={() => onEscolher(m)} data-material={m.id}>
            <span className="h-4 w-4 rounded-sm border shrink-0" style={{ background: m.cor }} />
            <span className="min-w-0"><span className="block text-xs text-foreground">{m.nome}</span>
              <span className="block text-[10px] text-muted-foreground">{m.categoria}{m.espessuras_cm.length ? ` · ${m.espessuras_cm.filter((e) => e > 0).map((e) => String(e).replace(".", ",")).join(" / ")} cm` : ""}</span></span>
          </button>
        ))}
        {!lista.length && <p className="text-xs text-muted-foreground p-2">Nenhum material com esse nome. Pode escrever o nome à mão na camada.</p>}
      </div>
    </div>
  );
}

function EditorCamadas({ tipo, usos, catalogo, onMudar }) {
  const [aberta, setAberta] = useState(null);       // índice da camada cujo material está a ser escolhido
  const camadas = tipo.camadas;
  const muda = (i, patch) => onMudar({ ...tipo, camadas: camadas.map((c, k) => (k === i ? { ...c, ...patch } : c)) });
  const porNome = (nome) => catalogo.biblioteca.find((m) => m.nome === nome);
  return (
    <div className="space-y-2 border rounded p-2" data-testid="estudio-camadas">
      <Campo rotulo="Nome da parede"><Input className="h-8" value={tipo.nome} onChange={(e) => onMudar({ ...tipo, nome: e.target.value.slice(0, 80) })} /></Campo>
      <label className="text-xs flex items-center gap-2"><input type="checkbox" checked={!!tipo.exterior} onChange={(e) => onMudar({ ...tipo, exterior: e.target.checked })} />Parede exterior</label>
      <p className="text-[11px] text-muted-foreground">Camadas do interior para o exterior. Usada em {usos} parede(s).</p>
      {camadas.map((c, i) => {
        const m = porNome(c.material);
        return (
          <div key={i} className="space-y-1 border-t pt-2">
            <div className="flex items-center gap-1">
              <span className="h-4 w-4 rounded-sm border shrink-0" style={{ background: m?.cor || "#ddd" }} />
              <button type="button" className="text-xs text-left underline decoration-dotted min-w-0 flex-1" onClick={() => setAberta(aberta === i ? null : i)} data-testid={`estudio-camada-material-${i}`}>{c.material}</button>
              <button type="button" className="text-muted-foreground disabled:opacity-30" disabled={camadas.length <= 1} title="Remover camada"
                onClick={() => { setAberta(null); onMudar({ ...tipo, camadas: camadas.filter((_, k) => k !== i) }); }}><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
            <div className="flex items-center gap-1 flex-wrap">
              <div className="w-20"><Num valor={Math.round(c.esp_m * 1e4) / 100} min={0.01} onChange={(x) => muda(i, { esp_m: Math.round(x * 100) / 1e4 })} /></div>
              <span className="text-[11px] text-muted-foreground">cm</span>
              {(m?.espessuras_cm || []).filter((e) => e > 0).slice(0, 8).map((e) => (
                <button type="button" key={e} className={`text-[10px] border rounded px-1 ${Math.abs(c.esp_m * 100 - e) < 1e-6 ? "bg-muted" : ""}`} onClick={() => muda(i, { esp_m: Math.round(e * 100) / 1e4 })}>{String(e).replace(".", ",")}</button>
              ))}
            </div>
            {aberta === i && <SeletorMaterial biblioteca={catalogo.biblioteca} categorias={catalogo.categorias} onFechar={() => setAberta(null)}
              onEscolher={(nm) => { const e = nm.espessuras_cm.find((x) => x > 0); muda(i, { material: nm.nome, ...(e ? { esp_m: Math.round(e * 100) / 1e4 } : {}) }); setAberta(null); }} />}
          </div>
        );
      })}
      <Button size="sm" variant="outline" disabled={camadas.length >= 8} data-testid="estudio-camada-nova"
        onClick={() => { onMudar({ ...tipo, camadas: [...camadas, { material: "Reboco tradicional de cimento e areia", esp_m: 0.015 }] }); setAberta(camadas.length); }}>+ Camada</Button>
      <div className="text-xs">Espessura total <b>{G.fmt(G.espessuraTipo(tipo) * 100, 1)} cm</b></div>
    </div>
  );
}

// Desenho calculado pelo servidor (SVG mostrado como imagem: nenhum script do SVG é executado).
function Desenho({ modelo, params, ativo }) {
  const [url, setUrl] = useState(null);
  const [erro, setErro] = useState("");
  const chave = JSON.stringify(params);
  useEffect(() => {
    if (!ativo) return undefined;
    let vivo = true, u = null;
    const t = setTimeout(() => {
      api.post("/estudio-projeto/desenho.svg", { modelo, ...params }, { responseType: "blob", timeout: 60000 })
        .then((r) => { if (!vivo) return; u = URL.createObjectURL(new Blob([r.data], { type: "image/svg+xml" })); setUrl(u); setErro(""); })
        .catch(() => { if (vivo) setErro("Não foi possível gerar este desenho com o modelo atual."); });
    }, 350);
    return () => { vivo = false; clearTimeout(t); if (u) setTimeout(() => URL.revokeObjectURL(u), 3000); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelo, chave, ativo]);
  if (erro) return <p className="text-sm text-amber-700 p-4">{erro}</p>;
  return url ? <img src={url} alt="Peça desenhada do Estúdio" className="w-full bg-white rounded border" data-testid="estudio-desenho" />
    : <div className="w-full aspect-[16/11] bg-muted animate-pulse rounded" />;
}

function Medicoes({ md }) {
  if (!md) return null;
  const n = G.fmt;
  const T = ({ cab, linhas }) => (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead><tr className="text-left text-muted-foreground border-b">{cab.map((c) => <th key={c} className="py-1 pr-3 font-medium whitespace-nowrap">{c}</th>)}</tr></thead>
        <tbody>{linhas.map((l, i) => <tr key={i} className="border-b last:border-0">{l.map((c, j) => <td key={j} className="py-1 pr-3 whitespace-nowrap">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
  return (
    <div className="space-y-4" data-testid="estudio-medicoes">
      <p className="text-xs text-muted-foreground">{md.convencao}</p>
      <div className="grid sm:grid-cols-4 gap-2 text-sm">
        <div className="border rounded p-2"><div className="text-xs text-muted-foreground">Área bruta de construção</div><b>{n(md.totais.area_bruta_construcao_m2)} m²</b></div>
        <div className="border rounded p-2"><div className="text-xs text-muted-foreground">Área útil</div><b>{n(md.totais.area_util_m2)} m²</b></div>
        <div className="border rounded p-2"><div className="text-xs text-muted-foreground">Fachada (líquida)</div><b>{n(md.fachada.area_liquida_m2)} m²</b></div>
        <div className="border rounded p-2"><div className="text-xs text-muted-foreground">Cobertura (área real)</div><b>{n(md.cobertura.area_m2)} m²</b></div>
      </div>
      {md.quadro_areas && <div><div className="font-medium text-sm mb-1">Quadro de áreas</div>
        <T cab={["Piso", "Área bruta (m²)", "Área útil (m²)", "Divisões", "Paredes e vazios (m²)"]}
          linhas={[...md.quadro_areas.map((q) => [q.piso, n(q.area_bruta_m2), n(q.area_util_m2), q.n_divisoes, n(q.paredes_e_vazios_m2)]),
            ["Área de implantação", n(md.area_implantacao_m2), "—", "—", "—"]]} /></div>}
      {md.mapa_vaos?.length > 0 && <div data-testid="estudio-mapa-vaos"><div className="font-medium text-sm mb-1">Mapa de vãos (o código é o que aparece na planta)</div>
        <T cab={["Código", "Tipo", "Modelo", "Largura", "Altura", "Peitoril", "Caixilharia", "Proteção", "Ext.", "Qtd.", "Área (m²)"]}
          linhas={md.mapa_vaos.map((v) => [v.codigo, v.tipo, v.modelo, n(v.largura_m, 3), n(v.altura_m, 3), n(v.peitoril_m), v.caixilharia, v.protecao, v.exterior ? "sim" : "não", v.quantidade, n(v.area_m2)])} /></div>}
      {md.objetos?.length > 0 && <div><div className="font-medium text-sm mb-1">Equipamento e mobiliário</div>
        <T cab={["Peça", "Categoria", "Qtd."]} linhas={md.objetos.map((o) => [o.nome, o.categoria, o.quantidade])} /></div>}
      <div><div className="font-medium text-sm mb-1">Camadas por tipo de parede</div>
        <T cab={["Tipo", "Camada", "Esp. (m)", "Área (m²)", "Volume (m³)"]}
          linhas={md.por_tipo.flatMap((t) => t.camadas.map((c) => [t.nome, c.material, n(c.esp_m, 3), n(c.area_m2), n(c.volume_m3, 3)]))} /></div>
      <div><div className="font-medium text-sm mb-1">Paredes, uma a uma (identificador igual ao da planta)</div>
        <T cab={["Parede", "Piso", "Comp. eixo", "Comp. líquido", "Altura", "Bruta (m²)", "Vãos (m²)", "Líquida (m²)"]}
          linhas={md.paredes.map((p) => [p.id, p.piso, n(p.comprimento_eixo_m), n(p.comprimento_liquido_m), n(p.altura_m), n(p.area_bruta_m2), n(p.area_vaos_m2), n(p.area_liquida_m2)])} /></div>
      <div><div className="font-medium text-sm mb-1">Divisões</div>
        <T cab={["Divisão", "Piso", "Área útil (m²)", "Perímetro (m)", "Paredes (m²)", "Rodapé (m)", "Pavimento", "Paredes", "Teto"]}
          linhas={md.divisoes.map((d) => [d.nome, d.piso, n(d.area_m2), n(d.perimetro_m), n(d.area_paredes_m2), n(d.rodape_m), d.pavimento, d.parede_interior, d.teto])} /></div>
      {md.acabamentos && <div><div className="font-medium text-sm mb-1">Acabamentos escolhidos</div>
        <T cab={["Elemento", "Material", "Área (m²)"]} linhas={md.acabamentos.map((a) => [a.elemento, a.material, n(a.area_m2)])} /></div>}
      {md.escadas?.length > 0 && <div><div className="font-medium text-sm mb-1">Escadas</div>
        <T cab={["Escada", "Piso", "Tipo", "Espelhos", "Espelho (cm)", "Cobertor (cm)", "Largura (m)", "2e + c (m)", "Em planta (m²)", "Vazio (m²)"]}
          linhas={md.escadas.map((e) => [e.id, e.piso, { reta: "Reta", l: "Em L", u: "Em U" }[e.tipo], e.n_espelhos, n(e.espelho_m * 100, 1), n(e.cobertor_m * 100, 1),
            n(e.largura_m), n(e.blondel_m), n(e.area_planta_m2), n(e.vazio_m2)])} />
        <p className="text-xs text-muted-foreground mt-1">{md.regra_vazio_escada}</p></div>}
      <div className="grid md:grid-cols-2 gap-4">
        <div><div className="font-medium text-sm mb-1">Vãos</div>
          <T cab={["Tipo", "Largura", "Altura", "Qtd.", "Área (m²)"]} linhas={md.vaos.map((v) => [v.tipo, n(v.largura_m, 3), n(v.altura_m, 3), v.quantidade, n(v.area_m2)])} /></div>
        <div><div className="font-medium text-sm mb-1">Lajes e cobertura</div>
          <T cab={["Elemento", "Área (m²)", "Esp. (m)", "Volume (m³)"]}
            linhas={[...md.lajes.map((l) => [l.nome, n(l.area_m2), n(l.espessura_m), n(l.volume_m3, 3)]),
              ...md.terracos.map((t) => [`Terraço sobre ${t.sobre}`, n(t.area_m2), "—", "—"]),
              [`Cobertura (${COB[md.cobertura.tipo]}, ${n(md.cobertura.inclinacao_graus, 1)}°)`, n(md.cobertura.area_m2), "—", "—"],
              ["Empenas", n(md.cobertura.empenas_m2), "—", "—"]]} /></div>
      </div>
    </div>
  );
}

export default function EstudioProjeto({ pid }) {
  const [modelo, setModelo] = useState(null);
  const [derivado, setDerivado] = useState(null);
  const [info, setInfo] = useState(null);
  const [erro, setErro] = useState("");
  const [ferramenta, setFerramenta] = useState("selecionar");
  const [piso, setPiso] = useState(null);
  const [sel, setSel] = useState(null);                 // { tipo: "parede" | "vao", id }
  const [tipoParede, setTipoParede] = useState("ext_30");
  const [inicio, setInicio] = useState(null);           // ponto de partida da parede em curso
  const [cursor, setCursor] = useState(null);
  const [sujo, setSujo] = useState(false);
  const [aGuardar, setAGuardar] = useState(false);
  const [aba, setAba] = useState("3d");
  const [lado, setLado] = useState("frente");
  const [eixo, setEixo] = useState("x");
  const [grande, setGrande] = useState(false);
  const [interior, setInterior] = useState(false);
  const [aEditarCamadas, setAEditarCamadas] = useState(false);
  const [tipoObjeto, setTipoObjeto] = useState("sofa_3");
  const [catObjeto, setCatObjeto] = useState("");
  const [compTxt, setCompTxt] = useState("");           // comprimento escrito à mão enquanto se desenha uma parede
  const [posCorte, setPosCorte] = useState(null);       // posição do plano de corte (null = a meio)
  const [difs, setDifs] = useState(null);
  const [aLevar, setALevar] = useState(false);
  const refazerPilha = useRef([]);
  const [vista, setVista] = useState({ cx: 5, cy: 4, esc: 40 });
  const [largura, setLargura] = useState(700);
  const historia = useRef([]);
  const arrasto = useRef(null);
  const caixa = useRef(null);
  const svgRef = useRef(null);
  const seq = useRef(0);

  const enquadrar = useCallback((m, p, w) => {
    const [x0, y0, x1, y1] = G.limitesModelo(m, p);
    const esc = Math.max(8, Math.min(90, Math.min((w - 80) / Math.max(x1 - x0, 4), (ALTURA_2D - 90) / Math.max(y1 - y0, 3))));
    setVista({ cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, esc });
  }, []);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      const { data } = await api.get(`/estudio-projeto/processos/${pid}`);
      setModelo(data.modelo); setDerivado(data.derivado); setInfo(data);
      setPiso(data.modelo.pisos[0].id); setSujo(false); setSel(null); setInicio(null);
      historia.current = []; refazerPilha.current = []; setDifs(null);
      enquadrar(data.modelo, data.modelo.pisos[0].id, caixa.current?.clientWidth || 700);
    } catch (e) { setErro(e?.response?.data?.detail || "Não foi possível abrir o Estúdio de Projeto."); }
  }, [pid, enquadrar]);
  useEffect(() => { carregar(); }, [carregar]);

  useEffect(() => {
    const el = caixa.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setLargura(el.clientWidth || 700));
    ro.observe(el);
    return () => ro.disconnect();
  }, [modelo === null]);

  // qualquer alteração → o servidor recalcula tudo do mesmo modelo (pequeno atraso para não pedir a cada movimento)
  useEffect(() => {
    if (!modelo || !sujo) return undefined;
    const n = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const { data } = await api.post("/estudio-projeto/derivar", { modelo });
        if (n === seq.current) { setDerivado(data.derivado); setErro(""); }
      } catch (e) { if (n === seq.current) setErro(e?.response?.data?.detail || "O modelo não pôde ser calculado."); }
    }, 260);
    return () => clearTimeout(t);
  }, [modelo, sujo]);

  const aplicar = useCallback((novo, registar = true) => {
    setModelo((atual) => {
      if (novo === atual) return atual;
      if (registar) { historia.current.push(atual); if (historia.current.length > 60) historia.current.shift(); refazerPilha.current = []; }
      return novo;
    });
    setSujo(true);
  }, []);
  const anular = () => { const ant = historia.current.pop(); if (ant) { refazerPilha.current.push(modelo); setModelo(ant); setSujo(true); setSel(null); } };
  const refazer = () => { const seg = refazerPilha.current.pop(); if (seg) { historia.current.push(modelo); setModelo(seg); setSujo(true); setSel(null); } };

  const objCat = useMemo(() => Object.fromEntries((info?.catalogo?.objetos || []).map((o) => [o.id, o])), [info]);
  const paredesPiso = useMemo(() => (modelo ? modelo.paredes.filter((w) => w.piso === piso) : []), [modelo, piso]);
  const derPorId = useMemo(() => Object.fromEntries((derivado?.paredes || []).map((w) => [w.id, w])), [derivado]);
  const esp = useCallback((w) => G.espessuraTipo(modelo.tipos_parede[w.tipo]) || 0.2, [modelo]);

  const H2 = grande ? Math.max(ALTURA_2D, (typeof window !== "undefined" ? window.innerHeight : 800) - 330) : ALTURA_2D;
  const mundo = useCallback((ev) => {
    const r = svgRef.current.getBoundingClientRect();
    return [vista.cx + (ev.clientX - r.left - r.width / 2) / vista.esc, vista.cy - (ev.clientY - r.top - r.height / 2) / vista.esc];
  }, [vista]);
  const ecra = (p) => [largura / 2 + (p[0] - vista.cx) * vista.esc, H2 / 2 - (p[1] - vista.cy) * vista.esc];

  const centroVao = (v) => {
    const w = modelo.paredes.find((x) => x.id === v.parede);
    if (!w) return null;
    const { u, n } = G.geoParede(w);
    return { w, u, n, c: [w.a[0] + u[0] * v.pos_m, w.a[1] + u[1] * v.pos_m], t: esp(w) };
  };
  const acertar = (p) => {
    const tol = 12 / vista.esc;
    for (const v of modelo.vaos) {
      const g = centroVao(v);
      if (!g || g.w.piso !== piso) continue;
      const dx = p[0] - g.c[0], dy = p[1] - g.c[1];
      const s = dx * g.u[0] + dy * g.u[1], d = Math.abs(dx * g.n[0] + dy * g.n[1]);
      if (Math.abs(s) <= v.largura_m / 2 && d <= g.t / 2 + tol) return { tipo: "vao", id: v.id };
    }
    for (const nt of modelo.notas || []) {
      if (nt.piso === piso && Math.abs(p[0] - nt.x) <= Math.max(0.4, nt.texto.length * 3.2 / vista.esc) && Math.abs(p[1] - nt.y) <= 9 / vista.esc) return { tipo: "nota", id: nt.id };
    }
    for (const c of modelo.cotas || []) {
      if (c.piso !== piso) continue;
      const g = G.geoCota(c);
      if (G.projetar({ a: g.p, b: g.q }, p).dist <= 8 / vista.esc) return { tipo: "cota", id: c.id };
    }
    const ob = [...(modelo.objetos || [])].reverse().find((o) => o.piso === piso && objCat[o.tipo] && G.dentroPoligono(p, G.contornoObjeto(o, objCat[o.tipo]).pts));
    if (ob) return { tipo: "objeto", id: ob.id };
    // a escada antes das paredes: num compartimento estreito está sempre perto de uma parede, mas o clique foi dentro dela
    const esc = (derivado?.escadas || []).find((e) => e.piso === piso && e.contorno.some((a) => G.dentroPoligono(p, a)));
    if (esc) return { tipo: "escada", id: esc.id };
    const pr = G.paredeMaisProxima(paredesPiso, p, 0.25 + tol);
    return pr ? { tipo: "parede", id: pr.parede.id, s: pr.s } : null;
  };

  const baixar = (ev) => {
    if (!modelo) return;
    ev.currentTarget.setPointerCapture?.(ev.pointerId);
    const p = mundo(ev);
    if (ferramenta === "parede") {
      const q = G.encaixar(p, paredesPiso, inicio).ponto;
      if (!inicio) { setInicio(q); return; }
      aplicar(G.adicionarParede(modelo, piso, inicio, q, tipoParede));
      setInicio(q);
      return;
    }
    if (ferramenta === "sala") {
      const q = G.encaixar(p, paredesPiso, null).ponto;
      if (!inicio) { setInicio(q); return; }
      const m = G.adicionarSala(modelo, piso, inicio, q, tipoParede);
      if (m === modelo) toast.message("A sala tem de ter pelo menos 60 cm de lado.");
      else aplicar(m);
      setInicio(null); setCursor(null);
      return;
    }
    if (ferramenta === "cota") {
      const q = G.encaixar(p, paredesPiso, null).ponto;
      if (!inicio) { setInicio(q); return; }
      const r = G.adicionarCota(modelo, piso, inicio, q);
      if (r.id) { aplicar(r.modelo); setSel({ tipo: "cota", id: r.id }); }
      setInicio(null); setCursor(null);
      return;
    }
    if (ferramenta === "nota") {
      const r = G.adicionarNota(modelo, piso, p, window.prompt("Texto da nota (até 120 letras):", ""));
      if (r.id) { aplicar(r.modelo); setSel({ tipo: "nota", id: r.id }); }
      setFerramenta("selecionar");
      return;
    }
    if (ferramenta === "objeto") {
      if (!objCat[tipoObjeto]) return;
      const r = G.adicionarObjeto(modelo, piso, tipoObjeto, p);
      aplicar(r.modelo); setSel({ tipo: "objeto", id: r.id });
      return;
    }
    if (ferramenta === "escada") {
      if (modelo.pisos.findIndex((x) => x.id === piso) >= modelo.pisos.length - 1) {
        toast.message("A escada sobe do piso selecionado para o de cima: adicione primeiro o piso de cima.");
        return;
      }
      const r = G.adicionarEscada(modelo, piso, p);
      aplicar(r.modelo); setSel({ tipo: "escada", id: r.id }); setFerramenta("selecionar");
      return;
    }
    if (["porta", "janela", "portada", "portao"].includes(ferramenta)) {
      const pr = G.paredeMaisProxima(paredesPiso, p, 0.7);
      if (!pr) { toast.message("Clique sobre uma parede para colocar o vão."); return; }
      const r = G.adicionarVao(modelo, pr.parede, pr.s, ferramenta, info.catalogo.vaos[ferramenta]);
      if (!r) { toast.message("Este vão não cabe nesta parede."); return; }
      aplicar(r.modelo); setSel({ tipo: "vao", id: r.id });
      return;
    }
    if (sel?.tipo === "parede") {      // pegas das pontas da parede selecionada
      const w = modelo.paredes.find((x) => x.id === sel.id);
      for (const ponta of ["a", "b"]) {
        if (w && Math.hypot(p[0] - w[ponta][0], p[1] - w[ponta][1]) <= 12 / vista.esc) {
          arrasto.current = { tipo: "ponta", id: w.id, ponta, antes: modelo }; return;
        }
      }
    }
    const alvo = acertar(p);
    if (ferramenta === "apagar") {
      if (alvo?.tipo === "vao") aplicar(G.removerVao(modelo, alvo.id));
      else if (alvo) aplicar(removerAlvo(alvo));
      setSel(null);
      return;
    }
    if (alvo) {
      // arrastar o corpo de uma parede já selecionada desloca-a (as paredes que nela tocam esticam)
      if (alvo.tipo === "parede" && sel?.tipo === "parede" && sel.id === alvo.id) arrasto.current = { tipo: "parede", id: alvo.id, antes: modelo, p0: p };
      setSel({ tipo: alvo.tipo, id: alvo.id });
      if (alvo.tipo === "objeto") {
        const o = modelo.objetos.find((x) => x.id === alvo.id);
        arrasto.current = { tipo: "objeto", id: alvo.id, antes: modelo, dx: p[0] - o.x, dy: p[1] - o.y };
      }
      if (alvo.tipo === "nota") {
        const o = modelo.notas.find((x) => x.id === alvo.id);
        arrasto.current = { tipo: "nota", id: alvo.id, antes: modelo, dx: p[0] - o.x, dy: p[1] - o.y };
      }
      if (alvo.tipo === "vao") arrasto.current = { tipo: "vao", id: alvo.id, antes: modelo };
      if (alvo.tipo === "escada") {
        const e = modelo.escadas.find((x) => x.id === alvo.id);
        arrasto.current = { tipo: "escada", id: alvo.id, antes: modelo, dx: p[0] - e.x, dy: p[1] - e.y };
      }
    } else {
      // clique dentro de uma divisão seleciona-a (guarda-se o ponto: as divisões são recalculadas a cada alteração)
      const dv = (derivado?.divisoes || []).find((d) => d.piso === piso && G.dentroPoligono(p, d.pts));
      setSel(dv ? { tipo: "divisao", pt: p } : null);
      arrasto.current = { tipo: "pan", x: ev.clientX, y: ev.clientY, cx: vista.cx, cy: vista.cy };
    }
  };

  const mover = (ev) => {
    if (!modelo) return;
    const p = mundo(ev);
    const a = arrasto.current;
    if (a?.tipo === "pan") {
      setVista((v) => ({ ...v, cx: a.cx - (ev.clientX - a.x) / v.esc, cy: a.cy + (ev.clientY - a.y) / v.esc }));
      return;
    }
    if (a?.tipo === "ponta") {
      const w = modelo.paredes.find((x) => x.id === a.id);
      const fixo = a.ponta === "a" ? w.b : w.a;
      const q = G.encaixar(p, paredesPiso, fixo, a.id).ponto;
      if (Math.hypot(q[0] - fixo[0], q[1] - fixo[1]) >= 0.1) aplicar(G.mudarParede(modelo, a.id, { [a.ponta]: q }), false);
      return;
    }
    if (a?.tipo === "parede") {
      const w = a.antes.paredes.find((x) => x.id === a.id);
      const { n } = G.geoParede(w);
      const d = G.arred((p[0] - a.p0[0]) * n[0] + (p[1] - a.p0[1]) * n[1]);
      const novo = G.moverParede(a.antes, a.id, G.r3(n[0] * d), G.r3(n[1] * d));
      const wn = novo.paredes.find((x) => x.id === a.id), wa = modelo.paredes.find((x) => x.id === a.id);
      if (wa && (wn.a[0] !== wa.a[0] || wn.a[1] !== wa.a[1])) aplicar(novo, false);
      return;
    }
    if (a?.tipo === "objeto" || a?.tipo === "nota") {
      const x = G.r3(G.arred(p[0] - a.dx)), y = G.r3(G.arred(p[1] - a.dy));
      const lista = a.tipo === "objeto" ? modelo.objetos : modelo.notas;
      const o = (lista || []).find((k) => k.id === a.id);
      if (o && (o.x !== x || o.y !== y)) aplicar(a.tipo === "objeto" ? G.mudarObjeto(modelo, a.id, { x, y }) : G.mudarNota(modelo, a.id, { x, y }), false);
      return;
    }
    if (a?.tipo === "escada") {
      const x = G.r3(G.arred(p[0] - a.dx)), y = G.r3(G.arred(p[1] - a.dy));
      const e = modelo.escadas.find((k) => k.id === a.id);
      if (e && (e.x !== x || e.y !== y)) aplicar(G.mudarEscada(modelo, a.id, { x, y }), false);
      return;
    }
    if (a?.tipo === "vao") {
      const v = modelo.vaos.find((x) => x.id === a.id);
      const w = v && modelo.paredes.find((x) => x.id === v.parede);
      if (w) {
        const pos = G.posicaoVao(modelo, w, G.projetar(w, p).s, v.largura_m, v.id);
        if (pos != null && pos !== v.pos_m) aplicar(G.mudarVao(modelo, v.id, { pos_m: pos }), false);
      }
      return;
    }
    if (ferramenta === "parede") setCursor(G.encaixar(p, paredesPiso, inicio));
    else if (ferramenta === "sala" || ferramenta === "cota") setCursor(G.encaixar(p, paredesPiso, null));
    else if (ferramenta === "objeto") setCursor({ ponto: [G.r3(G.arred(p[0])), G.r3(G.arred(p[1]))], tipo: "grelha" });
    else setCursor(null);
  };

  const largar = () => {
    const a = arrasto.current;
    if (a?.antes && a.antes !== modelo) { historia.current.push(a.antes); }
    arrasto.current = null;
  };

  useEffect(() => {       // zoom com a roda, centrado no cursor (ouvinte não passivo para travar o scroll da página)
    const el = svgRef.current;
    if (!el) return undefined;
    const roda = (ev) => {
      ev.preventDefault();
      const r = el.getBoundingClientRect();
      setVista((v) => {
        const f = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
        const esc = Math.max(6, Math.min(260, v.esc * f));
        const mx = v.cx + (ev.clientX - r.left - r.width / 2) / v.esc, my = v.cy - (ev.clientY - r.top - r.height / 2) / v.esc;
        return { esc, cx: mx - (ev.clientX - r.left - r.width / 2) / esc, cy: my + (ev.clientY - r.top - r.height / 2) / esc };
      });
    };
    el.addEventListener("wheel", roda, { passive: false });
    return () => el.removeEventListener("wheel", roda);
  }, [modelo === null]);

  const removerAlvo = (a) => ({ vao: G.removerVao, escada: G.removerEscada, parede: G.removerParede, objeto: G.removerObjeto, cota: G.removerCota, nota: G.removerNota }[a.tipo] || ((m) => m))(modelo, a.id);
  const tecla = (ev) => {
    if (ev.target.tagName === "INPUT" || ev.target.tagName === "SELECT") return;
    if (ev.target.tagName === "TEXTAREA") return;
    if (ev.key === "Escape") { setInicio(null); setCursor(null); setCompTxt(""); setFerramenta("selecionar"); }
    // comprimento exato: com uma parede em curso, escrever os algarismos e Enter
    if (ferramenta === "parede" && inicio && !ev.ctrlKey && !ev.metaKey) {
      if (/^[0-9.,]$/.test(ev.key)) { ev.preventDefault(); setCompTxt((t) => (t + ev.key).slice(0, 7)); return; }
      if (ev.key === "Backspace" && compTxt) { ev.preventDefault(); setCompTxt((t) => t.slice(0, -1)); return; }
      if (ev.key === "Enter" && compTxt && cursor) {
        ev.preventDefault();
        const L = Number(compTxt.replace(",", "."));
        const dx = cursor.ponto[0] - inicio[0], dy = cursor.ponto[1] - inicio[1], d = Math.hypot(dx, dy);
        if (Number.isFinite(L) && L >= 0.1 && d > 1e-6) {
          const q = [G.r3(inicio[0] + (dx / d) * L), G.r3(inicio[1] + (dy / d) * L)];
          aplicar(G.adicionarParede(modelo, piso, inicio, q, tipoParede)); setInicio(q);
        }
        setCompTxt("");
        return;
      }
    }
    if ((ev.key === "Delete" || ev.key === "Backspace") && sel && sel.tipo !== "divisao") {
      ev.preventDefault();
      aplicar(removerAlvo(sel)); setSel(null);
    }
    if (sel?.tipo === "objeto") {
      const o = (modelo.objetos || []).find((x) => x.id === sel.id);
      const seta = { ArrowLeft: [-0.05, 0], ArrowRight: [0.05, 0], ArrowUp: [0, 0.05], ArrowDown: [0, -0.05] }[ev.key];
      if (o && seta) { ev.preventDefault(); aplicar(G.mudarObjeto(modelo, o.id, { x: G.r3(o.x + seta[0]), y: G.r3(o.y + seta[1]) })); }
      if (o && ev.key.toLowerCase() === "r" && !ev.ctrlKey && !ev.metaKey) { ev.preventDefault(); aplicar(G.mudarObjeto(modelo, o.id, { rot: ((o.rot || 0) + 90) % 360 })); }
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") { ev.preventDefault(); if (ev.shiftKey) refazer(); else anular(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "y") { ev.preventDefault(); refazer(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "s") { ev.preventDefault(); if (sujo && !aGuardar) guardar(); }
  };

  const guardar = async () => {
    setAGuardar(true);
    try {
      const { data } = await api.put(`/estudio-projeto/processos/${pid}`, { modelo });
      setDerivado(data.derivado); setSujo(false);
      setInfo((i) => ({ ...i, origem: "guardado", updated_at: data.updated_at }));
      toast.success("Modelo guardado.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar."); }
    setAGuardar(false);
  };
  const repor = async () => {
    if (!window.confirm("Repor o modelo a partir do processo? As alterações feitas no Estúdio são apagadas.")) return;
    try { await api.delete(`/estudio-projeto/processos/${pid}`); await carregar(); } catch { toast.error("Não foi possível repor."); }
  };
  const verDiferencas = useCallback(async () => {
    try { const { data } = await api.get(`/estudio-projeto/processos/${pid}/divergencias`); setDifs(data); }
    catch { setDifs({ divergencias: [], erro: "Não foi possível comparar com o processo." }); }
  }, [pid]);
  useEffect(() => { if (aba === "processo" && !sujo) verDiferencas(); }, [aba, sujo, verDiferencas]);
  const levarAcabamentos = async () => {
    setALevar(true);
    try {
      const { data } = await api.post(`/estudio-projeto/processos/${pid}/sincronizar-materiais`);
      if (data.ok) toast.success("Acabamentos levados para o processo. A memória descritiva foi refeita."); else toast.message(data.msg);
      await verDiferencas();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível levar os acabamentos."); }
    setALevar(false);
  };
  const descarregar = async (caminho, nome) => {
    try {
      const r = await api.get(caminho, { responseType: "blob", timeout: 180000 });
      const u = URL.createObjectURL(r.data);
      const a = document.createElement("a"); a.href = u; a.download = nome; a.click();
      setTimeout(() => URL.revokeObjectURL(u), 4000);
    } catch { toast.error("Não foi possível descarregar."); }
  };

  if (erro && !modelo) return <div className="p-6 text-sm text-amber-800" data-testid="estudio-erro">{erro}</div>;
  if (!modelo) return <div className="p-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  const idxPiso = modelo.pisos.findIndex((p) => p.id === piso);
  const pisoObj = modelo.pisos[idxPiso];
  const wSel = sel?.tipo === "parede" ? modelo.paredes.find((w) => w.id === sel.id) : null;
  const vSel = sel?.tipo === "vao" ? modelo.vaos.find((v) => v.id === sel.id) : null;
  const cat = info.catalogo;
  const noModelo = Object.entries(modelo.tipos_parede);
  const daBiblioteca = Object.entries(cat.paredes_tipo || {}).filter(([k]) => !modelo.tipos_parede[k]);
  // escolher uma parede-tipo da biblioteca copia-a para o modelo (o modelo guarda as suas próprias camadas)
  const comTipo = (m, tid) => (m.tipos_parede[tid] || !cat.paredes_tipo?.[tid] ? m : { ...m, tipos_parede: { ...m.tipos_parede, [tid]: cat.paredes_tipo[tid] } });
  const selTipo = (valor, onChange, resto = {}) => (
    <select className="w-full border rounded h-8 px-2 bg-background text-sm text-foreground" value={valor} onChange={(e) => onChange(e.target.value)} {...resto}>
      <optgroup label="Neste projeto">{noModelo.map(([k, t]) => <option key={k} value={k}>{t.nome}</option>)}</optgroup>
      {daBiblioteca.length > 0 && <optgroup label="Biblioteca — exteriores">{daBiblioteca.filter(([, t]) => t.exterior).map(([k, t]) => <option key={k} value={k}>{t.nome}</option>)}</optgroup>}
      {daBiblioteca.length > 0 && <optgroup label="Biblioteca — interiores">{daBiblioteca.filter(([, t]) => !t.exterior).map(([k, t]) => <option key={k} value={k}>{t.nome}</option>)}</optgroup>}
    </select>
  );
  const personalizar = (w) => {        // edita uma cópia própria, para não mudar as outras paredes do mesmo tipo sem querer
    if (w.tipo.startsWith("pers_")) { setAEditarCamadas(w.id); return; }
    let n = 1;
    while (modelo.tipos_parede[`pers_${n}`]) n += 1;
    const base = modelo.tipos_parede[w.tipo];
    const novo = { ...base, nome: `${base.nome} (personalizada)`.slice(0, 80), camadas: base.camadas.map((c) => ({ ...c })) };
    aplicar(G.mudarParede({ ...modelo, tipos_parede: { ...modelo.tipos_parede, [`pers_${n}`]: novo } }, w.id, { tipo: `pers_${n}` }));
    setAEditarCamadas(w.id);
  };
  const mudaMat = (k, v) => aplicar({ ...modelo, materiais: { ...modelo.materiais, [k]: v } });
  const cob = modelo.cobertura;
  const mudaCob = (patch) => aplicar({ ...modelo, cobertura: { ...cob, ...patch } });
  const mudaPiso = (patch) => aplicar({ ...modelo, pisos: modelo.pisos.map((p) => (p.id === piso ? { ...p, ...patch } : p)) });
  const tx = largura / 2 - vista.cx * vista.esc, ty = H2 / 2 + vista.cy * vista.esc;
  const px = 1 / vista.esc;
  const x0v = vista.cx - largura / 2 / vista.esc, x1v = vista.cx + largura / 2 / vista.esc;
  const y0v = vista.cy - H2 / 2 / vista.esc, y1v = vista.cy + H2 / 2 / vista.esc;
  const passoGrelha = vista.esc > 18 ? 1 : 5;
  const grelha = [];
  for (let x = Math.ceil(x0v / passoGrelha) * passoGrelha; x <= x1v && grelha.length < 400; x += passoGrelha) grelha.push(<line key={`gx${x}`} x1={x} y1={y0v} x2={x} y2={y1v} />);
  for (let y = Math.ceil(y0v / passoGrelha) * passoGrelha; y <= y1v && grelha.length < 800; y += passoGrelha) grelha.push(<line key={`gy${y}`} x1={x0v} y1={y} x2={x1v} y2={y} />);
  const divisoes = (derivado?.divisoes || []).filter((d) => d.piso === piso);
  const abaixo = idxPiso > 0 ? modelo.paredes.filter((w) => w.piso === modelo.pisos[idxPiso - 1].id) : [];
  const eSel = sel?.tipo === "escada" ? (modelo.escadas || []).find((e) => e.id === sel.id) : null;
  const eDer = eSel ? (derivado?.escadas || []).find((e) => e.id === eSel.id) : null;
  const mudaEsc = (patch) => aplicar(G.mudarEscada(modelo, eSel.id, patch));
  const escadasPiso = (derivado?.escadas || []).filter((e) => e.piso === piso);
  const escadasAbaixo = idxPiso > 0 ? (derivado?.escadas || []).filter((e) => e.piso === modelo.pisos[idxPiso - 1].id) : [];
  const oSel = sel?.tipo === "objeto" ? (modelo.objetos || []).find((o) => o.id === sel.id) : null;
  const cSel = sel?.tipo === "cota" ? (modelo.cotas || []).find((c) => c.id === sel.id) : null;
  const nSel = sel?.tipo === "nota" ? (modelo.notas || []).find((x) => x.id === sel.id) : null;
  const objetosPiso = (modelo.objetos || []).filter((o) => o.piso === piso && objCat[o.tipo]);
  const cotasPiso = (modelo.cotas || []).filter((c) => c.piso === piso);
  const notasPiso = (modelo.notas || []).filter((x) => x.piso === piso);
  const codigoVao = Object.fromEntries((derivado?.medicoes?.mapa_vaos || []).flatMap((l) => l.ids.map((i) => [i, l.codigo])));
  const dSel = sel?.tipo === "divisao" ? divisoes.find((d) => G.dentroPoligono(sel.pt, d.pts)) : null;
  const mudaDiv = (patch) => aplicar(G.definirDivisao(modelo, piso, dSel, patch));
  const rotSel = dSel ? (modelo.rotulos || [])[G.rotuloDaDivisao(modelo, piso, dSel.pts)] : null;
  const erros = derivado?.erros || [], avisos = [...(info?.avisos_origem || []).map((msg) => ({ msg })), ...(derivado?.avisos || [])];
  const previa = ferramenta === "parede" && inicio && cursor ? [inicio, cursor.ponto] : null;
  const previaSala = ferramenta === "sala" && inicio && cursor ? [inicio, cursor.ponto] : null;
  const previaCota = ferramenta === "cota" && inicio && cursor ? [inicio, cursor.ponto] : null;
  const nadaSel = !wSel && !vSel && !dSel && !eSel && !oSel && !cSel && !nSel;

  return (
    <div className={grande ? "fixed inset-0 z-50 bg-background overflow-auto p-3 space-y-3 outline-none" : "space-y-3 outline-none"} data-testid="estudio-projeto" onKeyDown={tecla} tabIndex={-1}>
      <div className="flex flex-wrap items-center gap-2">
        {FERRAMENTAS.map(([k, t, Icone]) => (
          <Button key={k} size="sm" variant={ferramenta === k ? "default" : "outline"} data-testid={`estudio-ferramenta-${k}`}
            onClick={() => { setFerramenta(k); setInicio(null); setCursor(null); setCompTxt(""); }}><Icone className="h-4 w-4 mr-1" />{t}</Button>
        ))}
        <span className="mx-1 h-6 border-l" />
        <Button size="sm" variant="outline" onClick={anular} disabled={!historia.current.length} title="Ctrl+Z"><Undo2 className="h-4 w-4 mr-1" />Anular</Button>
        <Button size="sm" variant="outline" onClick={refazer} disabled={!refazerPilha.current.length} title="Ctrl+Y" data-testid="estudio-refazer"><Redo2 className="h-4 w-4 mr-1" />Refazer</Button>
        <Button size="sm" onClick={guardar} disabled={!sujo || aGuardar} data-testid="estudio-guardar">
          {aGuardar ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}Guardar</Button>
        <Button size="sm" variant="outline" onClick={repor}><RotateCcw className="h-4 w-4 mr-1" />Repor do processo</Button>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => setGrande((g) => !g)} data-testid="estudio-grande">
          {grande ? <Minimize2 className="h-4 w-4 mr-1" /> : <Maximize2 className="h-4 w-4 mr-1" />}{grande ? "Reduzir" : "Abrir em grande"}</Button>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        {modelo.pisos.map((p) => (
          <Button key={p.id} size="sm" variant={p.id === piso ? "secondary" : "ghost"} onClick={() => { setPiso(p.id); setSel(null); setInicio(null); }}>{p.nome}</Button>
        ))}
        <Button size="sm" variant="ghost" onClick={() => { const m = G.adicionarPiso(modelo); aplicar(m); setPiso(m.pisos[m.pisos.length - 1].id); }} disabled={modelo.pisos.length >= 6}>+ Piso</Button>
        {modelo.pisos.length > 1 && idxPiso === modelo.pisos.length - 1 && (
          <Button size="sm" variant="ghost" onClick={() => { const m = G.removerUltimoPiso(modelo); aplicar(m); setPiso(m.pisos[m.pisos.length - 1].id); setSel(null); }}>
            <Trash2 className="h-4 w-4 mr-1" />Remover este piso</Button>
        )}
        <span className="text-xs text-muted-foreground ml-auto">
          {DICA[ferramenta] || "Roda do rato = zoom · arrastar o fundo = mover · clicar numa peça = editar · arrastar uma parede selecionada = deslocá-la"}
        </span>
      </div>

      <div className="grid lg:grid-cols-4 gap-3 items-start">
        <div className="lg:col-span-3 border rounded-lg overflow-hidden bg-white" ref={caixa}>
          <svg ref={svgRef} width="100%" height={H2} style={{ touchAction: "none", cursor: ferramenta === "selecionar" ? "default" : "crosshair", display: "block" }}
            onPointerDown={baixar} onPointerMove={mover} onPointerUp={largar} onPointerLeave={() => { setCursor(null); }} data-testid="estudio-planta">
            <g transform={`matrix(${vista.esc} 0 0 ${-vista.esc} ${tx} ${ty})`}>
              <g stroke="#e8ecee" strokeWidth={px}>{grelha}</g>
              {divisoes.map((d) => <polygon key={d.id} points={d.pts.map((p) => p.join(",")).join(" ")} fill={d.acabamentos?.pavimento?.cor || "#f3f7f1"} fillOpacity="0.3"
                stroke={dSel?.id === d.id ? "#1f7a5c" : "none"} strokeWidth={3 * px} data-divisao={d.nome} />)}
              {objetosPiso.map((o) => {
                const b = objCat[o.tipo], g = G.contornoObjeto(o, b), ativo = oSel?.id === o.id;
                const c0 = g.pts.reduce((a, q) => [a[0] + q[0] / g.pts.length, a[1] + q[1] / g.pts.length], [0, 0]);
                return (
                  <g key={o.id} data-objeto={o.id}>
                    <polygon points={g.pts.map((q) => q.join(",")).join(" ")} fill={b.cor} fillOpacity="0.35" stroke={ativo ? "#1f7a5c" : "#4b5560"} strokeWidth={(ativo ? 2.2 : 1) * px} />
                    <line x1={c0[0]} y1={c0[1]} x2={g.frente[0]} y2={g.frente[1]} stroke={ativo ? "#1f7a5c" : "#4b5560"} strokeWidth={px} />
                  </g>
                );
              })}
              {abaixo.map((w) => <line key={`b${w.id}`} x1={w.a[0]} y1={w.a[1]} x2={w.b[0]} y2={w.b[1]} stroke="#9aa4ab" strokeWidth={px} strokeDasharray={`${6 * px} ${5 * px}`} />)}
              {paredesPiso.map((w) => {
                const { u } = G.geoParede(w);
                const dw = derPorId[w.id];
                const igual = dw && dw.a[0] === w.a[0] && dw.a[1] === w.a[1] && dw.b[0] === w.b[0] && dw.b[1] === w.b[1];
                const ea = igual ? dw.ext_a : 0, eb = igual ? dw.ext_b : 0;
                const ativo = sel?.tipo === "parede" && sel.id === w.id;
                return <line key={w.id} x1={w.a[0] - u[0] * ea} y1={w.a[1] - u[1] * ea} x2={w.b[0] + u[0] * eb} y2={w.b[1] + u[1] * eb}
                  stroke={ativo ? "#1f7a5c" : "#3a444c"} strokeWidth={esp(w)} data-parede={w.id} />;
              })}
              {modelo.vaos.map((v) => {
                const g = centroVao(v);
                if (!g || g.w.piso !== piso) return null;
                const h = v.largura_m / 2, t = g.t / 2;
                const P = (s, d) => `${g.c[0] + g.u[0] * s + g.n[0] * d},${g.c[1] + g.u[1] * s + g.n[1] * d}`;
                const invalido = erros.some((e) => e.id === v.id);
                const cor = invalido ? "#be2828" : sel?.id === v.id && sel.tipo === "vao" ? "#1f7a5c" : "#1f2933";
                const s0 = v.dobradica === "b" ? h : -h, sent = v.dobradica === "b" ? -1 : 1, ld = v.lado === -1 ? -1 : 1;
                const arco = Array.from({ length: 13 }, (_, i) => { const a = (i * Math.PI) / 24; return P(s0 + sent * v.largura_m * Math.sin(a), ld * (t + v.largura_m * Math.cos(a))); }).join(" ");
                return (
                  <g key={v.id} data-vao={v.id}>
                    <polygon points={`${P(-h, t + px)} ${P(h, t + px)} ${P(h, -t - px)} ${P(-h, -t - px)}`} fill="#fff" />
                    <polyline points={`${P(-h, t)} ${P(-h, -t)}`} stroke={cor} strokeWidth={1.5 * px} fill="none" />
                    <polyline points={`${P(h, t)} ${P(h, -t)}`} stroke={cor} strokeWidth={1.5 * px} fill="none" />
                    {v.tipo === "porta" ? (
                      <>
                        <polyline points={`${P(s0, ld * t)} ${P(s0, ld * (t + v.largura_m))}`} stroke={cor} strokeWidth={1.6 * px} fill="none" />
                        <polyline points={arco} stroke={cor} strokeWidth={px} fill="none" />
                      </>
                    ) : v.tipo === "portao" ? (
                      <polyline points={`${P(-h, 0)} ${P(h, 0)}`} stroke={cor} strokeWidth={2.5 * px} strokeDasharray={`${7 * px} ${5 * px}`} fill="none" />
                    ) : [t, t / 3, -t / 3, -t].map((d) => <polyline key={d} points={`${P(-h, d)} ${P(h, d)}`} stroke={v.tipo === "portada" ? "#2f6f9f" : cor} strokeWidth={px} fill="none" />)}
                  </g>
                );
              })}
              {escadasAbaixo.flatMap((e) => e.vazio.map((a, i) => <polygon key={`vz${e.id}${i}`} points={a.map((p) => p.join(",")).join(" ")} fill="#fff" fillOpacity="0.7"
                stroke="#8a949b" strokeWidth={1.5 * px} strokeDasharray={`${6 * px} ${4 * px}`} />))}
              {escadasPiso.map((e) => (
                <g key={`esc${e.id}`} data-escada={e.id}>
                  {[...e.degraus, ...e.patamares].map((d, i) => <polygon key={i} points={d.pts.map((p) => p.join(",")).join(" ")} fill="#fff"
                    stroke={eSel?.id === e.id ? "#1f7a5c" : "#1f2933"} strokeWidth={(eSel?.id === e.id ? 2 : 1) * px} />)}
                  <polyline points={e.marcha.map((p) => p.join(",")).join(" ")} fill="none" stroke="#be2828" strokeWidth={1.5 * px} />
                  <circle cx={e.marcha[0][0]} cy={e.marcha[0][1]} r={3.5 * px} fill="#be2828" />
                </g>
              ))}
              {cotasPiso.map((c) => {
                const g = G.geoCota(c), cor = cSel?.id === c.id ? "#1f7a5c" : "#be2828";
                return (
                  <g key={c.id} stroke={cor} strokeWidth={px} fill="none" data-cota={c.id}>
                    <line x1={g.p[0]} y1={g.p[1]} x2={g.q[0]} y2={g.q[1]} />
                    <line x1={c.a[0]} y1={c.a[1]} x2={g.p[0] + g.n[0] * 4 * px * Math.sign(c.afastamento_m || 1)} y2={g.p[1] + g.n[1] * 4 * px * Math.sign(c.afastamento_m || 1)} />
                    <line x1={c.b[0]} y1={c.b[1]} x2={g.q[0] + g.n[0] * 4 * px * Math.sign(c.afastamento_m || 1)} y2={g.q[1] + g.n[1] * 4 * px * Math.sign(c.afastamento_m || 1)} />
                  </g>
                );
              })}
              {previaSala && <polygon points={`${previaSala[0][0]},${previaSala[0][1]} ${previaSala[1][0]},${previaSala[0][1]} ${previaSala[1][0]},${previaSala[1][1]} ${previaSala[0][0]},${previaSala[1][1]}`}
                fill="#1f7a5c" fillOpacity="0.08" stroke="#1f7a5c" strokeWidth={G.espessuraTipo(modelo.tipos_parede[tipoParede])} strokeOpacity="0.45" />}
              {previaCota && <line x1={previaCota[0][0]} y1={previaCota[0][1]} x2={previaCota[1][0]} y2={previaCota[1][1]} stroke="#be2828" strokeWidth={1.5 * px} strokeDasharray={`${5 * px} ${4 * px}`} />}
              {ferramenta === "objeto" && cursor && objCat[tipoObjeto] && <polygon pointerEvents="none" fill="#1f7a5c" fillOpacity="0.15" stroke="#1f7a5c" strokeWidth={px}
                points={G.contornoObjeto({ x: cursor.ponto[0], y: cursor.ponto[1], rot: 0 }, objCat[tipoObjeto]).pts.map((q) => q.join(",")).join(" ")} />}
              {wSel && wSel.piso === piso && ["a", "b"].map((k) => <circle key={k} cx={wSel[k][0]} cy={wSel[k][1]} r={6 * px} fill="#fff" stroke="#1f7a5c" strokeWidth={2 * px} />)}
              {previa && <line x1={previa[0][0]} y1={previa[0][1]} x2={previa[1][0]} y2={previa[1][1]} stroke="#1f7a5c" strokeWidth={G.espessuraTipo(modelo.tipos_parede[tipoParede])} strokeOpacity="0.45" />}
              {["parede", "sala", "cota"].includes(ferramenta) && cursor && <circle cx={cursor.ponto[0]} cy={cursor.ponto[1]} r={(cursor.tipo === "ponta" ? 7 : 4) * px} fill="none" stroke={cursor.tipo === "grelha" ? "#8a949b" : "#d97706"} strokeWidth={2 * px} />}
            </g>
            {divisoes.map((d) => {
              const [x, y] = ecra(d.centro);
              const xs = d.pts.map((p) => p[0]);
              const livre = (Math.max(...xs) - Math.min(...xs)) * vista.esc - 8;       // largura da divisão no ecrã
              const tam = Math.max(8, Math.min(13, livre / (0.56 * Math.max(d.nome.length, 1))));
              if (livre < 34) return null;
              return (
                <g key={`t${d.id}`} pointerEvents="none" textAnchor="middle" fontFamily="Helvetica, Arial, sans-serif">
                  <text x={x} y={y - 3} fontSize={tam} fill="#1f2933">{d.nome}</text>
                  <text x={x} y={y + 13} fontSize={Math.min(11, tam)} fill="#6b7780">{G.fmt(d.area_m2)} m²</text>
                </g>
              );
            })}
            {previa && (() => { const [x, y] = ecra([(previa[0][0] + previa[1][0]) / 2, (previa[0][1] + previa[1][1]) / 2]);
              return <text x={x + 10} y={y - 10} fontSize="13" fill="#1f7a5c" pointerEvents="none" data-testid="estudio-comprimento">{compTxt ? `${compTxt} m ↵` : `${G.fmt(Math.hypot(previa[1][0] - previa[0][0], previa[1][1] - previa[0][1]))} m`}</text>; })()}
            {previaSala && (() => { const [x, y] = ecra([(previaSala[0][0] + previaSala[1][0]) / 2, (previaSala[0][1] + previaSala[1][1]) / 2]);
              return <text x={x} y={y} fontSize="13" fill="#1f7a5c" textAnchor="middle" pointerEvents="none">{G.fmt(Math.abs(previaSala[1][0] - previaSala[0][0]))} × {G.fmt(Math.abs(previaSala[1][1] - previaSala[0][1]))} m</text>; })()}
            {(previaCota ? [...cotasPiso, { id: "_p", a: previaCota[0], b: previaCota[1], afastamento_m: 0 }] : cotasPiso).map((c) => {
              const g = G.geoCota(c); const [x, y] = ecra(g.meio);
              return <text key={`ct${c.id}`} x={x} y={y - 4} fontSize="12" fill={cSel?.id === c.id ? "#1f7a5c" : "#be2828"} textAnchor="middle" pointerEvents="none">{G.fmt(g.L)}</text>;
            })}
            {notasPiso.map((nt) => { const [x, y] = ecra([nt.x, nt.y]);
              return <text key={nt.id} x={x} y={y + 4} fontSize="12" fontStyle="italic" fill={nSel?.id === nt.id ? "#1f7a5c" : "#1f2933"} textAnchor="middle" pointerEvents="none" data-nota={nt.id}>{nt.texto}</text>; })}
            {vista.esc > 26 && modelo.vaos.map((v) => {
              const g = centroVao(v);
              if (!g || g.w.piso !== piso || !codigoVao[v.id]) return null;
              const [x, y] = ecra([g.c[0] - g.n[0] * (g.t / 2 + 0.22) * (v.lado === -1 ? -1 : 1), g.c[1] - g.n[1] * (g.t / 2 + 0.22) * (v.lado === -1 ? -1 : 1)]);
              return <text key={`cv${v.id}`} x={x} y={y + 3} fontSize="10" fill="#6b7780" textAnchor="middle" pointerEvents="none">{codigoVao[v.id]}</text>;
            })}
            <text x={12} y={H2 - 10} fontSize="11" fill="#6b7780" pointerEvents="none">FRENTE (via pública) ↓ · grelha de {passoGrelha} m</text>
          </svg>
        </div>

        <div className="border rounded-lg p-3 space-y-3 text-sm" data-testid="estudio-painel">
          {ferramenta === "objeto" && (
            <div className="space-y-2" data-testid="estudio-objetos">
              <div className="font-medium">Mobiliário e equipamento ({cat.objetos.length} peças)</div>
              <Sel valor={catObjeto} onChange={setCatObjeto} opcoes={[["", "Todas as categorias"], ...cat.categorias_objetos.map((c) => [c, c])]} />
              <div className="max-h-72 overflow-auto divide-y border rounded">
                {cat.objetos.filter((o) => !catObjeto || o.categoria === catObjeto).map((o) => (
                  <button type="button" key={o.id} data-objeto-tipo={o.id} onClick={() => setTipoObjeto(o.id)}
                    className={`w-full text-left py-1.5 px-2 flex items-center gap-2 hover:bg-muted ${tipoObjeto === o.id ? "bg-muted" : ""}`}>
                    <span className="h-4 w-4 rounded-sm border shrink-0" style={{ background: o.cor }} />
                    <span className="min-w-0"><span className="block text-xs text-foreground">{o.nome}</span>
                      <span className="block text-[10px] text-muted-foreground">{G.fmt(o.largura_m)} × {G.fmt(o.prof_m)} × {G.fmt(o.altura_m)} m</span></span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {(ferramenta === "parede" || ferramenta === "sala") && (
            <Campo rotulo="Tipo da parede a desenhar">{selTipo(tipoParede, (t) => { if (!modelo.tipos_parede[t]) aplicar(comTipo(modelo, t)); setTipoParede(t); })}</Campo>
          )}
          {wSel && (
            <div className="space-y-2">
              <div className="font-medium">Parede {wSel.id}</div>
              <Campo rotulo="Tipo (camadas)">{selTipo(wSel.tipo, (t) => { setAEditarCamadas(false); aplicar(G.mudarParede(comTipo(modelo, t), wSel.id, { tipo: t })); }, { "data-testid": "estudio-parede-tipo" })}</Campo>
              <Campo rotulo="Comprimento no eixo (m)"><Num valor={G.r3(G.geoParede(wSel).L)} min={0.1} onChange={(L) => aplicar(G.comprimentoParede(modelo, wSel.id, L))} /></Campo>
              {modelo.tipos_parede[wSel.tipo].exterior && (
                <Campo rotulo="Fachada desta parede">
                  <SelAcabamento valor={wSel.fachada || ""} onChange={(v) => aplicar(G.mudarParede(modelo, wSel.id, { fachada: v || undefined }))} lista={cat.acabamentos.fachada}
                    herdado={cat.acabamentos.fachada.find((x) => x.id === (modelo.materiais?.fachada || cat.padrao.fachada))} data-testid="estudio-parede-fachada" />
                </Campo>
              )}
              {aEditarCamadas === wSel.id && wSel.tipo.startsWith("pers_") ? (
                <EditorCamadas tipo={modelo.tipos_parede[wSel.tipo]} catalogo={cat} usos={modelo.paredes.filter((w) => w.tipo === wSel.tipo).length}
                  onMudar={(t) => aplicar({ ...modelo, tipos_parede: { ...modelo.tipos_parede, [wSel.tipo]: t } })} />
              ) : (
                <div className="text-xs text-muted-foreground space-y-0.5">
                  {modelo.tipos_parede[wSel.tipo].camadas.map((c, i) => <div key={i}>{c.material} — {G.fmt(c.esp_m * 100, 1)} cm</div>)}
                  <div className="text-foreground">Espessura total {G.fmt(esp(wSel) * 100, 1)} cm</div>
                </div>
              )}
              {!(aEditarCamadas === wSel.id && wSel.tipo.startsWith("pers_")) && (
                <Button size="sm" variant="outline" onClick={() => personalizar(wSel)} data-testid="estudio-editar-camadas">Editar camadas e materiais</Button>
              )}
              <Button size="sm" variant="outline" onClick={() => { aplicar(G.removerParede(modelo, wSel.id)); setSel(null); }}><Trash2 className="h-4 w-4 mr-1" />Apagar parede</Button>
            </div>
          )}
          {vSel && (
            <div className="space-y-2">
              <div className="font-medium">Vão {vSel.id}</div>
              <Campo rotulo="Tipo"><Sel valor={vSel.tipo} onChange={(t) => aplicar(G.mudarVao(modelo, vSel.id, { tipo: t, ...(t === "janela" ? {} : { peitoril_m: 0 }) }))}
                opcoes={[["porta", "Porta"], ["janela", "Janela"], ["portada", "Portada / envidraçado"], ["portao", "Portão de garagem"]]} /></Campo>
              <div className="grid grid-cols-2 gap-2">
                <Campo rotulo="Largura (m)"><Num valor={vSel.largura_m} min={0.3} onChange={(x) => aplicar(G.mudarVao(modelo, vSel.id, { largura_m: x }))} /></Campo>
                <Campo rotulo="Altura (m)"><Num valor={vSel.altura_m} min={0.3} onChange={(x) => aplicar(G.mudarVao(modelo, vSel.id, { altura_m: x }))} /></Campo>
                <Campo rotulo="Peitoril (m)"><Num valor={vSel.peitoril_m} onChange={(x) => aplicar(G.mudarVao(modelo, vSel.id, { peitoril_m: x }))} /></Campo>
                <Campo rotulo="Centro desde a ponta (m)"><Num valor={vSel.pos_m} onChange={(x) => aplicar(G.mudarVao(modelo, vSel.id, { pos_m: x }))} /></Campo>
              </div>
              <Campo rotulo="Modelo"><Sel valor={vSel.modelo && cat.modelos_vao[vSel.tipo]?.[vSel.modelo] ? vSel.modelo : cat.modelo_vao_padrao[vSel.tipo]} data-testid="estudio-vao-modelo"
                onChange={(x) => aplicar(G.mudarVao(modelo, vSel.id, { modelo: x }))} opcoes={Object.entries(cat.modelos_vao[vSel.tipo] || {}).map(([k, x]) => [k, x.nome])} /></Campo>
              {vSel.tipo !== "porta" && vSel.tipo !== "portao" && (
                <Campo rotulo="Proteção solar"><Sel valor={vSel.protecao || ""} onChange={(x) => aplicar(G.mudarVao(modelo, vSel.id, { protecao: x }))} opcoes={Object.entries(cat.protecoes)} data-testid="estudio-vao-protecao" /></Campo>
              )}
              <Campo rotulo="Caixilharia deste vão">
                <SelAcabamento valor={vSel.caixilharia || ""} onChange={(v) => aplicar(G.mudarVao(modelo, vSel.id, { caixilharia: v || undefined }))} lista={cat.acabamentos.caixilharia}
                  herdado={cat.acabamentos.caixilharia.find((x) => x.id === (modelo.materiais?.caixilharia || cat.padrao.caixilharia))} data-testid="estudio-vao-caixilharia" />
              </Campo>
              {vSel.tipo === "porta" && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => aplicar(G.mudarVao(modelo, vSel.id, { lado: vSel.lado === -1 ? 1 : -1 }))}>Abrir para o outro lado</Button>
                  <Button size="sm" variant="outline" onClick={() => aplicar(G.mudarVao(modelo, vSel.id, { dobradica: vSel.dobradica === "b" ? "a" : "b" }))}>Trocar dobradiça</Button>
                </div>
              )}
              <Button size="sm" variant="outline" onClick={() => { aplicar(G.removerVao(modelo, vSel.id)); setSel(null); }}><Trash2 className="h-4 w-4 mr-1" />Apagar vão</Button>
            </div>
          )}
          {dSel && !wSel && !vSel && (
            <div className="space-y-2" data-testid="estudio-divisao">
              <div className="font-medium">Divisão — {G.fmt(dSel.area_m2)} m²</div>
              <Campo rotulo="Nome"><Texto valor={rotSel?.nome ?? dSel.nome} onChange={(v) => mudaDiv({ nome: v })} data-testid="estudio-divisao-nome" /></Campo>
              {[["pavimento", "Pavimento"], ["parede_interior", "Paredes"], ["teto", "Teto"]].map(([k, t]) => (
                <Campo key={k} rotulo={`${t} desta divisão`}>
                  <SelAcabamento valor={rotSel?.[k] || ""} onChange={(v) => mudaDiv({ [k]: v })} lista={cat.acabamentos[k]} data-testid={`estudio-divisao-${k}`}
                    herdado={cat.acabamentos[k].find((x) => x.id === (modelo.materiais?.[k] || cat.padrao[k]))} />
                </Campo>
              ))}
              <div className="text-xs text-muted-foreground">Paredes da divisão {G.fmt(dSel.area_paredes_m2)} m² · rodapé {G.fmt(dSel.rodape_m)} m · perímetro {G.fmt(dSel.perimetro_m)} m</div>
            </div>
          )}
          {eSel && (
            <div className="space-y-2" data-testid="estudio-escada">
              <div className="font-medium">Escada {eSel.id}</div>
              <Campo rotulo="Tipo"><Sel valor={eSel.tipo} onChange={(t) => mudaEsc({ tipo: t })} data-testid="estudio-escada-tipo"
                opcoes={[["reta", "Reta (um lanço)"], ["l", "Em L (quarto de volta com patamar)"], ["u", "Em U (meia volta com patamar)"]]} /></Campo>
              <div className="grid grid-cols-2 gap-2">
                <Campo rotulo="Largura (m)"><Num valor={eSel.largura_m} min={0.6} onChange={(x) => mudaEsc({ largura_m: x })} /></Campo>
                <Campo rotulo="Cobertor (m)"><Num valor={eSel.cobertor_m} min={0.22} passo={0.01} onChange={(x) => mudaEsc({ cobertor_m: x })} /></Campo>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => mudaEsc({ rot: (eSel.rot + 90) % 360 })} data-testid="estudio-escada-rodar"><RotateCcw className="h-4 w-4 mr-1" />Rodar 90°</Button>
                {eSel.tipo !== "reta" && <Button size="sm" variant="outline" onClick={() => mudaEsc({ sentido: eSel.sentido === "esq" ? "dir" : "esq" })}>Virar para o outro lado</Button>}
              </div>
              {eDer ? (
                <div className="text-xs text-muted-foreground space-y-0.5" data-testid="estudio-escada-calculo">
                  <div className="text-foreground">{eDer.n_espelhos} espelhos de {G.fmt(eDer.espelho_m * 100, 1)} cm · {eDer.n_cobertores} cobertores</div>
                  <div>Altura vencida {G.fmt(eDer.altura_m)} m · 2 × espelho + cobertor = {G.fmt(eDer.blondel_m)} m</div>
                  <div>Em planta {G.fmt(eDer.area_planta_m2)} m² · vazio na laje de cima {G.fmt(eDer.vazio_m2)} m²</div>
                </div>
              ) : <p className="text-xs text-muted-foreground">A calcular os degraus…</p>}
              <p className="text-[11px] text-muted-foreground">O ponto vermelho é o arranque; arraste a escada para a mover.</p>
              <Button size="sm" variant="outline" onClick={() => { aplicar(G.removerEscada(modelo, eSel.id)); setSel(null); }}><Trash2 className="h-4 w-4 mr-1" />Apagar escada</Button>
            </div>
          )}
          {oSel && objCat[oSel.tipo] && (() => { const b = objCat[oSel.tipo]; return (
            <div className="space-y-2" data-testid="estudio-objeto">
              <div className="font-medium">{b.nome}</div>
              <div className="grid grid-cols-2 gap-2">
                <Campo rotulo="Largura (m)"><Num valor={oSel.largura_m ?? b.largura_m} min={0.1} onChange={(x) => aplicar(G.mudarObjeto(modelo, oSel.id, { largura_m: x }))} /></Campo>
                <Campo rotulo="Profundidade (m)"><Num valor={oSel.prof_m ?? b.prof_m} min={0.05} onChange={(x) => aplicar(G.mudarObjeto(modelo, oSel.id, { prof_m: x }))} /></Campo>
                <Campo rotulo="Rotação (°)"><Num valor={oSel.rot || 0} passo={15} onChange={(x) => aplicar(G.mudarObjeto(modelo, oSel.id, { rot: x % 360 }))} /></Campo>
                <Campo rotulo="Altura (m)"><div className="h-8 flex items-center text-xs text-muted-foreground">{G.fmt(b.altura_m)}{b.base_m ? ` (base a ${G.fmt(b.base_m)})` : ""}</div></Campo>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => aplicar(G.mudarObjeto(modelo, oSel.id, { rot: ((oSel.rot || 0) + 90) % 360 }))} data-testid="estudio-objeto-rodar"><RotateCcw className="h-4 w-4 mr-1" />Rodar 90°</Button>
                <Button size="sm" variant="outline" onClick={() => { const r = G.adicionarObjeto(modelo, piso, oSel.tipo, [oSel.x + 0.3, oSel.y - 0.3], oSel.rot || 0); aplicar(r.modelo); setSel({ tipo: "objeto", id: r.id }); }}><Copy className="h-4 w-4 mr-1" />Duplicar</Button>
              </div>
              <p className="text-[11px] text-muted-foreground">Arraste para mover; setas = 5 cm; R = rodar. O traço indica a frente da peça.</p>
              <Button size="sm" variant="outline" onClick={() => { aplicar(G.removerObjeto(modelo, oSel.id)); setSel(null); }}><Trash2 className="h-4 w-4 mr-1" />Apagar peça</Button>
            </div>
          ); })()}
          {cSel && (
            <div className="space-y-2" data-testid="estudio-cota">
              <div className="font-medium">Cota — {G.fmt(G.geoCota(cSel).L)} m</div>
              <Campo rotulo="Afastamento da linha de cota (m; negativo = outro lado)"><Num valor={cSel.afastamento_m ?? 0.6} min={-20} onChange={(x) => aplicar(G.mudarCota(modelo, cSel.id, { afastamento_m: x }))} /></Campo>
              <Button size="sm" variant="outline" onClick={() => { aplicar(G.removerCota(modelo, cSel.id)); setSel(null); }}><Trash2 className="h-4 w-4 mr-1" />Apagar cota</Button>
            </div>
          )}
          {nSel && (
            <div className="space-y-2" data-testid="estudio-nota">
              <div className="font-medium">Nota</div>
              <Campo rotulo="Texto"><Texto valor={nSel.texto} maxLength={120} onChange={(v) => aplicar(G.mudarNota(modelo, nSel.id, { texto: v }))} /></Campo>
              <Button size="sm" variant="outline" onClick={() => { aplicar(G.removerNota(modelo, nSel.id)); setSel(null); }}><Trash2 className="h-4 w-4 mr-1" />Apagar nota</Button>
            </div>
          )}
          {nadaSel && ferramenta !== "objeto" && (
            <div className="space-y-2">
              <div className="font-medium">{pisoObj?.nome}</div>
              <div className="grid grid-cols-2 gap-2">
                <Campo rotulo="Pé-direito (m)"><Num valor={pisoObj.pe_direito_m} min={2} onChange={(x) => mudaPiso({ pe_direito_m: x })} /></Campo>
                {idxPiso > 0 && <Campo rotulo="Laje sob o piso (m)"><Num valor={pisoObj.laje_m} min={0.08} onChange={(x) => mudaPiso({ laje_m: x })} /></Campo>}
              </div>
              <div className="font-medium pt-2 border-t">Cobertura</div>
              <Campo rotulo="Tipo"><Sel valor={cob.tipo} onChange={(t) => mudaCob({ tipo: t })} opcoes={Object.entries(COB)} data-testid="estudio-cobertura-tipo" /></Campo>
              {cob.tipo !== "plana" && (
                <div className="grid grid-cols-2 gap-2">
                  <Campo rotulo="Inclinação (°)"><Num valor={cob.inclinacao_graus} min={3} passo={1} onChange={(x) => mudaCob({ inclinacao_graus: x })} /></Campo>
                  <Campo rotulo="Beiral (m)"><Num valor={cob.beiral_m} onChange={(x) => mudaCob({ beiral_m: x })} /></Campo>
                  {cob.tipo === "duas_aguas" && <Campo rotulo="Cumeeira"><Sel valor={cob.cumeeira} onChange={(x) => mudaCob({ cumeeira: x })} opcoes={[["auto", "Automática"], ["x", "Paralela à frente"], ["y", "Perpendicular"]]} /></Campo>}
                  {cob.tipo === "uma_agua" && <Campo rotulo="Lado baixo"><Sel valor={cob.lado_baixo} onChange={(x) => mudaCob({ lado_baixo: x })} opcoes={Object.entries(LADOS)} /></Campo>}
                </div>
              )}
              <div className="font-medium pt-2 border-t">Acabamentos da casa</div>
              <p className="text-[11px] text-muted-foreground">Para escolher outro pavimento, paredes ou teto numa divisão, clique dentro dela na planta.</p>
              {[["fachada", "Fachada"], ["cobertura", "Cobertura"], ["caixilharia", "Caixilharia"], ["pavimento", "Pavimentos"], ["parede_interior", "Paredes interiores"], ["teto", "Tetos"]].map(([k, t]) => (
                <Campo key={k} rotulo={`${t} (${cat.acabamentos[k].length} opções)`}>
                  <SelAcabamento valor={modelo.materiais?.[k] || cat.padrao[k]} onChange={(v) => mudaMat(k, v)} lista={cat.acabamentos[k]} data-testid={`estudio-acabamento-${k}`} />
                </Campo>
              ))}
            </div>
          )}
          {(erros.length > 0 || avisos.length > 0) && (
            <div className="pt-2 border-t space-y-1" data-testid="estudio-avisos">
              {erros.map((e, i) => <p key={`e${i}`} className="text-xs text-red-700 flex gap-1"><AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />{e.msg}</p>)}
              {avisos.map((a, i) => <p key={`a${i}`} className="text-xs text-amber-800">• {a.msg}</p>)}
            </div>
          )}
          {erro && <p className="text-xs text-red-700">{erro}</p>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b pb-2">
        {[["3d", "3D"], ["alcados", "Alçados"], ["cortes", "Cortes"], ["medicoes", "Medições"], ["processo", "Processo"]].map(([k, t]) => (
          <Button key={k} size="sm" variant={aba === k ? "secondary" : "ghost"} onClick={() => setAba(k)} data-testid={`estudio-aba-${k}`}>{t}</Button>
        ))}
        <span className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={sujo} title={sujo ? "Guarde primeiro" : ""} onClick={() => descarregar(`/estudio-projeto/processos/${pid}/pranchas.pdf`, "estudio-pranchas.pdf")}>
            <Download className="h-4 w-4 mr-1" />Pranchas à escala (PDF)</Button>
          <Button size="sm" variant="outline" disabled={sujo} title={sujo ? "Guarde primeiro" : ""} data-testid="estudio-dxf" onClick={() => descarregar(`/estudio-projeto/processos/${pid}/desenhos.dxf`, "estudio-desenhos.dxf")}>
            <Download className="h-4 w-4 mr-1" />Desenhos (DXF)</Button>
          <Button size="sm" variant="outline" disabled={sujo} title={sujo ? "Guarde primeiro" : ""} onClick={() => descarregar(`/estudio-projeto/processos/${pid}/medicoes.csv`, "estudio-medicoes.csv")}>
            <Download className="h-4 w-4 mr-1" />Medições (CSV)</Button>
          <Button size="sm" variant="outline" disabled={sujo} title={sujo ? "Guarde primeiro" : ""} data-testid="estudio-ifc" onClick={() => descarregar(`/estudio-projeto/processos/${pid}/modelo.ifc`, "estudio-modelo.ifc")}>
            <Download className="h-4 w-4 mr-1" />Modelo (IFC)</Button>
        </span>
      </div>
      {sujo && <p className="text-xs text-muted-foreground">Há alterações por guardar: os ficheiros para descarregar usam o último modelo guardado.</p>}

      {aba === "3d" && derivado && (
        <div className="space-y-2">
          <Estudio3D derivado={derivado} contexto={info?.contexto} altura={grande ? 560 : 440} pisoVisivel={interior ? idxPiso : null}
            onSelecionar={(alvo) => {       // clique numa peça do 3D → abre o painel dessa peça
              setFerramenta("selecionar"); setInicio(null); setPiso(alvo.piso);
              setSel(alvo.tipo === "divisao" ? { tipo: "divisao", pt: alvo.pt } : { tipo: alvo.tipo, id: alvo.id });
            }} />
          <p className="text-xs text-muted-foreground">Clique numa parede, num vão ou numa divisão do 3D para editar essa peça.</p>
          <label className="text-xs flex items-center gap-2"><input type="checkbox" checked={interior} onChange={(e) => setInterior(e.target.checked)} />
            Ver o interior (esconde a cobertura e os pisos acima do piso selecionado)</label>
        </div>
      )}
      {aba === "alcados" && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">{Object.entries(LADOS).map(([k, t]) => <Button key={k} size="sm" variant={lado === k ? "secondary" : "outline"} onClick={() => setLado(k)}>{t}</Button>)}</div>
          <Desenho modelo={modelo} params={{ tipo: "alcado", lado }} ativo />
        </div>
      )}
      {aba === "cortes" && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={eixo === "x" ? "secondary" : "outline"} onClick={() => { setEixo("x"); setPosCorte(null); }}>A-A transversal</Button>
            <Button size="sm" variant={eixo === "y" ? "secondary" : "outline"} onClick={() => { setEixo("y"); setPosCorte(null); }}>B-B longitudinal</Button>
          </div>
          {derivado?.limites && (() => {
            const [a, b] = eixo === "x" ? [derivado.limites[0], derivado.limites[2]] : [derivado.limites[1], derivado.limites[3]];
            const v = posCorte == null ? (a + b) / 2 : Math.max(a, Math.min(b, posCorte));
            return (
              <label className="text-xs text-muted-foreground flex items-center gap-2">Posição do plano de corte
                <input type="range" className="flex-1 max-w-md" min={a + 0.05} max={b - 0.05} step={0.05} value={v} onChange={(e) => setPosCorte(Number(e.target.value))} data-testid="estudio-corte-pos" />
                <span className="text-foreground w-14">{G.fmt(v)} m</span>
                <Button size="sm" variant="ghost" onClick={() => setPosCorte(null)}>A meio</Button>
              </label>
            );
          })()}
          <Desenho modelo={modelo} params={{ tipo: "corte", eixo, ...(posCorte == null ? {} : { pos: posCorte }) }} ativo />
        </div>
      )}
      {aba === "medicoes" && <Medicoes md={derivado?.medicoes} />}
      {aba === "processo" && (
        <div className="space-y-3 text-sm" data-testid="estudio-processo">
          <p className="text-xs text-muted-foreground">As peças do licenciamento (implantação, quadro de áreas, memória) são as do processo, verificadas contra o PDM, o RGEU e o RJUE.
            Aqui vê o que o Estúdio tem de diferente. Ao exportar o processo, o ZIP leva também a pasta «Estudio-de-Projeto» com as pranchas, o DXF, o IFC e as medições deste modelo.</p>
          {sujo ? <p className="text-xs text-amber-800">Guarde o modelo para comparar com o processo.</p>
            : !difs ? <Loader2 className="h-5 w-5 animate-spin" />
              : difs.erro ? <p className="text-xs text-red-700">{difs.erro}</p>
                : difs.divergencias.length === 0 ? <p className="text-sm text-emerald-700" data-testid="estudio-sem-diferencas">O Estúdio coincide com o processo nas medidas comparadas (pisos, áreas, cobertura, vãos, acabamentos).</p>
                  : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs" data-testid="estudio-diferencas">
                        <thead><tr className="text-left text-muted-foreground border-b"><th className="py-1 pr-3 font-medium">O que mudou</th><th className="py-1 pr-3 font-medium">No processo</th><th className="py-1 pr-3 font-medium">No Estúdio</th></tr></thead>
                        <tbody>{difs.divergencias.map((x, i) => (
                          <tr key={i} className="border-b last:border-0"><td className="py-1 pr-3">{x.campo}</td>
                            <td className="py-1 pr-3">{typeof x.processo === "number" ? G.fmt(x.processo) : x.processo} {x.unidade}</td>
                            <td className="py-1 pr-3 font-medium">{typeof x.estudio === "number" ? G.fmt(x.estudio) : x.estudio} {x.unidade}</td></tr>
                        ))}</tbody>
                      </table>
                    </div>
                  )}
          <div className="flex flex-wrap gap-2 items-center">
            <Button size="sm" variant="outline" disabled={sujo || aLevar} onClick={levarAcabamentos} data-testid="estudio-levar-acabamentos">
              {aLevar && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}Levar fachada, cobertura e caixilharia para o processo</Button>
            <span className="text-[11px] text-muted-foreground">Só passam os acabamentos que o catálogo das peças de licenciamento conhece; a memória descritiva é refeita.</span>
          </div>
        </div>
      )}
      {info?.nota && <p className="text-xs text-muted-foreground border-t pt-2">{info.nota}</p>}
    </div>
  );
}
