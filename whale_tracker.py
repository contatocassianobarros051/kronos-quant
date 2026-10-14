import pandas as pd

def detect_whale_activity(df: pd.DataFrame):
    """
    Motor SMC (Smart Money Concepts) / Rastreador de Baleias.
    Procura por FVG (Fair Value Gaps), Stop Hunts (Liquidity Sweeps) e Anomalias de Volume.
    """
    signals = []
    score_boost = 0
    
    if len(df) < 20:
        return signals, score_boost
        
    # Extrai os dados essenciais das últimas velas
    L1, H1 = df['low'].iloc[-3], df['high'].iloc[-3]
    L3, H3 = df['low'].iloc[-1], df['high'].iloc[-1]
    
    C_close = df['close'].iloc[-1]
    C_open = df['open'].iloc[-1]
    C_vol = df['volume'].iloc[-1]
    vol_sma = df['volume'].tail(20).mean()

    # ---------------------------------------------------------
    # 1. FAIR VALUE GAPS (FVG) - O Rastro do Deslocamento
    # ---------------------------------------------------------
    bullish_fvg = L3 > H1
    bearish_fvg = H3 < L1
    
    if bullish_fvg and C_close > C_open:
        signals.append("BALEIA: FVG de Alta (Injeção Agressiva)")
        score_boost += 15
    elif bearish_fvg and C_close < C_open:
        signals.append("BALEIA: FVG de Baixa (Despejo Agressivo)")
        score_boost -= 15

    # ---------------------------------------------------------
    # 2. CAÇA AOS STOPS (LIQUIDITY SWEEPS / MANIPULAÇÃO)
    # ---------------------------------------------------------
    # Encontra a máxima e mínima das últimas 15 velas (o "porto seguro" do retalho)
    min_15 = df['low'].iloc[-16:-2].min()
    max_15 = df['high'].iloc[-16:-2].max()
    
    # Sweep de Fundo: Rompe a mínima com o pavio para apanhar stops, mas fecha acima.
    if df['low'].iloc[-1] < min_15 and df['close'].iloc[-1] > min_15:
        signals.append("BALEIA: Stop Hunt de Fundo (Manipulação p/ Subir)")
        score_boost += 20
        
    # Sweep de Topo: Rompe a máxima com o pavio, mas fecha abaixo.
    elif df['high'].iloc[-1] > max_15 and df['close'].iloc[-1] < max_15:
        signals.append("BALEIA: Stop Hunt de Topo (Manipulação p/ Cair)")
        score_boost -= 20

    # ---------------------------------------------------------
    # 3. ANOMALIA DE VOLUME EXTREMO (BIG BLOCKS)
    # ---------------------------------------------------------
    # Detecta se o volume da vela atual é mais de 300% a média
    if C_vol > (vol_sma * 3.0):
        if C_close > C_open:
            signals.append("BALEIA: Bloqueio de Compra Brutal (>300% Vol)")
            score_boost += 15
        else:
            signals.append("BALEIA: Despejo de Venda Brutal (>300% Vol)")
            score_boost -= 15

    return signals, score_boost
