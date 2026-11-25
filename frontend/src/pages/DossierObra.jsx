import { useState } from "react";
import { Link, Route, Routes, useLocation, useParams } from "react-router-dom";
import { useDossierContext, useOverview, useCatalog, useMode, DossierNav, DossierTree, Loading, ErrorBox } from "@/components/dossierObra/common";
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
  const { chantierId } = useDossierContext();
  const { data: ov, error, reload } = useOverview(chantierId);
  const cat = useCatalog();
  const [mode, setMode] = useMode();
  const [hasAssistant, setHasAssistant] = useState(false);
  const location = useLocation();
  const activeKey = (location.pathname.match(/\/especialidade\/([^/?]+)/) || [])[1];

  if (error === "notfound") return <ErrorBox>Processo não encontrado. <Link to="/chantiers" className="text-primary underline">Voltar às obras</Link></ErrorBox>;
  if (error) return <ErrorBox onRetry={reload}>{error}</ErrorBox>;
  if (!ov || !cat) return <Loading>A abrir o dossier de obra…</Loading>;
  const isCompile = location.pathname.endsWith("/compilar");
  return (
    <div className={`dob ${hasAssistant ? "assistant-open" : ""}`} data-testid="dossier-obra">
      <DossierNav active={isCompile ? "final" : new URLSearchParams(location.search).get("vista") === "especialidades" ? "especialidades" : "overview"} />
      <div className={`dob-layout ${hasAssistant ? "has-assistant" : ""}`}>
        <DossierTree overview={ov} activeKey={activeKey} />
        <Routes>
          <Route index element={<div className="min-w-0"><Overview ov={ov} cat={cat} mode={mode} reload={reload} /></div>} />
          <Route path="especialidade/:key" element={<SpecialtyRoute cat={cat} mode={mode} setMode={setMode} reloadTree={reload} setHasAssistant={setHasAssistant} />} />
          <Route path="compilar" element={<div className="min-w-0"><Compile ov={ov} cat={cat} mode={mode} /></div>} />
        </Routes>
      </div>
    </div>
  );
}
