"""Imagens realistas do processo — o mais fotorrealistas possível, SEM alterar a geometria.

Cadeia automática (sem perguntas):
1. Vista 3D exata gerada no servidor (render3d / interiores) — a referência geométrica.
2. Runway gen4_image → OpenAI gpt-image-1 (edição, alta fidelidade) → Emergent (Gemini, chave universal):
   cada fornecedor só entra se o anterior falhar ou não passar os controlos.
3. Controlos: verificação numérica dos contornos (geometria) + Claude como juiz por visão (realismo 0-10 e geometria);
   os defeitos apontados pelo Claude entram nas instruções do fornecedor seguinte.
4. Se tudo falhar: fica a vista exata (nunca uma imagem inventada).
Antes / depois: ortofotomapa oficial (DGT) do terreno e a mesma vista com a implantação desenhada à escala,
depois tornada fotorrealista pelo mesmo processo.

Todas as imagens são ILUSTRATIVAS; as medidas de referência são as das peças desenhadas.
"""
from __future__ import annotations

import base64
import io
import logging
import math
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from engines.urbanismo_pt.auto import estilos as E
from engines.urbanismo_pt.auto import pecas_auto as PA
from engines.urbanismo_pt.auto import render3d as R3

log = logging.getLogger(__name__)

# Calibração inicial (vista exata vs. outra vista ≈ 0,35; mesma vista com texturas/ruído ≥ 0,95).
# A afinar com imagens reais no ambiente de teste — configurável sem novo deploy.
LIMIAR_GEOMETRIA = float(os.environ.get("URB_IMG_LIMIAR_GEOMETRIA", "0.45"))
NOTA = "Imagem ilustrativa gerada sobre a geometria exata do projeto; as medidas de referência são as das peças desenhadas."

_REGIAO_NORTE = ("braga", "viana", "porto", "guimar", "barcelos", "famalic", "vila real", "braganc", "amarante",
                 "penafiel", "fafe", "povoa de lanhoso", "ponte de lima", "arcos", "melga", "chaves", "viseu")
_REGIAO_SUL = ("evora", "beja", "portalegre", "setubal", "faro", "loule", "albufeira", "lagos", "tavira", "portimao",
               "silves", "odemira", "grandola", "alcacer", "elvas", "estremoz")


def _paisagem(concelho: str) -> str:
    c = (concelho or "").lower()
    import unicodedata
    c = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode()
    if any(k in c for k in _REGIAO_NORTE):
        return "green landscape of northern Portugal, granite walls, vineyards and native oaks in the background"
    if any(k in c for k in _REGIAO_SUL):
        return "southern Portugal landscape, dry golden grass, olive, cork oak and carob trees, strong Mediterranean light"
    return "central Portugal countryside, pine and olive trees, soft hills"


# Nível exigido: visualização de arquitetura profissional (imobiliário de gama alta, renders tipo V-Ray/Corona/D5).
QUALIDADE = ("high-end real-estate architectural visualization, indistinguishable from a professional V-Ray / Corona render "
             "or a magazine photograph, physically based materials with real texture detail (stone grain, timber grain, render "
             "micro-texture), accurate global illumination and ambient occlusion, soft contact shadows, realistic glass with "
             "reflections and visible interior depth, perfectly straight vertical lines, sharp 4K detail")
NEGATIVO = "no people, no cars in the foreground, no text, no watermark, no logo, no distortion, no cartoon or CGI look"
ILUMINACAO = {
    "dia": "late-afternoon sun, deep blue sky with a few soft white clouds, warm sunlight raking across the facade",
    "entardecer": "blue-hour dusk just after sunset, glowing warm interior lights visible through every window, hidden LED "
                  "strips under eaves and in the garden, illuminated pool glowing turquoise, deep blue-violet sky",
}
# vistas fotorrealistas extra que reutilizam a vista exata de outra (só muda a luz): nome → (vista exata, iluminação)
VARIANTES = {"perspetiva_entardecer": ("perspetiva", "entardecer")}


def _arranjos(processo: Dict[str, Any], concelho: str) -> str:
    a = processo.get("auto") or {}
    piscina = ("the blue area is the swimming pool: crystal-clear turquoise water with light caustics, light stone coping, "
               "large-format travertine or light stone deck with designer sun loungers and a parasol; " if a.get("piscina") else "")
    return (piscina + "manicured lawn, gravel and light stone paving, ornamental grasses, lavender, rosemary and agapanthus "
            "beds, a few mature olive trees, low rendered garden walls with timber gate, outdoor dining table on the terrace; "
            + _paisagem(concelho))


