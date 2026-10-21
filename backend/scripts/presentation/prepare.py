"""Demo-only source documents and real assistant results. Never sends correspondence."""
import json
from pathlib import Path

import ezdxf
import fitz

from config import BASE, WORK, api_session, read_state, save_state


def sources():
    drawing = WORK / "Appartement-temoin.dxf"
    if not drawing.exists():
        doc = ezdxf.new("R2013"); doc.header["$INSUNITS"] = 4
        for name, color in [("MURS", 7), ("CLOISONS", 8), ("TEXTES", 7), ("OUVERTURES", 5)]:
            doc.layers.new(name, dxfattribs={"color": color})
        space = doc.modelspace()
        def rect(x, y, w, h, layer="MURS"):
            space.add_lwpolyline([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],close=True,dxfattribs={"layer":layer})
        rect(0,0,12000,8000); rect(200,200,11600,7600)
        for x,y,w,h in [(5900,200,150,7600),(6050,3900,5750,150),(9000,200,150,3700),(200,2500,5700,150)]:
            rect(x,y,w,h,"CLOISONS")
        for x,y,w,h in [(1200,-30,2200,260),(7200,7780,2000,250),(11800,4900,230,1800),(11800,1500,230,1500)]:
            rect(x,y,w,h,"OUVERTURES")
        for text,x,y in [("SEJOUR / CUISINE",1700,5300),("CHAMBRE 1",7600,6000),("CHAMBRE 2",6500,2200),("SALLE D'EAU",9350,2300),("ENTREE / BUREAU",1300,1400)]:
            space.add_text(text,dxfattribs={"height":240,"insert":(x,y),"layer":"TEXTES"})
        for text,x,y,h in [("APPARTEMENT TEMOIN",1000,9300,400),("PLAN DE DEMONSTRATION - NON DESTINE A L'EXECUTION",1000,8600,200),("12.00 m",5100,-600,230),("Surface de reference : 96 m2 - unite du fichier : mm",1000,-1400,200)]:
            space.add_text(text,dxfattribs={"height":h,"insert":(x,y),"layer":"TEXTES"})
        doc.saveas(drawing)
    brief = WORK / "Cahier-des-charges-demonstration.pdf"
    if not brief.exists():
        doc=fitz.open(); page=doc.new_page(width=595,height=842)
        page.draw_rect(fitz.Rect(0,0,595,126),color=(.03,.14,.10),fill=(.03,.14,.10))
        page.insert_text((42,57),"CONSTRUPILOT",fontsize=24,color=(.8,.96,.32),fontname="hebo")
        page.insert_text((42,88),"Appartement temoin - Note de travaux",fontsize=16,color=(1,1,1))
        text=("DOCUMENT DE DEMONSTRATION - AUCUNE DONNEE PERSONNELLE\n\n"
              "Client : Client demonstration\nProjet : Renovation d'un appartement temoin.\n\n"
              "TRAVAUX A CHIFFRER\n\n"
              "1. Peinture des murs : 40 m2, preparation puis deux couches. Prix HT fourni : 18 EUR/m2.\n\n"
              "2. Peinture du plafond : 24 m2. Prix HT fourni : 16 EUR/m2.\n\n"
              "3. Protection des sols : forfait de 95 EUR HT.\n\n"
              "TVA indiquee pour cette demonstration : 20 %.\nLe devis doit rester un BROUILLON, sans envoi au client.\n\n"
              "POINTS A VERIFIER SUR SITE\nEtat des supports, humidite, acces et quantites definitives.\nLes prix sont des donnees d'exemple, pas une offre commerciale.")
        page.insert_textbox(fitz.Rect(42,156,548,760),text,fontsize=12,lineheight=1.55)
        doc.save(brief)
    return drawing, brief


def main():
    state=read_state(); session, auth=api_session()
    drawing,brief=sources()
    def post(path, **kwargs):
        r=session.post(BASE+"/api"+path,timeout=180,**kwargs); r.raise_for_status(); return r.json()
    if not state.get("plan_id"):
        with drawing.open("rb") as f:
            plan=post("/takeoffs/upload",files={"file":(drawing.name,f,"application/dxf")},data={"cad_unit":"mm"})
        state["plan_id"]=plan["plan_id"]; save_state(state); print("DXF demo imported",state["plan_id"],flush=True)
    if not state.get("attachment_id"):
        with brief.open("rb") as f:
            attachment=post("/assistant/documents",files={"file":(brief.name,f,"application/pdf")},data={"kind":"cctp"})
        state["attachment_id"]=attachment["doc_id"]; save_state(state)
    if not state.get("quote_conversation"):
        conv=post("/assistant/conversations",json={"title":"Appartement témoin — préparer le devis"})
        state["quote_conversation"]=conv["conversation_id"];save_state(state)
    messages=[
        ("summary","À partir du cahier des charges joint, résume les travaux en trois points et les vérifications à prévoir sur le chantier. Réponds en français, de manière concise. C'est une démonstration, aucune donnée réelle de client."),
        ("quote","Crée maintenant le devis Appartement témoin — rénovation peinture, pour Client démonstration, avec les quantités, prix HT et TVA indiqués dans le document : murs 40 m² à 18 €/m², plafond 24 m² à 16 €/m², protection des sols forfait 95 € HT, TVA 20 %. Enregistre-le dans Suivi devis, uniquement en brouillon. Aucun envoi, aucun email."),
    ]
    for key,text in messages:
        if state.get(key+"_done"): continue
        result=post("/assistant/message",json={"conversation_id":state["quote_conversation"],"request_id":"presentation-fr-2026-"+key,"text":text,"response_mode":"fast","web_enabled":False,"doc_ids":[state["attachment_id"]]})
        (WORK/f"assistant_{key}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
        for action in result.get("actions",[]):
            if action.get("tool")=="create_quote_draft" and action.get("result",{}).get("ok"):
                state["quote_id"]=action["result"]["doc_id"]
        state[key+"_done"]=True;save_state(state);print("Real assistant turn saved:",key,flush=True)
    if not state.get("quote_id"):
        raise RuntimeError("Assistant did not create quote; inspect real response, do not invent a result")
    if not state.get("analysis_done"):
        current=session.get(BASE+f"/api/takeoffs/{state['plan_id']}",timeout=60);current.raise_for_status()
        existing=current.json().get('ai_analysis') or {}
        result=existing if existing.get('rooms') and not existing.get('error') else post(f"/takeoffs/{state['plan_id']}/analyze")
        (WORK/"plan_analysis.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
        state["analysis_done"]=True;save_state(state);print("Real plan analysis completed",flush=True)
    state["autocad_plan_id"]="plan_33974e93a5e5"
    save_state(state)
    print("Prepared demo assets; no DWG job, mail, invoice, or payment executed.",flush=True)


if __name__=="__main__": main()