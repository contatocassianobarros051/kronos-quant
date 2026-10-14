import numpy as np

def detect_patterns(O, H, L, C):
    """
    Motor Analítico de Micro-Estrutura (Candlesticks)
    Caça padrões de exaustão e reversão institucional de curtíssimo prazo.
    """
    signals = []
    score_boost = 0
    
    if len(C) < 10: return signals, score_boost

    # Extrai as duas últimas velas (Vela Atual e Vela Anterior)
    o1, h1, l1, c1 = O[-2], H[-2], L[-2], C[-2]  # Penúltima vela
    o2, h2, l2, c2 = O[-1], H[-1], L[-1], C[-1]  # Última vela (atual)

    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)

    # Mede a micro-tendência das últimas 5 velas
    local_trend_up = C[-1] > C[-5]
    local_trend_down = C[-1] < C[-5]

    # ---------------------------------------------------------
    # 1. ENGOLFOS INSTITUCIONAIS (ENGULFING)
    # ---------------------------------------------------------
    # Engolfo de Alta (Bullish Engulfing) - Forte para CALL
    if c1 < o1 and c2 > o2 and c2 > o1 and o2 < c1 and local_trend_down:
        signals.append("Vela: Engolfo de Alta (+20%)")
        score_boost += 20

    # Engolfo de Baixa (Bearish Engulfing) - Forte para PUT
    elif c1 > o1 and c2 < o2 and c2 < o1 and o2 > c1 and local_trend_up:
        signals.append("Vela: Engolfo de Baixa (+20%)")
        score_boost -= 20  # Negativo significa força para PUT

    # ---------------------------------------------------------
    # 2. REJEIÇÕES DE CAUDA (HAMMER / SHOOTING STAR)
    # ---------------------------------------------------------
    lower_wick = min(o2, c2) - l2
    upper_wick = h2 - max(o2, c2)
    
    # Prevenção de divisão por zero
    if body2 == 0: body2 = 0.0001 

    # Martelo / Pinbar de Alta (Rejeição de Fundo) - Forte para CALL
    if local_trend_down and lower_wick > (2.0 * body2) and upper_wick < (0.5 * body2):
        signals.append("Vela: Martelo / Rejeição de Fundo (+15%)")
        score_boost += 15

    # Estrela Cadente / Pinbar de Baixa (Rejeição de Topo) - Forte para PUT
    elif local_trend_up and upper_wick > (2.0 * body2) and lower_wick < (0.5 * body2):
        signals.append("Vela: Estrela Cadente / Rejeição Topo (+15%)")
        score_boost -= 15

    return signals, score_boost
