"""Lote 109 PT — Blog HeyCatch em /blog e /blog/:slug (guia https://heycatch.ai/blog-agents.md).

  · backend/routes/heycatch_blog.py : GET /api/blog/heycatch (todos os artigos, paginação offset/50) e
    GET /api/blog/heycatch/{slug} (content_html limpo no servidor) ; chave em HEYCATCH_API_KEY (backend/.env),
    só em parâmetro `key` ; 401/403 → vazio, 404 → 404, 429 → Retry-After + 1 nova tentativa, cache 120 s.
  · /api/blog/sitemap.xml inclui cada artigo HeyCatch (lastmod = updated).
  · /blog : artigos HeyCatch no mesmo cartão (título, data, tempo de leitura), paginação ?page=, estado vazio.
  · /blog/:slug : h1 único, data, leitura, pontos-chave → índice (h2 com id, sem FAQ) → corpo → FAQ ; SEO
    (title, description, OG, canonical absoluto, JSON-LD com < → \\u003c, lang/dir) ; slug desconhecido → 404.
Idempotente ; ARRÊT (nada escrito) se faltar uma âncora. Uso : python3 lots/l109_blog_heycatch/apply.py /app
"""
import json
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/app")
here = pathlib.Path(__file__).resolve().parent
if (root / "backend" / "routes" / "heycatch_blog.py").exists() and "HeyCatchBlogPost" in (root / "frontend/src/pages/BlogPost.jsx").read_text(encoding="utf-8"):
    print("já aplicado"); print("L109 OK"); sys.exit(0)
EDITS = json.loads((here / "edits.json").read_text(encoding="utf-8"))
cur = {}
for f, old, new in EDITS:
    if f not in cur:
        cur[f] = (root / f).read_text(encoding="utf-8")
    if cur[f].count(old) != 1:
        print("ÂNCORA não encontrada — ARRÊT, nada escrito:", f, "|", old.strip()[:90].replace("\n", " ⏎ ")); sys.exit(1)
    cur[f] = cur[f].replace(old, new, 1)
for f, s in cur.items():
    if f.endswith(".py"):
        compile(s, f, "exec")
for f, s in cur.items():
    (root / f).write_text(s, encoding="utf-8")
shutil.copy(here / "heycatch_blog.py", root / "backend" / "routes" / "heycatch_blog.py")
shutil.copy(here / "HeyCatchBlogPost.jsx", root / "frontend" / "src" / "components" / "HeyCatchBlogPost.jsx")
print("ficheiros:", ", ".join(sorted(cur)))
print("L109 OK")
