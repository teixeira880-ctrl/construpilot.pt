"""ETRS89 (lat, lon) ↔ ETRS89 / PT-TM06 (EPSG:3763), em Python puro + numpy (sem PROJ).

Projeção Transversa de Mercator com as séries de Krüger (ordem 6, erro < 0,1 mm em Portugal continental).
Parâmetros oficiais da DGT: elipsoide GRS80, φ0 = 39°40'05,73'' N, λ0 = 8°07'59,19'' W, k0 = 1, FE = FN = 0.
O sistema de referência dos ficheiros MDT/MDS LiDAR da DGT é este (EPSG:3763).
"""
from __future__ import annotations

import math
from typing import Tuple

import numpy as np

A = 6378137.0
F = 1 / 298.257222101
LAT0 = 39.0 + 40 / 60 + 5.73 / 3600
LON0 = -(8.0 + 7 / 60 + 59.19 / 3600)
K0 = 1.0

_n = F / (2 - F)
_A = A / (1 + _n) * (1 + _n ** 2 / 4 + _n ** 4 / 64 + _n ** 6 / 256)
_alpha = (
    _n / 2 - 2 * _n ** 2 / 3 + 5 * _n ** 3 / 16 + 41 * _n ** 4 / 180 - 127 * _n ** 5 / 288 + 7891 * _n ** 6 / 37800,
    13 * _n ** 2 / 48 - 3 * _n ** 3 / 5 + 557 * _n ** 4 / 1440 + 281 * _n ** 5 / 630 - 1983433 * _n ** 6 / 1935360,
    61 * _n ** 3 / 240 - 103 * _n ** 4 / 140 + 15061 * _n ** 5 / 26880 + 167603 * _n ** 6 / 181440,
    49561 * _n ** 4 / 161280 - 179 * _n ** 5 / 168 + 6601661 * _n ** 6 / 7257600,
    34729 * _n ** 5 / 80640 - 3418889 * _n ** 6 / 1995840,
    212378941 * _n ** 6 / 319334400,
)
_beta = (
    _n / 2 - 2 * _n ** 2 / 3 + 37 * _n ** 3 / 96 - _n ** 4 / 360 - 81 * _n ** 5 / 512 + 96199 * _n ** 6 / 604800,
    _n ** 2 / 48 + _n ** 3 / 15 - 437 * _n ** 4 / 1440 + 46 * _n ** 5 / 105 - 1118711 * _n ** 6 / 3870720,
    17 * _n ** 3 / 480 - 37 * _n ** 4 / 840 - 209 * _n ** 5 / 4480 + 5569 * _n ** 6 / 90720,
    4397 * _n ** 4 / 161280 - 11 * _n ** 5 / 504 - 830251 * _n ** 6 / 7257600,
    4583 * _n ** 5 / 161280 - 108847 * _n ** 6 / 3991680,
    20648693 * _n ** 6 / 638668800,
)
_e = math.sqrt(F * (2 - F))


def _xi_eta(lat, lon):
    phi = np.radians(lat)
    lam = np.radians(lon - LON0)
    t = np.sinh(np.arctanh(np.sin(phi)) - _e * np.arctanh(_e * np.sin(phi)))
    xi_ = np.arctan2(t, np.cos(lam))
    eta_ = np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
    xi, eta = xi_.copy(), eta_.copy()
    for j, a in enumerate(_alpha, start=1):
        xi = xi + a * np.sin(2 * j * xi_) * np.cosh(2 * j * eta_)
        eta = eta + a * np.cos(2 * j * xi_) * np.sinh(2 * j * eta_)
    return xi, eta


_XI0, _ = _xi_eta(np.array(LAT0), np.array(LON0))
_N0 = float(K0 * _A * _XI0)


def para_tm(lat, lon) -> Tuple[np.ndarray, np.ndarray]:
    """(lat, lon) graus ETRS89 → (x = este, y = norte) metros PT-TM06. Aceita escalares ou arrays."""
    xi, eta = _xi_eta(np.asarray(lat, dtype=float), np.asarray(lon, dtype=float))
    return K0 * _A * eta, K0 * _A * xi - _N0


def para_ll(x, y) -> Tuple[np.ndarray, np.ndarray]:
    """(x, y) metros PT-TM06 → (lat, lon) graus ETRS89."""
    xi = (np.asarray(y, dtype=float) + _N0) / (K0 * _A)
    eta = np.asarray(x, dtype=float) / (K0 * _A)
    xi_, eta_ = xi.copy(), eta.copy()
    for j, b in enumerate(_beta, start=1):
        xi_ = xi_ - b * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        eta_ = eta_ - b * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    lam = np.arctan2(np.sinh(eta_), np.cos(xi_))
    tau_ = np.sin(xi_) / np.sqrt(np.sinh(eta_) ** 2 + np.cos(xi_) ** 2)
    tau = tau_.copy()
    for _ in range(6):   # Newton (Karney 2011)
        sig = np.sinh(_e * np.arctanh(_e * tau / np.sqrt(1 + tau * tau)))
        tp = tau * np.sqrt(1 + sig * sig) - sig * np.sqrt(1 + tau * tau)
        dtau = (tau_ - tp) / np.sqrt(1 + tp * tp) * (1 + (1 - _e * _e) * tau * tau) / ((1 - _e * _e) * np.sqrt(1 + tau * tau))
        tau = tau + dtau
    return np.degrees(np.arctan(tau)), np.degrees(lam) + LON0


def ponto_tm(lat: float, lon: float) -> Tuple[float, float]:
    x, y = para_tm(lat, lon)
    return float(x), float(y)


def ponto_ll(x: float, y: float) -> Tuple[float, float]:
    a, b = para_ll(x, y)
    return float(a), float(b)
