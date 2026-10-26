"""Placement le long des parois : un paramètre curviligne `s` parcourt le périmètre d'une
pièce ; les portes, les angles et les zones réservées sont des intervalles interdits."""
from __future__ import annotations

from . import geometry as G

CORNER_MARGIN = 0.20
DOOR_MARGIN = 0.15
MIN_SPACING = 0.40


class Wall:
    def __init__(self, room, inset: float = 0.12):
        self.room = room
        self.poly = room.polygon
        self.inset = inset
        self.edges = G.edges(self.poly)
        self.lengths = [G.dist(a, b) for a, b in self.edges]
        self.cum = [0.0]
        for L in self.lengths:
            self.cum.append(self.cum[-1] + L)
        self.P = self.cum[-1]
        self.blocked: list[tuple[float, float]] = []
        for i, L in enumerate(self.lengths):
            s = self.cum[i]
            self.block(s - CORNER_MARGIN, s + CORNER_MARGIN)
        for o, ei, t0, t1 in room.doors:
            s0 = self.cum[ei] + t0 * self.lengths[ei]
            s1 = self.cum[ei] + t1 * self.lengths[ei]
            self.block(s0 - DOOR_MARGIN, s1 + DOOR_MARGIN)

    # -- intervalles ------------------------------------------------------------------
    def block(self, s0: float, s1: float) -> None:
        P = self.P
        if s1 - s0 >= P:
            self.blocked.append((0, P))
            return
        s0m, s1m = s0 % P, s1 % P
        if s0m <= s1m:
            self.blocked.append((s0m, s1m))
        else:
            self.blocked.append((s0m, P))
            self.blocked.append((0, s1m))

    def is_free(self, s: float) -> bool:
        s %= self.P
        return not any(a <= s <= b for a, b in self.blocked)

    def snap(self, s: float, step: float = 0.05) -> float | None:
        """Position libre la plus proche de `s` (recherche alternée des deux côtés)."""
        k = 0
        while k * step <= self.P / 2:
            for cand in (s + k * step, s - k * step):
                if self.is_free(cand):
                    return cand % self.P
            k += 1
        return None

    # -- conversions --------------------------------------------------------------------
    def locate(self, s: float) -> tuple[int, float]:
        s %= self.P
        for i in range(len(self.lengths)):
            if self.cum[i] <= s <= self.cum[i + 1]:
                L = self.lengths[i] or 1.0
                return i, (s - self.cum[i]) / L
        return len(self.lengths) - 1, 1.0

    def point(self, s: float, inset: float | None = None):
        ei, t = self.locate(s)
        a, b = self.edges[ei]
        return G.offset_into(self.poly, a, b, t, self.inset if inset is None else inset)

    def s_of(self, p) -> float:
        """Abscisse curviligne du projeté d'un point sur la paroi la plus proche."""
        best = None
        for i, (a, b) in enumerate(self.edges):
            t, d = G.project_on_segment(p, a, b)
            t = max(0.0, min(1.0, t))
            if best is None or d < best[0]:
                best = (d, self.cum[i] + t * self.lengths[i])
        return best[1]

    def edge_free_length(self, ei: int) -> float:
        n = 40
        L = self.lengths[ei]
        free = sum(1 for k in range(n) if self.is_free(self.cum[ei] + (k + 0.5) * L / n))
        return L * free / n

    # -- placement ----------------------------------------------------------------------
    def place_even(self, n: int, s_start: float = 0.0, s_end: float | None = None) -> list[float]:
        """Répartit n points régulièrement sur [s_start, s_end] puis les cale sur du libre."""
        if n <= 0:
            return []
        s_end = self.P if s_end is None else s_end
        span = s_end - s_start
        out = []
        for i in range(n):
            target = s_start + (i + 0.5) * span / n
            s = self.snap(target)
            if s is None:
                break
            out.append(s)
            self.block(s - MIN_SPACING, s + MIN_SPACING)
        return out

    def place_at(self, s: float) -> float | None:
        s2 = self.snap(s)
        if s2 is not None:
            self.block(s2 - MIN_SPACING, s2 + MIN_SPACING)
        return s2

    def best_far_from(self, footprints: list, clearance: float, n: int = 1) -> list[tuple[float, float]]:
        """Positions libres les plus éloignées d'empreintes (douche/baignoire)."""
        cands = []
        k = 0
        while k * 0.1 < self.P:
            s = k * 0.1
            if self.is_free(s):
                p = self.point(s)
                d = min((G.dist_point_to_rect(p, fp) for fp in footprints), default=99.0)
                cands.append((d, s))
            k += 1
        cands.sort(reverse=True)
        out = []
        for d, s in cands:
            if len(out) >= n:
                break
            if self.is_free(s):
                out.append((s, d))
                self.block(s - MIN_SPACING, s + MIN_SPACING)
        return out


def door_switch_s(wall: Wall, door) -> float:
    """Abscisse d'un interrupteur à côté d'une porte : côté du jambage le plus dégagé."""
    o, ei, t0, t1 = door
    L = wall.lengths[ei]
    s0 = wall.cum[ei] + t0 * L
    s1 = wall.cum[ei] + t1 * L
    before = t0 * L
    after = (1 - t1) * L
    if after >= before:
        return s1 + DOOR_MARGIN + 0.10
    return s0 - DOOR_MARGIN - 0.10
