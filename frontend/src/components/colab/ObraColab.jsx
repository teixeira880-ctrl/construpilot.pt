import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Users, FolderOpen, ShieldCheck, Calculator, CalendarRange, ClipboardList, Upload, Download, Plus, Trash2, Check, X, AlertTriangle, GitCompareArrows, Loader2, Stamp } from "lucide-react";

/**
 * Obra colaborativa (assinatura por obra).
 * O mesmo componente serve o titular da conta (`client` = api, `base` = /chantiers/{id}/colab)
 * e os intervenientes convidados (`client` = portalApi, `base` = /{ref}/colab).
 * O que cada um vê e pode fazer vem do servidor (`capacidades`): aqui só se esconde o que não é permitido.
 */
const eur = (v) => new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }).format(Number(v || 0));
const num = (v) => new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 3 }).format(Number(v || 0));
const day = (s) => (s ? String(s).slice(0, 10).split("-").reverse().join("/") : "—");
const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

const PERFIS = [["dono_obra", "Dono de obra"], ["fiscalizacao", "Fiscalização"], ["arquiteto", "Arquiteto"], ["empresa", "Empresa"]];
const TIPOS = [["execucao", "Plano de execução"], ["arquitetura", "Plano de arquitetura"], ["caderno_encargos", "Caderno de encargos"], ["outro", "Outro documento"]];
const VISTO = {
  pendente: ["A aguardar visto", "bg-amber-100 text-amber-800"],
  visto: ["Visto", "bg-emerald-100 text-emerald-800"],
  visto_com_observacoes: ["Visto com observações", "bg-sky-100 text-sky-800"],
  recusado: ["Visto recusado", "bg-red-100 text-red-800"],
  nao_aplicavel: ["Sem visto", "bg-slate-100 text-slate-600"],
};
const SUB = {
  rascunho: ["Rascunho", "bg-slate-100 text-slate-600"],
  submetido: ["A aguardar decisão", "bg-amber-100 text-amber-800"],
  aprovado: ["Aprovado", "bg-emerald-100 text-emerald-800"],
  aprovado_com_reservas: ["Aprovado com reservas", "bg-sky-100 text-sky-800"],
  recusado: ["Recusado", "bg-red-100 text-red-800"],
};
const AUTO = {
  submetido: ["A aguardar a fiscalização", "bg-amber-100 text-amber-800"],
  validado_fiscalizacao: ["A aguardar o dono de obra", "bg-sky-100 text-sky-800"],
  validado: ["Validado", "bg-emerald-100 text-emerald-800"],
  rejeitado_fiscalizacao: ["Rejeitado pela fiscalização", "bg-red-100 text-red-800"],
  rejeitado_dono: ["Rejeitado pelo dono de obra", "bg-red-100 text-red-800"],
};
const PONTO = {
  ok: "text-emerald-700", a_expirar: "text-amber-700", opcional_em_falta: "text-slate-500",
  em_falta: "text-red-700", expirado: "text-red-700", sem_validade: "text-red-700", excede_limite: "text-red-700",
};

const card = "rounded-2xl border border-slate-200 bg-white text-slate-900";
const field = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-600";
const btn = "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-10 disabled:opacity-50";
const primary = `${btn} bg-emerald-700 text-white hover:bg-emerald-800`;
const ghost = `${btn} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`;
const danger = `${btn} border border-red-300 bg-white text-red-700 hover:bg-red-50`;

const Pill = ({ map, k }) => { const [label, cls] = map[k] || [k, "bg-slate-100 text-slate-600"]; return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>; };
const Empty = ({ children }) => <p className="p-6 text-center text-sm text-slate-500">{children}</p>;
const Head = ({ title, sub, children }) => (
  <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 p-4">
    <div><h3 className="font-semibold">{title}</h3>{sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}</div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
);

