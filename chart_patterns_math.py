"""
chart_patterns_math.py
======================
Formalizacao matematica/algoritmica de padroes graficos (chart patterns).

Tudo aqui e uma formulacao PROPRIA (notacao, codigo e estrutura originais):
regras geometricas -> desigualdades sobre pivos, retas e razoes. Nenhum texto,
figura ou tabela do livro e reproduzido. Os limiares numericos sao PARAMETROS
(dataclass Params) que voce deve calibrar com seus proprios dados.

Entrada: arrays numpy  O, H, L, C, V  (open, high, low, close, volume), 1 barra = 1 periodo.
Convencao: detectores de "fundo/alta" servem tambem para "topo/baixa" via flip().
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

# ----------------------------------------------------------------------------
# 0. Parametros (todos calibraveis)
# ----------------------------------------------------------------------------
@dataclass
class Params:
    zigzag_theta: float = 0.05      # reversao minima (fracao) para confirmar pivo
    min_pivot_sep: int = 5          # barras minimas entre pivos de mesmo lado (~1 semana)
    horiz_eps: float = 0.03         # |deriva total da reta| <= eps*preco  => "horizontal"
    touch_tol: float = 0.02         # distancia relativa p/ contar "toque" na reta
    min_touches: int = 2            # toques minimos por lado
    flag_max_bars: int = 15         # flags/pennants: duracao maxima (~3 semanas)
    wedge_min_bars: int = 15        # cunhas/triangulos: duracao minima
    twin_tol: float = 0.06          # tolerancia entre picos/vales gemeos
    twin_min_rise: float = 0.10     # subida minima entre dois fundos (queda p/ topos)
    twin_sep: tuple = (10, 40)      # separacao (barras) entre gemeos
    eve_min_width: int = 4          # largura minima (barras) p/ chamar um vertice de "Eve"
    hs_shoulder_tol: float = 0.10   # |ombro_E - ombro_D| / cabeca
    hs_time_sym: float = 0.50       # assimetria temporal maxima
    target_rule_frac: float = 1.0   # alvo = rompimento +- frac * altura
    ultimate_move: float = 0.20     # reversao que encerra a tendencia (topo/fundo final)
    breakeven_move: float = 0.05    # "falha break-even" se movimento < 5%
    throwback_window: int = 30      # barras para throwback/pullback
    throwback_tol: float = 0.005    # proximidade do preco de rompimento


P = Params()

# ----------------------------------------------------------------------------
# 1. Utilidades basicas
# ----------------------------------------------------------------------------
def flip(O, H, L, C, V=None):
    """Espelha precos (p -> -p): transforma detector de fundo em detector de topo.
       Todas as razoes relativas dos detectores usam |denominador|, entao os percentuais
       continuam medidos na escala original."""
    return (-O, -L, -H, -C) + ((V,) if V is not None else ())


def linfit(x, y):
    """Reta y = a*x + b por minimos quadrados. Retorna (a, b)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0
    a, b = np.polyfit(x, y, 1)
    return float(a), float(b)


def drift(a, n_bars, ref_price):
    """Deriva fracionaria total da reta ao longo do padrao: a*N / preco."""
    return a * n_bars / ref_price


def zigzag(H, L, theta=P.zigzag_theta):
    """
    Pivos (i, preco, kind) alternados; kind=+1 maxima local, -1 minima local.
    Um pivo so e confirmado quando o preco reverte >= theta do extremo.
    """
    n = len(H); piv = []; d = 0; hi = lo = 0
    for i in range(1, n):
        if d == 0:
            if H[i] > H[hi]: hi = i
            if L[i] < L[lo]: lo = i
            if hi > lo and H[hi] - L[lo] >= theta * abs(L[lo]):
                if lo > 0: piv.append((lo, L[lo], -1))   # pivo na barra 0 e indeterminado: descartado
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
#    Modelo:  U(t)=a_u t+b_u  (sobre maximas),  L(t)=a_l t+b_l  (sobre minimas)
#             largura w(t)=U-L,   dw/dt = a_u - a_l
#    Taxonomia = sinais de (a_u, a_l) e de (a_u - a_l).
# ----------------------------------------------------------------------------
@dataclass
class Channel:
    label: str
    a_u: float; b_u: float; a_l: float; b_l: float
    start: int; end: int
    touches_u: int; touches_l: int
    apex: Optional[float]           # t onde U(t)=L(t) (so se convergente)
    height: float                   # max(H)-min(L) na janela
    extra: dict = field(default_factory=dict)

    def U(self, t): return self.a_u * t + self.b_u
    def L(self, t): return self.a_l * t + self.b_l


