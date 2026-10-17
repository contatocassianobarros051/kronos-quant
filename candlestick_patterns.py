import numpy as np

def detect_patterns(O, H, L, C):
    """
    Motor Analítico de Micro-Estrutura (Candlesticks)
    Caça padrões de exaustão, absorção e impulsão institucional.
    """
    signals = []
    score_boost = 0

    if len(C) < 10:
        return signals, score_boost

    o1, h1, l1, c1 = float(O[-2]), float(H[-2]), float(L[-2]), float(C[-2])
    o2, h2, l2, c2 = float(O[-1]), float(H[-1]), float(L[-1]), float(C[-1])

    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)
    range2 = max(h2 - l2, 1e-9)

    local_trend_up = C[-1] > C[-5]
    local_trend_down = C[-1] < C[-5]

    # 1. ENGOLFOS INSTITUCIONAIS (ENGULFING)
    if c1 < o1 and c2 > o2 and c2 >= o1 and o2 <= c1:
        signals.append("Vela: Engolfo de Alta (+20%)")
        score_boost += 20
    elif c1 > o1 and c2 < o2 and c2 <= o1 and o2 >= c1:
        signals.append("Vela: Engolfo de Baixa (+20%)")
        score_boost -= 20

    # 2. REJEIÇÕES DE CAUDA (HAMMER / SHOOTING STAR)
    lower_wick = min(o2, c2) - l2
    upper_wick = h2 - max(o2, c2)
    safe_body = max(body2, range2 * 0.1)

    if lower_wick >= (2.0 * safe_body) and upper_wick <= (0.6 * safe_body):
        signals.append("Vela: Martelo / Rejeição de Fundo (+15%)")
        score_boost += 15
    elif upper_wick >= (2.0 * safe_body) and lower_wick <= (0.6 * safe_body):
        signals.append("Vela: Estrela Cadente / Rejeição de Topo (+15%)")
        score_boost -= 15

    # 3. MARUBOZU DE IMPULSÃO (Corpo preenche > 82% da vela inteira)
    avg_body = float(np.mean(np.abs(C[-10:-1] - O[-10:-1])))
    if body2 > (avg_body * 1.5) and (body2 / range2) >= 0.82:
        if c2 > o2 and local_trend_up:
            signals.append("Vela: Marubozu de Impulsão Compradora (+15%)")
            score_boost += 15
        elif c2 < o2 and local_trend_down:
            signals.append("Vela: Marubozu de Impulsão Vendedora (+15%)")
            score_boost -= 15

    return signals, score_boost
