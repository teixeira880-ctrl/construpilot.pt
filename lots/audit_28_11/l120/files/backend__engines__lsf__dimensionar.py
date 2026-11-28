"""Dimensionamento automático LSF — reforça só o que a verificação EN 1993-1-3 dá « a rever » (taxa > 1).

Ordem de reforço (a mais económica primeiro, sem mudar a geometria quando possível):
  • montantes de parede : mesma secção (h, b) com espessura maior (0,8 → 1,0 → 1,2 → 1,5 → 2,0 → 2,5 mm),
    depois espaçamento 600 → 400 → 300 mm ;
  • vergas : C150 1,5 → C150 2,0 → C200 1,5 → C200 2,0 → C250 2,0 → C250 2,5 ;
  • vigas de piso : C150 1,5 → C200 1,5 → C200 2,0 → C250 2,0 → C250 2,5 → C300 2,5, depois espaçamento 400 ;
  • asnas : banzo / diagonal com espessura maior, depois espaçamento 400.
O reforço de uma parede de perímetro só se aplica ao lado em causa (tipo próprio desse lado, `tiposLado`) ;
nada é reduzido. Cada alteração fica registada (texto PT/FR) para o dossier.
"""
from __future__ import annotations

import copy
import re

from .engine import calcular
from .verificacao import verificar

ESPESSURAS = [0.8, 1.0, 1.2, 1.5, 2.0, 2.5]
VERGAS = [(150, 1.5), (150, 2.0), (200, 1.5), (200, 2.0), (250, 2.0), (250, 2.5)]
VIGAS = [(150, 1.5), (200, 1.5), (200, 2.0), (250, 2.0), (250, 2.5), (300, 2.5)]
ESPACAMENTOS = [600, 400, 300]
MAX_ITER = 12


def _chave(h, t):
    return f"C{int(round(h))}_{int(round(t * 10)):02d}"


def _garante_perfil(proj, h, t, modelo=None):
    k = _chave(h, t)
    if k not in proj["perfis"]:
        base = dict(modelo or {"tipo": "C", "b": 50 if h >= 200 else 43, "c": 15 if h >= 150 else 10})
        base.update({"tipo": "C", "h": h, "t": t})
        base.setdefault("b", 50 if h >= 200 else 43)
        base.setdefault("c", 15 if h >= 150 else 10)
        proj["perfis"][k] = base
    return k


def _mais_espesso(proj, chave):
    p = proj["perfis"].get(chave)
    if not p or p.get("tipo") != "C":
        return None
    seg = [t for t in ESPESSURAS if t > p["t"] + 1e-9]
    if not seg:
        return None
    k = _chave(p["h"], seg[0])
    if k not in proj["perfis"]:
        proj["perfis"][k] = {**p, "t": seg[0]}
    return k


def _seguinte(proj, chave, escada):
    p = proj["perfis"].get(chave) or {}
    h, t = p.get("h", 0), p.get("t", 0)
    for hh, tt in escada:
        if (hh, tt) > (h, t + 1e-9) and (hh > h or tt > t + 1e-9):
            return _garante_perfil(proj, hh, tt)
    return None


def _parede_fonte(proj, ref):
    """ref « RC-3 » → (perímetro RC, lado 2) ; ref « I1 » → parede avulsa I1."""
    for per in proj.get("perimetros") or []:
        m = re.fullmatch(re.escape(str(per["id"])) + r"-(\d+)", str(ref))
        if m:
            return "per", per, int(m.group(1)) - 1
    for w in proj.get("paredes") or []:
        if str(w.get("id")) == str(ref):
            return "par", w, None
    return None, None, None


def _tipo_proprio(proj, kind, obj, lado, ref):
    """Tipo de parede só desta parede (cópia do tipo atual) para a reforçar sem mexer nas outras."""
    T = proj["tiposParede"]
    if kind == "per":
        atual = (obj.get("tiposLado") or {}).get(str(lado)) or obj["tipo"]
    else:
        atual = obj["tipo"]
    novo = f"{obj['tipo'] if kind == 'per' else atual}@{ref}"
    if atual != novo:
        T[novo] = copy.deepcopy(T[atual])
        T[novo]["nome"] = f"{T[atual].get('nome', atual)} — {ref} (reforçada)"
        if kind == "per":
            obj.setdefault("tiposLado", {})[str(lado)] = novo
        else:
            obj["tipo"] = novo
    return T[novo]


