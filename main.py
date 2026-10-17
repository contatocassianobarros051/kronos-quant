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
# KRONOS QUANT CORE API // V7.2 (MULTI-TIMEFRAME 1m A 1h & CALIBRAÇÃO DINÂMICA)
# ==============================================================================

app = FastAPI(title="KRONOS QUANT PRO", version="7.2.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class QuantRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "30m"
    capital_usd: float = 1000.0

# Mapa de Hierarquia Fractal (Timeframe Operacional -> Timeframe Âncora Macro)
HTF_MAP = {
    "1m": "5m",
    "5m": "15m",
    "15m": "1h",
    "30m": "2h",
    "45m": "2h",
    "1h": "4h"
}

# Limite adaptativo de ruído L2 por Timeframe (evita penalizar tendências fortes em 30m/1h)
L2_NOISE_THRESHOLD = {
    "1m": 0.010,
    "5m": 0.015,
    "15m": 0.020,
    "30m": 0.025,
    "45m": 0.028,
    "1h": 0.032
}

@app.get("/")
async def root_health_check():
    return {
        "status": "KRONOS QUANT CORE ONLINE - MOTOR FRACTAL V7.2 (1m/5m/15m/30m/45m/1h)",
        "version": "7.2.0"
    }

def get_calibrated_params(tf: str):
    """Ajusta a régua geométrica de Bulkowski para a volatilidade exata de cada Timeframe."""
    if not HAS_MATH:
        return None
    if tf == "1m":
        return cpm.Params(zigzag_theta=0.0025, min_pivot_sep=3, horiz_eps=0.003, touch_tol=0.003,
                          twin_tol=0.010, twin_min_rise=0.003, twin_sep=(4, 50), hs_shoulder_tol=0.015)
    elif tf == "5m":
        return cpm.Params(zigzag_theta=0.0045, min_pivot_sep=3, horiz_eps=0.005, touch_tol=0.004,
                          twin_tol=0.012, twin_min_rise=0.004, twin_sep=(4, 55), hs_shoulder_tol=0.020)
    elif tf == "15m":
        return cpm.Params(zigzag_theta=0.0065, min_pivot_sep=3, horiz_eps=0.006, touch_tol=0.005,
                          twin_tol=0.015, twin_min_rise=0.006, twin_sep=(4, 60), hs_shoulder_tol=0.025)
    elif tf in ("30m", "45m"):
        return cpm.Params(zigzag_theta=0.0090, min_pivot_sep=3, horiz_eps=0.008, touch_tol=0.006,
                          twin_tol=0.018, twin_min_rise=0.008, twin_sep=(4, 65), hs_shoulder_tol=0.030)
    else:  # 1h ou superior
        return cpm.Params(zigzag_theta=0.0120, min_pivot_sep=3, horiz_eps=0.010, touch_tol=0.008,
                          twin_tol=0.022, twin_min_rise=0.010, twin_sep=(4, 70), hs_shoulder_tol=0.035)

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-9)
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
    recent = df.iloc[-40:]
    recent_highs = recent[recent['is_high_pivot']]['high'].values
    recent_lows = recent[recent['is_low_pivot']]['low'].values
    highest_res = np.max(recent_highs) if len(recent_highs) > 0 else recent['high'].max()
    lowest_sup = np.min(recent_lows) if len(recent_lows) > 0 else recent['low'].min()
    return float(highest_res), float(lowest_sup)

def calculate_l2_divergence(close_series: pd.Series, ma_series: pd.Series) -> float:
    diff_vector = close_series.tail(10).values - ma_series.tail(10).values
    l2_norm = np.linalg.norm(diff_vector)
    return float(l2_norm / np.mean(close_series.tail(10).values))