export function ObraColab({ client, base, fileBase }) {
  const [info, setInfo] = useState(null);
  const [fail, setFail] = useState("");
  const [tab, setTab] = useState("planos");
  const load = useCallback(() => client.get(base).then(({ data }) => { setInfo(data); setFail(""); })
    .catch((e) => setFail(e?.response?.data?.detail || "Espaço colaborativo indisponível.")), [client, base]);
  useEffect(() => { load(); }, [load]);

  const caps = info?.capacidades || {};
  const tabs = useMemo(() => [
    ["planos", "Caixa de planos", FolderOpen, caps["planos.ver"]],
    ["subs", "Subempreiteiros", ShieldCheck, caps["subs.ver"]],
    ["autos", "Autos de medição", Calculator, caps["autos.ver"]],
    ["planeamento", "Planeamento", CalendarRange, caps["cronograma.ver"]],
    ["atas", "Atas de obra", ClipboardList, caps["atas.ver"]],
    ["intervenientes", "Intervenientes", Users, true],
  ].filter((t) => t[3]), [caps]);

  if (fail) return <p className="text-sm text-red-600" data-testid="colab-error">{fail}</p>;
  if (!info) return <p className="text-sm text-slate-500">A carregar…</p>;
  const empresas = info.intervenientes.filter((i) => i.perfil === "empresa");
  const ctx = { client, base, fileBase, caps, info, empresas, reload: load };
  const n = info.contadores;

  return (
    <div className="space-y-4" data-testid="obra-colab">
      <div className={`${card} flex flex-wrap items-center justify-between gap-3 p-4`}>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Obra colaborativa</p>
          <p className="font-semibold">{info.obra.nome}</p>
          <p className="text-sm text-slate-600">O seu perfil nesta obra: <strong>{info.eu.perfil_label}</strong>{info.eu.gestor && info.eu.perfil !== "gestor" ? " (gestor da obra)" : ""}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-lg bg-slate-100 px-2.5 py-1.5">{n.planos_sem_visto} plano(s) sem visto</span>
          {n.subs_pendentes != null && <span className="rounded-lg bg-slate-100 px-2.5 py-1.5">{n.subs_pendentes} subempreiteiro(s) por decidir</span>}
          {n.autos_pendentes != null && <span className="rounded-lg bg-slate-100 px-2.5 py-1.5">{n.autos_pendentes} auto(s) em validação</span>}
        </div>
      </div>
      <nav className="flex flex-wrap gap-1 rounded-2xl border border-slate-200 bg-white p-1.5" aria-label="Secções da obra colaborativa">
        {tabs.map(([k, l, I]) => (
          <button key={k} type="button" onClick={() => setTab(k)} aria-pressed={tab === k} data-testid={`colab-tab-${k}`}
            className={`inline-flex min-h-10 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium ${tab === k ? "bg-emerald-700 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
            <I className="h-4 w-4" /> {l}
          </button>))}
      </nav>
      {tab === "planos" && <Planos {...ctx} />}
      {tab === "subs" && <Subs {...ctx} />}
      {tab === "autos" && <Autos {...ctx} />}
      {tab === "planeamento" && <Planeamento {...ctx} />}
      {tab === "atas" && <Atas {...ctx} />}
      {tab === "intervenientes" && <Intervenientes {...ctx} />}
    </div>
  );
}

/* ------------------------------------------------------------------ intervenientes */
function Intervenientes({ client, base, caps, info, reload }) {
  const [f, setF] = useState({ perfil: "empresa", email: "", nome: "", lote: "" });
  const [busy, setBusy] = useState(false);
  const gestor = caps["intervenientes.gerir"];
  const invite = async (e) => {
    e.preventDefault(); setBusy(true);
    try { await client.post(`${base}/intervenientes`, f); toast.success("Convite enviado por e-mail"); setF({ perfil: "empresa", email: "", nome: "", lote: "" }); reload(); }
    catch (x) { err(x, "Convite impossível"); } finally { setBusy(false); }
  };
  const setPerfil = async (i, perfil) => { try { await client.put(`${base}/intervenientes/${i.participant_id}`, { perfil }); reload(); } catch (x) { err(x, "Alteração impossível"); } };
  const setOwner = async (owner_role) => {
    try { await client.put(`${base}/definicoes`, { ...info.definicoes, owner_role: owner_role || null }); toast.success("Perfil atualizado"); reload(); }
    catch (x) { err(x, "Alteração impossível"); }
  };
  return (
    <section className={card}>
      <Head title="Intervenientes da obra" sub="Dono de obra, fiscalização e arquiteto administram os documentos. As empresas consultam e carregam, e só veem os seus próprios autos, pedidos e cronograma." />
      {gestor && (
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 p-4 text-sm">
          <label htmlFor="colab-owner-role">O meu papel nesta obra</label>
          <select id="colab-owner-role" className={`${field} max-w-56`} value={info.definicoes?.owner_role || ""} onChange={(e) => setOwner(e.target.value)} data-testid="colab-owner-role">
            <option value="">Só gestor (sem visto nem decisão)</option>
            {PERFIS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>)}
      <ul className="divide-y divide-slate-200">
        {info.intervenientes.map((i) => (
          <li key={i.participant_id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
            <div><p className="font-medium">{i.nome}{i.lote ? ` · ${i.lote}` : ""}</p>{i.email && <p className="text-xs text-slate-500">{i.email} · {i.estado === "active" ? "ativo" : "convite por aceitar"}</p>}</div>
            {gestor ? (
              <select aria-label={`Perfil de ${i.nome}`} className={`${field} max-w-48`} value={i.perfil} onChange={(e) => setPerfil(i, e.target.value)}>
                {PERFIS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>) : <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">{i.perfil_label}</span>}
          </li>))}
        {info.intervenientes.length === 0 && <Empty>Ainda não há intervenientes convidados.</Empty>}
      </ul>
      {gestor && (
        <form onSubmit={invite} className="grid gap-2 border-t border-slate-200 p-4 sm:grid-cols-5" data-testid="colab-invite-form">
          <select aria-label="Perfil" className={field} value={f.perfil} onChange={(e) => setF({ ...f, perfil: e.target.value })}>{PERFIS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <input aria-label="E-mail" type="email" required placeholder="E-mail" className={field} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <input aria-label="Nome" placeholder="Nome ou empresa" className={field} value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} />
          <input aria-label="Especialidade" placeholder="Especialidade (estrutura, canalização…)" className={field} value={f.lote} onChange={(e) => setF({ ...f, lote: e.target.value })} />
          <button className={primary} disabled={busy}><Plus className="h-4 w-4" /> Convidar</button>
        </form>)}
    </section>
  );
}

/* ------------------------------------------------------------------ caixa de planos */
function Planos({ client, base, fileBase, caps, reload }) {
  const [rows, setRows] = useState(null);
  const [f, setF] = useState({ titulo: "", tipo: "execucao", especialidade: "" });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState([]);
  const [cmp, setCmp] = useState(null);
  const load = useCallback(() => client.get(`${base}/planos`).then(({ data }) => setRows(data.planos)).catch((x) => err(x, "Planos indisponíveis")), [client, base]);
  useEffect(() => { load(); }, [load]);
  const after = () => { load(); reload(); };

  const upload = async (e) => {
    e.preventDefault(); if (!file) return; setBusy(true);
    const fd = new FormData(); fd.append("file", file); Object.entries(f).forEach(([k, v]) => fd.append(k, v));
    try { await client.post(`${base}/planos`, fd); toast.success("Documento carregado"); setFile(null); setF({ titulo: "", tipo: "execucao", especialidade: "" }); e.target.reset(); after(); }
    catch (x) { err(x, "Carregamento impossível"); } finally { setBusy(false); }
  };
  const versao = async (p, fl) => { if (!fl) return; const fd = new FormData(); fd.append("file", fl); try { await client.post(`${base}/planos/${p.plano_id}/versoes`, fd); toast.success("Nova versão carregada — o visto volta a ser pedido"); after(); } catch (x) { err(x, "Carregamento impossível"); } };
  const visto = async (p, decisao) => {
    const observacoes = decisao === "visto" ? "" : (window.prompt("Observações (obrigatórias)", "") || "").trim();
    if (decisao !== "visto" && !observacoes) return;
    try { await client.post(`${base}/planos/${p.plano_id}/visto`, { decisao, observacoes }); toast.success("Visto registado"); after(); } catch (x) { err(x, "Visto impossível"); }
  };
  const anotar = async (p) => { const texto = (window.prompt("Anotação", "") || "").trim(); if (!texto) return; try { await client.post(`${base}/planos/${p.plano_id}/anotacoes`, { texto }); after(); } catch (x) { err(x, "Anotação impossível"); } };
  const remove = async (p) => { if (!window.confirm(`Eliminar «${p.titulo}»?`)) return; try { await client.delete(`${base}/planos/${p.plano_id}`); after(); } catch (x) { err(x, "Eliminação impossível"); } };
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));
  const comparar = async () => {
    setBusy(true); setCmp(null);
    try { const { data } = await client.post(`${base}/planos/comparar`, { plano_a: sel[0], plano_b: sel[1] }); setCmp(data); }
    catch (x) { err(x, "Comparação indisponível"); } finally { setBusy(false); }
  };

  return (
    <section className={card} data-testid="colab-planos">
      <Head title="Caixa de planos" sub="Os planos de execução precisam do visto da fiscalização ou do arquiteto. Uma nova versão anula o visto anterior.">
        {caps["planos.comparar"] && <button type="button" className={ghost} disabled={sel.length !== 2 || busy} onClick={comparar} data-testid="colab-comparar">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitCompareArrows className="h-4 w-4" />} Comparar os 2 selecionados (IA)</button>}
      </Head>
      {caps["planos.carregar"] && (
        <form onSubmit={upload} className="grid gap-2 border-b border-slate-200 p-4 sm:grid-cols-5" data-testid="colab-plano-form">
          <input aria-label="Título" placeholder="Título" className={field} value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} />
          <select aria-label="Tipo" className={field} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}>{TIPOS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <input aria-label="Especialidade" placeholder="Especialidade" className={field} value={f.especialidade} onChange={(e) => setF({ ...f, especialidade: e.target.value })} />
          <input aria-label="Ficheiro" type="file" required accept=".pdf,.png,.jpg,.jpeg,.webp,.dwg,.dxf,.ifc" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <button className={primary} disabled={busy || !file}><Upload className="h-4 w-4" /> Carregar</button>
        </form>)}
      {cmp && (
        <div className="border-b border-slate-200 bg-slate-50 p-4 text-sm" data-testid="colab-comparacao">
          <p className="font-medium">Comparação por IA: «{cmp.titulo_a}» e «{cmp.titulo_b}»</p>
          <p className="mb-2 text-xs text-slate-500">Análise automática a confirmar por quem dá o visto. Foco: {cmp.foco}</p>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs">{typeof cmp.resultado === "string" ? cmp.resultado : JSON.stringify(cmp.resultado, null, 2)}</pre>
        </div>)}
      {rows === null ? <Empty>A carregar…</Empty> : rows.length === 0 ? <Empty>Nenhum plano carregado.</Empty> : (
        <ul className="divide-y divide-slate-200">
          {rows.map((p) => (
            <li key={p.plano_id} className="space-y-2 p-4 text-sm" data-testid={`colab-plano-${p.plano_id}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <label className="flex items-start gap-2">
                  {caps["planos.comparar"] && <input type="checkbox" className="mt-1" checked={sel.includes(p.plano_id)} onChange={() => toggle(p.plano_id)} aria-label={`Selecionar ${p.titulo} para comparar`} />}
                  <span><span className="font-medium">{p.titulo}</span> <span className="text-xs text-slate-500">v{p.versao_atual}</span>
                    <span className="block text-xs text-slate-500">{(TIPOS.find((t) => t[0] === p.tipo) || [])[1]}{p.especialidade ? ` · ${p.especialidade}` : ""} · {p.empresa_nome || p.carregado_por?.nome} · {day(p.updated_at)}</span></span>
                </label>
                <Pill map={VISTO} k={p.visto_estado} />
              </div>
              <div className="flex flex-wrap gap-2">
                <a className={ghost} href={`${fileBase}/planos/${p.plano_id}/ficheiro`} target="_blank" rel="noreferrer"><Download className="h-4 w-4" /> Abrir</a>
                {caps["planos.carregar"] && <label className={`${ghost} cursor-pointer`}><Upload className="h-4 w-4" /> Nova versão<input type="file" className="sr-only" onChange={(e) => versao(p, e.target.files?.[0])} /></label>}
                {caps["planos.visto"] && p.tipo === "execucao" && <>
                  <button type="button" className={primary} onClick={() => visto(p, "visto")}><Stamp className="h-4 w-4" /> Dar visto</button>
                  <button type="button" className={ghost} onClick={() => visto(p, "visto_com_observacoes")}>Visto com observações</button>
                  <button type="button" className={danger} onClick={() => visto(p, "recusado")}>Recusar</button></>}
                {caps["planos.anotar"] && <button type="button" className={ghost} onClick={() => anotar(p)}>Anotar</button>}
                {caps["planos.modificar"] && <button type="button" className={danger} onClick={() => remove(p)} aria-label={`Eliminar ${p.titulo}`}><Trash2 className="h-4 w-4" /></button>}
              </div>
              {(p.vistos || []).slice(-1).map((v) => <p key={v.at} className="text-xs text-slate-600">Último visto (v{v.versao}): {VISTO[v.decisao]?.[0]} por {v.por?.nome} em {day(v.at)}{v.observacoes ? ` — ${v.observacoes}` : ""}</p>)}
              {(p.anotacoes || []).map((a) => <p key={a.anotacao_id} className="rounded-lg bg-slate-50 px-3 py-1.5 text-xs text-slate-700">{a.por?.nome}: {a.texto}</p>)}
            </li>))}
        </ul>)}
    </section>
  );
}

