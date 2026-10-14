from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import traceback
import os

# ==============================================================================
# KRONOS QUANT CORE API // V6.2 (FUSÃO DE MACRO & MICRO ESTRUTURA)
# ==============================================================================

app = FastAPI(title="KRONOS QUANT PRO", version="6.2.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class QuantRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    capital_usd: float = 1000.0

@app.get("/")
async def root_health_check():
    return {"status": "KRONOS QUANT CORE ONLINE - LENDO MICRO ESTRUTURA", "version": "6.2.0"}

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.ewm(alpha=1/period, adjust=False).mean()

def detect_structural_pivots(df: pd.DataFrame, window: int = 5):
    df['is_high_pivot'] = df['high'] == df['high'].rolling(window=window, center=True).max()
    df['is_low_pivot'] = df['low'] == df['low'].rolling(window=window, center=True).min()
    recent_highs = df[df['is_high_pivot']]['high'].values
    recent_lows = df[df['is_low_pivot']]['low'].values
    highest_res = np.max(recent_highs) if len(recent_highs) > 0 else df['high'].max()
    lowest_sup = np.min(recent_lows) if len(recent_lows) > 0 else df['low'].min()
    return float(highest_res), float(lowest_sup)

def calculate_l2_divergence(close_series: pd.Series, ma_series: pd.Series) -> float:
    diff_vector = close_series.tail(10).values - ma_series.tail(10).values
    l2_norm = np.linalg.norm(diff_vector)
    return float(l2_norm / np.mean(close_series.tail(10).values))

@app.post("/api/oracle")
async def process_quant_analysis(req: QuantRequest):
    exchange = ccxt_async.binanceus({'enableRateLimit': True}) 
    try:
        bars = await exchange.fetch_ohlcv(req.symbol, req.timeframe, limit=200)
        await exchange.close()
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['mme5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['mme20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['mme100'] = df['close'].ewm(span=100, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'], 14)
        df['atr'] = calculate_atr(df, 14)
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        
        res_zone, sup_zone = detect_structural_pivots(df, window=5)
        
        last_idx = df.index[-1]
        current_price = float(df.at[last_idx, 'close'])
        current_atr = float(df.at[last_idx, 'atr'])
        current_rsi = float(df.at[last_idx, 'rsi'])
        current_vol = float(df.at[last_idx, 'volume'])
        vol_sma = float(df.at[last_idx, 'volume_sma'])
        
        is_lta = current_price > df.at[last_idx, 'mme100']
        
        breakout_threshold_up = res_zone + (current_atr * 0.2) 
        breakout_threshold_down = sup_zone - (current_atr * 0.2) 
        
        dynamic_stop = current_price - (current_atr * 1.5) if is_lta else current_price + (current_atr * 1.5)
        dynamic_target = current_price + (current_atr * 3.0) if is_lta else current_price - (current_atr * 3.0)
        
        confluence_score = 0
        signals = []
        
        # 1. MOTOR DIRECIONAL & PRICE ACTION LOCAL
        if is_lta:
            if df.at[last_idx, 'mme5'] > df.at[last_idx, 'mme20']: confluence_score += 15; signals.append("Médias Alta Alinhadas")
            if 40 <= current_rsi <= 70: confluence_score += 10
            if current_price > breakout_threshold_up: confluence_score += 20; signals.append("Fuga de Resistência")
        else:
            if df.at[last_idx, 'mme5'] < df.at[last_idx, 'mme20']: confluence_score += 15; signals.append("Médias Baixa Alinhadas")
            if 30 <= current_rsi <= 60: confluence_score += 10
            if current_price < breakout_threshold_down: confluence_score += 20; signals.append("Quebra de Suporte")

        if current_vol > (vol_sma * 1.5): confluence_score += 15; signals.append("Volume Institucional")

        # 2. SABEDORIA EXTERNA (Micro e Macro Estrutura)
        knowledge_applied = False
        H, L, C, O = df['high'].values, df['low'].values, df['close'].values, df['open'].values

        # A. AÇÃO MICRO-ESTRUTURAL (NOVO MÓDULO DE VELAS JAPONESAS)
        try:
            if os.path.exists("candlestick_patterns.py"):
                import candlestick_patterns as cdp
                c_sigs, c_boost = cdp.detect_patterns(O, H, L, C)
                
                # Aplica os pontos dependendo da tendência da Bússola
                if is_lta and c_boost > 0:  # Fortalece o Call
                    confluence_score += c_boost
                    signals.extend(c_sigs)
                    knowledge_applied = True
                elif not is_lta and c_boost < 0: # Fortalece o Put
                    confluence_score += abs(c_boost)
                    signals.extend(c_sigs)
                    knowledge_applied = True
        except Exception as e:
            print(f"Erro Candlesticks: {e}")

        # B. AÇÃO MACRO-ESTRUTURAL (PADRÕES INSTITUCIONAIS)
        try:
            if os.path.exists("chart_patterns_math.py"):
                import chart_patterns_math as cpm
                found_pattern = False
                pattern_name_for_csv = None

                if is_lta:
                    db = cpm.double_bottoms(H, L, C)
                    hs = cpm.head_shoulders_bottoms(H, L, C)
                    if db:
                        confluence_score += 25; signals.append(f"Padrão: Fundo Duplo"); found_pattern = True; pattern_name_for_csv = "Double Bottom"
                    if hs:
                        confluence_score += 25; signals.append("Padrão: OCO Invertido"); found_pattern = True
                else:
                    dt = cpm.top_version(cpm.double_bottoms, H, L, C)
                    pt = cpm.pipe_top(O, H, L, C)
                    if dt:
                        confluence_score += 25; signals.append(f"Padrão: Topo Duplo"); found_pattern = True; pattern_name_for_csv = "Double Top"
                    if pt:
                        confluence_score += 15; signals.append("Padrão: Tubo de Topo"); found_pattern = True

                if found_pattern: knowledge_applied = True

                if found_pattern and pattern_name_for_csv and os.path.exists("pattern_stats.csv"):
                    df_stats = pd.read_csv("pattern_stats.csv")
                    t_market = 'Bull' if is_lta else 'Bear'
                    t_break = 'up' if is_lta else 'down'
                    stats_match = df_stats[df_stats['pattern'].str.contains(pattern_name_for_csv, case=False, na=False)]
                    exact_stats = stats_match[(stats_match['market'] == t_market) & (stats_match['breakout'] == t_break)]
                    
                    if not exact_stats.empty:
                        win_chance = 100 - float(exact_stats.iloc[0]['break_even_failure_pct'])
                        signals.append(f"Backtest: ~{win_chance:.0f}% Acerto")
                        if win_chance > 70: confluence_score += 15
        except Exception as e:
            signals.append(f"ERRO DE ARQUIVO: {str(e)[:30]}")

        # 3. FILTRO FINAL DE RUÍDO
        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        is_stable = l2_div < 0.015 
        if not is_stable: confluence_score *= 0.5; signals.append("⚠️ Ruído L2 Alto")

        confluence_score = max(0.0, min(round(confluence_score, 2), 100.0))
        
        if confluence_score >= 80: verdict = "FORÇA TOTAL INSTITUCIONAL"
        elif confluence_score >= 60: verdict = "MOMENTUM MODERADO"
        else: verdict = "AGUARDAR (SEM ENTRADA CLARA)"

        return {
            "telemetry": {
                "symbol": req.symbol,
                "price": current_price,
                "rsi_14": round(current_rsi, 2),
                "atr_14": round(current_atr, 4),
                "l2_divergence": round(l2_div, 6),
                "market_state": "ESTÁVEL" if is_stable else "CAÓTICO",
                "knowledge_applied": knowledge_applied
            },
            "tactical_coordinates": {
                "atr_stop_loss": round(dynamic_stop, 4),
                "atr_take_profit": round(dynamic_target, 4)
            },
            "bayesian_oracle": {
                "confluence_score_pct": confluence_score,
                "active_signals": signals,
                "final_verdict": verdict
            }
        }
    except Exception as e:
        if hasattr(exchange, 'close'): await exchange.close()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