def prompt_vista(processo: Dict[str, Any], vista: str, estrito: bool = False, luz: str = "dia") -> str:
    a = processo.get("auto") or {}
    mats = a.get("materiais") or {}
    est = E.obter((a.get("estilo") or {}).get("id"))
    concelho = (processo.get("terreno") or {}).get("concelho") or ""
    enquadr = {"perspetiva": "eye-level three-quarter view from the front garden",
               "frente": "eye-level frontal view from the front garden", "tardoz": "eye-level view from the back garden",
               "piscina": "eye-level view from across the swimming pool towards the house, pool in the foreground",
               "aerea": "elevated three-quarter drone view"}.get(vista, "eye-level view")
    regra = ("Keep the geometry 100% identical to the reference image: same volumes and footprint (including the L shape), "
             "same roof shape and height, same number of floors, every window and door in exactly the same position and size, "
             "same detached garage and swimming pool, same camera position, lens and framing. Do not add, remove, move or "
             "resize any window, door, floor, balcony, chimney, volume or pool. ")
    if estrito:
        regra = ("STRICT: this is a texture-and-lighting pass ONLY. The output must overlay pixel-for-pixel onto the reference: "
                 "identical silhouette and edges of every building, window and door. " + regra)
    return (
        f"Ultra photorealistic architectural photograph, {enquadr}, of THIS exact house. " + regra +
        f"Style: {est['render']}. Replace the flat colours with real materials: facade = "
        f"{PA.MATERIAIS_FACHADA.get(mats.get('fachada'), 'white render')} (grey areas = natural split-face granite "
        f"stone cladding with real joints, brown areas = warm vertical timber slats with visible grain, light areas = render; "
        f"keep each material exactly on the faces where the reference shows it); roof = {PA.MATERIAIS_COBERTURA.get(mats.get('cobertura'), 'clay tiles')}; "
        f"window frames = {PA.CAIXILHARIA.get(mats.get('caixilharia'), 'anthracite aluminium')}, slim profiles; dark rectangles = "
        "floor-to-ceiling clear glazing showing a furnished, warmly lit interior. Landscaping (only on the ground, never on "
        f"the building): {_arranjos(processo, concelho)}. Lighting: {ILUMINACAO.get(luz, ILUMINACAO['dia'])}. "
        f"{QUALIDADE}, 35mm lens. {NEGATIVO}."
    )


# ------------------------------------------------------------------ verificação de geometria
def _contornos(im: Image.Image, size=(384, 256)) -> np.ndarray:
    g = im.convert("L").resize(size, Image.BILINEAR).filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(2.2))
    a = np.asarray(g, dtype=np.float64)
    return a / (a.max() + 1e-9)


def semelhanca_geometria(ref_png: bytes, gen_bytes: bytes, mascara_png: bytes) -> float:
    """Correlação dos contornos (vista exata vs imagem gerada) dentro da silhueta dilatada da construção (0..1)."""
    ref = Image.open(io.BytesIO(ref_png))
    gen = Image.open(io.BytesIO(gen_bytes)).convert("RGB").resize(ref.size, Image.BILINEAR)
    m = Image.open(io.BytesIO(mascara_png)).resize((384, 256), Image.NEAREST).filter(ImageFilter.MaxFilter(9))
    mk = np.asarray(m) > 0
    if mk.sum() < 50:
        return 1.0
    a, b = _contornos(ref)[mk], _contornos(gen)[mk]
    a, b = a - a.mean(), b - b.mean()
    den = math.sqrt(float((a * a).sum() * (b * b).sum())) + 1e-9
    return max(0.0, float((a * b).sum() / den))


# ------------------------------------------------------------------ fornecedores (cadeia automática)
# Ordem pedida pelo cliente: Runway → OpenAI (gpt-image-1, chave da empresa) → Emergent (Gemini, chave universal).
# Claude não gera imagens: é o JUIZ (realismo + geometria, por visão) e reescreve as instruções da ronda seguinte
# a partir dos defeitos que encontrou. Fornecedor sem chave configurada é saltado sem erro.
ORDEM_FORNECEDORES = [f.strip() for f in os.environ.get("URB_IMG_FORNECEDORES", "runway,openai,gemini").split(",") if f.strip()]
REALISMO_MIN = float(os.environ.get("URB_IMG_REALISMO_MIN", "7"))
ASPETO = {"runway": 16 / 9}           # proporção imposta pelo fornecedor (a referência é alargada, nunca deformada)


def disponivel(nome: str) -> bool:
    if nome == "runway":
        return bool(os.environ.get("RUNWAYML_API_SECRET"))
    if nome == "openai":
        try:
            from engines.llm_keys import openai_direct_active
            return openai_direct_active()
        except Exception:  # noqa: BLE001
            return bool(os.environ.get("OPENAI_API_KEY"))
    return True   # gemini (Emergent): tenta sempre; sem chave falha e passa-se à vista exata


async def _gemini(prompt: str, ref: bytes, sessao: str, extra: Optional[List[bytes]] = None) -> bytes:
    from engines import image_studio
    imgs = await image_studio.generate(prompt=prompt, provider="gemini", reference_images=[*(extra or []), ref], number=1,
                                       feature="licenciamento_imagens", session_id=sessao,
                                       model=os.environ.get("URB_IMG_GEMINI_MODEL") or None)
    return imgs[0][0]


_MODELO_OPENAI: Dict[str, Any] = {}


def _ordem_modelos_imagem(ids: List[str]) -> List[str]:
    """Modelos de imagem com edição: primeiro as versões estáveis «gpt-image-N[.M]» da mais recente para a mais antiga,
    depois as variantes com sufixo (ex.: -flare, -sunburst — possivelmente pré-visualizações) e por fim as datadas/mini."""
    import re
    cands = [i for i in ids if i.startswith("gpt-image")]

    def chave(i):
        m = re.match(r"gpt-image-(\d+)(?:\.(\d+))?(.*)$", i)
        if not m:
            return (False, (0, 0), False, False)
        resto = m.group(3)
        estavel = resto == ""
        return (estavel, (int(m.group(1)), int(m.group(2) or 0)), "mini" not in resto, not re.search(r"-20\d\d", resto))
    return sorted(cands, key=chave, reverse=True)


