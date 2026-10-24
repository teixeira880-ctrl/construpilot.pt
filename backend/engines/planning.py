"""Module 6 — Planning de chantier déterministe (CPM + ressources) et propositions de réorganisation.

Aucune IA : chemin critique, ordonnancement sous contrainte d'équipes, replanification sur avancement réel,
suggestions calculées en rejouant le planning (gain mesuré, jamais estimé).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

TRADE_ORDER = [
    ("demolition", "Demolição", ["demol", "dépose", "depose", "curage"]),
    ("terrassement", "Movimentação de terras", ["terrass", "fouille", "vrd", "réseaux ext"]),
    ("gros_oeuvre", "Obra grossa", ["gros", "maçon", "macon", "béton", "beton", "fondation", "dalle", "semelle", "parpaing", "structure", "ipn"]),
    ("charpente", "Carpintaria", ["charpente", "ossature bois"]),
    ("couverture", "Cobertura", ["couvert", "toiture", "tuile", "zinguerie", "étanch", "etanch"]),
    ("menuiseries_ext", "Caixilharia exterior", ["menuiserie ext", "fenêtre", "fenetre", "porte d'entrée", "volet", "baie"]),
    ("plomberie", "Canalização", ["plomb", "sanitaire", "evacuation", "évacuation"]),
    ("electricite", "Eletricidade", ["élec", "elec", "courant", "tableau"]),
    ("chauffage", "Aquecimento / AVAC", ["chauff", "pac", "bomba de calor", "vmc", "ventil", "clim", "radiateur"]),
    ("isolation", "Isolamento", ["isol", "ite", "iti", "laine"]),
    ("platrerie", "Estuques / Divisórias", ["plâtre", "platre", "placo", "cloison", "doublage", "faux plafond", "ba13"]),
    ("chape", "Betonilha / Autonivelante", ["chape", "ragré", "ragre"]),
    ("carrelage", "Revestimento cerâmico / Azulejo", ["carrel", "faïence", "faience"]),
    ("menuiseries_int", "Carpintarias interiores", ["menuiserie int", "porte int", "placard", "escalier", "parquet"]),
    ("peinture", "Pintura", ["peint", "enduit", "ravalement", "papier peint"]),
    ("sols", "Pavimentos vinílicos", ["sol souple", "pvc", "lino", "moquette", "stratifié"]),
    ("cuisine", "Cozinha / Mobiliário", ["cuisine", "agencement", "meuble"]),
    ("nettoyage", "Limpeza / Receção", ["nettoy", "réception", "reception", "livraison"]),
]
_RANK = {code: i for i, (code, _, _) in enumerate(TRADE_ORDER)}
DEFAULT_DURATION = 5


def guess_trade(label: str) -> tuple[str, str]:
    low = (label or "").lower()
    for code, name, keys in TRADE_ORDER:
        if any(k in low for k in keys):
            return code, name
    return "autre", (label or "Autres").strip() or "Autres"


def tasks_from_lots(lots: list[str]) -> list[dict]:
    """Tâches séquentielles ordonnées selon l'ordre BTP classique ; durée par défaut explicitement flaggée."""
    rows = []
    for i, lot in enumerate(lots):
        code, trade = guess_trade(lot)
        rows.append((_RANK.get(code, 99), i, lot, trade))
    rows.sort()
    tasks, prev = [], None
    for n, (_, _, lot, trade) in enumerate(rows, 1):
        tid = f"t{n}"
        tasks.append({"id": tid, "name": lot, "resource": trade, "duration": DEFAULT_DURATION,
                      "duration_source": "defaut", "progress": 0, "auto_link": True,
                      "predecessors": [{"id": prev, "lag": 0}] if prev else []})
        prev = tid
    return tasks