def _sgn(a, n, ref, eps):
    d = drift(a, n, ref)
    return 0 if abs(d) <= eps else (1 if d > 0 else -1)


def classify_two_lines(a_u, a_l, n, ref, eps=P.horiz_eps):
    """
    Rotulo geometrico a partir das inclinacoes. Retorna string ou None.
      su, sl in {-1,0,+1}; conv = a_u < a_l (converge), div = a_u > a_l (diverge)
    """
    su, sl = _sgn(a_u, n, ref, eps), _sgn(a_l, n, ref, eps)
    div, conv = a_u > a_l, a_u < a_l
    if su == 0 and sl == 0:                      return "rectangle"
    if div:
        if su > 0 and sl < 0:                    return "broadening"                 # megafone
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
        return "parallel_sloped"                 # canal paralelo (flag se curto + impulso)
    return None


def fit_channel(H, L, start, end, p: Params = P) -> Optional[Channel]:
    """Ajusta U e L sobre pivos dentro de [start, end] e classifica."""
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
    # flag/pennant: janela curta com canal paralelo/convergente
    if n <= p.flag_max_bars and lab in ("parallel_sloped", "triangle_symmetrical", "wedge_rising", "wedge_falling"):
        lab = "flag" if lab == "parallel_sloped" else "pennant"
    elif n < p.wedge_min_bars and lab.startswith(("wedge", "triangle")):
        return None
    return Channel(lab, a_u, b_u, a_l, b_l, start, end, tu, tl, apex,
                   float(H[start:end + 1].max() - L[start:end + 1].min()))


def channel_breakout(C, ch: Channel, max_look=None):
    """Primeiro t>end com fechamento fora das retas. Retorna (t, +1/-1) ou None."""
    n = len(C); stop = n if max_look is None else min(n, ch.end + 1 + max_look)
    for t in range(ch.end + 1, stop):
        if C[t] > ch.U(t): return t, +1
        if C[t] < ch.L(t): return t, -1
    return None


def measure_target(ch: Channel, t_break, direction, bo_price, frac=P.target_rule_frac):
    """Regra da medida: alvo = preco de rompimento +- frac*altura."""
    return bo_price + direction * frac * ch.height


def is_diamond(H, L, start, end, p: Params = P):
    """Diamante = largura w(t) cresce e depois decresce (w concava, pico no miolo)."""
    t = np.arange(start, end + 1); w = H[start:end + 1] - L[start:end + 1]
    w_s = np.convolve(w, np.ones(5) / 5, mode="same")
    q = np.polyfit(t, w_s, 2)                         # w ~ q0 t^2 + q1 t + q2
    vertex = -q[1] / (2 * q[0]) if q[0] != 0 else np.nan
    return q[0] < 0 and start + 0.25 * (end - start) < vertex < start + 0.75 * (end - start)


# ----------------------------------------------------------------------------
# 3. Padroes por pivos (fundo duplo/triplo, OCO). Topos = mesmo codigo sobre flip().
# ----------------------------------------------------------------------------
def turn_width(L, i, tol=0.015, k=10):
    """Largura (barras) do vertice: quantas barras em [i-k,i+k] tem low <= (1+tol)*low_i."""
    lo, hi = max(0, i - k), min(len(L), i + k + 1)
    return int(np.sum(L[lo:hi] <= L[i] + tol * abs(L[i])))


