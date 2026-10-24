"""Contrôles de conformité, recalculés sur l'implantation FINALE (proposée ou modifiée)."""
from __future__ import annotations

from collections import Counter

from . import geometry as G
from .equipment import FOOTPRINT
from .i18n import tr
from .rules import HABITABLE


def run(levels, points, equipment, elec, plumb, options, rules, lang) -> list[dict]:
    er, pr = rules["elec"], rules["plumbing"]
    out: list[dict] = []

    def add(domain, status, msg, source=None, ref=None):
        out.append({"domain": domain, "status": status, "message": msg, "source": source, "ref": ref})

    src = er["sources"]
    by_room = {}
    for p in points:
        by_room.setdefault(p["room_id"], Counter())[p["kind"]] += 1
    for lv in levels:
        for r in lv.rooms:
            if r.type in ("escalier", "exterieur"):
                continue
            c = by_room.get(r.id, Counter())
            s = r.area
            need = er["sockets"](r.type, s)
            have = c["prise"]
            status = "ok" if have >= need else ("warning" if er["sockets_practice"] else "error")
            if need:
                add("elec", status, tr(lang, "chk.sockets", room=r.name, n=have, min=need), src["sockets"], r.id)
            need_w = er["worktop"](r.type, s)
            if need_w:
                hw = c["prise_plan_travail"]
                add("elec", "ok" if hw >= need_w else "error",
                    tr(lang, "chk.worktop", room=r.name, n=hw, min=need_w), src["sockets"], r.id)
            nl = c["point_lumineux"]
            add("elec", "ok" if nl >= 1 else "error", tr(lang, "chk.light", room=r.name, n=nl), src["sockets"], r.id)
            if nl and not (c["interrupteur"] + c["va_et_vient"]):
                add("elec", "error", tr(lang, "chk.switch", room=r.name), src["sockets"], r.id)
            need_rj = er["rj45"](r.type, s)
            if need_rj:
                add("elec", "ok" if c["rj45"] >= need_rj else "warning",
                    tr(lang, "chk.rj45", room=r.name, n=c["rj45"], min=need_rj), src["sockets"], r.id)
            if r.type in ("salle_de_bain", "salle_d_eau"):
                fps = [G.rect_footprint((f["x"], f["y"]), *FOOTPRINT[f["kind"]])
                       for f in equipment if f["room_id"] == r.id and f["kind"] in ("douche", "baignoire")]
                for p in points:
                    if p["room_id"] == r.id and p["kind"] in ("prise", "prise_specialisee") and fps:
                        d = min(G.dist_point_to_rect((p["x"], p["y"]), fp) for fp in fps)
                        lim = er["bathroom_clearance_m"]
                        add("elec", "ok" if d >= lim else "error",
                            tr(lang, "chk.bath", room=r.name, d=f"{d:.2f}", min=lim), src["bathroom"], p["id"])
    if er["sockets_practice"]:
        add("elec", "info", tr(lang, "chk.practice"), src["sockets"])
    # circuits
    for c in elec["circuits"]:
        lim = {"eclairage": er["lighting_circuit"]["max_points"], "prises": er["socket_circuit"]["max_points"],
               "prises_cuisine": er["worktop_circuit"]["max_points"]}.get(c["kind"])
        if lim:
            n = len(c["points"])
            add("elec", "ok" if n <= lim else "error", tr(lang, "chk.circuit", c=f'{c["id"]} {c["label"]}', n=n, max=lim),
                src["circuits"], c["id"])
    uses = {c.get("use") for c in elec["circuits"]}
    for u in ("plaque", "lave_linge", "lave_vaisselle", "four", "chauffe_eau"):
        if u in uses:
            add("elec", "ok", tr(lang, "chk.spec", u=er["specialised"][u]["label"]), src["circuits"])
    for r in elec["rcds"]:
        n = len(r["circuits"])
        add("elec", "ok" if n <= er["rcd_max_circuits"] else "error",
            tr(lang, "chk.rcd", r=f'{r["id"]} {r["rating_a"]} A type {r["type"]}', n=n, max=er["rcd_max_circuits"]),
            src["rcd"], r["id"])
    surf = round(sum(r.area for lv in levels for r in lv.rooms if r.type in HABITABLE), 1)
    add("elec", "info", tr(lang, "chk.rcd_count", n=len(elec["rcds"]), s=surf), src["rcd"])
    pnl = elec["panel"]
    pct = round(100 * pnl["modules_reserve"] / max(1, pnl["modules_used"]))
    add("elec", "ok" if pct >= 100 * er["reserve_ratio"] - 0.5 else "error",
        tr(lang, "chk.reserve", r=pnl["modules_reserve"], u=pnl["modules_used"], p=pct), src["reserve"])
    if er["smoke_detector_per_level"]:
        for lv in levels:
            n = sum(1 for p in points if p["kind"] == "daaf" and p["level_id"] == lv.id)
            add("elec", "ok" if n >= er["smoke_detector_per_level"] else "warning",
                tr(lang, "chk.daaf", level=lv.name, n=n), src["smoke"])
    # plomberie
    psrc = pr["sources"]
    vmax = pr["max_velocity"]
    for s in plumb["supplies"] + plumb["risers"] + ([plumb["main"]] if plumb.get("main") else []):
        v = s.get("velocity_ms")
        if v is None:
            continue
        if v > s.get("v_max", vmax):
            add("plumb", "error", tr(lang, "chk.velocity", id=s.get("id", "AEP"), f=s.get("fixture", s.get("net", "")),
                                     v=v, max=s.get("v_max", vmax)), psrc["velocity"], s.get("id"))
    worst = [d for d in plumb["drains"] if d["drop_m"] > d["available_m"]]
    for d in worst:
        add("plumb", "error", tr(lang, "chk.drop", id=d["id"], f=d["fixture"], d=d["drop_m"], a=d["available_m"],
                                 s=round(d["slope"] * 100, 1)), psrc["drain"], d["id"])
    if plumb["drains"] and not worst:
        add("plumb", "ok", tr(lang, "chk.drop", id="EU/EV", f="—", d=max(d["drop_m"] for d in plumb["drains"]),
                              a=min(d["available_m"] for d in plumb["drains"]), s=round(pr["slope_min"] * 100, 1)),
            psrc["drain"])
    col = plumb.get("collector")
    if col and col["drop_m"] > col["available_m"]:
        add("plumb", "error", tr(lang, "chk.drop", id="COL", f="collecteur", d=col["drop_m"], a=col["available_m"],
                                 s=round(col["slope"] * 100, 1)), psrc["drain"], "COL")
    for d in plumb["drains"]:
        if d["fixture"] == "wc" and d["to"] != "COL" and d["length_m"] > 2.0:
            add("plumb", "warning", tr(lang, "chk.wc_long", id=d["id"], l=d["length_m"]), psrc["drain"], d["id"])
    for st in plumb["stacks"]:
        add("plumb", "warning", tr(lang, "chk.stack", id=st["id"], d=st["diameter_mm"], room=st["lands_in_room"] or "?"),
            psrc["drain"], st["id"])
    if pr.get("dtu"):
        _dtu_checks(add, plumb, equipment, options, pr, lang)
    auto = [f for f in equipment if f.get("source") == "auto"]
    if auto:
        add("plumb", "warning", tr(lang, "chk.auto", n=len(auto)), None)
    for lv in levels[1:]:
        add("plumb", "warning", tr(lang, "chk.levels", level=lv.name), None)
    return out