# ---------------------------------------------------------------- calendrier (jours ouvrés)
class Calendar:
    def __init__(self, start: date, workdays: list[int], holidays: list[str]):
        self.start = start
        self.workdays = set(workdays or [0, 1, 2, 3, 4])
        self.holidays = {date.fromisoformat(h) for h in (holidays or []) if h}
        self._cache: list[date] = []

    def is_work(self, d: date) -> bool:
        return d.weekday() in self.workdays and d not in self.holidays

    def day(self, idx: int) -> date:
        """Date du idx-ième jour ouvré (0 = premier jour ouvré ≥ start)."""
        while len(self._cache) <= idx:
            d = (self._cache[-1] + timedelta(days=1)) if self._cache else self.start
            while not self.is_work(d):
                d += timedelta(days=1)
            self._cache.append(d)
        return self._cache[idx]

    def index(self, d: date) -> int:
        """Index ouvré de la date (le prochain jour ouvré si d est chômé) ; 0 si antérieure au début."""
        if d <= self.start:
            return 0
        i = 0
        while self.day(i) < d:
            i += 1
        return i


# ---------------------------------------------------------------- noyau CPM + ressources
class PlanningError(ValueError):
    pass


def _topo(tasks: dict) -> list[str]:
    indeg = {t: 0 for t in tasks}
    for t in tasks.values():
        for p in t["predecessors"]:
            if p["id"] not in tasks:
                raise PlanningError(f"Antecessora desconhecida «{p['id']}» para a tarefa «{t['name']} »")
            indeg[t["id"]] += 1
    order, stack = [], sorted([t for t, d in indeg.items() if d == 0])
    while stack:
        cur = stack.pop(0)
        order.append(cur)
        for t in tasks.values():
            if any(p["id"] == cur for p in t["predecessors"]):
                indeg[t["id"]] -= 1
                if indeg[t["id"]] == 0:
                    stack.append(t["id"])
        stack.sort()
    if len(order) != len(tasks):
        raise PlanningError("Ciclo de dependências detetado: uma tarefa depende (indiretamente) de si própria.")
    return order


def _normalize(raw_tasks: list[dict]) -> dict:
    tasks = {}
    for t in raw_tasks:
        tid = str(t.get("id") or "").strip()
        if not tid:
            raise PlanningError("Tarefa sem identificador")
        dur = int(t.get("duration") or 0)
        if dur < 1:
            raise PlanningError(f"Duração inválida para «{t.get('name') or tid}» (≥ 1 dia útil)")
        preds = []
        for p in t.get("predecessors") or []:
            pid = p.get("id") if isinstance(p, dict) else p
            if pid and pid != tid:
                preds.append({"id": str(pid), "lag": int((p.get("lag") if isinstance(p, dict) else 0) or 0)})
        tasks[tid] = {"id": tid, "name": (t.get("name") or tid).strip(), "resource": (t.get("resource") or "Equipa").strip(),
                      "duration": dur, "predecessors": preds, "progress": max(0, min(100, int(t.get("progress") or 0))),
                      "not_before": t.get("not_before") or None, "actual_start": t.get("actual_start") or None,
                      "actual_end": t.get("actual_end") or None, "auto_link": bool(t.get("auto_link")),
                      "duration_source": t.get("duration_source") or "saisie"}
    return tasks


def _cpm(tasks: dict, order: list[str], release: dict) -> dict:
    es, ef = {}, {}
    for tid in order:
        t = tasks[tid]
        start = release.get(tid, 0)
        for p in t["predecessors"]:
            start = max(start, ef[p["id"]] + p["lag"])
        es[tid], ef[tid] = start, start + t["duration"]
    horizon = max(ef.values()) if ef else 0
    lf, ls = {}, {}
    for tid in reversed(order):
        end = horizon
        for s in tasks.values():
            for p in s["predecessors"]:
                if p["id"] == tid:
                    end = min(end, ls[s["id"]] - p["lag"])
        lf[tid], ls[tid] = end, end - tasks[tid]["duration"]
    return {tid: {"es": es[tid], "ef": ef[tid], "ls": ls[tid], "lf": lf[tid], "slack": ls[tid] - es[tid]} for tid in order}


