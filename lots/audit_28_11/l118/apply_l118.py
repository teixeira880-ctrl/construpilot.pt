"""Lot 118 (FR + PT) — bulle « Besoin d'aide ? » : le gras s'affichait en Markdown brut (« **bibliothèque de prix** »).
Rendu du gras (**…**) dans les réponses de l'assistant d'aide ; les messages de l'utilisateur restent tels quels.

Usage : python3 lots/l118/apply_l118.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-10)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
MARK = "CP-AUDIT-NUIT-10"
p = root / "frontend/src/components/HelpChatbot.jsx"
txt = p.read_text(encoding="utf-8")
OLD_USE = """whitespace-pre-wrap ${m.role === "user" ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-secondary text-foreground rounded-bl-sm"}`}>
                    {m.content}
"""
NEW_USE = """whitespace-pre-wrap ${m.role === "user" ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-secondary text-foreground rounded-bl-sm"}`}>
                    {m.role === "user" ? m.content : boldMd(m.content)}
"""
OLD_DEF = "export default function HelpChatbot() {"
NEW_DEF = (f"// {MARK} : **gras** des réponses rendu en gras (au lieu des astérisques bruts)\n"
           "const boldMd = (s) => String(s || \"\").split(/(\\*\\*[^*\\n]+\\*\\*)/g).map((part, i) =>\n"
           "  part.length > 4 && part.startsWith(\"**\") && part.endsWith(\"**\") ? <strong key={i}>{part.slice(2, -2)}</strong> : part);\n\n"
           "export default function HelpChatbot() {")
if MARK in txt:
    print("DÉJÀ      aide : gras rendu")
elif txt.count(OLD_USE) != 1 or txt.count(OLD_DEF) != 1:
    print("IGNORÉ    aide : gras rendu (ancre absente)")
else:
    p.write_text(txt.replace(OLD_USE, NEW_USE).replace(OLD_DEF, NEW_DEF), encoding="utf-8")
    print("OK        aide : gras rendu")