def _dtu_checks(add, plumb, equipment, options, pr, lang):
    """Contrôles tirés des DTU fournis (60.11, 60.33, 60.1 P1-1-3) — FR uniquement."""
    from engines import dtu_plomberie as D
    psrc = pr["sources"]
    fx = pr["fixtures"]
    seen = set()
    for d in plumb["drains"]:
        k = d["fixture"]
        if k in fx and d["diameter_mm"] > fx[k]["drain"] and (k, d["diameter_mm"]) not in seen:
            seen.add((k, d["diameter_mm"]))
            add("plumb", "info", tr(lang, "chk.branch_up", f=fx[k]["label"], d=d["diameter_mm"], need=d["d_int_min_mm"]),
                psrc["siphon"], d["id"])
    for st in plumb["stacks"]:
        add("plumb", "ok", tr(lang, "chk.stack_dtu", id=st["id"], d=st["diameter_mm"], need=st["d_int_min_mm"],
                              n=len(st["fixtures"])), psrc["drain"], st["id"])
    col = plumb.get("collector")
    if col and "capacity_ls" in col:
        add("plumb", "ok" if col["q_probable_ls"] <= col["capacity_ls"] else "error",
            tr(lang, "chk.collector", d=col["diameter_mm"], q=col["q_probable_ls"], c=col["capacity_ls"],
               s=round(col["slope"] * 100, 1)), psrc["collector"], "COL")
    if plumb["drains"] or plumb["stacks"]:
        add("plumb", "info", tr(lang, "chk.supports"), psrc["supports"])
        add("plumb", "info", tr(lang, "chk.hyp", h=D.HYPOTHESES["pvc_wall"]), psrc["drain"])
    if plumb.get("heater"):
        add("plumb", "info", tr(lang, "chk.heater"), psrc["heater"])
        if pr["pipe_material"] != "cuivre":
            add("plumb", "warning", tr(lang, "chk.heater_per", mat=pr["pipe_material"]), psrc["heater"])
    if any(f["kind"] == "baignoire" for f in equipment) and not options.get("bath_capacity_l"):
        add("plumb", "info", tr(lang, "chk.hyp", h=D.HYPOTHESES["baignoire"]), psrc["supply"])
    if any(r.get("method") == "individuelle" for r in plumb["risers"] + [plumb.get("main") or {}]):
        add("plumb", "info", tr(lang, "chk.hyp", h=D.HYPOTHESES["graphique"]), psrc["supply"])
