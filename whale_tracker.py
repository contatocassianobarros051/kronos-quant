import pandas as pd
import numpy as np

def detect_whale_activity(df: pd.DataFrame):
    """
    Motor SMC (Smart Money Concepts) / Rastreador de Baleias.
    Deteta Fair Value Gaps (FVG), Liquidity Sweeps (Stop Hunts), Order Blocks e Anomalias de Volume.
    """
    signals = []
    score_boost = 0

    if len(df) < 25:
        return signals, score_boost

    L1, H1 = float(df['low'].iloc[-3]), float(df['high'].iloc[-3])
    L3, H3 = float(df['low'].iloc[-1]), float(df['high'].iloc[-1])

    C_close = float(df['close'].iloc[-1])
    C_open = float(df['open'].iloc[-1])
    C_vol = float(df['volume'].iloc[-1])
    vol_sma = float(df['volume'].tail(20).mean())

    # 1. FAIR VALUE GAPS (FVG - Deslocamento Institucional)
    bullish_fvg = L3 > H1
    bearish_fvg = H3 < L1

    if bullish_fvg and C_close > C_open:
        signals.append("BALEIA: FVG de Alta (Injeção Institucional)")
        score_boost += 15
    elif bearish_fvg and C_close < C_open:
        signals.append("BALEIA: FVG de Baixa (Despejo Institucional)")
        score_boost -= 15

    # 2. LIQUIDITY SWEEPS (Caça aos Stops / Manipulação de Fundo e Topo)
    min_15 = float(df['low'].iloc[-18:-1].min())
    max_15 = float(df['high'].iloc[-18:-1].max())

    if L3 < min_15 and C_close > min_15:
        signals.append("BALEIA: Stop Hunt de Fundo (Absorção p/ Subir)")
        score_boost += 20
    elif H3 > max_15 and C_close < max_15:
        signals.append("BALEIA: Stop Hunt de Topo (Absorção p/ Cair)")
        score_boost -= 20

    # 3. ANOMALIA DE VOLUME INSTITUCIONAL (Big Blocks > 220% da Média)
    if vol_sma > 0 and C_vol > (vol_sma * 2.2):
        if C_close > C_open:
            signals.append("BALEIA: Bloco de Compra Agressivo (>220% Vol)")
            score_boost += 15
        elif C_close < C_open:
            signals.append("BALEIA: Bloco de Venda Agressivo (>220% Vol)")
            score_boost -= 15

    return signals, score_boost