/* ------------------------------------------------------------------ subempreiteiros */
function Subs({ client, base, fileBase, caps, reload }) {
  const [data, setData] = useState(null);
  const [f, setF] = useState({ nome: "", nif: "", trabalhos: "", valor: "" });
  const load = useCallback(() => client.get(`${base}/subs`).then(({ data }) => setData(data)).catch((x) => err(x, "Pedidos indisponíveis")), [client, base]);
  useEffect(() => { load(); }, [load]);
  const after = () => { load(); reload(); };
  const create = async (e) => { e.preventDefault(); try { await client.post(`${base}/subs`, { ...f, valor: Number(f.valor || 0) }); setF({ nome: "", nif: "", trabalhos: "", valor: "" }); after(); } catch (x) { err(x, "Criação impossível"); } };
  const addDoc = async (s, key, file, validade) => { if (!file) return; const fd = new FormData(); fd.append("file", file); fd.append("key", key); fd.append("validade", validade || ""); try { await client.post(`${base}/subs/${s.sub_id}/documentos`, fd); after(); } catch (x) { err(x, "Carregamento impossível"); } };
  const submit = async (s) => { try { await client.post(`${base}/subs/${s.sub_id}/submeter`); toast.success("Pedido submetido ao dono de obra"); after(); } catch (x) { err(x, "Submissão impossível"); } };
  const decide = async (s, decisao) => {
    const body = { decisao, reservas: "", motivos: "" };
    if (decisao === "aprovado_com_reservas") { body.reservas = (window.prompt("Reservas: o que falta e até quando", s.controlo.motivos.join("; ")) || "").trim(); if (!body.reservas) return; }
    if (decisao === "recusado") { body.motivos = (window.prompt("Motivos da recusa", s.controlo.motivos.join("; ")) || "").trim(); if (!body.motivos) return; }
    try { await client.post(`${base}/subs/${s.sub_id}/decisao`, body); toast.success("Decisão registada"); after(); } catch (x) { err(x, "Decisão impossível"); }
  };
  if (!data) return <Empty>A carregar…</Empty>;
  return (
    <section className={card} data-testid="colab-subs">
      <Head title="Aprovação de subempreiteiros" sub="Cada pedido é confrontado com o regulamento do dono de obra: documentos em falta, validades e limite de subcontratação." />
      {caps["subs.submeter"] && (
        <form onSubmit={create} className="grid gap-2 border-b border-slate-200 p-4 sm:grid-cols-5" data-testid="colab-sub-form">
          <input aria-label="Subempreiteiro" required placeholder="Nome do subempreiteiro" className={field} value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} />
          <input aria-label="NIF" placeholder="NIF" className={field} value={f.nif} onChange={(e) => setF({ ...f, nif: e.target.value })} />
          <input aria-label="Trabalhos" placeholder="Trabalhos a subcontratar" className={field} value={f.trabalhos} onChange={(e) => setF({ ...f, trabalhos: e.target.value })} />
          <input aria-label="Valor" type="number" min="0" step="0.01" placeholder="Valor (€)" className={field} value={f.valor} onChange={(e) => setF({ ...f, valor: e.target.value })} />
          <button className={primary}><Plus className="h-4 w-4" /> Novo pedido</button>
        </form>)}
      {data.pedidos.length === 0 ? <Empty>Nenhum pedido de aprovação.</Empty> : (
        <ul className="divide-y divide-slate-200">
          {data.pedidos.map((s) => (
            <li key={s.sub_id} className="space-y-3 p-4 text-sm" data-testid={`colab-sub-${s.sub_id}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div><p className="font-medium">{s.nome}{s.nif ? ` · NIF ${s.nif}` : ""}</p><p className="text-xs text-slate-500">Pedido de {s.empresa_nome} · {s.trabalhos || "trabalhos por indicar"} · {eur(s.valor)}</p></div>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 text-xs font-medium ${s.controlo.conforme ? "text-emerald-700" : "text-red-700"}`}>{s.controlo.conforme ? <Check className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}{s.controlo.conforme ? "Cumpre o regulamento" : "Não cumpre o regulamento"}</span>
                  <Pill map={SUB} k={s.estado} />
                </div>
              </div>
              <table className="w-full text-xs">
                <tbody>
                  {s.controlo.pontos.map((p) => {
                    const doc = (s.documentos || []).find((d) => d.key === p.key);
                    return (
                      <tr key={p.key} className="border-t border-slate-100">
                        <td className="py-1.5 pr-2">{p.label}{p.obrigatorio ? "" : " (opcional)"}</td>
                        <td className={`py-1.5 pr-2 ${PONTO[p.estado] || ""}`}>{p.detalhe}</td>
                        <td className="py-1.5 text-right">
                          {doc && <a className="underline" href={`${fileBase}/subs/${s.sub_id}/documentos/${p.key}`} target="_blank" rel="noreferrer">Abrir</a>}
                          {caps["subs.submeter"] && p.key !== "limite_subcontratacao" && ["rascunho", "submetido", "aprovado_com_reservas"].includes(s.estado) && <DocUpload onSend={(file, validade) => addDoc(s, p.key, file, validade)} />}
                        </td>
                      </tr>);
                  })}
                </tbody>
              </table>
              {s.decisao && <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs">Decisão de {s.decisao.por?.nome} em {day(s.decisao.at)}{s.decisao.reservas ? ` — reservas: ${s.decisao.reservas}` : ""}{s.decisao.motivos ? ` — motivos: ${s.decisao.motivos}` : ""}</p>}
              <div className="flex flex-wrap gap-2">
                {caps["subs.submeter"] && s.estado === "rascunho" && <button type="button" className={primary} onClick={() => submit(s)}>Submeter ao dono de obra</button>}
                {caps["subs.decidir"] && ["submetido", "aprovado_com_reservas"].includes(s.estado) && <>
                  <button type="button" className={primary} disabled={!s.controlo.conforme} title={s.controlo.conforme ? "" : "O pedido não cumpre o regulamento"} onClick={() => decide(s, "aprovado")}><Check className="h-4 w-4" /> Aprovar</button>
                  {s.estado === "submetido" && <button type="button" className={ghost} onClick={() => decide(s, "aprovado_com_reservas")}>Aprovar com reservas</button>}
                  <button type="button" className={danger} onClick={() => decide(s, "recusado")}><X className="h-4 w-4" /> Recusar</button></>}
              </div>
            </li>))}
        </ul>)}
    </section>
  );
}

