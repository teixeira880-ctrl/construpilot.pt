import { catalog } from "@/connect/engine";
import { QualifyPage } from "./ConnectInvestor";

export default function ConnectPartner() {
  const par = catalog.partner;
  return (
    <QualifyPage profile="partner" title="par_title" required={["partner_type"]}
      validate={(a) => !a.website || /^(https?:\/\/)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(\/\S*)?$/.test(a.website)}
      fields={[
        { key: "partner_type", label: "par_q_type", options: par.types },
        { key: "organization", label: "f_org", kind: "text", max: 120 },
        { key: "website", label: "f_website", kind: "text", max: 200 },
        { key: "kinds", label: "par_q_kinds", options: par.kinds, multi: true },
        { key: "geos", label: "par_q_geos", options: catalog.investor.geos, multi: true },
        { key: "clients_desc", label: "par_q_clients", kind: "textarea", max: 300 },
        { key: "scale", label: "par_q_scale", options: par.scale, columns: 3 },
        { key: "timeline", label: "par_q_timeline", options: par.timeline, columns: 3 },
      ]} />
  );
}