def double_bottoms(H, L, C, p: Params = P):
    """
    Pivos (low P1, high M, low P2):
      |P1-P2|/mean <= twin_tol ;  (M - min(P1,P2))/min >= twin_min_rise
      sep = t2 - t1 in twin_sep ;  confirmacao: 1o t>t2 com C > M sem C < P2 antes.
    Adam/Eve por turn_width. Alvo = M + (M - min(P1,P2)).
    """
    piv = zigzag(H, L, p.zigzag_theta); out = []
    for k in range(len(piv) - 2):
        (i1, v1, k1), (im, vm, km), (i2, v2, k2) = piv[k:k + 3]
        if not (k1 == -1 and km == +1 and k2 == -1): continue
        if abs(v1 - v2) / abs((v1 + v2) / 2) > p.twin_tol: continue
        if (vm - min(v1, v2)) / abs(min(v1, v2)) < p.twin_min_rise: continue
        if not (p.twin_sep[0] <= i2 - i1 <= p.twin_sep[1]): continue
        brk = None
        for t in range(i2 + 1, len(C)):
            if C[t] < v2: break
            if C[t] > vm: brk = t; break
        w1, w2 = turn_width(L, i1) >= p.eve_min_width, turn_width(L, i2) >= p.eve_min_width
        kind = ("Eve" if w1 else "Adam") + "&" + ("Eve" if w2 else "Adam")
        out.append(dict(pattern="double_bottom", kind=kind, t1=i1, t2=i2, confirm_level=vm,
                        breakout_t=brk, height=vm - min(v1, v2), target=vm + (vm - min(v1, v2))))
    return out


def triple_bottoms(H, L, C, p: Params = P):
    """Tres vales ~ mesmo preco; centro nao muito abaixo (senao e OCO). Confirma: C > max(H) do padrao."""
    piv = zigzag(H, L, p.zigzag_theta); out = []
    for k in range(len(piv) - 4):
        s = piv[k:k + 5]
        if [x[2] for x in s] != [-1, 1, -1, 1, -1]: continue
        lows = [s[0][1], s[2][1], s[4][1]]
        if (max(lows) - min(lows)) / abs(np.mean(lows)) > p.twin_tol: continue
        if s[2][1] < min(s[0][1], s[4][1]) - (p.twin_tol / 2) * abs(min(s[0][1], s[4][1])): continue   # centro fundo demais => OCO
        top = max(s[1][1], s[3][1]); brk = None
        for t in range(s[4][0] + 1, len(C)):
            if C[t] > top: brk = t; break
        out.append(dict(pattern="triple_bottom", t=(s[0][0], s[2][0], s[4][0]), confirm_level=top,
                        breakout_t=brk, height=top - min(lows), target=top + (top - min(lows))))
    return out


def head_shoulders_bottoms(H, L, C, p: Params = P):
    """
    Pivos (L_s, T1, Head, T2, R_s) = (-,+,-,+,-):
      Head < min(L_s, R_s);  |L_s-R_s|/|Head| <= hs_shoulder_tol (aprox. simetria de preco)
      simetria temporal: |(tH-tL)-(tR-tH)|/(tR-tL) <= hs_time_sym
      linha de pescoco N(t) pelos picos T1,T2.  Rompimento: C[t] > N(t), t>tR.
      altura = N(tH) - Head ;  alvo = N(t_break) + altura.
    """
    piv = zigzag(H, L, p.zigzag_theta); out = []
    for k in range(len(piv) - 4):
        s = piv[k:k + 5]
        if [x[2] for x in s] != [-1, 1, -1, 1, -1]: continue
        (iL, vL, _), (i1, v1, _), (iH, vH, _), (i2, v2, _), (iR, vR, _) = s
        if not (vH < vL and vH < vR): continue
        if abs(vL - vR) / abs(vH) > p.hs_shoulder_tol: continue
        if abs((iH - iL) - (iR - iH)) / (iR - iL) > p.hs_time_sym: continue
        a, b = linfit([i1, i2], [v1, v2]); N = lambda t: a * t + b
        brk = None
        for t in range(iR + 1, len(C)):
            if C[t] > N(t): brk = t; break
        h = N(iH) - vH
        out.append(dict(pattern="head_shoulders_bottom", t=(iL, iH, iR), neckline=(a, b), breakout_t=brk,
                        height=h, target=(N(brk) + h) if brk is not None else None))
    return out


def top_version(detector, H, L, C, p: Params = P):
    """Roda um detector de FUNDO sobre a serie espelhada => detecta TOPOS.
       Precos nos resultados ficam refletidos (multiplique por -1 para voltar)."""
    return detector(-L, -H, -C, p)


