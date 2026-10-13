from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import traceback

# ==============================================================================
# KRONOS QUANT CORE API // MOTOR BAYESIANO E L2
# ==============================================================================

app = FastAPI(title="KRONOS QUANT PRO", version="4.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QuantRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    capital_usd: float = 1000.0

@app.get("/")
async def root_health_check():
    return {"status": "KRONOS QUANT CORE ONLINE", "version": "4.2.0"}

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
    # A SOLUÇÃO: Usar a filial americana da Binance para IPs dos Estados Unidos (Render)
    exchange = ccxt_async.binanceus({'enableRateLimit': True}) 
    try:
        bars = await exchange.fetch_ohlcv(req.symbol, req.timeframe, limit=100)
        await exchange.close()
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['mme5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['mme20'] = df['close'].ewm(span=20, adjust=False).mean()
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
        
        breakout_threshold = res_zone + (current_atr * 0.2) 
        dynamic_stop = current_price - (current_atr * 1.5) 
        dynamic_target = current_price + (current_atr * 3.0) 
        
        confluence_score = 0
        signals = []
        
        if df.at[last_idx, 'mme5'] > df.at[last_idx, 'mme20']:
            confluence_score += 25
            signals.append("MME5 > MME20")
            
        if current_vol > (vol_sma * 1.5):
            confluence_score += 20
            signals.append("Volume Alto")
            
        if 55 <= current_rsi <= 75:
            confluence_score += 15
            signals.append("RSI Saudável")
        elif current_rsi > 75:
            confluence_score -= 10
            signals.append("RSI Exausto")
            
        if current_price > breakout_threshold:
            confluence_score += 40
            signals.append("Fuga Estrutural")

        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        is_stable = l2_div < 0.015 
        
        if not is_stable:
            confluence_score *= 0.5 
            signals.append("Risco Whipsaw (Ruído L2)")

        if confluence_score >= 80:
            verdict = "COMPRA FORTE"
        elif confluence_score >= 60:
            verdict = "COMPRA MODERADA"
        else:
            verdict = "MERCADO NEUTRO"

        return {
            "telemetry": {
                "symbol": req.symbol,
                "price": current_price,
                "rsi_14": round(current_rsi, 2),
                "atr_14": round(current_atr, 4),
                "l2_divergence": round(l2_div, 6),
                "market_state": "ESTÁVEL" if is_stable else "CAÓTICO"
            },
            "tactical_coordinates": {
                "atr_stop_loss": round(dynamic_stop, 4),
                "atr_take_profit": round(dynamic_target, 4)
            },
            "bayesian_oracle": {
                "confluence_score_pct": round(confluence_score, 2),
                "active_signals": signals,
                "final_verdict": verdict
            }
        }
    except Exception as e:
        error_msg = f"ERRO CRÍTICO NO ORÁCULO: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        if hasattr(exchange, 'close'):
            await exchange.close()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