def resample_15m_to_45m(bars_15m: list) -> list:
    """Funde blocos de 3 velas de 15m para construir o gráfico institucional de 45m."""
    df_15 = pd.DataFrame(bars_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_15['dt'] = pd.to_datetime(df_15['timestamp'], unit='ms')
    df_15.set_index('dt', inplace=True)
    df_45 = df_15.resample('45min').agg({
        'timestamp': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    return df_45[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values.tolist()[-200:]

async def fetch_ohlcv_resilient(exchange, symbol: str, timeframe: str) -> list:
    """Busca dados OHLCV na Binance e sintetiza o 45m caso selecionado."""
    if timeframe == "45m":
        raw_15m = await exchange.fetch_ohlcv(symbol, "15m", limit=600)
        return resample_15m_to_45m(raw_15m)
    return await exchange.fetch_ohlcv(symbol, timeframe, limit=200)

def enrich_dataframe(bars: list) -> pd.DataFrame:
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
        htf_timeframe = HTF_MAP.get(req.timeframe, "4h")

        # 0. EXTRAÇÃO ASSÍNCRONA PARALELA (Timeframe Operacional + Timeframe Âncora)
        bars_ltf, bars_htf = await asyncio.gather(
            fetch_ohlcv_resilient(exchange, req.symbol, req.timeframe),
            fetch_ohlcv_resilient(exchange, req.symbol, htf_timeframe)
        )
        await exchange.close()

        df = enrich_dataframe(bars_ltf)
        df_htf = enrich_dataframe(bars_htf)

        res_zone, sup_zone = detect_structural_pivots(df, window=5)

        # Telemetria do Timeframe Operacional
        last_idx = df.index[-1]
        current_price = float(df.at[last_idx, 'close'])
        current_atr = float(df.at[last_idx, 'atr'])
        current_rsi = float(df.at[last_idx, 'rsi'])
        current_vol = float(df.at[last_idx, 'volume'])
        vol_sma = float(df.at[last_idx, 'volume_sma'])
        is_lta = current_price > float(df.at[last_idx, 'mme100'])

        # Telemetria do Timeframe Âncora (Macro)
        htf_last_idx = df_htf.index[-1]
        htf_price = float(df_htf.at[htf_last_idx, 'close'])
        htf_mme20 = float(df_htf.at[htf_last_idx, 'mme20'])
        htf_mme100 = float(df_htf.at[htf_last_idx, 'mme100'])
        htf_rsi = float(df_htf.at[htf_last_idx, 'rsi'])
        is_htf_lta = htf_price > htf_mme100

        # Coordenadas Táticas baseadas em ATR
        dynamic_stop = current_price - (current_atr * 1.5) if is_lta else current_price + (current_atr * 1.5)
        dynamic_target = current_price + (current_atr * 3.0) if is_lta else current_price - (current_atr * 3.0)

        confluence_score = 0.0
        signals = []
        knowledge_applied = False

        # ======================================================================
        # 1. MOTOR DIRECIONAL & PRICE ACTION LOCAL
        # ======================================================================
        if is_lta:
            if df.at[last_idx, 'mme5'] > df.at[last_idx, 'mme20']:
                confluence_score += 15; signals.append(f"Médias {req.timeframe} Alinhadas (Alta)")
            if 40 <= current_rsi <= 72:
                confluence_score += 10
            if current_price >= res_zone * 0.999:
                confluence_score += 20; signals.append("Pressão / Fuga de Resistência")
        else:
            if df.at[last_idx, 'mme5'] < df.at[last_idx, 'mme20']:
                confluence_score += 15; signals.append(f"Médias {req.timeframe} Alinhadas (Baixa)")
            if 28 <= current_rsi <= 60:
                confluence_score += 10
            if current_price <= sup_zone * 1.001:
                confluence_score += 20; signals.append("Pressão / Quebra de Suporte")

        if current_vol > (vol_sma * 1.15):
            confluence_score += 15; signals.append("Volume Institucional Ativo")

        H, L, C, O = df['high'].values, df['low'].values, df['close'].values, df['open'].values

        # ======================================================================
        # 2A. PILAR MICRO-ESTRUTURAL (VELAS JAPONESAS)
        # ======================================================================
        if HAS_CANDLES:
            try:
                c_sigs, c_boost = cdp.detect_patterns(O, H, L, C)
                if is_lta and c_boost > 0:
                    confluence_score += c_boost; signals.extend(c_sigs); knowledge_applied = True
                elif not is_lta and c_boost < 0:
                    confluence_score += abs(c_boost); signals.extend(c_sigs); knowledge_applied = True
            except Exception as e:
                signals.append(f"⚠️ Erro Velas: {str(e)[:25]}")

        # ======================================================================
        # 2B. PILAR DE BALEIAS / SMART MONEY CONCEPTS (LTF + HTF)
        # ======================================================================
        if HAS_WHALES:
            try:
                w_sigs, w_boost = wt.detect_whale_activity(df)
                if is_lta and w_boost > 0:
                    confluence_score += w_boost; signals.extend(w_sigs); knowledge_applied = True
                elif not is_lta and w_boost < 0:
                    confluence_score += abs(w_boost); signals.extend(w_sigs); knowledge_applied = True

                w_htf_sigs, w_htf_boost = wt.detect_whale_activity(df_htf)
                if (is_lta and w_htf_boost > 0) or (not is_lta and w_htf_boost < 0):
                    confluence_score += 10
                    signals.append(f"🐋 Baleia Confirmada no {htf_timeframe} (+10%)")
                    knowledge_applied = True
            except Exception as e:
                signals.append(f"⚠️ Erro Baleias: {str(e)[:25]}")

        # ======================================================================
        # 2C. PILAR MACRO-GEOMÉTRICO (BULKOWSKI COMPLETO + CALIBRAÇÃO DINÂMICA)
        # ======================================================================
        if HAS_MATH:
            try:
                cal_p = get_calibrated_params(req.timeframe)
                found_pattern = False
                pattern_name_for_csv = None

                # Varredura de Canais, Triângulos, Cunhas e Bandeiras nas últimas 60 velas
                ch = cpm.fit_channel(H, L, max(0, len(C) - 60), len(C) - 1, p=cal_p)

                if is_lta:
                    db = cpm.double_bottoms(H, L, C, p=cal_p)
                    tb = cpm.triple_bottoms(H, L, C, p=cal_p)
                    hs = cpm.head_shoulders_bottoms(H, L, C, p=cal_p)
                    barr = cpm.bump_and_run_reversal(H, L, C, p=cal_p, is_bottom=True)

                    if db:
                        confluence_score += 25; signals.append(f"Geometria: Fundo Duplo ({db[-1]['kind']})"); found_pattern = True; pattern_name_for_csv = "Double Bottoms"
                    elif tb:
                        confluence_score += 25; signals.append("Geometria: Fundo Triplo"); found_pattern = True; pattern_name_for_csv = "Triple Bottoms"
                    elif hs:
                        confluence_score += 25; signals.append("Geometria: OCO Invertido (Alta)"); found_pattern = True; pattern_name_for_csv = "Head-and-Shoulders Bottoms"
                    elif barr:
                        confluence_score += 25; signals.append("Geometria: BARR Bottom"); found_pattern = True; pattern_name_for_csv = "Bump-and-Run Reversal Bottom"
                    elif ch and ch.label in ("flag", "pennant", "triangle_ascending", "wedge_falling", "rectangle"):
                        confluence_score += 20; signals.append(f"Geometria: {ch.label.upper()} de Alta"); found_pattern = True
                        pattern_name_for_csv = "Flags" if ch.label == "flag" else ("Triangles, Ascending" if "triangle" in ch.label else "Wedges, Falling")
                else:
                    dt = cpm.top_version(cpm.double_bottoms, H, L, C, p=cal_p)
                    tt = cpm.top_version(cpm.triple_bottoms, H, L, C, p=cal_p)
                    hst = cpm.top_version(cpm.head_shoulders_bottoms, H, L, C, p=cal_p)
                    pt = cpm.pipe_top(O, H, L, C, lookback=30)
                    barr_top = cpm.bump_and_run_reversal(H, L, C, p=cal_p, is_bottom=False)

                    if dt:
                        confluence_score += 25; signals.append(f"Geometria: Topo Duplo ({dt[-1]['kind']})"); found_pattern = True; pattern_name_for_csv = "Double Tops"
                    elif tt:
                        confluence_score += 25; signals.append("Geometria: Topo Triplo"); found_pattern = True; pattern_name_for_csv = "Triple Tops"
                    elif hst:
                        confluence_score += 25; signals.append("Geometria: OCO de Topo (Queda)"); found_pattern = True; pattern_name_for_csv = "Head-and-Shoulders Tops"
                    elif barr_top:
                        confluence_score += 25; signals.append("Geometria: BARR Top"); found_pattern = True; pattern_name_for_csv = "Bump-and-Run Reversal Top"
                    elif pt:
                        confluence_score += 20; signals.append("Geometria: Pipe Top (Espiga Dupla)"); found_pattern = True; pattern_name_for_csv = "Pipe Tops"
                    elif ch and ch.label in ("flag", "pennant", "triangle_descending", "wedge_rising", "broadening_wedge_desc"):
                        confluence_score += 20; signals.append(f"Geometria: {ch.label.upper()} de Queda"); found_pattern = True
                        pattern_name_for_csv = "Triangles, Descending" if "triangle" in ch.label else "Wedges, Rising"

                if found_pattern:
                    knowledge_applied = True

                if found_pattern and pattern_name_for_csv:
                    try:
                        df_stats = pd.read_csv("pattern_stats.csv")
                        t_market = 'Bull' if is_htf_lta else 'Bear'
                        t_break = 'up' if is_lta else 'down'
                        stats_match = df_stats[df_stats['pattern'].str.contains(pattern_name_for_csv, case=False, na=False)]
                        exact_stats = stats_match[(stats_match['market'] == t_market) & (stats_match['breakout'] == t_break)]

                        if not exact_stats.empty:
                            win_chance = 100.0 - float(exact_stats.iloc[0]['break_even_failure_pct'])
                            signals.append(f"Backtest Bulkowski ({t_market}): ~{win_chance:.0f}% Acerto")
                            if win_chance >= 85:
                                confluence_score += 15
                            elif win_chance >= 70:
                                confluence_score += 10
                    except Exception:
                        pass
            except Exception as e:
                signals.append(f"⚠️ Erro Geometria: {str(e)[:25]}")

        # ======================================================================
        # 3. A 4ª DIMENSÃO: CONFLUÊNCIA FRACTAL MULTI-TIMEFRAME
        # ======================================================================
        fractal_aligned = (is_lta == is_htf_lta)

        if fractal_aligned:
            confluence_score += 15
            trend_str = "LTA (Alta)" if is_htf_lta else "LTB (Baixa)"
            signals.append(f"🌐 Fractal {htf_timeframe} Alinhado em {trend_str} (+15%)")

            if (is_lta and htf_mme20 > htf_mme100 and htf_rsi < 74) or (not is_lta and htf_mme20 < htf_mme100 and htf_rsi > 26):
                confluence_score += 5
                signals.append(f"⚡ Fluxo Macro {htf_timeframe} Limpo (+5%)")
        else:
            confluence_score -= 20
            htf_dir = "ALTA (LTA)" if is_htf_lta else "QUEDA (LTB)"
            signals.append(f"🛑 Divergência: Macro {htf_timeframe} está em {htf_dir} (-20%)")

        # ======================================================================
        # 4. FILTRO L2 ADAPTATIVO & TRAVA DE SEGURANÇA INSTITUCIONAL
        # ======================================================================
        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        max_l2_allowed = L2_NOISE_THRESHOLD.get(req.timeframe, 0.025)
        is_stable = l2_div < max_l2_allowed

        if not is_stable:
            confluence_score *= 0.65
            signals.append("⚠️ Volatilidade Esticada (Aguardar Pullback)")

        # Trava Matemática: Nunca permite >= 80% se o Timeframe Macro estiver contra
        if not fractal_aligned and confluence_score > 65.0:
            confluence_score = 65.0
            signals.append(f"🔒 Trava Fractal: Limitado a 65% (Contra {htf_timeframe})")

        confluence_score = max(0.0, min(round(confluence_score, 2), 100.0))

        if confluence_score >= 80:
            verdict = f"FORÇA INSTITUCIONAL ({req.timeframe} + {htf_timeframe})"
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
                "market_state": "ESTÁVEL" if is_stable else "ESTI-CADO",
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