# ----------------------------------------------------------------------------
# 4. Gaps, ilhas, espigas semanais (horn / pipe)
# ----------------------------------------------------------------------------
def islands(H, L):
    """Ilha de topo: gap_up em t1 e gap_down em t2>t1 com intervalos de gap sobrepostos."""
    out = []; n = len(H)
    for t1 in range(1, n):
        if not gap_up(H, L, t1): continue
        lo1, hi1 = H[t1 - 1], L[t1]                    # zona do gap esquerdo
        for t2 in range(t1 + 1, n):
            if gap_down(H, L, t2):
                lo2, hi2 = H[t2], L[t2 - 1]
                if max(lo1, lo2) <= min(hi1, hi2):     # intervalos se intersectam
                    out.append(dict(pattern="island_top", t1=t1, t2=t2, length=t2 - t1))
                break
            if gap_up(H, L, t2): break
    return out


def weekly_spike_lengths(Ow, Hw, Lw, Cw):
    """Pavio superior/inferior por barra semanal (medida de 'espiga')."""
    return Hw - np.maximum(Ow, Cw), np.minimum(Ow, Cw) - Lw


def pipe_top(Ow, Hw, Lw, Cw, q=0.75, lookback=52, overlap_min=0.5, hi_tol=0.02):
    """
    Duas semanas adjacentes k,k+1: pavios superiores > quantil q dos pavios do ultimo ano,
    sobreposicao de faixas >= overlap_min, |H_k - H_k+1|/H <= hi_tol.
    Confirmacao: fechamento < min(L_k, L_k+1).
    """
    up, _ = weekly_spike_lengths(Ow, Hw, Lw, Cw); out = []
    for k in range(lookback, len(Hw) - 1):
        thr = np.quantile(up[k - lookback:k], q)
        if up[k] < thr or up[k + 1] < thr: continue
        rng = max(Hw[k], Hw[k + 1]) - min(Lw[k], Lw[k + 1])
        ov = (min(Hw[k], Hw[k + 1]) - max(Lw[k], Lw[k + 1])) / rng if rng > 0 else 0
        if ov < overlap_min or abs(Hw[k] - Hw[k + 1]) / Hw[k] > hi_tol: continue
        lvl = min(Lw[k], Lw[k + 1])
        brk = next((t for t in range(k + 2, len(Cw)) if Cw[t] < lvl), None)
        out.append(dict(pattern="pipe_top", k=k, confirm_level=lvl, breakout_t=brk))
    return out


def horn_top(Ow, Hw, Lw, Cw, q=0.75, lookback=52):
    """Duas espigas separadas por 1 semana (k e k+2); semana central com maxima bem menor.
       Confirmacao: fechamento abaixo da menor minima das 3 semanas."""
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
# 5. Padroes em duas pernas / curvos (formulas de verificacao)
# ----------------------------------------------------------------------------
def measured_move_up(start_low, leg1_high, corr_low, retrace_band=(0.38, 0.62)):
    """r = (leg1_high-corr_low)/(leg1_high-start_low); alvo da 2a perna = corr_low + (leg1_high-start_low)."""
    leg = leg1_high - start_low; r = (leg1_high - corr_low) / leg
    return dict(retrace=r, valid=retrace_band[0] <= r <= retrace_band[1] and r < 0.80,
                target=corr_low + leg)


def measured_move_down(start_high, leg1_low, corr_high, retrace_band=(0.38, 0.62)):
    leg = start_high - leg1_low; r = (corr_high - leg1_low) / leg
    return dict(retrace=r, valid=retrace_band[0] <= r <= retrace_band[1] and r < 0.80,
                target=corr_high - leg)


def cup_with_handle(rimL, rimR, cup_low, handle_low, rim_tol=0.06,
                    prior_rise=None, cup_weeks=None, handle_bars=None):
    """
    rim_diff=|rimL-rimR|/max;  depth=(min(rims)-cup_low)/min(rims);
    handle_retrace=(rimR-handle_low)/(rimR-cup_low).
    Valido se: rim_diff<rim_tol, handle_low>cup_low e, quando informados,
      prior_rise >= 0.30 (subida antes da borda esquerda), 7 <= cup_weeks <= 65, handle_bars >= 5.
    Rompimento: fechamento acima de rimR (ou da linha de tendencia da alca).
    """
    top = min(rimL, rimR); rd = abs(rimL - rimR) / max(rimL, rimR)
    ok = rd < rim_tol and handle_low > cup_low
    if prior_rise is not None:  ok &= prior_rise >= 0.30
    if cup_weeks is not None:   ok &= 7 <= cup_weeks <= 65
    if handle_bars is not None: ok &= handle_bars >= 5
    return dict(rim_diff=rd, depth=(top - cup_low) / top,
                handle_retrace=(rimR - handle_low) / (rimR - cup_low),
                valid=bool(ok), breakout_level=rimR)