def _serial_sgs(tasks: dict, order: list[str], cpm: dict, release: dict, capacity: dict) -> dict:
    """Ordonnancement série : priorité au plus petit LS, puis ES, puis id. Capacité par ressource (équipes)."""
    busy: dict[str, list[tuple[int, int]]] = {}
    sched = {}
    for tid in sorted(order, key=lambda x: ("_fixed_start" not in tasks[x], cpm[x]["ls"], cpm[x]["es"], x)):
        t = tasks[tid]
        cap = max(1, int(capacity.get(t["resource"], 1)))
        intervals = busy.setdefault(t["resource"], [])
        if "_fixed_start" in t:  # réalité terrain : jamais déplacée
            start = t["_fixed_start"]
            intervals.append((start, start + t["duration"]))
            sched[tid] = {"start": start, "end": start + t["duration"], "resource_delay": 0}
            continue
        start = release.get(tid, 0)
        for p in t["predecessors"]:
            start = max(start, sched.get(p["id"], {"end": cpm[p["id"]]["ef"]})["end"] + p["lag"])
        earliest = start
        while True:
            end = start + t["duration"]
            overlap_peak = 0
            for d in range(start, end):
                n = sum(1 for (a, b) in intervals if a <= d < b)
                overlap_peak = max(overlap_peak, n)
            if overlap_peak < cap:
                break
            start += 1
        intervals.append((start, start + t["duration"]))
        sched[tid] = {"start": start, "end": start + t["duration"], "resource_delay": start - earliest}
    return sched


def _release_dates(tasks: dict, cal: Calendar, today: date) -> tuple[dict, dict]:
    """Avancement réel : tâches finies figées, en cours → reliquat dès aujourd'hui, non démarrées ≥ aujourd'hui."""
    release, fixed = {}, {}
    today_idx = cal.index(today)
    for tid, t in tasks.items():
        if t["not_before"]:
            release[tid] = max(release.get(tid, 0), cal.index(date.fromisoformat(t["not_before"])))
        if t["progress"] >= 100 or t["actual_end"]:
            end_d = date.fromisoformat(t["actual_end"]) if t["actual_end"] else today
            start_d = date.fromisoformat(t["actual_start"]) if t["actual_start"] else end_d
            fixed[tid] = (cal.index(start_d), max(cal.index(end_d) + 1, cal.index(start_d) + 1))
        elif t["actual_start"] or t["progress"] > 0:
            remaining = max(1, math.ceil(t["duration"] * (100 - t["progress"]) / 100))
            fixed[tid] = (cal.index(date.fromisoformat(t["actual_start"])) if t["actual_start"] else today_idx, today_idx + remaining)
        else:
            release[tid] = max(release.get(tid, 0), today_idx)
    return release, fixed


def _apply_fixed(tasks: dict, fixed: dict) -> dict:
    """Les tâches figées deviennent des tâches à date imposée (durée = fenêtre réelle, départ forcé)."""
    out = {}
    for tid, t in tasks.items():
        t2 = dict(t)
        if tid in fixed:
            s, e = fixed[tid]
            t2["duration"], t2["_fixed_start"] = e - s, s
        out[tid] = t2
    return out


