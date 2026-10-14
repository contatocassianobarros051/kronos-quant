from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import traceback

# ==============================================================================
# IMPORTAÇÃO DOS MÓDULOS DE CONHECIMENTO (MACRO, MICRO & BALEIAS)
# ==============================================================================
try:
    import candlestick_patterns as cdp
    HAS_CANDLES = True
except Exception as e:
    HAS_CANDLES = False
    ERR_CANDLES = str(e)

try:
    import whale_tracker as wt
    HAS_WHALES = True
except Exception as e:
    HAS_WHALES = False
    ERR_WHALES = str(e)

try:
    import chart_patterns_math as cpm
    HAS_MATH = True
except Exception as e:
    HAS_MATH = False
    ERR_MATH = str(e)

# ==============================================================================
# KRONOS QUANT CORE API // V7.0 (MOTOR FRACTAL MULTI-TIMEFRAME 5m + 15m)
# ==============================================================================

app = FastAPI(title="KRONOS QUANT PRO", version="7.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class QuantRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    capital_usd: float = 1000.0

# Mapa de Hierarquia Fractal (Timeframe Operacional -> Timeframe Âncora Institucional)
HTF_MAP = {
    "1m": "5m",
    "5m": "15m",
    "15m": "1h",
    "1h": "4h"
}

@app.get("/")
async def root_health_check():
    return {"status": "KRONOS QUANT CORE ONLINE - MOTOR FRACTAL 4D ATIVO", "version": "7.0.0"}

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

def enrich_dataframe(bars: list) -> pd.DataFrame:
    """Vetoriza o cálculo de indicadores para qualquer Timeframe."""
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['mme5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['mme20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['mme100'] = df['close'].ewm(span=100, adjust=False).mean()
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['atr'] = calculate_atr(df, 14)
    df['volume_sma'] = df['volume'].rolling(window=20).mean()
    return df

@app.post("/api/oracle")
async def process_quant_analysis(req: QuantRequest):
    exchange = ccxt_async.binanceus({'enableRateLimit': True}) 
    try:
        htf_timeframe = HTF_MAP.get(req.timeframe, "15m")
        
        # ======================================================================
        # 0. EXTRAÇÃO ASSÍNCRONA PARALELA (LTF 5m + HTF 15m SIMULTÂNEOS)
        # ======================================================================
        bars_ltf, bars_htf = await asyncio.gather(
            exchange.fetch_ohlcv(req.symbol, req.timeframe, limit=200),
            exchange.fetch_ohlcv(req.symbol, htf_timeframe, limit=200)
        )
        await exchange.close()
        
        df = enrich_dataframe(bars_ltf)
        df_htf = enrich_dataframe(bars_htf)
        
        res_zone, sup_zone = detect_structural_pivots(df, window=5)
        
        # Leitura do Timeframe Atual (ex: 5m)
        last_idx = df.index[-1]
        current_price = float(df.at[last_idx, 'close'])
        current_atr = float(df.at[last_idx, 'atr'])
        current_rsi = float(df.at[last_idx, 'rsi'])
        current_vol = float(df.at[last_idx, 'volume'])
        vol_sma = float(df.at[last_idx, 'volume_sma'])
        is_lta = current_price > float(df.at[last_idx, 'mme100'])
        
        # Leitura do Timeframe Âncora (ex: 15m)
        htf_last_idx = df_htf.index[-1]
        htf_price = float(df_htf.at[htf_last_idx, 'close'])
        htf_mme20 = float(df_htf.at[htf_last_idx, 'mme20'])
        htf_mme100 = float(df_htf.at[htf_last_idx, 'mme100'])
        htf_rsi = float(df_htf.at[htf_last_idx, 'rsi'])
        is_htf_lta = htf_price > htf_mme100
        
        # Coordenadas de Execução para Futuros (Baseadas em ATR)
        dynamic_stop = current_price - (current_atr * 1.5) if is_lta else current_price + (current_atr * 1.5)
        dynamic_target = current_price + (current_atr * 3.0) if is_lta else current_price - (current_atr * 3.0)
        
        confluence_score = 0.0
        signals = []
        knowledge_applied = False
        
        # ======================================================================
        # 1. MOTOR DIRECIONAL & PRICE ACTION LOCAL (LTF - 5m)
        # ======================================================================
        if is_lta:
            if df.at[last_idx, 'mme5'] > df.at[last_idx, 'mme20']:
                confluence_score += 15; signals.append("Médias 5m Alinhadas (Alta)")
            if 40 <= current_rsi <= 70:
                confluence_score += 10
            if current_price >= res_zone:
                confluence_score += 20; signals.append("Rompimento de Resistência Local")
        else:
            if df.at[last_idx, 'mme5'] < df.at[last_idx, 'mme20']:
                confluence_score += 15; signals.append("Médias 5m Alinhadas (Baixa)")
            if 30 <= current_rsi <= 60:
                confluence_score += 10
            if current_price <= sup_zone:
                confluence_score += 20; signals.append("Quebra de Suporte Local")

        if current_vol > (vol_sma * 1.2):
            confluence_score += 15; signals.append("Volume Institucional Ativo")

        H, L, C, O = df['high'].values, df['low'].values, df['close'].values, df['open'].values

        # ======================================================================
        # 2. OS 3 PILARES DE INTELIGÊNCIA (VELAS, BALEIAS E BULKOWSKI)
        # ======================================================================
        # 2A. Micro-Estrutura (Candlesticks)
        if HAS_CANDLES:
            try:
                c_sigs, c_boost = cdp.detect_patterns(O, H, L, C)
                if is_lta and c_boost > 0:
                    confluence_score += c_boost; signals.extend(c_sigs); knowledge_applied = True
                elif not is_lta and c_boost < 0:
                    confluence_score += abs(c_boost); signals.extend(c_sigs); knowledge_applied = True
            except Exception as e:
                signals.append(f"⚠️ Erro Velas: {str(e)[:25]}")

        # 2B. Rastreio de Baleias (SMC no 5m + Verificação no 15m)
        if HAS_WHALES:
            try:
                w_sigs, w_boost = wt.detect_whale_activity(df)
                if is_lta and w_boost > 0:
                    confluence_score += w_boost; signals.extend(w_sigs); knowledge_applied = True
                elif not is_lta and w_boost < 0:
                    confluence_score += abs(w_boost); signals.extend(w_sigs); knowledge_applied = True
                
                # Bónus extra se houver Baleia também no gráfico de 15m!
                w_htf_sigs, w_htf_boost = wt.detect_whale_activity(df_htf)
                if (is_lta and w_htf_boost > 0) or (not is_lta and w_htf_boost < 0):
                    confluence_score += 10
                    signals.append(f"🐋 Baleia Confirmada no {htf_timeframe} (+10%)")
                    knowledge_applied = True
            except Exception as e:
                signals.append(f"⚠️ Erro Baleias: {str(e)[:25]}")

        # 2C. Macro-Estrutura Matemática (Bulkowski)
        if HAS_MATH:
            try:
                found_pattern = False
                pattern_name_for_csv = None

                if is_lta:
                    db = cpm.double_bottoms(H, L, C)
                    hs = cpm.head_shoulders_bottoms(H, L, C)
                    barr = cpm.bump_and_run_reversal(H, L, C, is_bottom=True)
                    if db:
                        confluence_score += 25; signals.append("Geometria: Fundo Duplo"); found_pattern = True; pattern_name_for_csv = "Double Bottom"
                    elif hs:
                        confluence_score += 25; signals.append("Geometria: OCO Invertido"); found_pattern = True
                    elif barr:
                        confluence_score += 25; signals.append("Geometria: BARR Bottom"); found_pattern = True; pattern_name_for_csv = "Bump-and-Run Reversal Bottom"
                else:
                    dt = cpm.top_version(cpm.double_bottoms, H, L, C)
                    pt = cpm.pipe_top(O, H, L, C)
                    barr_top = cpm.bump_and_run_reversal(H, L, C, is_bottom=False)
                    if dt:
                        confluence_score += 25; signals.append("Geometria: Topo Duplo"); found_pattern = True; pattern_name_for_csv = "Double Top"
                    elif pt:
                        confluence_score += 15; signals.append("Geometria: Tubo de Topo"); found_pattern = True
                    elif barr_top:
                        confluence_score += 25; signals.append("Geometria: BARR Top"); found_pattern = True; pattern_name_for_csv = "Bump-and-Run Reversal Top"

                if found_pattern:
                    knowledge_applied = True

                if found_pattern and pattern_name_for_csv:
                    try:
                        df_stats = pd.read_csv("pattern_stats.csv")
                        t_market = 'Bull' if is_htf_lta else 'Bear' # Usa o 15m para definir se o mercado global é Bull ou Bear!
                        t_break = 'up' if is_lta else 'down'
                        stats_match = df_stats[df_stats['pattern'].str.contains(pattern_name_for_csv, case=False, na=False)]
                        exact_stats = stats_match[(stats_match['market'] == t_market) & (stats_match['breakout'] == t_break)]
                        
                        if not exact_stats.empty:
                            win_chance = 100 - float(exact_stats.iloc[0]['break_even_failure_pct'])
                            signals.append(f"Backtest ({t_market}): ~{win_chance:.0f}% Acerto")
                            if win_chance > 70:
                                confluence_score += 15
                    except Exception:
                        pass
            except Exception as e:
                signals.append(f"⚠️ Erro Geometria: {str(e)[:25]}")

        # ======================================================================
        # 3. A 4ª DIMENSÃO: FILTRO FRACTAL MULTI-TIMEFRAME (5m vs 15m)
        # ======================================================================
        fractal_aligned = (is_lta == is_htf_lta)
        
        if fractal_aligned:
            confluence_score += 15
            trend_str = "LTA (Alta)" if is_htf_lta else "LTB (Baixa)"
            signals.append(f"🌐 Fractal {htf_timeframe} Alinhado em {trend_str} (+15%)")
            
            # Bónus de Momentum se a MME20 do 15m também confirmar a MME100 do 15m
            if (is_lta and htf_mme20 > htf_mme100 and htf_rsi < 72) or (not is_lta and htf_mme20 < htf_mme100 and htf_rsi > 28):
                confluence_score += 5
                signals.append(f"⚡ Fluxo {htf_timeframe} Limpo (Sem Exaustão)")
        else:
            # DIVERGÊNCIA FRACTAL: 5m está contra a tendência principal de 15m!
            confluence_score -= 20
            htf_dir = "ALTA (LTA)" if is_htf_lta else "QUEDA (LTB)"
            signals.append(f"🛑 Alerta: Gráfico {htf_timeframe} está em {htf_dir} (-20%)")

        # ======================================================================
        # 4. FILTRO L2 (WHIPSAW) & TRAVA DE SEGURANÇA INSTITUCIONAL
        # ======================================================================
        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        is_stable = l2_div < 0.015 
        if not is_stable:
            confluence_score *= 0.5
            signals.append("⚠️ Ruído L2 Alto (Risco de Violino)")

        # TRAVA HARD CAP: Nunca permite sinal >= 80% se o 15m estiver contra a operação
        if not fractal_aligned and confluence_score > 65.0:
            confluence_score = 65.0
            signals.append("🔒 Trava Fractal: Score limitado a 65% (Contra 15m)")

        confluence_score = max(0.0, min(round(confluence_score, 2), 100.0))
        
        if confluence_score >= 80:
            verdict = "FORÇA INSTITUCIONAL (5m + 15m)"
        elif confluence_score >= 60:
            verdict = "MOMENTUM MODERADO"
        else:
            verdict = "AGUARDAR (SEM CONFLUÊNCIA)"

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
        if hasattr(exchange, 'close'):
            await exchange.close()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
