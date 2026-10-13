from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import traceback
import os

# ==============================================================================
# KRONOS QUANT CORE API // V5.0 (INTEGRAÇÃO DE CONHECIMENTO EXTERNO)
# ==============================================================================

app = FastAPI(title="KRONOS QUANT PRO", version="5.0.0")

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
    return {"status": "KRONOS QUANT CORE ONLINE - LENDO DADOS EXTERNOS", "version": "5.0.0"}

# --- MATEMÁTICA BASE DO KRONOS ---
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
        bars = await exchange.fetch_ohlcv(req.symbol, req.timeframe, limit=200) # Mais limite para padrões
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
        
        # 1. ANÁLISE TÉCNICA BASE (KRONOS)
        if df.at[last_idx, 'mme5'] > df.at[last_idx, 'mme20']:
            confluence_score += 15
            signals.append("MME5 > MME20")
            
        if current_vol > (vol_sma * 1.5):
            confluence_score += 15
            signals.append("Volume Institucional")
            
        if 55 <= current_rsi <= 75:
            confluence_score += 10
            signals.append("RSI Saudável")
        elif current_rsi > 75:
            confluence_score -= 15
            signals.append("RSI Exausto")
            
        if current_price > breakout_threshold:
            confluence_score += 20
            signals.append("Fuga Estrutural Confirmada")

        # 2. INTEGRAÇÃO DA BASE DE CONHECIMENTO (ARQUIVOS DO USUÁRIO)
        knowledge_applied = False
        
        # Tentar usar as fórmulas de chart_patterns_math.py e estatísticas do CSV
        try:
            # Tentar importar o seu ficheiro matematico
            if os.path.exists("chart_patterns_math.py"):
                import chart_patterns_math as cpm
                
                # Extrair arrays numpy puros para as funções do seu ficheiro
                H = df['high'].values
                L = df['low'].values
                C = df['close'].values
                
                # 1. Procurar Topo em Tubo (Pipe Top) - Um dos seus padrões
                pipes = cpm.pipe_top(df['open'].values, H, L, C, lookback=20)
                if pipes:
                    confluence_score -= 20 # Tubo no topo indica queda
                    signals.append("Padrão de Queda: Tubo Topo (Pipe Top)")
                    knowledge_applied = True
                
                # 2. Procurar Duplo Fundo (Double Bottom) - Padrão de alta forte[cite: 13, 14]
                dbottoms = cpm.double_bottoms(H, L, C)
                if dbottoms:
                    confluence_score += 25
                    signals.append(f"Fundo Duplo Encontrado ({dbottoms[-1]['kind']})")
                    knowledge_applied = True
                    
                    # 3. Ligar os Padrões ao seu CSV de Estatísticas[cite: 13, 14]
                    if os.path.exists("pattern_stats.csv"):
                        try:
                            df_stats = pd.read_csv("pattern_stats.csv")
                            # Procurar as estatísticas para Duplo Fundo (Eve & Eve etc)[cite: 13, 14]
                            # Simplificando a busca para qualquer fundo duplo[cite: 13, 14]
                            stats_match = df_stats[df_stats['pattern'].str.contains('Double Bottom', case=False, na=False)]
                            if not stats_match.empty:
                                # Usar o mercado "Bull" e rompimento "up" como referência
                                bull_stats = stats_match[(stats_match['market'] == 'Bull') & (stats_match['breakout'] == 'up')]
                                if not bull_stats.empty:
                                    win_chance = 100 - float(bull_stats.iloc[0]['break_even_failure_pct']) # Winrate aproximado
                                    signals.append(f"Estatística CSV: ~{win_chance:.0f}% Acerto")
                                    if win_chance > 80: confluence_score += 10
                        except Exception as csv_e:
                            print(f"Erro lendo CSV: {csv_e}")
                            
        except Exception as e:
            print(f"Erro ao aplicar módulos de conhecimento externo: {e}")
            
        # 3. FILTRO FINAL DE RUÍDO
        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        is_stable = l2_div < 0.015 
        
        if not is_stable:
            confluence_score *= 0.5 
            signals.append("Risco Whipsaw (L2)")

        # Limitar o score a 100% e mínimo de 0%
        confluence_score = max(0.0, min(round(confluence_score, 2), 100.0))

        if confluence_score >= 80:
            verdict = "COMPRA INSTITUCIONAL"
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
        if hasattr(exchange, 'close'):
            await exchange.close()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