def compute_schedule(plan: dict, today: Optional[date] = None, capacity_override: Optional[dict] = None,
                     duration_override: Optional[dict] = None) -> dict:
    today = today or date.today()
    start = date.fromisoformat(plan["start_date"])
    tasks = _normalize(plan.get("tasks") or [])
    for t in tasks.values():  # le calendrier doit couvrir les dates réelles saisies, même antérieures au début prévu
        for k in ("actual_start", "actual_end", "not_before"):
            if t.get(k):
                start = min(start, date.fromisoformat(t[k]))
    cal = Calendar(start, plan.get("workdays") or [0, 1, 2, 3, 4], plan.get("holidays") or [])
    base_idx = cal.index(date.fromisoformat(plan["start_date"]))
    if duration_override:
        for tid, d in duration_override.items():
            if tid in tasks:
                tasks[tid]["duration"] = max(1, int(d))
    capacity = dict(plan.get("capacities") or {})
    if capacity_override:
        capacity.update(capacity_override)
    order = _topo(tasks)
    release, fixed = _release_dates(tasks, cal, today)
    for tid in tasks:
        if tid not in fixed:
            release[tid] = max(release.get(tid, 0), base_idx)
    tasks = _apply_fixed(tasks, fixed)
    for tid, (s, _) in fixed.items():
        release[tid] = s
    cpm = _cpm(tasks, order, release)
    sched = _serial_sgs(tasks, order, cpm, release, capacity)
    for tid, (s, e) in fixed.items():  # une tâche réelle ne bouge pas
        sched[tid] = {"start": s, "end": e, "resource_delay": 0}
    end_idx = max((v["end"] for v in sched.values()), default=0)
    # marge effective après prise en compte des équipes (jours de décalage possibles sans retarder la fin)
    eff = {}
    for tid in reversed(order):
        lim = end_idx
        for s in tasks.values():
            for p in s["predecessors"]:
                if p["id"] == tid:
                    lim = min(lim, sched[s["id"]]["start"] - p["lag"])
        eff[tid] = max(0, lim - sched[tid]["end"])
    rows = []
    for tid in order:
        t, c, s = tasks[tid], cpm[tid], sched[tid]
        slack = min(c["slack"], eff[tid])
        rows.append({**{k: t[k] for k in ("id", "name", "resource", "duration", "predecessors", "progress", "not_before",
                                           "actual_start", "actual_end", "auto_link", "duration_source")},
                     "start_idx": s["start"], "end_idx": s["end"], "start_date": cal.day(s["start"]).isoformat(),
                     "end_date": cal.day(s["end"] - 1).isoformat(), "slack": slack, "critical": slack == 0,
                     "resource_delay": s["resource_delay"], "fixed": tid in fixed,
                     "late": (tid not in fixed and s["end"] <= cal.index(today) and t["progress"] < 100 and cal.index(today) > 0)})
    critical_path = [r["id"] for r in rows if r["critical"]]
    deadline = plan.get("deadline")
    deadline_gap = None
    if deadline:
        deadline_gap = cal.index(date.fromisoformat(deadline)) + 1 - end_idx  # >0 = avance, <0 = retard (j ouvrés)
    load = {}
    for r in rows:
        g = load.setdefault(r["resource"], {"resource": r["resource"], "tasks": 0, "days": 0, "capacity": int(capacity.get(r["resource"], 1))})
        g["tasks"] += 1
        g["days"] += r["duration"]
    first_idx = min((r["start_idx"] for r in rows), default=0)
    return {"tasks": rows, "project": {"start_date": cal.day(first_idx).isoformat() if rows else plan["start_date"],
                                        "end_date": cal.day(max(end_idx - 1, 0)).isoformat(), "duration_workdays": end_idx - first_idx,
                                        "critical_path": critical_path, "deadline": deadline, "deadline_gap_days": deadline_gap,
                                        "as_of": today.isoformat()},
            "resources": sorted(load.values(), key=lambda g: -g["days"]), "_cal": cal}


