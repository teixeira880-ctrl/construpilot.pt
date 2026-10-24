import { useState } from "react";
import { Ruler, FileText, HardHat, ArrowUpRight, Check, FolderOpen } from "lucide-react";

export function ProductPreview() {
  const [tab, setTab] = useState("plan");
  const tabs = [{ key: "plan", title: "A planta", icon: Ruler }, { key: "devis", title: "O orçamento", icon: FileText }, { key: "suivi", title: "O acompanhamento", icon: HardHat }];
  return <div className="landing-product-preview" data-testid="landing-product-preview">
    <div className="landing-preview-top"><span className="landing-preview-mark"><HardHat size={19} /></span><span>O meu espaço de trabalho<small>Projeto de remodelação</small></span><span className="landing-preview-dot" /></div>
    <div className="landing-preview-tabs" role="group" aria-label="Escolher uma pré-visualização">{tabs.map(({ key, title, icon: Icon }) => <button type="button" key={key} onClick={() => setTab(key)} aria-pressed={tab === key} data-testid={`landing-preview-${key}`}><Icon size={15} />{title}</button>)}</div>
    <div className="landing-preview-content" data-testid="landing-preview-panel">
      {tab === "plan" && <><div className="landing-preview-heading"><span><small>PLANTAS & MEDIÇÕES</small><strong>Cada medida no seu lugar.</strong></span><Ruler size={20} /></div>
        <svg viewBox="0 0 460 260" className="landing-floorplan" role="img" aria-label="Ilustração de uma planta com divisões e medidas a controlar">
          <defs><pattern id="landing-plan-grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#d5c9b4" strokeWidth=".6" /></pattern></defs>
          <rect width="460" height="260" fill="url(#landing-plan-grid)" />
          <path d="M62 42H386V216H62Z" fill="#f6eee1" stroke="#1a5670" strokeWidth="7" />
          <path d="M268 42V146H386M62 146H172V216M268 146V216" fill="none" stroke="#1a5670" strokeWidth="5" />
          <path d="M88 43H186M316 43H360M63 164V194" stroke="#c28a60" strokeWidth="8" />
          <path d="M211 146H251M132 146H168M268 171V202" stroke="#f6eee1" strokeWidth="8" />
          <path d="M211 146V109A37 37 0 0 1 248 146M268 201H237A31 31 0 0 1 268 170" fill="none" stroke="#a26a44" strokeWidth="1.2" />
          <text x="162" y="97" textAnchor="middle">Sala de estar</text><text x="326" y="97" textAnchor="middle">Quarto</text><text x="112" y="187" textAnchor="middle">Cozinha</text><text x="326" y="187" textAnchor="middle">Casa de banho de serviço</text>
          <path d="M62 25H386M62 19V31M386 19V31" stroke="#9c6849" strokeWidth="1.2" /><circle cx="62" cy="216" r="5" fill="#b67a51" />
        </svg><div className="landing-preview-summary"><span><Check size={15} />Escala e quantidades a controlar</span><ArrowUpRight size={16} /></div></>}
      {tab === "devis" && <><div className="landing-preview-heading"><span><small>ORÇAMENTOS & ORÇAMENTAÇÃO</small><strong>Linhas claras. Um total legível.</strong></span><FileText size={20} /></div><div className="landing-demo-document"><span className="landing-demo-document-title">Orçamento · Remodelação</span>{[["Preparação da obra", "1 250 €"], ["Divisórias e isolamento", "6 800 €"], ["Revestimentos e acabamentos", "10 400 €"]].map(([l, v]) => <div key={l}><span>{l}</span><b>{v}</b></div>)}<div className="landing-demo-total"><span>Total s/ IVA</span><b>18 450 €</b></div></div><div className="landing-preview-summary"><span><Check size={15} />Um documento à sua imagem</span><ArrowUpRight size={16} /></div></>}
      {tab === "suivi" && <><div className="landing-preview-heading"><span><small>PROCESSO DE OBRA</small><strong>O documento certo, no sítio certo.</strong></span><FolderOpen size={20} /></div><div className="landing-demo-tasks">{[["Plantas do projeto", "A verificar", Ruler], ["Orçamento de remodelação", "Rascunho", FileText], ["Próxima visita", "A planear", HardHat]].map(([l, status, Icon]) => <div key={l}><Icon size={20} /><span><strong>{l}</strong><small>{status}</small></span><ArrowUpRight size={16} /></div>)}</div><div className="landing-preview-summary"><span><Check size={15} />A informação fica reunida</span><ArrowUpRight size={16} /></div></>}
    </div>
    <p className="landing-preview-caption">Pré-visualização ilustrativa · dados de demonstração</p>
  </div>;
}