function DocUpload({ onSend }) {
  const [validade, setValidade] = useState("");
  return (
    <span className="ml-2 inline-flex items-center gap-1">
      <input aria-label="Validade" type="date" className="rounded border border-slate-300 px-1 py-0.5 text-xs" value={validade} onChange={(e) => setValidade(e.target.value)} />
      <label className="cursor-pointer underline">Carregar<input type="file" className="sr-only" onChange={(e) => onSend(e.target.files?.[0], validade)} /></label>
    </span>
  );
}

/* ------------------------------------------------------------------ autos de medição */
function Autos({ client, base, caps, empresas, reload }) {
  const [autos, setAutos] = useState(null);
  const [contratos, setContratos] = useState([]);
  const [periodo, setPeriodo] = useState(new Date().toISOString().slice(0, 7));
  const [qtd, setQtd] = useState({});
  const [open, setOpen] = useState(null);
  const [novo, setNovo] = useState({ empresa_id: "", texto: "" });
  const load = useCallback(() => Promise.all([client.get(`${base}/autos`), client.get(`${base}/contratos`)])
    .then(([a, c]) => { setAutos(a.data.autos); setContratos(c.data.contratos); }).catch((x) => err(x, "Autos indisponíveis")), [client, base]);
  useEffect(() => { load(); }, [load]);
  const after = () => { load(); reload(); };
  const meu = caps["autos.carregar"] ? contratos[0] : null;

  const submeter = async (e) => {
    e.preventDefault();
    const linhas = Object.entries(qtd).filter(([, v]) => Number(v)).map(([ref, v]) => ({ ref, quantidade_periodo: Number(v) }));
    if (!linhas.length) { toast.error("Indique pelo menos uma quantidade."); return; }
    try { const { data } = await client.post(`${base}/autos`, { periodo, linhas }); setQtd({}); setOpen(data.auto_id); toast.success(data.controlo.conforme ? "Auto submetido — conforme com o orçamento" : "Auto submetido — com incoerências assinaladas"); after(); }
    catch (x) { err(x, "Submissão impossível"); }
  };
  const decidir = async (a, aprovar) => {
    const motivo = aprovar ? "" : (window.prompt("Motivo da rejeição", "") || "").trim();
    if (!aprovar && !motivo) return;
    try { await client.post(`${base}/autos/${a.auto_id}/decisao`, { aprovar, motivo }); toast.success(aprovar ? "Auto validado" : "Auto rejeitado"); after(); } catch (x) { err(x, "Decisão impossível"); }
  };
  // Colar o orçamento contratado: uma linha por artigo → ref ; designação ; unidade ; quantidade ; preço unitário
  const guardarContrato = async (e) => {
    e.preventDefault();
    const linhas = novo.texto.split("\n").map((l) => l.split(/[;\t]/).map((c) => c.trim())).filter((c) => c.length >= 5 && c[0])
      .map((c) => ({ ref: c[0], designacao: c[1], unidade: c[2], quantidade: Number(c[3].replace(",", ".")), preco_unitario: Number(c[4].replace(",", ".")) }));
    if (!linhas.length || linhas.some((l) => Number.isNaN(l.quantidade) || Number.isNaN(l.preco_unitario))) { toast.error("Formato: ref ; designação ; unidade ; quantidade ; preço unitário"); return; }
    try { await client.put(`${base}/contratos/${novo.empresa_id}`, { linhas }); toast.success("Orçamento contratado registado"); setNovo({ empresa_id: "", texto: "" }); after(); } catch (x) { err(x, "Registo impossível"); }
  };
  const podeDecidir = (a) => (caps["autos.validar_fiscal"] && a.estado === "submetido") || (caps["autos.validar_dono"] && a.estado === "validado_fiscalizacao");
  if (autos === null) return <Empty>A carregar…</Empty>;

  return (
    <section className={card} data-testid="colab-autos">
      <Head title="Autos de medição" sub="Cada auto é verificado contra o orçamento contratado, os autos anteriores e o avanço registado pela fiscalização. Validação: fiscalização, depois dono de obra." />
      {caps["contratos.gerir"] && (
        <form onSubmit={guardarContrato} className="space-y-2 border-b border-slate-200 p-4 text-sm" data-testid="colab-contrato-form">
          <p className="font-medium">Orçamentos contratados</p>
          {contratos.map((c) => <p key={c.empresa_id} className="text-xs text-slate-600">{c.empresa_nome}: {c.linhas.length} artigo(s) · {eur(c.total)}</p>)}
          <div className="grid gap-2 sm:grid-cols-4">
            <select aria-label="Empresa" required className={field} value={novo.empresa_id} onChange={(e) => setNovo({ ...novo, empresa_id: e.target.value })}><option value="">Empresa…</option>{empresas.map((e) => <option key={e.participant_id} value={e.participant_id}>{e.nome}</option>)}</select>
            <textarea aria-label="Artigos do orçamento" required rows={3} className={`${field} sm:col-span-2`} placeholder={"1.1 ; Betão C25/30 ; m³ ; 100 ; 120,00\n1.2 ; Aço A500 ; kg ; 8000 ; 1,35"} value={novo.texto} onChange={(e) => setNovo({ ...novo, texto: e.target.value })} />
            <button className={primary}>Registar orçamento</button>
          </div>
        </form>)}
      {caps["autos.carregar"] && (meu ? (
        <form onSubmit={submeter} className="space-y-2 border-b border-slate-200 p-4 text-sm" data-testid="colab-auto-form">
          <div className="flex flex-wrap items-center gap-2"><label htmlFor="colab-periodo" className="font-medium">Novo auto — período</label><input id="colab-periodo" type="month" required className={`${field} max-w-44`} value={periodo} onChange={(e) => setPeriodo(e.target.value)} /></div>
          <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="text-left text-slate-500"><th className="py-1">Artigo</th><th>Un.</th><th className="text-right">Contrato</th><th className="text-right">P. unit.</th><th className="text-right">Quantidade do período</th></tr></thead>
            <tbody>{meu.linhas.map((l) => (<tr key={l.ref} className="border-t border-slate-100"><td className="py-1">{l.ref} · {l.designacao}</td><td>{l.unidade}</td><td className="text-right">{num(l.quantidade)}</td><td className="text-right">{eur(l.preco_unitario)}</td>
              <td className="text-right"><input aria-label={`Quantidade ${l.ref}`} type="number" step="any" className="w-24 rounded border border-slate-300 px-1 py-0.5 text-right" value={qtd[l.ref] || ""} onChange={(e) => setQtd({ ...qtd, [l.ref]: e.target.value })} /></td></tr>))}</tbody></table></div>
          <button className={primary}><Upload className="h-4 w-4" /> Submeter auto</button>
        </form>) : <p className="border-b border-slate-200 p-4 text-sm text-amber-700">O orçamento contratado da sua empresa ainda não foi registado pelo dono de obra.</p>)}
      {autos.length === 0 ? <Empty>Nenhum auto de medição.</Empty> : (
        <ul className="divide-y divide-slate-200">
          {autos.map((a) => (
            <li key={a.auto_id} className="space-y-2 p-4 text-sm" data-testid={`colab-auto-${a.auto_id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button type="button" className="text-left" onClick={() => setOpen(open === a.auto_id ? null : a.auto_id)} aria-expanded={open === a.auto_id}>
                  <span className="font-medium">Auto n.º {a.numero} · {a.periodo}</span> <span className="text-xs text-slate-500">{a.empresa_nome} · {eur(a.controlo.total_periodo)} · acumulado {a.controlo.pct_financeiro ?? "—"} %</span>
                </button>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 text-xs font-medium ${a.controlo.conforme ? "text-emerald-700" : "text-red-700"}`}>{a.controlo.conforme ? <Check className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}{a.controlo.resumo}</span>
                  <Pill map={AUTO} k={a.estado} />
                </div>
              </div>
              {open === a.auto_id && <>
                {a.controlo.incoerencias.map((i, k) => <p key={k} className={`rounded-lg px-3 py-1.5 text-xs ${i.gravidade === "bloqueante" ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-800"}`}>{i.texto}</p>)}
                <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="text-left text-slate-500"><th className="py-1">Artigo</th><th className="text-right">Contrato</th><th className="text-right">Anterior</th><th className="text-right">Período</th><th className="text-right">Acumulado</th><th className="text-right">%</th><th className="text-right">Valor</th></tr></thead>
                  <tbody>{a.controlo.linhas.map((l) => (<tr key={l.ref} className="border-t border-slate-100"><td className="py-1">{l.ref} · {l.designacao}</td><td className="text-right">{l.quantidade_contrato == null ? "—" : num(l.quantidade_contrato)}</td><td className="text-right">{num(l.quantidade_anterior)}</td><td className="text-right">{num(l.quantidade_periodo)}</td><td className="text-right">{num(l.quantidade_acumulada)}</td><td className="text-right">{l.pct_acumulado ?? "—"}</td><td className="text-right">{eur(l.valor_periodo)}</td></tr>))}</tbody></table></div>
                <p className="text-xs text-slate-600">Contrato {eur(a.controlo.total_contrato)} · anteriores {eur(a.controlo.total_anterior)} · este auto {eur(a.controlo.total_periodo)} · acumulado {eur(a.controlo.total_acumulado)}{a.controlo.avanco_registado_pct != null ? ` · avanço físico registado ${a.controlo.avanco_registado_pct} %` : ""}</p>
                {a.historico.map((h, k) => <p key={k} className="text-xs text-slate-500">{day(h.at)} · {AUTO[h.acao]?.[0] || h.acao} · {h.por?.nome}{h.motivo ? ` — ${h.motivo}` : ""}</p>)}
              </>}
              {podeDecidir(a) && <div className="flex gap-2"><button type="button" className={primary} onClick={() => decidir(a, true)}><Check className="h-4 w-4" /> Validar</button><button type="button" className={danger} onClick={() => decidir(a, false)}><X className="h-4 w-4" /> Rejeitar</button></div>}
            </li>))}
        </ul>)}
    </section>
  );
}