def bump_and_run(lead_in_height, bump_height, lead_in_bars, min_ratio=2.0, min_lead_bars=21):
    """Regra: altura da protuberancia >= min_ratio * altura do lead-in; lead-in >= ~1 mes."""
    return dict(ratio=bump_height / lead_in_height,
                valid=bump_height >= min_ratio * lead_in_height and lead_in_bars >= min_lead_bars)


def rounding_fit(C, bottom=True):
    """Ajuste parabolico C ~ al t^2 + bl t + c. Fundo: al>0; topo: al<0.
       Retorna R^2, posicao do vertice em [0,1] e diferenca relativa entre as pontas."""
    t = np.arange(len(C), dtype=float); q = np.polyfit(t, C, 2)
    fit = np.polyval(q, t); ss_res = ((C - fit) ** 2).sum(); ss_tot = ((C - C.mean()) ** 2).sum()
    vtx = -q[1] / (2 * q[0]) / (len(C) - 1) if q[0] != 0 else np.nan
    ok = (q[0] > 0) if bottom else (q[0] < 0)
    return dict(curvature=q[0], r2=1 - ss_res / ss_tot, vertex_pos=vtx,
                ends_diff=abs(C[0] - C[-1]) / C.mean(), valid_shape=bool(ok and 0.25 < vtx < 0.75))


def scallop_metrics(start, peak_or_trough, end, next_move):
    """Razoes de proporcao: retrace=(extremo-fim)/(extremo-inicio); bowl_to_move = |extremo-inicio|/|next_move|."""
    return dict(retrace=(peak_or_trough - end) / (peak_or_trough - start),
                bowl_to_move=abs(peak_or_trough - start) / abs(next_move))


# ----------------------------------------------------------------------------
# 6. Padroes de evento (anuncios)
# ----------------------------------------------------------------------------
def event_breakout(H, L, C, ann_idx, avg_window=21):
    """
    Faixa do dia do anuncio R = H-L deve superar a media das ultimas avg_window faixas (ou haver gap).
    Rompimento: 1o fechamento > H[ann] (alta) ou < L[ann] (baixa).
    """
    R = H[ann_idx] - L[ann_idx]
    big = R > np.mean(H[ann_idx - avg_window:ann_idx] - L[ann_idx - avg_window:ann_idx]) \
        or gap_up(H, L, ann_idx) or gap_down(H, L, ann_idx)
    for t in range(ann_idx + 1, len(C)):
        if C[t] > H[ann_idx]: return dict(valid=bool(big), t=t, direction=+1, level=H[ann_idx])
        if C[t] < L[ann_idx]: return dict(valid=bool(big), t=t, direction=-1, level=L[ann_idx])
    return dict(valid=bool(big), t=None, direction=0, level=None)


def dead_cat_bounce_phases(plunge, bounce, decline):
    """Fracoes: plunge (queda inicial), bounce (recuperacao da queda), decline (nova queda)."""
    return dict(plunge=plunge, bounce_frac_of_plunge=bounce, new_decline=decline)


# ----------------------------------------------------------------------------
# 7. Metrica de desempenho (metodologia generica de avaliar um rompimento)
# ----------------------------------------------------------------------------
def breakout_price(H, L, t, direction):
    """Preco de referencia do rompimento: minima (alta) ou maxima (baixa) do dia do rompimento."""
    return L[t] if direction > 0 else H[t]


def ultimate_extreme(H, L, C, t_break, direction, formation_ref, p: Params = P):
    """
    Alta (direction=+1): percorre ate o fim; mantem maxima corrente M_t; encerra quando
        C <= (1-ultimate_move)*M_t   OU   C < formation_ref (fundo da formacao).
    Retorna (indice, preco) do extremo final (maxima p/ alta; minima p/ baixa).
    """
    n = len(C)
    if direction > 0:
        m, mi = H[t_break], t_break
        for t in range(t_break + 1, n):
            if H[t] > m: m, mi = H[t], t
            if C[t] <= (1 - p.ultimate_move) * m or C[t] < formation_ref: break
        return mi, m
    m, mi = L[t_break], t_break
    for t in range(t_break + 1, n):
        if L[t] < m: m, mi = L[t], t
        if C[t] >= (1 + p.ultimate_move) * m or C[t] > formation_ref: break
    return mi, m


