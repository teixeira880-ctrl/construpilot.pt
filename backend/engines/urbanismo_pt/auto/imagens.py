"""Imagens realistas do processo — o mais fotorrealistas possível, SEM alterar a geometria.

Cadeia (todas as APIs de imagem disponíveis na plataforma, por ordem):
1. Vista 3D exata gerada no servidor (render3d) — a referência geométrica.
2. Gemini «Nano Banana» (chave universal Emergent) em modo edição: aplica materiais reais, luz, vegetação e
   envolvente à vista exata, com um prompt construído a partir do estilo, dos materiais e da região.
3. Verificação automática da geometria: compara os contornos da imagem gerada com os da vista exata dentro da
   silhueta da casa; abaixo do limiar tenta de novo com instruções mais estritas.
4. Se o Gemini falhar: Runway gen4_image com a vista exata como referência (se RUNWAYML_API_SECRET existir).
5. Se tudo falhar: fica a vista exata (nunca uma imagem inventada).
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
        f"{PA.MATERIAIS_FACHADA.get(mats.get('fachada'), 'white render')} (dark grey areas = natural granite stone, "
        f"brown areas = natural timber cladding, light areas = render); roof = {PA.MATERIAIS_COBERTURA.get(mats.get('cobertura'), 'clay tiles')}; "
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


# ------------------------------------------------------------------ fornecedores
async def _gemini(prompt: str, ref: bytes, sessao: str) -> bytes:
    from engines import image_studio
    imgs = await image_studio.generate(prompt=prompt, provider="gemini", reference_images=[ref], number=1,
                                       feature="licenciamento_imagens", session_id=sessao,
                                       model=os.environ.get("URB_IMG_GEMINI_MODEL") or None)
    return imgs[0][0]


async def _runway(prompt: str, ref: bytes) -> Optional[bytes]:
    if not os.environ.get("RUNWAYML_API_SECRET"):
        return None
    import asyncio
    import httpx
    from runwayml import AsyncRunwayML
    client = AsyncRunwayML(api_key=os.environ["RUNWAYML_API_SECRET"])
    uri = "data:image/png;base64," + base64.b64encode(ref).decode()
    task = await client.text_to_image.create(model="gen4_image", ratio="1920:1080",
                                             prompt_text="Use @Projeto as the exact geometry reference. " + prompt[:900],
                                             reference_images=[{"uri": uri, "tag": "Projeto"}])
    for _ in range(90):
        await asyncio.sleep(3)
        t = await client.tasks.retrieve(task.id)
        if t.status == "SUCCEEDED" and t.output:
            async with httpx.AsyncClient(timeout=60) as h:
                r = await h.get(t.output[0])
                r.raise_for_status()
                return r.content
        if t.status in ("FAILED", "CANCELLED"):
            return None
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


async def _candidatos(gerar, prompt: str, ref: bytes, sessao: str, n: int) -> List[Any]:
    import asyncio
    res = await asyncio.gather(*[gerar(prompt, ref, sessao) for _ in range(n)], return_exceptions=True)
    return list(res)


async def fotorrealista(processo: Dict[str, Any], exata: Dict[str, Any], sessao: str,
                        gerar: Optional[Callable[[str, bytes, str], Awaitable[bytes]]] = None,
                        prompt_fn: Optional[Callable[[bool], str]] = None, limiar: Optional[float] = None,
                        luz: str = "dia", nome: Optional[str] = None) -> Dict[str, Any]:
    """Uma vista: Gemini (N candidatos em paralelo; 2.ª ronda mais estrita) → Runway → vista exata.
    Escolhe o candidato com melhor geometria (desempate pela nitidez). Devolve sempre um resultado."""
    gerar = gerar or _gemini
    limiar = LIMIAR_GEOMETRIA if limiar is None else limiar
    prompt_fn = prompt_fn or (lambda estrito: prompt_vista(processo, exata["vista"], estrito, luz))
    nome = nome or exata["vista"]
    tentativas: List[Dict[str, Any]] = []
    melhor = None

    def considerar(img, forn, estrito):
        nonlocal melhor
        sc = semelhanca_geometria(exata["png"], img, exata["mascara_png"])
        nt = nitidez(img)
        tentativas.append({"fornecedor": forn, "estrito": estrito, "geometria": round(sc, 3), "nitidez": round(nt, 1)})
        if melhor is None or (sc >= limiar, sc + min(nt, 400) / 4000) > (melhor[1] >= limiar, melhor[1] + min(melhor[3], 400) / 4000):
            melhor = (img, sc, forn, nt)
    for estrito in (False, True):
        for r in await _candidatos(gerar, prompt_fn(estrito), exata["png"], sessao, CANDIDATOS):
            if isinstance(r, BaseException):
                tentativas.append({"fornecedor": "gemini", "estrito": estrito, "erro": type(r).__name__})
            else:
                considerar(r, "gemini", estrito)
        if melhor is not None and melhor[1] >= limiar:
            break
    if melhor is None or melhor[1] < limiar:
        try:
            rw = await _runway(prompt_fn(True), exata["png"])
            if rw:
                considerar(rw, "runway", True)
        except Exception as e:  # noqa: BLE001
            tentativas.append({"fornecedor": "runway", "erro": type(e).__name__})
    if melhor is None:
        jpeg, q = acabar(exata["png"], 1536)
        return {"vista": nome, "tipo": "exata", "jpeg": jpeg, "fornecedor": "render3d", "qualidade": q,
                "geometria": 1.0, "verificada": True, "tentativas": tentativas,
                "nota": "Os serviços de imagem fotorrealista não responderam: mostra-se a vista 3D exata do projeto."}
    img, sc, forn, nt = melhor
    jpeg, q = acabar(img)
    q["nitidez"] = round(nt, 1)
    return {"vista": nome, "tipo": "fotorrealista", "jpeg": jpeg, "fornecedor": forn, "qualidade": q,
            "geometria": round(sc, 3), "verificada": sc >= limiar, "tentativas": tentativas, "iluminacao": luz,
            "nota": NOTA + ("" if sc >= limiar else
                            " ATENÇÃO: a verificação automática detetou diferenças de geometria — comparar com a vista exata.")}


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
    from engines import image_studio
    imgs = await image_studio.generate(prompt=prompt_montagem(processo), provider="gemini", reference_images=[foto, ref_png],
                                       number=1, feature="licenciamento_imagens", session_id=sessao,
                                       model=os.environ.get("URB_IMG_GEMINI_MODEL") or None)
    return imgs[0][0] if imgs else None
