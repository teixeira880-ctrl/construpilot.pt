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
from typing import Any, Awaitable, Callable, Dict, List, Optional

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


def prompt_vista(processo: Dict[str, Any], vista: str, estrito: bool = False) -> str:
    a = processo.get("auto") or {}
    mats = a.get("materiais") or {}
    est = E.obter((a.get("estilo") or {}).get("id"))
    concelho = (processo.get("terreno") or {}).get("concelho") or ""
    enquadr = {"perspetiva": "eye-level three-quarter view from the front garden",
               "frente": "eye-level frontal view from the front garden", "tardoz": "eye-level view from the back garden",
               "aerea": "elevated drone view"}.get(vista, "eye-level view")
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
        f"window frames = {PA.CAIXILHARIA.get(mats.get('caixilharia'), 'anthracite aluminium')}; dark rectangles = clear glazing with "
        "realistic reflections and interior depth; blue area = swimming pool water with stone coping. Landscaping: natural lawn, "
        f"paving and plants appropriate to the style; {_paisagem(concelho)}. Golden-hour natural sunlight, soft realistic shadows, "
        "physically based materials, high dynamic range, 35mm lens, crisp details, no people, no text, no watermark."
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
                                       feature="licenciamento_imagens", session_id=sessao)
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


async def fotorrealista(processo: Dict[str, Any], exata: Dict[str, Any], sessao: str,
                        gerar: Optional[Callable[[str, bytes, str], Awaitable[bytes]]] = None) -> Dict[str, Any]:
    """Uma vista: tenta Gemini (2 tentativas, a 2.ª mais estrita) → Runway → vista exata. Devolve sempre um resultado."""
    gerar = gerar or _gemini
    tentativas: List[Dict[str, Any]] = []
    melhor = None
    for estrito in (False, True):
        p = prompt_vista(processo, exata["vista"], estrito)
        try:
            img = await gerar(p, exata["png"], sessao)
            sc = semelhanca_geometria(exata["png"], img, exata["mascara_png"])
            tentativas.append({"fornecedor": "gemini", "estrito": estrito, "geometria": round(sc, 3)})
            if melhor is None or sc > melhor[1]:
                melhor = (img, sc, "gemini")
            if sc >= LIMIAR_GEOMETRIA:
                break
        except Exception as e:  # noqa: BLE001
            tentativas.append({"fornecedor": "gemini", "estrito": estrito, "erro": type(e).__name__})
    if melhor is None or melhor[1] < LIMIAR_GEOMETRIA:
        try:
            rw = await _runway(prompt_vista(processo, exata["vista"], True), exata["png"])
            if rw:
                sc = semelhanca_geometria(exata["png"], rw, exata["mascara_png"])
                tentativas.append({"fornecedor": "runway", "geometria": round(sc, 3)})
                if melhor is None or sc > melhor[1]:
                    melhor = (rw, sc, "runway")
        except Exception as e:  # noqa: BLE001
            tentativas.append({"fornecedor": "runway", "erro": type(e).__name__})
    if melhor is None:
        return {"vista": exata["vista"], "tipo": "exata", "jpeg": _jpeg(exata["png"]), "fornecedor": "render3d",
                "geometria": 1.0, "verificada": True, "tentativas": tentativas,
                "nota": "Os serviços de imagem fotorrealista não responderam: mostra-se a vista 3D exata do projeto."}
    img, sc, forn = melhor
    return {"vista": exata["vista"], "tipo": "fotorrealista", "jpeg": _jpeg(img), "fornecedor": forn,
            "geometria": round(sc, 3), "verificada": sc >= LIMIAR_GEOMETRIA, "tentativas": tentativas,
            "nota": NOTA + ("" if sc >= LIMIAR_GEOMETRIA else
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
