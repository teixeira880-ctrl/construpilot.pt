import { useEffect } from "react";
import { Link, Route, Routes, useLocation, useParams } from "react-router-dom";
import { useDossierContext, useOverview, useCatalog, useMode, DossierNav, DossierTree, Loading, ErrorBox } from "@/components/dossierObra/common";
import { setDossierSidebar } from "@/components/dossierObra/sidebarStore";
import { Overview } from "@/components/dossierObra/Overview";
import { Specialty } from "@/components/dossierObra/Specialty";
import { Compile } from "@/components/dossierObra/Compile";
import "@/styles/dossier-obra.css";

/** Dossier de Obra: centro de trabalho da obra (visão geral, especialidades, compilação). */
export default function DossierObra() {
  const { chantierId } = useParams();
  return <DossierObraContent key={chantierId} />;
}

function SpecialtyRoute(props) {
  const { key } = useParams();
  return <Specialty key={key} {...props} />;
}

function DossierObraContent() {
  const { chantierId, base, qs } = useDossierContext();
  const { data: ov, error, reload } = useOverview(chantierId);
  const cat = useCatalog();
  const [mode, setMode] = useMode();
  const location = useLocation();
  const activeKey = (location.pathname.match(/\/especialidade\/([^/?]+)/) || [])[1];
  const isCompile = location.pathname.endsWith("/compilar");
  const isOverview = !activeKey && !isCompile;

  // A árvore de especialidades vive no menu lateral verde (computador); no telemóvel, dentro da página.
  useEffect(() => {
    if (ov) setDossierSidebar({ overview: ov, activeKey, base, qs, compile: isCompile });
  }, [ov, activeKey, base, qs, isCompile]);
  useEffect(() => () => setDossierSidebar(null), []);

  if (error === "notfound") return <ErrorBox>Processo não encontrado. <Link to="/chantiers" className="text-primary underline">Voltar às obras</Link></ErrorBox>;
  if (error) return <ErrorBox onRetry={reload}>{error}</ErrorBox>;
  if (!ov || !cat) return <Loading>A abrir o dossier de obra…</Loading>;
  return (
    <div className="dob" data-testid="dossier-obra">
      {isOverview && <DossierNav active={new URLSearchParams(location.search).get("vista") === "especialidades" ? "especialidades" : "overview"} />}
      <div className="dob-mobile-tree"><DossierTree overview={ov} activeKey={activeKey} /></div>
      <Routes>
        <Route index element={<Overview ov={ov} cat={cat} mode={mode} reload={reload} />} />
        <Route path="especialidade/:key" element={<SpecialtyRoute cat={cat} mode={mode} setMode={setMode} reloadTree={reload} />} />
        <Route path="compilar" element={<Compile ov={ov} cat={cat} mode={mode} />} />
      </Routes>
    </div>
  );
}
