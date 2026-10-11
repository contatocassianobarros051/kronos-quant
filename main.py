from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import logging

# ==============================================================================
# KRONOS QUANT CORE API // V4.0 - INSTITUTIONAL GRADE ENGINE
# ==============================================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - KRONOS ENGINE - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="KRONOS QUANT PRO",
    description="Motor de Inferência Bayesiana, Geometria Vetorial e Filtragem L2",
    version="4.0.0"
)

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
    return {
        "status": "KRONOS QUANT CORE ONLINE",
        "version": "4.0.0",
        "message": "Servidor Institucional Ativo. Motor Bayesiano e L2 a aguardar comunicacao do Terminal Web."
    }

# ==============================================================================
# MÓDULOS DE MATEMÁTICA FINANCEIRA AVANÇADA
# ==============================================================================

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

# ==============================================================================
# ROTA PRINCIPAL DO ORÁCULO
# ==============================================================================

@app.post("/api/oracle")
async def process_quant_analysis(req: QuantRequest):
    exchange = ccxt_async.binance({'enableRateLimit': True})
    
    try:
        logger.info(f"Iniciando cálculo vetorial para {req.symbol} em {req.timeframe}")
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
            signals.append("MME5 > MME20 (Momentum de Alta)")
            
        if current_vol > (vol_sma * 1.5):
            confluence_score += 20
            signals.append("Choque de Volume Institucional")
            
        if 55 <= current_rsi <= 75:
            confluence_score += 15
            signals.append("RSI Saudável (Tendência Forte)")
        elif current_rsi > 75:
            confluence_score -= 10
            signals.append("RSI Sobrecomprado (Risco de Retracao)")
            
        if current_price > breakout_threshold:
            confluence_score += 40
            signals.append("Forte Fuga Estrutural (Breakout)")

        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        is_stable = l2_div < 0.015 
        
        if not is_stable:
            confluence_score *= 0.5 
            signals.append("ALERTA: Alta Divergência L2 (Risco de Whipsaw)")

        risk_per_coin = current_price - dynamic_stop
        if risk_per_coin > 0:
            suggested_position_size_usd = (req.capital_usd * 0.02) / (risk_per_coin / current_price)
        else:
            suggested_position_size_usd = 0.0

        if confluence_score >= 80:
            verdict = "COMPRA AGRESSIVA (STRONG LONG)"
        elif confluence_score >= 60:
            verdict = "COMPRA MODERADA (LONG)"
        else:
            verdict = "AGUARDAR (NEUTRAL/FLAT)"

        logger.info(f"Análise concluída. Score: {confluence_score}%. Veredito: {verdict}")

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
                "resistance_fractal": round(res_zone, 4),
                "support_fractal": round(sup_zone, 4),
                "dynamic_entry": round(breakout_threshold, 4),
                "atr_stop_loss": round(dynamic_stop, 4),
                "atr_take_profit": round(dynamic_target, 4)
            },
            "bayesian_oracle": {
                "confluence_score_pct": round(confluence_score, 2),
                "active_signals": signals,
                "final_verdict": verdict
            },
            "risk_management": {
                "account_capital": req.capital_usd,
                "suggested_position_usd": round(min(suggested_position_size_usd, req.capital_usd), 2)
            }
        }
        
    except Exception as e:
        logger.error(f"Falha Crítica no Motor: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro Interno no Processamento Quantitativo")
