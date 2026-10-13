import { Link } from "react-router-dom";
import { useExperienceCopy } from "./experienceCopy";
export function WorkspaceFooter() {
  const copy = useExperienceCopy();
  return <footer className="workspace-footer"><span>© {new Date().getFullYear()} ConstruPilot</span><nav aria-label="ConstruPilot"><Link to="/aide">{copy("help")}</Link><Link to="/confidentialite">{copy("privacy")}</Link><Link to="/mentions-legales">{copy("legal")}</Link></nav></footer>;
}