/* ------------------------------------------------------------------ planeamento */
function Planeamento({ client, base, caps, reload }) {
  const [rows, setRows] = useState(null);
  const [texto, setTexto] = useState("");
  const [pct, setPct] = useState({});
  const load = useCallback(() => client.get(`${base}/cronogramas`).then(({ data }) => setRows(data.cronogramas)).catch((x) => err(x, "Planeamento indisponível")), [client, base]);
  useEffect(() => { load(); }, [load]);
  const meu = caps["cronograma.carregar"] ? rows?.[0] : null;
  useEffect(() => { if (meu) setTexto(meu.tarefas.map((t) => `${t.titulo} ; ${t.inicio} ; ${t.fim}`).join("\n")); }, [meu]);

  const guardar = async (e) => {
    e.preventDefault();
    const antigas = Object.fromEntries((meu?.tarefas || []).map((t) => [t.titulo, t.tarefa_id]));
    const tarefas = texto.split("\n").map((l) => l.split(/[;\t]/).map((c) => c.trim())).filter((c) => c.length >= 3 && c[0])
      .map((c) => ({ tarefa_id: antigas[c[0]], titulo: c[0], inicio: c[1], fim: c[2] }));
    try { await client.put(`${base}/cronograma`, { tarefas }); toast.success("Cronograma guardado"); load(); } catch (x) { err(x, "Formato: tarefa ; AAAA-MM-DD ; AAAA-MM-DD"); }
  };
  const registar = async (c) => {
    const tarefas = c.tarefas.filter((t) => pct[t.tarefa_id] !== undefined && pct[t.tarefa_id] !== "").map((t) => ({ tarefa_id: t.tarefa_id, avanco_pct: Number(pct[t.tarefa_id]) }));
    if (!tarefas.length) { toast.error("Indique o avanço de pelo menos uma tarefa."); return; }
    try { await client.post(`${base}/cronogramas/${c.empresa_id}/avanco`, { data_reuniao: new Date().toISOString().slice(0, 10), tarefas }); toast.success("Avanço registado"); setPct({}); load(); reload(); } catch (x) { err(x, "Registo impossível"); }
  };
  if (rows === null) return <Empty>A carregar…</Empty>;
  return (
    <section className={card} data-testid="colab-planeamento">
      <Head title="Acompanhamento do planeamento" sub="Cada empresa carrega o seu cronograma. Em cada reunião de obra, a fiscalização regista o avanço e os atrasos." />
      {caps["cronograma.carregar"] && (
        <form onSubmit={guardar} className="space-y-2 border-b border-slate-200 p-4 text-sm" data-testid="colab-cronograma-form">
          <label htmlFor="colab-cron" className="font-medium">O meu cronograma <span className="font-normal text-slate-500">(uma tarefa por linha: tarefa ; início ; fim)</span></label>
          <textarea id="colab-cron" rows={5} className={field} placeholder={"Fundações ; 2026-10-01 ; 2026-10-31\nPilares ; 2026-11-01 ; 2026-12-31"} value={texto} onChange={(e) => setTexto(e.target.value)} />
          <button className={primary}>Guardar cronograma</button>
        </form>)}
      {rows.length === 0 ? <Empty>Nenhum cronograma carregado.</Empty> : rows.map((c) => (
        <div key={c.empresa_id} className="border-b border-slate-200 p-4 text-sm last:border-b-0">
          <p className="mb-2 font-medium">{c.empresa_nome} <span className="text-xs font-normal text-slate-500">· avanço global {c.avanco_pct ?? "—"} % · {c.em_atraso} tarefa(s) em atraso</span></p>
          <ul className="space-y-2">
            {c.tarefas.map((t) => (
              <li key={t.tarefa_id} className="grid items-center gap-2 sm:grid-cols-[1fr_10rem_auto]">
                <div><p>{t.titulo} {t.em_atraso && <span className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-800">Atraso{t.atraso_dias ? ` ${t.atraso_dias} d` : ""}</span>}</p><p className="text-xs text-slate-500">{day(t.inicio)} → {day(t.fim)} · previsto {t.esperado_pct ?? "—"} %{t.nota ? ` · ${t.nota}` : ""}</p></div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuenow={t.avanco_pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Avanço de ${t.titulo}`}><div className={`h-full ${t.em_atraso ? "bg-red-500" : "bg-emerald-600"}`} style={{ width: `${t.avanco_pct}%` }} /></div>
                {caps["cronograma.registar_avanco"] ? <input aria-label={`Novo avanço de ${t.titulo}`} type="number" min="0" max="100" placeholder={`${t.avanco_pct} %`} className="w-20 rounded border border-slate-300 px-1 py-0.5 text-right text-xs" value={pct[t.tarefa_id] ?? ""} onChange={(e) => setPct({ ...pct, [t.tarefa_id]: e.target.value })} /> : <span className="text-xs">{t.avanco_pct} %</span>}
              </li>))}
          </ul>
          {caps["cronograma.registar_avanco"] && <button type="button" className={`${primary} mt-3`} onClick={() => registar(c)}>Registar o avanço desta reunião</button>}
        </div>))}
    </section>
  );
}

/* ------------------------------------------------------------------ atas */
function Atas({ client, base, caps, empresas }) {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState(null);
  const load = useCallback(() => client.get(`${base}/atas`).then(({ data }) => setData(data)).catch((x) => err(x, "Atas indisponíveis")), [client, base]);
  useEffect(() => { load(); }, [load]);
  const nomes = Object.fromEntries(empresas.map((e) => [e.participant_id, e.nome]));
  const editar = caps["atas.editar"];

  const preparar = async () => { try { const { data } = await client.post(`${base}/atas/rascunho`); setDraft({ ata_id: null, numero: data.numero, data: data.data, presentes: "", resumo: "", linhas: data.linhas }); } catch (x) { err(x, "Rascunho impossível"); } };
  const setLinha = (i, patch) => setDraft((d) => ({ ...d, linhas: d.linhas.map((l, k) => (k === i ? { ...l, ...patch } : l)) }));
  const guardar = async (publicar) => {
    const body = { data: draft.data, presentes: draft.presentes, resumo: draft.resumo, linhas: draft.linhas.filter((l) => (l.ponto || "").trim()).map((l) => ({ empresa_id: l.empresa_id || null, ponto: l.ponto, ata_origem: l.ata_origem, estado: l.estado || "", fechado: !!l.fechado })) };
    try {
      const { data: saved } = draft.ata_id ? await client.put(`${base}/atas/${draft.ata_id}`, body) : await client.post(`${base}/atas`, body);
      if (publicar) await client.post(`${base}/atas/${saved.ata_id}/publicar`);
      toast.success(publicar ? "Ata publicada para todos os intervenientes" : "Ata guardada em rascunho"); setDraft(null); load();
    } catch (x) { err(x, "Gravação impossível"); }
  };
  if (!data) return <Empty>A carregar…</Empty>;

  return (
    <section className={card} data-testid="colab-atas">
      <Head title="Atas semanais de reunião de obra" sub="Uma linha por empresa e por ponto, a ata em que o ponto foi registado, e o estado: atraso, ponto importante ou para memória.">
        {editar && !draft && <button type="button" className={primary} onClick={preparar} data-testid="colab-ata-nova"><Plus className="h-4 w-4" /> Preparar a ata desta semana</button>}
      </Head>
      {draft && (
        <div className="space-y-3 border-b border-slate-200 p-4 text-sm" data-testid="colab-ata-draft">
          <p className="font-medium">Ata n.º {draft.numero}</p>
          <p className="text-xs text-slate-500">Rascunho preparado a partir da ata anterior, dos cronogramas, dos vistos pendentes e dos autos em validação. Reveja e complete antes de publicar.</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <input aria-label="Data" type="date" className={field} value={draft.data} onChange={(e) => setDraft({ ...draft, data: e.target.value })} />
            <input aria-label="Presentes" placeholder="Presentes" className={`${field} sm:col-span-2`} value={draft.presentes} onChange={(e) => setDraft({ ...draft, presentes: e.target.value })} />
          </div>
          <textarea aria-label="Informações principais" rows={2} placeholder="Informações principais discutidas na reunião" className={field} value={draft.resumo} onChange={(e) => setDraft({ ...draft, resumo: e.target.value })} />
          {draft.linhas.map((l, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[12rem_1fr_5rem_10rem_auto]">
              <select aria-label="Empresa" className={field} value={l.empresa_id || ""} onChange={(e) => setLinha(i, { empresa_id: e.target.value || null })}><option value="">Geral</option>{empresas.map((e) => <option key={e.participant_id} value={e.participant_id}>{e.nome}</option>)}</select>
              <input aria-label="Ponto" className={field} value={l.ponto} onChange={(e) => setLinha(i, { ponto: e.target.value })} />
              <input aria-label="Ata de origem" type="number" min="1" className={field} value={l.ata_origem || draft.numero} onChange={(e) => setLinha(i, { ata_origem: Number(e.target.value) })} />
              <select aria-label="Estado" className={field} value={l.estado || ""} onChange={(e) => setLinha(i, { estado: e.target.value })}>{Object.entries(data.estados).map(([k, v]) => <option key={k} value={k}>{v || "—"}</option>)}</select>
              <button type="button" className={danger} onClick={() => setDraft({ ...draft, linhas: draft.linhas.filter((_, k) => k !== i) })} aria-label="Remover linha"><Trash2 className="h-4 w-4" /></button>
            </div>))}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ghost} onClick={() => setDraft({ ...draft, linhas: [...draft.linhas, { empresa_id: null, ponto: "", ata_origem: draft.numero, estado: "" }] })}><Plus className="h-4 w-4" /> Acrescentar ponto</button>
            <button type="button" className={ghost} onClick={() => guardar(false)}>Guardar rascunho</button>
            <button type="button" className={primary} onClick={() => guardar(true)}>Publicar a ata</button>
            <button type="button" className={ghost} onClick={() => setDraft(null)}>Cancelar</button>
          </div>
        </div>)}
      {data.atas.length === 0 ? <Empty>Nenhuma ata publicada.</Empty> : data.atas.map((a) => (
        <div key={a.ata_id} className="border-b border-slate-200 p-4 text-sm last:border-b-0" data-testid={`colab-ata-${a.numero}`}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium">Ata n.º {a.numero} · {day(a.data)} {!a.publicada && <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs">Rascunho</span>}</p>
            {editar && !a.publicada && !draft && <button type="button" className={ghost} onClick={() => setDraft({ ...a })}>Retomar</button>}
          </div>
          {a.presentes && <p className="text-xs text-slate-500">Presentes: {a.presentes}</p>}
          {a.resumo && <p className="my-2">{a.resumo}</p>}
          <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="text-left text-slate-500"><th className="py-1">Empresa · ponto</th><th>Ata de origem</th><th>Estado</th></tr></thead>
            <tbody>{a.linhas.map((l, i) => (<tr key={i} className="border-t border-slate-100"><td className="py-1.5"><strong>{l.empresa_nome || nomes[l.empresa_id] || "Geral"}</strong> — {l.ponto}</td><td>n.º {l.ata_origem}</td><td>{l.estado_label}</td></tr>))}</tbody></table></div>
        </div>))}
    </section>
  );
}