# ---------------------------------------------------------------- propositions de réorganisation
def suggestions(plan: dict, result: dict, today: Optional[date] = None, baseline: Optional[dict] = None) -> list[dict]:
    today = today or date.today()
    out = []
    rows = result["tasks"]
    end = result["project"]["duration_workdays"]
    by_id = {r["id"]: r for r in rows}

    gap = result["project"].get("deadline_gap_days")
    if gap is not None:
        if gap < 0:
            out.append({"kind": "deadline", "severity": "critical", "title": f'Fim previsto {abs(gap)} dia(s) útil(eis) após a data objetivo',
                        "detail": f"Fim calculado em {result['project']['end_date']} para um objetivo a {plan['deadline']}. Ver as alavancas abaixo (ganho medido).",
                        "task_ids": [], "gain_days": 0})
        else:
            out.append({"kind": "deadline", "severity": "success", "title": f'Objetivo cumprido com {gap} dia(s) útil(eis) de antecedência',
                        "detail": f"Fim calculado em {result['project']['end_date']}.", "task_ids": [], "gain_days": gap})

    if baseline and baseline.get("end_date"):
        b_end = date.fromisoformat(baseline["end_date"])
        cur_end = date.fromisoformat(result["project"]["end_date"])
        drift = (cur_end - b_end).days
        if drift > 0:
            shifted = [r["id"] for r in rows if (baseline.get("tasks") or {}).get(r["id"]) and r["end_date"] > baseline["tasks"][r["id"]]]
            out.append({"kind": "drift", "severity": "high", "title": f'Desvio de {drift} dia(s) de calendário vs planeamento de referência',
                        "detail": f"Referência: fim em {baseline['end_date']} → agora {result['project']['end_date']}. {len(shifted)} tarefa(s) desfasada(s).",
                        "task_ids": shifted[:20], "gain_days": 0})

    late = [r for r in rows if r["late"]]
    if late:
        out.append({"kind": "late", "severity": "high", "title": f'{len(late)} tarefa(s) deveriam estar concluídas',
                    "detail": "Introduza o avanço real (%) ou a data de fim: o planeamento é recalculado a partir de hoje.",
                    "task_ids": [r["id"] for r in late], "gain_days": 0})

    # Levier 1 : équipe supplémentaire — gain MESURÉ en rejouant le planning
    delayed_res = {}
    for r in rows:
        if r["resource_delay"] > 0 and not r["fixed"]:
            delayed_res.setdefault(r["resource"], []).append(r["id"])
    caps = plan.get("capacities") or {}
    for res, tids in sorted(delayed_res.items(), key=lambda kv: -len(kv[1])):
        cur_cap = int(caps.get(res, 1))
        alt = compute_schedule(plan, today, capacity_override={res: cur_cap + 1})
        gain = end - alt["project"]["duration_workdays"]
        if gain > 0:
            out.append({"kind": "add_crew", "severity": "medium", "title": f'Uma equipa «{res}» a mais: fim antecipado em {gain} dia(s) útil(eis)',
                        "detail": f"{len(tids)} tarefa(s) aguardam que uma equipa {res} fique livre (capacidade atual {cur_cap}). Passar a {cur_cap + 1} equipas encurta a obra para {alt['project']['end_date']}.",
                        "task_ids": tids, "gain_days": gain, "action": {"type": "capacity", "resource": res, "value": cur_cap + 1}})

    # Levier 2 : raccourcir une tâche critique — gain mesuré (−1 j)
    crit = sorted([r for r in rows if r["critical"] and not r["fixed"] and r["duration"] > 1], key=lambda r: -r["duration"])[:5]
    for r in crit:
        alt = compute_schedule(plan, today, duration_override={r["id"]: r["duration"] - 1})
        gain = end - alt["project"]["duration_workdays"]
        if gain > 0:
            out.append({"kind": "crash", "severity": "info", "title": f"Caminho crítico: «{r['name']} » −1 j = fin −{gain} j",
                        "detail": f"Tarefa crítica ({r['duration']} j, {r['resource']}). Cada dia ganho aqui repercute-se no fim da obra; um dia perdido atrasa-o outro tanto.",
                        "task_ids": [r["id"]], "gain_days": gain})

    # Levier 3 : enchaînements automatiques (ordre BTP par défaut) → chevauchement possible si validé par le pro
    for r in rows:
        if r["auto_link"] and r["predecessors"] and not r["fixed"] and r["critical"]:
            p = by_id.get(r["predecessors"][0]["id"])
            if p and p["resource"] != r["resource"]:
                out.append({"kind": "overlap", "severity": "info", "title": f"« {p['name']} » → « {r['name']}» : encadeamento por omissão",
                            "detail": "Esta ligação foi criada automaticamente (ordem clássica da construção). Se as especialidades se puderem sobrepor na obra, remova ou reduza a dependência (desfasamento negativo): o planeamento será recalculado.",
                            "task_ids": [p["id"], r["id"]], "gain_days": 0})
    out = out[:12] if len([o for o in out if o["kind"] == "overlap"]) > 4 else out

    # Marges disponibles
    slackers = [r for r in rows if r["slack"] >= 5 and not r["fixed"] and r["progress"] < 100]
    if slackers:
        out.append({"kind": "slack", "severity": "info", "title": f'{len(slackers)} tarefa(s) com ≥ 5 d de folga',
                    "detail": "Estas tarefas podem ser desfasadas sem atrasar o fim: útil para alisar a carga das equipas ou absorver um imprevisto. "
                              + ", ".join(f"{r['name']} ({r['slack']} j)" for r in slackers[:6]),
                    "task_ids": [r["id"] for r in slackers], "gain_days": 0})

    # Creux par ressource (> 3 j entre deux tâches)
    for res in {r["resource"] for r in rows}:
        rr = sorted([r for r in rows if r["resource"] == res], key=lambda r: r["start_idx"])
        for a, b in zip(rr, rr[1:]):
            idle = b["start_idx"] - a["end_idx"]
            if idle > 3:
                out.append({"kind": "idle", "severity": "info", "title": f'Equipa {res} sem ocupação durante {idle} dias úteis',
                            "detail": f"Entre « {a['name']} » e « {b['name']} ». Prever outra atribuição ou antecipar uma tarefa sem antecessora bloqueante.",
                            "task_ids": [a["id"], b["id"]], "gain_days": 0})
    sev = {"critical": 0, "high": 1, "medium": 2, "info": 3, "success": 4}
    out.sort(key=lambda s: (sev.get(s["severity"], 9), -s["gain_days"]))
    return out


