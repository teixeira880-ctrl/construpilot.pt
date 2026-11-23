#!/usr/bin/env python3
"""Língua declarada ao Google (construpilot.pt): pt-PT por omissão em vez de «fr», e sem tradução automática do Google.
Idempotente; cada âncora tem de existir exatamente uma vez, senão nada é escrito. Uso: python3 scripts/apply_claude_seo_lingua.py [--check]"""
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
ALT = {
    "frontend/src/components/SEO.jsx": ('cfg.lang || "pt-PT"', [
        ('  const lang = cfg.lang || "fr";\n  useEffect(() => { document.documentElement.lang = lang; }, [lang]);',
         '  // Site português: a língua declarada ao Google é sempre pt-PT, salvo página que indique outra.\n'
         '  const lang = cfg.lang || "pt-PT";\n'
         '  useEffect(() => { if (cfg.lang) document.documentElement.lang = lang; }, [lang, cfg.lang]);'),
        ('      <link rel="alternate" hrefLang={lang === "pt" ? "pt-PT" : "pt-PT"} href={url} />',
         '      <link rel="alternate" hrefLang="pt-PT" href={url} />'),
    ]),
    "frontend/public/index.html": ('name="google" content="notranslate"', [
        ('    <title>ConstruPilot — Orçamentos de obras com IA e estimativa de remodelação</title>',
         '    <meta http-equiv="content-language" content="pt-PT" />\n'
         '    <meta name="google" content="notranslate" />\n'
         '    <title>ConstruPilot — Orçamentos de obras com IA e estimativa de remodelação</title>'),
    ]),
}
check = "--check" in sys.argv
novos, erro = {}, False
for rel, (marca, pares) in ALT.items():
    p = R / rel
    s = p.read_text(encoding="utf-8")
    if marca in s:
        print("JA_APLICADO", rel); continue
    for a, b in pares:
        if s.count(a) != 1:
            print("ERRO", rel, "âncora encontrada", s.count(a), "vez(es):", a[:60]); erro = True; break
        s = s.replace(a, b)
    else:
        novos[p] = s; print("VERIFICADO" if check else "OK", rel)
if erro:
    print("FIM_ERRO — nada foi escrito"); sys.exit(1)
if not check:
    for p, s in novos.items():
        p.write_text(s, encoding="utf-8")
print("FIM_OK")