def _reforca(proj, c, log, fr):
    grupo, ref, el = c.get("grupo"), c.get("ref"), c.get("elemento") or ""
    r = c.get("ratio") or 0
    if grupo in ("Montantes", "Vergas"):
        kind, obj, lado = _parede_fonte(proj, ref)
        if not kind:
            return False
        T = _tipo_proprio(proj, kind, obj, lado, ref)
        if grupo == "Vergas":
            antes = T.get("verga")
            k = _seguinte(proj, antes, VERGAS)
            if not k:
                return False
            T["verga"] = k
            log.append((f"{ref} : linteaux {antes} → {k} (taux {r:.2f})" if fr else f"{ref}: vergas {antes} → {k} (taxa {r:.2f})"))
            return True
        antes = T.get("montante")
        k = _mais_espesso(proj, antes)
        if k:
            T["montante"] = k
            log.append((f"{ref} : montants {antes} → {k} (taux {r:.2f})" if fr else f"{ref}: montantes {antes} → {k} (taxa {r:.2f})"))
            return True
        sp = [s for s in ESPACAMENTOS if s < float(T.get("espacamento") or 600) - 1]
        if sp:
            log.append((f"{ref} : entraxe des montants {int(T.get('espacamento') or 600)} → {sp[0]} mm (taux {r:.2f})" if fr
                        else f"{ref}: espaçamento dos montantes {int(T.get('espacamento') or 600)} → {sp[0]} mm (taxa {r:.2f})"))
            T["espacamento"] = sp[0]
            return True
        return False
    if grupo == "Vigas de piso":
        f = next((x for x in proj.get("pisos") or [] if str(x.get("id")) == str(ref)), None)
        if not f:
            return False
        antes = f.get("viga")
        k = _seguinte(proj, antes, VIGAS)
        if k:
            f["viga"] = k
            log.append((f"{ref} : solives {antes} → {k} (taux {r:.2f})" if fr else f"{ref}: vigas {antes} → {k} (taxa {r:.2f})"))
            return True
        sp = [s for s in ESPACAMENTOS if s < float(f.get("espacamento") or 600) - 1]
        if sp:
            f["espacamento"] = sp[0]
            log.append((f"{ref} : entraxe des solives → {sp[0]} mm" if fr else f"{ref}: espaçamento das vigas → {sp[0]} mm"))
            return True
        return False
    if grupo == "Asnas":
        cb = next((x for x in proj.get("coberturas") or [] if str(x.get("id")) == str(ref)), None)
        if not cb:
            return False
        campo = "diagonal" if "Diagonal" in el else "banzo"
        antes = cb.get(campo)
        k = _mais_espesso(proj, antes)
        if k:
            cb[campo] = k
            log.append((f"{ref} : fermes ({campo}) {antes} → {k} (taux {r:.2f})" if fr
                        else f"{ref}: asnas ({campo}) {antes} → {k} (taxa {r:.2f})"))
            return True
        sp = [s for s in ESPACAMENTOS if s < float(cb.get("espacamento") or 600) - 1]
        if sp:
            cb["espacamento"] = sp[0]
            log.append((f"{ref} : entraxe des fermes → {sp[0]} mm" if fr else f"{ref}: espaçamento das asnas → {sp[0]} mm"))
            return True
    return False


def dimensionar(projeto: dict) -> tuple[dict, list[str]]:
    """Devolve (projeto reforçado, alterações). Projeto inalterado se tudo já passa ou se a verificação falha."""
    if projeto.get("dimensionamentoAuto") is False:
        return projeto, []
    fr = str(projeto.get("country") or "").upper() == "FR"
    proj = copy.deepcopy(projeto)
    log: list[str] = []
    for _ in range(MAX_ITER):
        try:
            ver = verificar(proj, calcular(proj))
        except Exception:  # noqa: BLE001 — sem verificação legível, não se mexe no projeto
            return (proj if log else projeto), log
        falhas = [c for c in ver.get("verificacoes") or [] if (c.get("ratio") or 0) > 1.0]
        if not falhas:
            break
        feito = set()
        mudou = False
        for c in sorted(falhas, key=lambda x: -(x.get("ratio") or 0)):
            chave = (c.get("grupo") == "Vergas", c.get("grupo"), c.get("ref"))
            if chave in feito:
                continue
            feito.add(chave)
            mudou |= _reforca(proj, c, log, fr)
        if not mudou:
            log.append("Certains éléments restent au-delà de la limite : à reprendre par le bureau d'études." if fr
                       else "Alguns elementos continuam acima do limite: a rever pelo gabinete de estruturas.")
            break
    return (proj if log else projeto), log
