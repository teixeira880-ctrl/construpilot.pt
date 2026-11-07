"""Gera brand-v2.css a partir de brand-v2.source.css, reforçando a especificidade
(:root:root) para as regras ganharem às folhas carregadas depois (páginas em lazy-load)."""
import pathlib, re
here = pathlib.Path(__file__).resolve().parent
src = (here / "brand-v2.source.css").read_text(encoding="utf-8")
src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
out, i, depth = [], 0, 0
B = ":root:root"
def boost(sel):
    parts = []
    pieces, cur, d = [], "", 0
    for ch in sel:
        if ch == "(": d += 1
        elif ch == ")": d -= 1
        if ch == "," and d == 0: pieces.append(cur); cur = ""
        else: cur += ch
    pieces.append(cur)
    for p in pieces:
        p = p.strip()
        if not p: continue
        if p.strip() == ":root": parts.append(p)
        elif p.startswith(":root"): parts.append(B + p)
        elif p.startswith(".dark"): parts.append(B + p)
        else: parts.append(f"{B} {p}")
    return ", ".join(parts)
# splitter simples por chavetas (sem nesting além de @media)
tokens = re.split(r"([{}])", src)
buf, stack = "", []
for t in tokens:
    if t == "{":
        head = buf.strip()
        if head.startswith("@"): out.append(head + " {"); stack.append("at")
        else: out.append(boost(head) + " {"); stack.append("rule")
        buf = ""
    elif t == "}":
        if stack and stack[-1] == "rule": out.append(buf.strip() + " }")
        else: out.append("}")
        stack.pop(); buf = ""
    else:
        buf += t
css = "/* ConstruPilot PT — Interface v2 (Lote 109). Gerado por build_css.py — editar brand-v2.source.css */\n" + "\n".join(out) + "\n"
(here / "brand-v2.css").write_text(css, encoding="utf-8")
print("brand-v2.css", len(css), "bytes")