async def _modelo_openai(client) -> str:
    """O modelo configurado (URB_IMG_OPENAI_MODEL) ou, se não existir nesta conta, o melhor modelo de imagem
    disponível na lista de modelos da conta. Resultado guardado em memória (1 consulta por arranque)."""
    if os.environ.get("URB_IMG_OPENAI_MODEL"):
        return os.environ["URB_IMG_OPENAI_MODEL"]
    if "id" not in _MODELO_OPENAI:
        try:
            ids = [m.id async for m in client.models.list()]
            ordem = _ordem_modelos_imagem(ids)
            _MODELO_OPENAI["id"] = ordem[0] if ordem else "gpt-image-1"
        except Exception:  # noqa: BLE001
            _MODELO_OPENAI["id"] = "gpt-image-1"
    return _MODELO_OPENAI["id"]


async def _openai(prompt: str, ref: bytes, sessao: str, extra: Optional[List[bytes]] = None) -> bytes:
    """Edição de imagem OpenAI (família gpt-image) a partir da vista exata, alta fidelidade à imagem de entrada."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=170, max_retries=0)
    modelo = await _modelo_openai(client)
    im = Image.open(io.BytesIO(ref))
    size = "1536x1024" if im.width > im.height * 1.15 else ("1024x1536" if im.height > im.width * 1.15 else "1024x1024")
    imagens = [(f"ref{k}.png", b, "image/png") for k, b in enumerate([*(extra or []), ref])]
    args = dict(model=modelo, image=imagens if len(imagens) > 1 else imagens[0], prompt=prompt[:30000],
                size=size, quality="high", n=1)
    try:
        try:
            r = await client.images.edit(**args, extra_body={"input_fidelity": "high"})
        except Exception as e:  # noqa: BLE001
            if "input_fidelity" not in str(e):
                raise
            r = await client.images.edit(**args)     # modelo sem esse parâmetro
    except Exception as e:  # noqa: BLE001
        if "does not exist" in str(e):
            _MODELO_OPENAI.pop("id", None)   # o modelo deixou de existir: volta a escolher no próximo pedido
        try:
            from engines.llm_keys import note_openai_error
            await note_openai_error(e)   # crédito esgotado / chave inválida → disjuntor para a chave Emergent
        except Exception:  # noqa: BLE001
            pass
        raise
    try:
        from engines.expenses.store import observe
        await observe(source="licenciamento_imagens", source_id=sessao, provider="openai_direct", feature="licenciamento_imagens",
                      model=modelo, units={"images": 1}, state="completed")
    except Exception:  # noqa: BLE001
        pass
    return base64.b64decode(r.data[0].b64_json)


async def _runway(prompt: str, ref: bytes, sessao: str = "", extra: Optional[List[bytes]] = None) -> bytes:
    import asyncio
    import httpx
    from runwayml import AsyncRunwayML
    client = AsyncRunwayML(api_key=os.environ["RUNWAYML_API_SECRET"], timeout=60, max_retries=1)
    refs = [{"uri": "data:image/png;base64," + base64.b64encode(ref).decode(), "tag": "Projeto"}]
    for k, b in enumerate(extra or []):
        refs.append({"uri": "data:image/jpeg;base64," + base64.b64encode(_jpeg(b, 88)).decode(), "tag": f"Foto{k + 1}"})
    task = await client.text_to_image.create(model="gen4_image", ratio="1920:1080", prompt_text=prompt[:990],
                                             reference_images=refs)
    for _ in range(70):
        await asyncio.sleep(3)
        t = await client.tasks.retrieve(task.id)
        if t.status == "SUCCEEDED" and t.output:
            async with httpx.AsyncClient(timeout=60) as h:
                r = await h.get(t.output[0])
                r.raise_for_status()
                return r.content
        if t.status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"runway {t.status}")
    raise TimeoutError("runway sem resposta")


def _erro_curto(e: BaseException) -> str:
    """Tipo + início da mensagem do fornecedor (para diagnóstico), sem nada que pareça uma chave."""
    import re
    msg = re.sub(r"(sk-|key_|Bearer\s+)[A-Za-z0-9_\-]{6,}", "***", str(e))[:220]
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def _fornecedor(nome: str):
    return {"runway": _runway, "openai": _openai, "gemini": _gemini}[nome]


def _alargar(png: bytes, aspeto: float, mascara: bool = False) -> bytes:
    """Alarga a imagem para a proporção pedida repetindo as margens (céu/chão) — a casa não é deformada."""
    a = np.asarray(Image.open(io.BytesIO(png)).convert("L" if mascara else "RGB"))
    h, w = a.shape[:2]
    alvo = int(round(h * aspeto))
    if alvo <= w:
        return png
    e = (alvo - w) // 2
    pad = ((0, 0), (e, alvo - w - e)) + (((0, 0),) if a.ndim == 3 else ())
    a = np.pad(a, pad, mode="constant" if mascara else "edge")
    b = io.BytesIO()
    Image.fromarray(a).save(b, "PNG")
    return b.getvalue()


def prompt_curto(p: str) -> str:
    """Versão ≤ 990 caracteres para o Runway: enquadramento + regra de geometria + estilo + luz + qualidade."""
    frases = [f.strip() for f in p.replace("\n", " ").split(". ") if f.strip()]
    chave = [f for f in frases if any(k in f for k in ("photograph", "Keep", "STRICT", "Style", "Lighting", "facade", "Fix"))]
    out = "Use @Projeto as the exact geometry reference. "
    for f in chave or frases:
        if len(out) + len(f) + 2 > 960:
            break
        out += f + ". "
    return (out + "Photorealistic, sharp, no text.")[:990]


# ------------------------------------------------------------------ Claude: juiz de realismo e de geometria
async def juiz_claude(ref_png: bytes, img: bytes) -> Optional[Dict[str, Any]]:
    """{"realismo": 0-10, "geometria": bool, "defeitos": [...]} ou None (sem chave / erro → decide só a verificação numérica)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import json
    import re
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=90)

        def b64(b):
            im = Image.open(io.BytesIO(b)).convert("RGB")
            im.thumbnail((1024, 1024))
            o = io.BytesIO()
            im.save(o, "JPEG", quality=85)
            return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.b64encode(o.getvalue()).decode()}}
        msg = await client.messages.create(
            model=os.environ.get("URB_IMG_JUIZ_MODEL", "claude-sonnet-5-5"), max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Image A is the exact geometric reference of an architectural project (flat colours)."},
                b64(ref_png),
                {"type": "text", "text": "Image B is a candidate photorealistic image of the same project."},
                b64(img),
                {"type": "text", "text": (
                    "Judge B strictly, as a real-estate archviz art director. realismo: 0-10, where 10 = indistinguishable from "
                    "a real photograph or a top V-Ray/Corona render, 7 = professional listing quality, <=5 = looks CGI, "
                    "painted, blurry or distorted. geometria: true only if B keeps the same building volumes, roof shape, "
                    "number of floors, the same number and positions of windows and doors, and the same camera as A "
                    "(landscaping, furniture and sky may differ). defeitos: up to 4 short concrete defects to fix. "
                    'Answer with JSON only: {"realismo": n, "geometria": true|false, "defeitos": ["..."]}')}]}])
        txt = "".join(getattr(c, "text", "") for c in msg.content)
        m = re.search(r"\{.*\}", txt, re.S)
        d = json.loads(m.group(0)) if m else None
        if not d:
            return None
        return {"realismo": float(d.get("realismo", 0)), "geometria": bool(d.get("geometria")),
                "defeitos": [str(x)[:160] for x in (d.get("defeitos") or [])][:4]}
    except Exception as e:  # noqa: BLE001
        log.warning("juiz Claude indisponível: %s", type(e).__name__)
        return None