def avg_move(bo, ult, direction):
    """Movimento fracionario do rompimento ate o extremo final (sempre >= 0 na direcao esperada)."""
    return direction * (ult - bo) / bo


def failure_curve(moves, thresholds=(0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50)):
    """F(x) = P(move < x). F(0.05) = taxa de falha break-even."""
    m = np.asarray(moves, float)
    return {x: float(np.mean(m < x)) for x in thresholds}


def throwback_or_pullback(H, L, t_break, direction, bo_price, p: Params = P):
    """True se, em <= throwback_window barras, o preco volta a (1+-tol)*bo_price depois de ter
       aberto 'espaco branco' (ao menos uma barra totalmente longe do nivel)."""
    n = len(H); end = min(n, t_break + 1 + p.throwback_window); left = False
    for t in range(t_break + 1, end):
        if direction > 0:
            if L[t] > bo_price * (1 + p.throwback_tol): left = True
            elif left and L[t] <= bo_price * (1 + p.throwback_tol): return True
        else:
            if H[t] < bo_price * (1 - p.throwback_tol): left = True
            elif left and H[t] >= bo_price * (1 - p.throwback_tol): return True
    return False


def hit_target(H, L, t_break, t_ult, direction, target):
    seg_H, seg_L = H[t_break:t_ult + 1], L[t_break:t_ult + 1]
    return bool(seg_H.max() >= target) if direction > 0 else bool(seg_L.min() <= target)


def trend_start_index(H, L, C, formation_start, entering_up: bool, p: Params = P):
    """Anda para tras ate achar maxima (se subia) cuja queda posterior de 20% fecha; marca inicio da tendencia."""
    if entering_up:     # tendencia de alta ate a formacao => procurar o MINIMO inicial
        lo, li = L[formation_start], formation_start
        for t in range(formation_start - 1, -1, -1):
            if L[t] < lo: lo, li = L[t], t
            if C[t] >= (1 + p.ultimate_move) * lo: break
        return li
    hi, hi_i = H[formation_start], formation_start
    for t in range(formation_start - 1, -1, -1):
        if H[t] > hi: hi, hi_i = H[t], t
        if C[t] <= (1 - p.ultimate_move) * hi: break
    return hi_i


# ---- volume -----------------------------------------------------------------
def volume_trend(V, start, end):
    """Sinal da inclinacao de regressao linear do volume (+1 sobe, -1 cai)."""
    a, _ = linfit(np.arange(start, end + 1), V[start:end + 1])
    return int(np.sign(a))


def volume_shape(V, start, end, flat_tol=0.15):
    """Classifica: 'U' (curvatura>0), 'dome' (curvatura<0), 'flat' (variacao pequena), 'other'."""
    v = np.asarray(V[start:end + 1], float); t = np.linspace(-1, 1, len(v))
    q = np.polyfit(t, v / v.mean(), 2)
    if np.ptp(np.convolve(v / v.mean(), np.ones(5) / 5, "valid")) < flat_tol: return "flat"
    if q[0] > 0.2: return "U"
    if q[0] < -0.2: return "dome"
    return "other"


def breakout_volume_ratio(V, t_break, window=30):
    """V[t]/media(V[t-window:t]); > 1 => volume de rompimento 'pesado'."""
    return float(V[t_break] / np.mean(V[max(0, t_break - window):t_break]))


def height_pct(H, L, start, end, bo_price):
    """Altura relativa = (maxH - minL)/preco de rompimento (classifica alto/baixo vs mediana)."""
    return float((H[start:end + 1].max() - L[start:end + 1].min()) / bo_price)


# ----------------------------------------------------------------------------
# 8. Priors estatisticos (lookup no CSV anexo)
# ----------------------------------------------------------------------------
def load_priors(path="pattern_stats.csv"):
    import csv
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def prior(rows, pattern, breakout, market="Bull"):
    """Retorna linha (dict) de pattern_stats.csv; breakout in {'up','down','na'}; market in {'Bull','Bear'}."""
    for r in rows:
        if r["pattern"].lower() == pattern.lower() and r["breakout"] == breakout and r["market"] == market:
            return r
    return None
