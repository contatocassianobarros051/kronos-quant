from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import traceback
import os

# ==============================================================================
# KRONOS QUANT CORE API // V6.0 (OMNIDIRECIONAL LTA/LTB + CONHECIMENTO EXTERNO)
# ==============================================================================

app = FastAPI(title="KRONOS QUANT PRO", version="6.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class QuantRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    capital_usd: float = 1000.0

@app.get("/")
async def root_health_check():
    return {"status": "KRONOS QUANT CORE ONLINE - MODO OMNIDIRECIONAL", "version": "6.0.0"}

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
        df['mme100'] = df['close'].ewm(span=100, adjust=False).mean() # O Cérebro da Tendência
        df['rsi'] = calculate_rsi(df['close'], 14)
        df['atr'] = calculate_atr(df, 14)
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        
        last_idx = df.index[-1]
        current_price = float(df.at[last_idx, 'close'])
        current_atr = float(df.at[last_idx, 'atr'])
        current_rsi = float(df.at[last_idx, 'rsi'])
        current_vol = float(df.at[last_idx, 'volume'])
        vol_sma = float(df.at[last_idx, 'volume_sma'])
        
        # BÚSSOLA MESTRA NO BACKEND
        is_lta = current_price > df.at[last_idx, 'mme100']
        
        dynamic_stop = current_price - (current_atr * 1.5) if is_lta else current_price + (current_atr * 1.5)
        dynamic_target = current_price + (current_atr * 3.0) if is_lta else current_price - (current_atr * 3.0)
        
        confluence_score = 0
        signals = []
        
        # =====================================================================
        # 1. MOTOR DIRECIONAL (LTA vs LTB)
        # =====================================================================
        if is_lta:
            # PONTUAÇÃO PARA CALL (COMPRAS)
            if df.at[last_idx, 'mme5'] > df.at[last_idx, 'mme20']: confluence_score += 15; signals.append("Médias de Alta Alinhadas")
            if 40 <= current_rsi <= 70: confluence_score += 10; signals.append("RSI Fértil para Alta")
            elif current_rsi > 75: confluence_score -= 15; signals.append("RSI Exausto (Perigo Alto)")
        else:
            # PONTUAÇÃO PARA PUT (VENDAS)
            if df.at[last_idx, 'mme5'] < df.at[last_idx, 'mme20']: confluence_score += 15; signals.append("Médias de Baixa Alinhadas")
            if 30 <= current_rsi <= 60: confluence_score += 10; signals.append("RSI Fértil para Queda")
            elif current_rsi < 25: confluence_score -= 15; signals.append("RSI Muito Baixo (Risco de Respiro)")

        if current_vol > (vol_sma * 1.5): confluence_score += 15; signals.append("Injeção de Volume Institucional")

        # =====================================================================
        # 2. INTEGRAÇÃO DA SABEDORIA EXTERNA (Os seus Ficheiros)
        # =====================================================================
        knowledge_applied = False
        try:
            if os.path.exists("chart_patterns_math.py"):
                import chart_patterns_math as cpm
                H, L, C, O = df['high'].values, df['low'].values, df['close'].values, df['open'].values
                found_pattern = False
                pattern_name_for_csv = None

                if is_lta:
                    # CAÇA A FUNDOS (CALL)
                    db = cpm.double_bottoms(H, L, C)
                    hs = cpm.head_shoulders_bottoms(H, L, C)
                    if db:
                        confluence_score += 25; signals.append(f"Fundo Duplo ({db[-1]['kind']})"); found_pattern = True; pattern_name_for_csv = "Double Bottom"
                    if hs:
                        confluence_score += 25; signals.append("Cabeça e Ombros Invertido (Fundo)"); found_pattern = True
                else:
                    # CAÇA A TOPOS (PUT) - Usando o poder do seu top_version()!
                    dt = cpm.top_version(cpm.double_bottoms, H, L, C)
                    pt = cpm.pipe_top(O, H, L, C)
                    if dt:
                        confluence_score += 25; signals.append(f"Topo Duplo ({dt[-1]['kind']})"); found_pattern = True; pattern_name_for_csv = "Double Top"
                    if pt:
                        confluence_score += 15; signals.append("Tubo de Topo Detetado"); found_pattern = True

                knowledge_applied = found_pattern

                # CONSULTA À ESTATÍSTICA (CSV)
                if found_pattern and pattern_name_for_csv and os.path.exists("pattern_stats.csv"):
                    df_stats = pd.read_csv("pattern_stats.csv")
                    # Se LTA, procura Bull/up. Se LTB, procura Bear/down.
                    t_market = 'Bull' if is_lta else 'Bear'
                    t_break = 'up' if is_lta else 'down'
                    
                    stats_match = df_stats[df_stats['pattern'].str.contains(pattern_name_for_csv, case=False, na=False)]
                    exact_stats = stats_match[(stats_match['market'] == t_market) & (stats_match['breakout'] == t_break)]
                    
                    if not exact_stats.empty:
                        win_chance = 100 - float(exact_stats.iloc[0]['break_even_failure_pct'])
                        signals.append(f"Backtest {t_market}: ~{win_chance:.0f}% Acerto")
                        if win_chance > 70: confluence_score += 15

        except Exception as e: print(f"Erro Base Conhecimento: {e}")

        # =====================================================================
        # 3. FILTRO FINAL
        # =====================================================================
        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        is_stable = l2_div < 0.015 
        if not is_stable: confluence_score *= 0.5; signals.append("Risco Whipsaw (Ruído L2 Alto)")

        confluence_score = max(0.0, min(round(confluence_score, 2), 100.0))
        
        # VEREDITO ADAPTADO PARA DIREÇÃO
        if confluence_score >= 80:
            verdict = "FORÇA TOTAL INSTITUCIONAL"
        elif confluence_score >= 60:
            verdict = "MOMENTUM MODERADO"
        else:
            verdict = "AGUARDAR (SEM ENTRADA CLARA)"

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
        error_msg = f"ERRO CRÍTICO NO ORÁCULO: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        if hasattr(exchange, 'close'): await exchange.close()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