def _jpeg(b: bytes, q: int = 90) -> bytes:
    im = Image.open(io.BytesIO(b)).convert("RGB")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=q, optimize=True)
    return out.getvalue()


# ------------------------------------------------------------------ controlo de qualidade da imagem
LARGURA_MIN = int(os.environ.get("URB_IMG_LARGURA_MIN", "1920"))
CANDIDATOS = max(1, min(int(os.environ.get("URB_IMG_CANDIDATOS", "2")), 4))
LIMIAR_INTERIOR = float(os.environ.get("URB_IMG_LIMIAR_INTERIOR", "0.40"))


def nitidez(b: bytes) -> float:
    """Variância do laplaciano numa versão a 1024 px (imagens desfocadas/«pintadas» ficam abaixo de ~60)."""
    g = Image.open(io.BytesIO(b)).convert("L")
    g = g.resize((1024, max(1, round(1024 * g.height / max(1, g.width)))), Image.BILINEAR)
    a = np.asarray(g, dtype=np.float64)
    lap = a[1:-1, 1:-1] * 4 - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]
    return float(lap.var())


def acabar(b: bytes, largura: int = 0) -> Tuple[bytes, Dict[str, Any]]:
    """Entrega final: JPEG de alta qualidade com pelo menos LARGURA_MIN px de largura. Se o fornecedor devolver menos,
    amplia (Lanczos + nitidez suave) e REGISTA que foi ampliada — nunca se apresenta como resolução nativa."""
    largura = largura or LARGURA_MIN
    im = Image.open(io.BytesIO(b)).convert("RGB")
    info = {"largura_nativa": im.width, "altura_nativa": im.height, "ampliada": False}
    if im.width < largura:
        h = round(im.height * largura / im.width)
        im = im.resize((largura, h), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
        info["ampliada"] = True
    out = io.BytesIO()
    im.save(out, "JPEG", quality=93, optimize=True, subsampling=0)
    info.update(largura=im.width, altura=im.height)
    return out.getvalue(), info


TEMPO_MAX_S = {"runway": float(os.environ.get("URB_IMG_TEMPO_RUNWAY_S", "240")),
               "openai": float(os.environ.get("URB_IMG_TEMPO_OPENAI_S", "180")),
               "gemini": float(os.environ.get("URB_IMG_TEMPO_GEMINI_S", "150"))}


async def _candidatos(gerar, prompt: str, ref: bytes, sessao: str, n: int, limite_s: float = 240) -> List[Any]:
    """N pedidos em paralelo, cada um com tempo máximo: um fornecedor que não responde nunca bloqueia o dossier."""
    import asyncio

    async def um():
        return await asyncio.wait_for(gerar(prompt, ref, sessao), timeout=limite_s)
    res = await asyncio.gather(*[um() for _ in range(n)], return_exceptions=True)
    return list(res)


async def fotorrealista(processo: Dict[str, Any], exata: Dict[str, Any], sessao: str,
                        gerar: Optional[Callable[[str, bytes, str], Awaitable[bytes]]] = None,
                        prompt_fn: Optional[Callable[[bool], str]] = None, limiar: Optional[float] = None,
                        luz: str = "dia", nome: Optional[str] = None) -> Dict[str, Any]:
    """Uma vista, totalmente automática: para cada fornecedor da cadeia (Runway → OpenAI → Emergent/Gemini), N candidatos
    em paralelo → verificação numérica da geometria → juiz Claude (realismo e geometria). Aceita o primeiro que passa
    as duas; senão a ronda seguinte usa instruções mais estritas com os defeitos apontados pelo Claude. Se nenhum passar,
    fica o melhor (marcado «não verificado» se a geometria não passou) ou, sem nenhum, a vista exata."""
    limiar = LIMIAR_GEOMETRIA if limiar is None else limiar
    prompt_fn = prompt_fn or (lambda estrito: prompt_vista(processo, exata["vista"], estrito, luz))
    nome = nome or exata["vista"]
    cadeia = [("teste", gerar)] if gerar else [(f, _fornecedor(f)) for f in ORDEM_FORNECEDORES if disponivel(f)]
    tentativas: List[Dict[str, Any]] = []
    melhor = None
    defeitos: List[str] = []

    def chave(c):
        img, sc, forn, nt, jz, ok = c
        return (ok, sc >= limiar, (jz or {}).get("realismo", REALISMO_MIN), sc + min(nt, 400) / 4000)

    plano = [(f, fn, k > 0) for k, (f, fn) in enumerate(cadeia)]
    if plano and not plano[-1][2]:           # o último fornecedor tem sempre uma ronda estrita
        plano.append((plano[-1][0], plano[-1][1], True))
    for forn, fn, estrito in plano:
        asp = ASPETO.get(forn)
        ref = _alargar(exata["png"], asp) if asp else exata["png"]
        msk = _alargar(exata["mascara_png"], asp, True) if asp else exata["mascara_png"]
        p = prompt_fn(estrito)
        if defeitos:
            p += " Fix these issues seen in the previous attempt: " + "; ".join(defeitos[:4]) + "."
        if forn == "runway":
            p = prompt_curto(p)
        for r in await _candidatos(fn, p, ref, sessao, CANDIDATOS, TEMPO_MAX_S.get(forn, 240)):
            if isinstance(r, BaseException):
                tentativas.append({"fornecedor": forn, "estrito": estrito, "erro": type(r).__name__,
                                   "detalhe": _erro_curto(r)})
                continue
            try:
                sc = semelhanca_geometria(ref, r, msk)
                nt = nitidez(r)
            except Exception as e:  # noqa: BLE001
                tentativas.append({"fornecedor": forn, "estrito": estrito, "erro": "imagem_invalida:" + type(e).__name__})
                continue
            jz = await juiz_claude(ref, r) if sc >= limiar * 0.85 else None
            ok = sc >= limiar and (jz is None or (jz["geometria"] and jz["realismo"] >= REALISMO_MIN))
            t = {"fornecedor": forn, "estrito": estrito, "geometria": round(sc, 3), "nitidez": round(nt, 1)}
            if jz:
                t["juiz"] = jz
                defeitos = jz["defeitos"] or defeitos
            tentativas.append(t)
            cand = (r, sc, forn, nt, jz, ok)
            if melhor is None or chave(cand) > chave(melhor):
                melhor = cand
        if melhor is not None and melhor[5]:
            break
    if melhor is None:
        jpeg, q = acabar(exata["png"], 1536)
        return {"vista": nome, "tipo": "exata", "jpeg": jpeg, "fornecedor": "render3d", "qualidade": q,
                "geometria": 1.0, "verificada": True, "tentativas": tentativas,
                "nota": "Os serviços de imagem fotorrealista não responderam: mostra-se a vista 3D exata do projeto."}
    img, sc, forn, nt, jz, ok = melhor
    jpeg, q = acabar(img)
    q["nitidez"] = round(nt, 1)
    if jz:
        q["realismo_claude"] = jz["realismo"]
    verificada = sc >= limiar and (jz is None or jz["geometria"])
    nota = NOTA
    if not verificada:
        nota += " ATENÇÃO: a verificação automática detetou diferenças de geometria — comparar com a vista exata."
    elif jz and jz["realismo"] < REALISMO_MIN:
        nota += " (Realismo abaixo do objetivo em todos os fornecedores — a melhor imagem obtida.)"
    return {"vista": nome, "tipo": "fotorrealista", "jpeg": jpeg, "fornecedor": forn, "qualidade": q,
            "geometria": round(sc, 3), "verificada": verificada, "tentativas": tentativas, "iluminacao": luz,
            "juiz": jz, "nota": nota}


async def editar_em_cadeia(prompt: str, ref: bytes, sessao: str, extra: Optional[List[bytes]] = None,
                           ordem: Optional[List[str]] = None) -> Tuple[Optional[bytes], Optional[str]]:
    """Edição sem verificação de geometria possível (aérea sobre ortofoto, montagem sobre foto): primeiro fornecedor
    disponível que responder. Devolve (imagem, fornecedor) ou (None, None)."""
    for f in ordem or [x for x in ORDEM_FORNECEDORES if x != "runway"] + ["runway"]:
        if f not in ("runway", "openai", "gemini") or not disponivel(f):
            continue
        try:
            import asyncio
            fn = _fornecedor(f)
            return await asyncio.wait_for(fn(prompt_curto(prompt) if f == "runway" else prompt, ref, sessao, extra),
                                          timeout=TEMPO_MAX_S.get(f, 240)), f
        except Exception as e:  # noqa: BLE001
            log.warning("edição %s falhou: %s", f, type(e).__name__)
    return None, None


# ------------------------------------------------------------------ antes / depois (vista aérea)
def antes_depois_base(processo: Dict[str, Any]) -> Optional[Dict[str, bytes]]:
    """«Antes»: ortofotomapa oficial; «depois (esquema)»: a mesma imagem com a implantação à escala (cobertura, garagem,
    piscina e sombra). Devolve None se não houver ortofotomapa."""
    a = processo.get("auto") or {}
    orto = a.get("orto") or {}
    if not orto.get("b64") or not orto.get("bbox"):
        return None
    base = Image.open(io.BytesIO(base64.b64decode(orto["b64"]))).convert("RGB")
    S = 1024
    base = base.resize((S, S), Image.LANCZOS)
    lo0, la0, lo1, la1 = [float(v) for v in orto["bbox"].split(",")]

    def P(la, lo):
        return (lo - lo0) / (lo1 - lo0) * S, (la1 - la) / (la1 - la0) * S
    dep = base.copy()
    dr = ImageDraw.Draw(dep, "RGBA")
    mats = a.get("materiais") or {}
    cor_tel = {"telha_ceramica": (170, 80, 55), "telha_preta": (55, 55, 60), "zinco": (130, 138, 145)}.get(
        mats.get("cobertura"), (160, 156, 148))
    casa = [[P(*pt) for pt in poly] for poly in (a.get("casa_latlon") or [])]
    for poly in casa:   # sombra projetada (sol a sul → sombra para norte)
        dr.polygon([(x + 6, y - 9) for x, y in poly], fill=(0, 0, 0, 90))
    for poly in casa:
        dr.polygon(poly, fill=cor_tel + (255,), outline=(60, 60, 60, 255))
    pi = a.get("piscina")
    ter = (a.get("terreno") or {})
    if pi and ter.get("poligono_m") and ter.get("poligono_latlon"):
        # transformação afim terreno (m) → lat/lon a partir de 3 vértices do próprio terreno
        pm, pl = np.array(ter["poligono_m"][:3], dtype=float), np.array(ter["poligono_latlon"][:3], dtype=float)
        A = np.c_[pm, np.ones(3)]
        try:
            coef = np.linalg.solve(A, pl)
            cantos = [(pi["x_m"], pi["y_m"]), (pi["x_m"] + pi["l_m"], pi["y_m"]), (pi["x_m"] + pi["l_m"], pi["y_m"] + pi["w_m"]),
                      (pi["x_m"], pi["y_m"] + pi["w_m"])]
            ll = [tuple(np.array([x, y, 1.0]) @ coef) for x, y in cantos]
            dr.polygon([P(la, lo) for la, lo in ll], fill=(40, 150, 200, 255), outline=(230, 230, 225, 255))
        except np.linalg.LinAlgError:
            pass
    b1, b2 = io.BytesIO(), io.BytesIO()
    base.save(b1, "JPEG", quality=90)
    dep.save(b2, "JPEG", quality=92)
    return {"antes": b1.getvalue(), "depois_esquema": b2.getvalue()}


def prompt_aerea(processo: Dict[str, Any]) -> str:
    a = processo.get("auto") or {}
    est = E.obter((a.get("estilo") or {}).get("id"))
    return ("Photorealistic aerial orthophoto (top-down satellite view) of this exact plot. Keep EVERYTHING outside the "
            "coloured shapes identical (neighbouring buildings, roads, trees, fields). Replace the flat coloured shapes with a "
            f"real newly built house seen from above with exactly the same footprint, position and orientation: roof as {est['render']}; "
            "the blue rectangle is a swimming pool with stone coping; add a natural lawn and short paved paths only inside the plot. "
            "Same scale, same north orientation, realistic shadows consistent with the existing photo, no text.")


# ------------------------------------------------------------------ planta de implantação humanizada (exata, sem IA)
def implantacao_humanizada(m: Dict[str, Any], S: int = 2000) -> bytes:
    """Planta de implantação a cores, à escala, como nas apresentações de promotores: relva, cobertura com sombra,
    piscina, lajeados, árvores ilustrativas fora das construções, norte e escala gráfica. Geometria = a do processo."""
    import random
    ter = [tuple(p) for p in (m.get("terreno") or [])]
    if len(ter) < 3:
        raise ValueError("terreno sem polígono")
    xs, ys = [p[0] for p in ter], [p[1] for p in ter]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    marg = 0.08 * max(x1 - x0, y1 - y0)
    esc = (S * 0.74) / max(x1 - x0 + 2 * marg, y1 - y0 + 2 * marg)
    ox, oy = (S - (x1 - x0) * esc) / 2, (S - (y1 - y0) * esc) / 2 - S * 0.05   # faixa de legenda no topo

    def P(x, y):   # norte para cima: y do terreno cresce da frente (rua, em baixo) para o tardoz
        return ox + (x - x0) * esc, S - (oy + (y - y0) * esc)
    rng = random.Random(7)
    # norte no referencial do terreno: o eixo +y aponta para o azimute da fachada de tardoz
    az_y = float(((m.get("azimutes") or {}).get("tardoz")) or 0.0)
    th = math.radians(-az_y)            # norte = +y rodado de -az (sentido horário positivo)
    nvx, nvy = math.sin(th), math.cos(th)   # vetor norte em coordenadas do terreno
    try:
        from PIL import ImageFont
        from engines.urbanismo_pt.pdf import _FONT_DIR
        fonte = ImageFont.truetype(os.path.join(_FONT_DIR, "DejaVuSans.ttf"), max(14, S // 60))
    except Exception:  # noqa: BLE001
        fonte = None
    img = Image.new("RGB", (S, S), (236, 233, 226))
    # envolvente e rua
    dr = ImageDraw.Draw(img, "RGBA")
    rua_y = P(0, y0 - 1)[1]
    dr.rectangle([0, rua_y, S, min(S, rua_y + 8 * esc)], fill=(120, 122, 126))
    for k in range(0, S, int(6 * esc)):
        dr.rectangle([k, rua_y + 3.8 * esc, k + 3 * esc, rua_y + 4.2 * esc], fill=(235, 235, 235))
    # relva com textura
    relva = Image.new("RGB", (S, S), (112, 150, 78))
    ruido = (np.random.default_rng(3).normal(0, 9, (S // 4, S // 4))).astype(np.float64)
    rz = Image.fromarray(np.clip(ruido + 128, 0, 255).astype(np.uint8)).resize((S, S), Image.BICUBIC)
    rz = np.asarray(rz, dtype=np.float64) - 128
    relva = Image.fromarray(np.clip(np.asarray(relva, dtype=np.float64) + rz[..., None] * np.array([0.6, 1.0, 0.5]), 0, 255).astype(np.uint8))
    mter = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mter).polygon([P(*p) for p in ter], fill=255)
    img.paste(relva, (0, 0), mter)
    dr = ImageDraw.Draw(img, "RGBA")
    ocupado = []
    vols = m.get("volumes") or []
    pi = m.get("piscina")
    # lajeado: caminho da rua à entrada + terraço junto à casa + deck da piscina
    casa = next((v for v in vols if not v.get("anexo")), None)
    if casa:
        cx = sum(p[0] for p in casa["pts"]) / len(casa["pts"])
        ymin = min(p[1] for p in casa["pts"])
        dr.polygon([P(cx - 0.8, y0), P(cx + 0.8, y0), P(cx + 0.8, ymin), P(cx - 0.8, ymin)], fill=(206, 200, 188))
    if pi:
        x, y, l, w = (float(pi[k]) for k in ("x_m", "y_m", "l_m", "w_m"))
        dr.polygon([P(x - 1.5, y - 1.5), P(x + l + 1.5, y - 1.5), P(x + l + 1.5, y + w + 1.5), P(x - 1.5, y + w + 1.5)], fill=(222, 214, 198))
        ocupado.append((x - 2, y - 2, x + l + 2, y + w + 2))
    # sombras (sol a sul-oeste) e coberturas
    for v in vols:
        h = float(v.get("altura_m") or 3) + float(v.get("altura_cobertura_m") or 0)
        sh = 0.55 * h   # sombra para norte-nordeste (sol a sul-sudoeste, a meio da tarde)
        sx_, sy_ = nvx * sh + nvy * sh * 0.35, nvy * sh - nvx * sh * 0.35
        dr.polygon([P(p[0] + sx_, p[1] + sy_) for p in v["pts"]], fill=(0, 0, 0, 70))
    for v in vols:
        pts = [P(*p) for p in v["pts"]]
        plana = v.get("cobertura") == "plana" or v.get("anexo")
        cor = (214, 210, 202) if plana else {"telha_ceramica": (178, 92, 62), "telha_preta": (70, 70, 76), "zinco": (140, 146, 152)}.get(
            (m.get("materiais") or {}).get("cobertura"), (178, 92, 62))
        dr.polygon(pts, fill=cor, outline=(70, 70, 70))
        if plana and not v.get("anexo"):   # platibanda
            dr.line(pts + [pts[0]], fill=(245, 244, 240), width=max(3, int(0.3 * esc)))
        bx = [p[0] for p in v["pts"]], [p[1] for p in v["pts"]]
        ocupado.append((min(bx[0]) - 1.5, min(bx[1]) - 1.5, max(bx[0]) + 1.5, max(bx[1]) + 1.5))
    if pi:
        x, y, l, w = (float(pi[k]) for k in ("x_m", "y_m", "l_m", "w_m"))
        a0, a1 = P(x, y + w), P(x + l, y)
        agua = Image.new("RGB", (max(1, int(a1[0] - a0[0])), max(1, int(a1[1] - a0[1]))))
        g = np.linspace(0, 1, agua.height)[:, None, None]
        arr = np.array([62, 178, 210]) * (1 - g) + np.array([28, 120, 170]) * g
        agua = Image.fromarray(np.broadcast_to(arr, (agua.height, agua.width, 3)).astype(np.uint8))
        img.paste(agua, (int(a0[0]), int(a0[1])))
        dr = ImageDraw.Draw(img, "RGBA")
        dr.rectangle([a0, a1], outline=(245, 242, 235), width=max(3, int(0.35 * esc)))
    # árvores ilustrativas: dentro do terreno, afastadas das construções e dos limites
    from shapely.geometry import Point, Polygon
    tp = Polygon(ter).buffer(-1.5)
    arv = []
    for _ in range(600):
        if len(arv) >= max(6, int(Polygon(ter).area / 90)):
            break
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        r = rng.uniform(1.6, 3.0)
        if not tp.contains(Point(x, y).buffer(r * 0.6)):
            continue
        if any(a - r * 0.5 < x < c + r * 0.5 and b - r * 0.5 < y < d + r * 0.5 for a, b, c, d in ocupado):
            continue
        if any((x - ax) ** 2 + (y - ay) ** 2 < (r + ar) ** 2 * 0.8 for ax, ay, ar in arv):
            continue
        arv.append((x, y, r))
    for x, y, r in arv:
        cx_, cy_ = P(x, y)
        R = r * esc
        dr.ellipse([cx_ - R + R * 0.25, cy_ - R - R * 0.35, cx_ + R + R * 0.25, cy_ + R - R * 0.35], fill=(0, 0, 0, 55))
        dr.ellipse([cx_ - R, cy_ - R, cx_ + R, cy_ + R], fill=(68, 112, 58, 255))
        dr.ellipse([cx_ - R * 0.6, cy_ - R * 0.75, cx_ + R * 0.35, cy_ + R * 0.2], fill=(98, 146, 76, 255))
    # limite do terreno
    dr.line([P(*p) for p in ter] + [P(*ter[0])], fill=(200, 40, 40), width=max(3, int(0.12 * esc)))
    # norte (orientado pelos azimutes reais do terreno) e escala gráfica — no topo, fora da rua
    nx, ny, R = S - S * 0.07, S * 0.075, S * 0.035
    ang = math.atan2(nvx, nvy)   # ângulo do norte em relação ao «cima» do ecrã (horário)
    def R2(dx, dy):
        ca, sa = math.cos(ang), math.sin(ang)
        return nx + dx * ca - dy * sa, ny + dx * sa + dy * ca
    dr.polygon([R2(0, -R), R2(-R * 0.4, R * 0.45), R2(0, R * 0.18), R2(R * 0.4, R * 0.45)], fill=(30, 30, 30))
    tx, ty = R2(0, -R * 1.45)
    dr.text((tx - 8, ty - 12), "N", fill=(30, 30, 30), font=fonte)
    L10 = 10 * esc
    bx0, by0 = S * 0.05, S * 0.04
    for k in range(5):
        dr.rectangle([bx0 + k * L10 / 5, by0, bx0 + (k + 1) * L10 / 5, by0 + 16], fill=(30, 30, 30) if k % 2 == 0 else (250, 250, 250),
                     outline=(30, 30, 30))
    dr.text((bx0, by0 + 24), "0", fill=(30, 30, 30), font=fonte)
    dr.text((bx0 + L10 - 30, by0 + 24), "10 m", fill=(30, 30, 30), font=fonte)
    dr.text((bx0, by0 + 34 + max(14, S // 60)), "Implantação — arranjos exteriores e vegetação ilustrativos; medidas nas peças desenhadas.",
            fill=(60, 60, 60), font=fonte)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=93, subsampling=0)
    return out.getvalue()


# ------------------------------------------------------------------ montagem sobre fotografia real do terreno
def prompt_montagem(processo: Dict[str, Any]) -> str:
    a = processo.get("auto") or {}
    est = E.obter((a.get("estilo") or {}).get("id"))
    mats = a.get("materiais") or {}
    return ("Photomontage. Image 1 is a REAL photograph of the empty plot (keep it: same camera, same sky, same neighbouring "
            "houses, roads, trees and terrain). Image 2 is the exact 3D view of the approved design. Insert THIS exact house into "
            "the plot of image 1, with the same volumes, roof, windows, doors, garage and pool as image 2, at a realistic scale "
            "and perspective matching the photo, sitting naturally on the ground with matching light direction and shadows. "
            f"Style: {est['render']}; facade = {PA.MATERIAIS_FACHADA.get(mats.get('fachada'), 'white render')}; "
            f"roof = {PA.MATERIAIS_COBERTURA.get(mats.get('cobertura'), 'clay tiles')}. New garden only inside the plot. "
            f"{QUALIDADE}. {NEGATIVO}.")


async def montagem(processo: Dict[str, Any], foto: bytes, ref_png: bytes, sessao: str) -> Optional[bytes]:
    img, _ = await editar_em_cadeia(prompt_montagem(processo), ref_png, sessao, extra=[foto], ordem=["openai", "gemini", "runway"])
    return img
