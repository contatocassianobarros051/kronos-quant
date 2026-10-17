"""
chart_patterns_math.py
======================
Formalizacao matematica/algoritmica de padroes graficos (chart patterns).
Calibrado para operacoes Intraday e Swing (1m, 5m, 15m, 30m, 45m e 1h).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

# ----------------------------------------------------------------------------
# 0. Parametros Calibrados (Escala Intraday / Multi-Timeframe)
# ----------------------------------------------------------------------------
@dataclass
class Params:
    zigzag_theta: float = 0.006     # reversao minima p/ confirmar pivo (ajustado dinamicamente no main.py)
    min_pivot_sep: int = 3          # barras minimas entre pivos de mesmo lado
    horiz_eps: float = 0.006        # |deriva total da reta| <= eps*preco => "horizontal"
    touch_tol: float = 0.005        # distancia relativa p/ contar "toque" na reta
    min_touches: int = 2            # toques minimos por lado
    flag_max_bars: int = 18         # flags/pennants: duracao maxima
    wedge_min_bars: int = 12        # cunhas/triangulos: duracao minima
    twin_tol: float = 0.015         # tolerancia entre picos/vales gemeos (1.5%)
    twin_min_rise: float = 0.005    # subida minima entre dois fundos (0.5% - destrava Fundos/Topos Duplos)
    twin_sep: tuple = (4, 65)       # separacao (barras) entre gemeos
    eve_min_width: int = 3          # largura minima (barras) p/ chamar um vertice de "Eve"
    hs_shoulder_tol: float = 0.025  # |ombro_E - ombro_D| / cabeca
    hs_time_sym: float = 0.60       # assimetria temporal maxima
    target_rule_frac: float = 1.0   # alvo = rompimento +- frac * altura
    ultimate_move: float = 0.05     # reversao que encerra a tendencia
    breakeven_move: float = 0.01    # falha break-even
    throwback_window: int = 20      # barras para throwback/pullback
    throwback_tol: float = 0.004    # proximidade do preco de rompimento


P = Params()

# ----------------------------------------------------------------------------
# 1. Utilidades basicas
# ----------------------------------------------------------------------------
def flip(O, H, L, C, V=None):
    return (-O, -L, -H, -C) + ((V,) if V is not None else ())


def linfit(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0
    a, b = np.polyfit(x, y, 1)
    return float(a), float(b)


def drift(a, n_bars, ref_price):
    return a * n_bars / ref_price


def zigzag(H, L, theta=P.zigzag_theta):
    n = len(H); piv = []; d = 0; hi = lo = 0
    for i in range(1, n):
        if d == 0:
            if H[i] > H[hi]: hi = i
            if L[i] < L[lo]: lo = i
            if hi > lo and H[hi] - L[lo] >= theta * abs(L[lo]):
                if lo > 0: piv.append((lo, L[lo], -1))
                d = 1
            elif lo > hi and H[hi] - L[lo] >= theta * abs(H[hi]):
                if hi > 0: piv.append((hi, H[hi], +1))
                d = -1
        elif d == 1:
            if H[i] > H[hi]: hi = i
            elif H[hi] - L[i] >= theta * abs(H[hi]):
                piv.append((hi, H[hi], +1)); d = -1; lo = i
        else:
            if L[i] < L[lo]: lo = i
            elif H[i] - L[lo] >= theta * abs(L[lo]):
                piv.append((lo, L[lo], -1)); d = 1; hi = i
    return piv


def gap_up(H, L, t):   return L[t] > H[t - 1]
def gap_down(H, L, t): return H[t] < L[t - 1]


# ----------------------------------------------------------------------------
# 2. Familia "duas retas" (broadening, triangulos, cunhas, retangulos, flags)
# ----------------------------------------------------------------------------
@dataclass
class Channel:
    label: str
    a_u: float; b_u: float; a_l: float; b_l: float
    start: int; end: int
    touches_u: int; touches_l: int
    apex: Optional[float]
    height: float
    extra: dict = field(default_factory=dict)

    def U(self, t): return self.a_u * t + self.b_u
    def L(self, t): return self.a_l * t + self.b_l


def _sgn(a, n, ref, eps):
    d = drift(a, n, ref)
    return 0 if abs(d) <= eps else (1 if d > 0 else -1)


def classify_two_lines(a_u, a_l, n, ref, eps=P.horiz_eps):
    su, sl = _sgn(a_u, n, ref, eps), _sgn(a_l, n, ref, eps)
    div, conv = a_u > a_l, a_u < a_l
    if su == 0 and sl == 0:                      return "rectangle"
    if div:
        if su > 0 and sl < 0:                    return "broadening"
        if su > 0 and sl == 0:                   return "broadening_right_angled_asc"
        if su == 0 and sl < 0:                   return "broadening_right_angled_desc"
        if su > 0 and sl > 0:                    return "broadening_wedge_asc"
        if su < 0 and sl < 0:                    return "broadening_wedge_desc"
    if conv:
        if su < 0 and sl > 0:                    return "triangle_symmetrical"
        if su == 0 and sl > 0:                   return "triangle_ascending"
        if su < 0 and sl == 0:                   return "triangle_descending"
        if su > 0 and sl > 0:                    return "wedge_rising"
        if su < 0 and sl < 0:                    return "wedge_falling"
    if su == sl and su != 0 and abs(a_u - a_l) * n / ref < eps:
        return "parallel_sloped"
    return None


def fit_channel(H, L, start, end, p: Params = P) -> Optional[Channel]:
    if p is None: p = P
    piv = [q for q in zigzag(H[start:end + 1], L[start:end + 1], p.zigzag_theta)]
    ph = [(i + start, v) for i, v, k in piv if k == +1]
    pl = [(i + start, v) for i, v, k in piv if k == -1]
    if len(ph) < p.min_touches or len(pl) < p.min_touches:
        return None
    a_u, b_u = linfit([i for i, _ in ph], [v for _, v in ph])
    a_l, b_l = linfit([i for i, _ in pl], [v for _, v in pl])
    n = end - start + 1
    ref = float(np.mean((H[start:end + 1] + L[start:end + 1]) / 2))
    lab = classify_two_lines(a_u, a_l, n, ref, p.horiz_eps)
    if lab is None:
        return None
    tu = sum(abs(v - (a_u * i + b_u)) <= p.touch_tol * ref for i, v in ph)
    tl = sum(abs(v - (a_l * i + b_l)) <= p.touch_tol * ref for i, v in pl)
    if tu < p.min_touches or tl < p.min_touches:
        return None
    apex = (b_l - b_u) / (a_u - a_l) if (a_u - a_l) < 0 else None
    if n <= p.flag_max_bars and lab in ("parallel_sloped", "triangle_symmetrical", "wedge_rising", "wedge_falling"):
        lab = "flag" if lab == "parallel_sloped" else "pennant"
    elif n < p.wedge_min_bars and lab.startswith(("wedge", "triangle")):
        return None
    return Channel(lab, a_u, b_u, a_l, b_l, start, end, tu, tl, apex,
                   float(H[start:end + 1].max() - L[start:end + 1].min()))


def channel_breakout(C, ch: Channel, max_look=None):
    n = len(C); stop = n if max_look is None else min(n, ch.end + 1 + max_look)
    for t in range(ch.end + 1, stop):
        if C[t] > ch.U(t): return t, +1
        if C[t] < ch.L(t): return t, -1
    return None


def measure_target(ch: Channel, t_break, direction, bo_price, frac=P.target_rule_frac):
    return bo_price + direction * frac * ch.height


def is_diamond(H, L, start, end, p: Params = P):
    t = np.arange(start, end + 1); w = H[start:end + 1] - L[start:end + 1]
    w_s = np.convolve(w, np.ones(5) / 5, mode="same")
    q = np.polyfit(t, w_s, 2)
    vertex = -q[1] / (2 * q[0]) if q[0] != 0 else np.nan
    return q[0] < 0 and start + 0.25 * (end - start) < vertex < start + 0.75 * (end - start)


# ----------------------------------------------------------------------------
# 3. Padroes por pivos (fundo duplo/triplo, OCO)
# ----------------------------------------------------------------------------
def turn_width(L, i, tol=0.005, k=6):
    lo, hi = max(0, i - k), min(len(L), i + k + 1)
    return int(np.sum(L[lo:hi] <= L[i] + tol * abs(L[i])))


def double_bottoms(H, L, C, p: Params = P):
    if p is None: p = P
    piv = zigzag(H, L, p.zigzag_theta); out = []
    for k in range(len(piv) - 2):
        (i1, v1, k1), (im, vm, km), (i2, v2, k2) = piv[k:k + 3]
        if not (k1 == -1 and km == +1 and k2 == -1): continue
        if abs(v1 - v2) / abs((v1 + v2) / 2) > p.twin_tol: continue
        if (vm - min(v1, v2)) / abs(min(v1, v2)) < p.twin_min_rise: continue
        if not (p.twin_sep[0] <= i2 - i1 <= p.twin_sep[1]): continue
        # Foca em padroes recentes/ativos na janela atual
        if i2 < len(C) - 70: continue
        brk = None
        for t in range(i2 + 1, len(C)):
            if C[t] < v2 * (1 - p.twin_tol): break
            if C[t] > vm: brk = t; break
        w1, w2 = turn_width(L, i1) >= p.eve_min_width, turn_width(L, i2) >= p.eve_min_width
        kind = ("Eve" if w1 else "Adam") + "&" + ("Eve" if w2 else "Adam")
        out.append(dict(pattern="double_bottom", kind=kind, t1=i1, t2=i2, confirm_level=vm,
                        breakout_t=brk, height=vm - min(v1, v2), target=vm + (vm - min(v1, v2))))
    return out


def triple_bottoms(H, L, C, p: Params = P):
    if p is None: p = P
    piv = zigzag(H, L, p.zigzag_theta); out = []
    for k in range(len(piv) - 4):
        s = piv[k:k + 5]
        if [x[2] for x in s] != [-1, 1, -1, 1, -1]: continue
        if s[4][0] < len(C) - 80: continue
        lows = [s[0][1], s[2][1], s[4][1]]
        if (max(lows) - min(lows)) / abs(np.mean(lows)) > p.twin_tol: continue
        if s[2][1] < min(s[0][1], s[4][1]) - (p.twin_tol / 2) * abs(min(s[0][1], s[4][1])): continue
        top = max(s[1][1], s[3][1]); brk = None
        for t in range(s[4][0] + 1, len(C)):
            if C[t] > top: brk = t; break
        out.append(dict(pattern="triple_bottom", t=(s[0][0], s[2][0], s[4][0]), confirm_level=top,
                        breakout_t=brk, height=top - min(lows), target=top + (top - min(lows))))
    return out


def head_shoulders_bottoms(H, L, C, p: Params = P):
    if p is None: p = P
    piv = zigzag(H, L, p.zigzag_theta); out = []
    for k in range(len(piv) - 4):
        s = piv[k:k + 5]
        if [x[2] for x in s] != [-1, 1, -1, 1, -1]: continue
        (iL, vL, _), (i1, v1, _), (iH, vH, _), (i2, v2, _), (iR, vR, _) = s
        if iR < len(C) - 80: continue
        if not (vH < vL and vH < vR): continue
        if abs(vL - vR) / abs(vH) > p.hs_shoulder_tol: continue
        if abs((iH - iL) - (iR - iH)) / max(1, (iR - iL)) > p.hs_time_sym: continue
        a, b = linfit([i1, i2], [v1, v2]); N = lambda t: a * t + b
        brk = None
        for t in range(iR + 1, len(C)):
            if C[t] > N(t): brk = t; break
        h = N(iH) - vH
        out.append(dict(pattern="head_shoulders_bottom", t=(iL, iH, iR), neckline=(a, b), breakout_t=brk,
                        height=h, target=(N(brk) + h) if brk is not None else None))
    return out


def top_version(detector, H, L, C, p: Params = P):
    return detector(-L, -H, -C, p)


# ----------------------------------------------------------------------------
# 4. Gaps, ilhas, espigas (horn / pipe)
# ----------------------------------------------------------------------------
def islands(H, L):
    out = []; n = len(H)
    for t1 in range(1, n):
        if not gap_up(H, L, t1): continue
        lo1, hi1 = H[t1 - 1], L[t1]
        for t2 in range(t1 + 1, n):
            if gap_down(H, L, t2):
                lo2, hi2 = H[t2], L[t2 - 1]
                if max(lo1, lo2) <= min(hi1, hi2):
                    out.append(dict(pattern="island_top", t1=t1, t2=t2, length=t2 - t1))
                break
            if gap_up(H, L, t2): break
    return out


def weekly_spike_lengths(Ow, Hw, Lw, Cw):
    return Hw - np.maximum(Ow, Cw), np.minimum(Ow, Cw) - Lw


def pipe_top(Ow, Hw, Lw, Cw, q=0.75, lookback=30, overlap_min=0.5, hi_tol=0.008):
    up, _ = weekly_spike_lengths(Ow, Hw, Lw, Cw); out = []
    start_k = max(lookback, len(Hw) - 25)
    for k in range(start_k, len(Hw) - 1):
        thr = np.quantile(up[k - lookback:k], q)
        if up[k] < thr or up[k + 1] < thr: continue
        rng = max(Hw[k], Hw[k + 1]) - min(Lw[k], Lw[k + 1])
        ov = (min(Hw[k], Hw[k + 1]) - max(Lw[k], Lw[k + 1])) / rng if rng > 0 else 0
        if ov < overlap_min or abs(Hw[k] - Hw[k + 1]) / Hw[k] > hi_tol: continue
        lvl = min(Lw[k], Lw[k + 1])
        brk = next((t for t in range(k + 2, len(Cw)) if Cw[t] < lvl), None)
        out.append(dict(pattern="pipe_top", k=k, confirm_level=lvl, breakout_t=brk))
    return out


def horn_top(Ow, Hw, Lw, Cw, q=0.75, lookback=30):
    up, _ = weekly_spike_lengths(Ow, Hw, Lw, Cw); out = []
    for k in range(lookback, len(Hw) - 2):
        thr = np.quantile(up[k - lookback:k], q)
        if up[k] < thr or up[k + 2] < thr: continue
        if Hw[k + 1] >= min(Hw[k], Hw[k + 2]): continue
        lvl = min(Lw[k:k + 3])
        brk = next((t for t in range(k + 3, len(Cw)) if Cw[t] < lvl), None)
        out.append(dict(pattern="horn_top", k=k, confirm_level=lvl, breakout_t=brk))
    return out


# ----------------------------------------------------------------------------
# 5. Padroes em duas pernas / curvos / BARR
# ----------------------------------------------------------------------------
def bump_and_run_reversal(H, L, C, p: Params = P, is_bottom=False):
    """
    Detector Matematico de Bump-and-Run Reversal (BARR).
    is_bottom=True  -> Procura BARR Bottom (Compra / Long)
    is_bottom=False -> Procura BARR Top (Venda / Short)
    """
    if p is None: p = P
    out = []
    n = len(C)
    if n < 50: return out

    # Inversao geometrica completa da matriz (H, L e C) para fundos
    if is_bottom:
        H, L, C = -L, -H, -C

    piv = zigzag(H, L, p.zigzag_theta)
    if len(piv) < 5: return out

    for k in range(len(piv) - 4):
        highs = [x for x in piv[k:k+8] if x[2] == +1]
        if len(highs) < 3: continue

        i1, v1 = highs[0][0], highs[0][1]
        i2, v2 = highs[1][0], highs[1][1]
        i3, v3 = highs[2][0], highs[2][1]

        if i3 < n - 45: continue

        a_lead, b_lead = linfit([i1, i2], [v1, v2])
        if a_lead <= 0: continue

        quarter_idx = i1 + (i2 - i1)
        lead_in_prices = H[i1:quarter_idx+1]
        if len(lead_in_prices) == 0: continue

        trend_vals = a_lead * np.arange(i1, quarter_idx+1) + b_lead
        lead_in_height = np.max(lead_in_prices - trend_vals)
        if lead_in_height <= 0: continue

        bump_prices = H[i2:i3+1]
        if len(bump_prices) == 0: continue
        bump_trend_vals = a_lead * np.arange(i2, i3+1) + b_lead
        bump_height = np.max(bump_prices - bump_trend_vals)

        if bump_height < (1.8 * lead_in_height): continue

        current_trend_val = a_lead * (n - 1) + b_lead
        is_breakout = C[-1] < current_trend_val

        if is_breakout:
            target = (C[-1] - lead_in_height) if not is_bottom else -(C[-1] - lead_in_height)
            out.append({
                "pattern": "BARR_Bottom" if is_bottom else "BARR_Top",
                "lead_in_slope": a_lead,
                "bump_ratio": float(bump_height / lead_in_height),
                "target": float(target)
            })

    return out