# ---------------------------------------------------------------- optimisation OR-Tools (CP-SAT)
def optimize(plan: dict, today: Optional[date] = None, time_limit_s: float = 10.0) -> dict:
    """Minimise la fin de chantier sous contraintes de précédence + capacité des équipes (CP-SAT)."""
    from ortools.sat.python import cp_model

    today = today or date.today()
    base = compute_schedule(plan, today)
    cal = base["_cal"]
    tasks = {r["id"]: r for r in base["tasks"]}
    horizon = sum(r["duration"] for r in base["tasks"]) + max((r["start_idx"] for r in base["tasks"]), default=0) + 1
    m = cp_model.CpModel()
    iv, st, en = {}, {}, {}
    for tid, r in tasks.items():
        d = r["end_idx"] - r["start_idx"] if r["fixed"] else r["duration"]
        s = m.NewIntVar(0, horizon, f"s_{tid}")
        e = m.NewIntVar(0, horizon, f"e_{tid}")
        iv[tid] = m.NewIntervalVar(s, d, e, f"i_{tid}")
        st[tid], en[tid] = s, e
        if r["fixed"]:
            m.Add(s == r["start_idx"])
        else:
            lb = max(cal.index(today), cal.index(date.fromisoformat(plan["start_date"])))
            if r["not_before"]:
                lb = max(lb, cal.index(date.fromisoformat(r["not_before"])))
            m.Add(s >= lb)
    for tid, r in tasks.items():
        for p in r["predecessors"]:
            m.Add(st[tid] >= en[p["id"]] + int(p["lag"]))
    caps = plan.get("capacities") or {}
    for res in {r["resource"] for r in tasks.values()}:
        ids = [t for t, r in tasks.items() if r["resource"] == res]
        cap = max(1, int(caps.get(res, 1)))
        if cap == 1:
            m.AddNoOverlap([iv[t] for t in ids])
        else:
            m.AddCumulative([iv[t] for t in ids], [1] * len(ids), cap)
    mk = m.NewIntVar(0, horizon, "makespan")
    m.AddMaxEquality(mk, list(en.values()))
    m.Minimize(mk)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 4
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"ok": False, "reason": "Nenhuma solução encontrada no tempo disponível", "baseline_days": base["project"]["duration_workdays"]}
    rows = []
    for r in base["tasks"]:
        s = solver.Value(st[r["id"]])
        e = solver.Value(en[r["id"]])
        rows.append({"id": r["id"], "name": r["name"], "resource": r["resource"], "start_idx": s, "end_idx": e,
                     "start_date": cal.day(s).isoformat(), "end_date": cal.day(max(e - 1, 0)).isoformat(),
                     "moved_days": s - r["start_idx"]})
    mk_v = solver.Value(mk)
    return {"ok": True, "optimal": status == cp_model.OPTIMAL, "makespan_days": mk_v, "baseline_days": base["project"]["duration_workdays"],
            "gain_days": base["project"]["duration_workdays"] - mk_v, "end_date": cal.day(max(mk_v - 1, 0)).isoformat(),
            "tasks": rows, "moved": [r for r in rows if r["moved_days"] != 0]}


def apply_optimized(plan: dict, opt: dict) -> dict:
    """Transforme la solution CP-SAT en dates « pas avant » (not_before) sur les tâches déplacées."""
    starts = {r["id"]: r["start_date"] for r in opt.get("tasks") or []}
    for t in plan.get("tasks") or []:
        if t.get("id") in starts and not (t.get("actual_start") or t.get("actual_end")):
            t["not_before"] = starts[t["id"]]
    return plan
