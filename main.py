from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import asyncio
import time

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
# KRONOS QUANT CORE API // V8.5 (3.000 VELAS | CRIPTO & FOREX | 1m A 1h)
# ==============================================================================

app = FastAPI(title="KRONOS QUANT PRO", version="8.5.0")

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
    "2m": "15m",
    "3m": "15m",
    "5m": "15m",
    "15m": "1h",
    "30m": "2h",
    "45m": "2h",
    "1h": "4h"
}

# Duração em milissegundos dos timeframes nativos para Paginação Paralela
TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000
}

L2_NOISE_THRESHOLD = {
    "1m": 0.010,
    "2m": 0.012,
    "3m": 0.013,
    "5m": 0.015,
    "15m": 0.020,
    "30m": 0.025,
    "45m": 0.028,
    "1h": 0.032
}

FOREX_PAIRS = {"EUR/USD", "GBP/USD", "USD/JPY"}

OHLCV_CACHE = {}
CACHE_TTL_SEC = 8.0

@app.get("/")
async def root_health_check():
    return {
        "status": "KRONOS QUANT CORE ONLINE - MOTOR V8.5 (3.000 VELAS | CRIPTO & FOREX | 1m A 1h)",
        "version": "8.5.0"
    }

def is_forex_symbol(symbol: str) -> bool:
    return symbol.upper() in FOREX_PAIRS or symbol.upper() in {"EUR/USDT", "GBP/USDT"}

def get_price_decimals(symbol: str) -> int:
    s = symbol.upper()
    if "EUR" in s or "GBP" in s:
        return 5
    if "JPY" in s:
        return 3
    return 2

def get_calibrated_params(tf: str, symbol: str):
    """
    Calibra a geometria de Bulkowski de acordo com o Timeframe (1m a 1h)
    e ajusta a escala automaticamente caso o ativo seja Forex (menor amplitude % por vela).
    """
    if not HAS_MATH:
        return None
    fx_scale = 0.35 if is_forex_symbol(symbol) else 1.0

    if tf in ("1m", "2m", "3m"):
        return cpm.Params(
            zigzag_theta=0.0025 * fx_scale, min_pivot_sep=3, horiz_eps=0.003 * fx_scale,
            touch_tol=0.003 * fx_scale, twin_tol=0.010 * fx_scale, twin_min_rise=0.003 * fx_scale,
            twin_sep=(4, 55), hs_shoulder_tol=0.015 * fx_scale
        )
    elif tf == "5m":
        return cpm.Params(
            zigzag_theta=0.0045 * fx_scale, min_pivot_sep=3, horiz_eps=0.005 * fx_scale,
            touch_tol=0.004 * fx_scale, twin_tol=0.012 * fx_scale, twin_min_rise=0.004 * fx_scale,
            twin_sep=(4, 55), hs_shoulder_tol=0.020 * fx_scale
        )
    elif tf == "15m":
        return cpm.Params(
            zigzag_theta=0.0065 * fx_scale, min_pivot_sep=3, horiz_eps=0.006 * fx_scale,
            touch_tol=0.005 * fx_scale, twin_tol=0.015 * fx_scale, twin_min_rise=0.006 * fx_scale,
            twin_sep=(4, 60), hs_shoulder_tol=0.025 * fx_scale
        )
    elif tf in ("30m", "45m"):
        return cpm.Params(
            zigzag_theta=0.0090 * fx_scale, min_pivot_sep=3, horiz_eps=0.008 * fx_scale,
            touch_tol=0.006 * fx_scale, twin_tol=0.018 * fx_scale, twin_min_rise=0.008 * fx_scale,
            twin_sep=(4, 65), hs_shoulder_tol=0.030 * fx_scale
        )
    else:  # 1h ou superior
        return cpm.Params(
            zigzag_theta=0.0120 * fx_scale, min_pivot_sep=3, horiz_eps=0.010 * fx_scale,
            touch_tol=0.008 * fx_scale, twin_tol=0.022 * fx_scale, twin_min_rise=0.010 * fx_scale,
            twin_sep=(4, 70), hs_shoulder_tol=0.035 * fx_scale
        )

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
    recent = df.iloc[-45:]
    recent_highs = recent[recent['is_high_pivot']]['high'].values
    recent_lows = recent[recent['is_low_pivot']]['low'].values
    highest_res = np.max(recent_highs) if len(recent_highs) > 0 else recent['high'].max()
    lowest_sup = np.min(recent_lows) if len(recent_lows) > 0 else recent['low'].min()
    return float(highest_res), float(lowest_sup)

def calculate_volume_profile_poc(df: pd.DataFrame, bins: int = 50):
    typical_price = (df['high'].values + df['low'].values + df['close'].values) / 3.0
    volumes = df['volume'].values
    if np.sum(volumes) <= 0:
        volumes = np.ones_like(typical_price)
    hist, bin_edges = np.histogram(typical_price, bins=bins, weights=volumes)
    max_bin_idx = int(np.argmax(hist))
    return float((bin_edges[max_bin_idx] + bin_edges[max_bin_idx + 1]) / 2.0)

def calculate_l2_divergence(close_series: pd.Series, ma_series: pd.Series) -> float:
    diff_vector = close_series.tail(10).values - ma_series.tail(10).values
    l2_norm = np.linalg.norm(diff_vector)
    return float(l2_norm / np.mean(close_series.tail(10).values))

def resample_ohlcv_bars(bars: list, rule: str) -> list:
    """Agrega velas matematicamente para construir gráficos exatos de 2m, 3m e 45m."""
    df_raw = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_raw['dt'] = pd.to_datetime(df_raw['timestamp'], unit='ms')
    df_raw.set_index('dt', inplace=True)
    df_res = df_raw.resample(rule).agg({
        'timestamp': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    return df_res[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values.tolist()

async def fetch_3000_ohlcv(symbol: str, timeframe: str, target_bars: int = 3000) -> list:
    """
    Roteador Assíncrono de 3.000 Velas:
    - Cripto (BTC, ETH, SOL, PAXG): Paginação em 3 blocos via Binance.US.
    - Forex (EUR/USD, GBP/USD, USD/JPY): Extração via Kraken FX Institucional.
    - Reconstrói matematicamente os tempos de 2m, 3m e 45m.
    """
    now_sec = time.time()
    cache_key = f"{symbol}_{timeframe}_{target_bars}"
    if cache_key in OHLCV_CACHE:
        cached_time, cached_data = OHLCV_CACHE[cache_key]
        if now_sec - cached_time < CACHE_TTL_SEC:
            return cached_data

    # Define o timeframe base nativo na corretora para agregação se for 2m, 3m ou 45m
    if timeframe in ("2m", "3m"):
        base_tf = "1m"
    elif timeframe == "45m":
        base_tf = "15m"
    else:
        base_tf = timeframe

    step_ms = TF_MS.get(base_tf, 1_800_000)
    now_ms = int(now_sec * 1000)

    use_kraken = symbol.upper() in FOREX_PAIRS
    exchange = ccxt_async.kraken({'enableRateLimit': True}) if use_kraken else ccxt_async.binanceus({'enableRateLimit': True})

    try:
        # Kraken usa '1h', '4h', etc., mas para 2h usamos 1h e agregamos se necessário
        fetch_tf = "1h" if (use_kraken and base_tf == "2h") else base_tf

        since_batch_1 = now_ms - (3000 * step_ms)
        since_batch_2 = now_ms - (2000 * step_ms)

        async def safe_fetch(since_val):
            try:
                if since_val is None:
                    return await exchange.fetch_ohlcv(symbol, fetch_tf, limit=1000)
                return await exchange.fetch_ohlcv(symbol, fetch_tf, since=since_val, limit=1000)
            except Exception:
                return []

        if use_kraken:
            # Kraken devolve até 720 velas diretas ou paginadas
            b1, b2 = await asyncio.gather(
                safe_fetch(now_ms - (1400 * step_ms)),
                safe_fetch(None)
            )
            combined = (b1 or []) + (b2 or [])
        else:
            b1, b2, b3 = await asyncio.gather(
                safe_fetch(since_batch_1),
                safe_fetch(since_batch_2),
                safe_fetch(None)
            )
            combined = (b1 or []) + (b2 or []) + (b3 or [])

        await exchange.close()

        if not combined:
            raise ValueError(f"Sem dados retornados para {symbol} ({timeframe}).")

        df_raw = pd.DataFrame(combined, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_raw.drop_duplicates(subset='timestamp', keep='last', inplace=True)
        df_raw.sort_values('timestamp', inplace=True)
        clean_bars = df_raw.values.tolist()[-target_bars:]

        # Agregação exata para 2m, 3m, 45m ou 2h no Kraken
        if timeframe == "2m":
            clean_bars = resample_ohlcv_bars(clean_bars, "2min")
        elif timeframe == "3m":
            clean_bars = resample_ohlcv_bars(clean_bars, "3min")
        elif timeframe == "45m":
            clean_bars = resample_ohlcv_bars(clean_bars, "45min")
        elif use_kraken and base_tf == "2h":
            clean_bars = resample_ohlcv_bars(clean_bars, "2h")

        OHLCV_CACHE[cache_key] = (now_sec, clean_bars)
        return clean_bars
    except Exception as e:
        if hasattr(exchange, 'close'):
            await exchange.close()
        raise e

def enrich_dataframe(bars: list) -> pd.DataFrame:
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['mme5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['mme20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['mme100'] = df['close'].ewm(span=100, adjust=False).mean()
    df['mme200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['atr'] = calculate_atr(df, 14)
    df['volume_sma'] = df['volume'].rolling(window=20).mean()
    return df

@app.post("/api/oracle")
async def process_quant_analysis(req: QuantRequest):
    try:
        htf_timeframe = HTF_MAP.get(req.timeframe, "4h")
        decimals = get_price_decimals(req.symbol)
        fx_mode = is_forex_symbol(req.symbol)

        # ======================================================================
        # 0. EXTRAÇÃO PROFUNDA ASSÍNCRONA (OPERACIONAL + MACRO ÂNCORA)
        # ======================================================================
        bars_ltf, bars_htf = await asyncio.gather(
            fetch_3000_ohlcv(req.symbol, req.timeframe, target_bars=3000),
            fetch_3000_ohlcv(req.symbol, htf_timeframe, target_bars=1500)
        )

        df = enrich_dataframe(bars_ltf)
        df_htf = enrich_dataframe(bars_htf)
        total_candles_loaded = len(df)

        res_zone, sup_zone = detect_structural_pivots(df, window=5)
        poc_macro_price = calculate_volume_profile_poc(df, bins=50)

        # Telemetria Operacional Atual
        last_idx = df.index[-1]
        current_price = float(df.at[last_idx, 'close'])
        current_atr = float(df.at[last_idx, 'atr'])
        current_rsi = float(df.at[last_idx, 'rsi'])
        current_vol = float(df.at[last_idx, 'volume'])
        vol_sma = float(df.at[last_idx, 'volume_sma'])
        mme100_val = float(df.at[last_idx, 'mme100'])
        mme200_val = float(df.at[last_idx, 'mme200'])
        is_lta = current_price > mme100_val

        # Telemetria do Timeframe Âncora Macro
        htf_last_idx = df_htf.index[-1]
        htf_price = float(df_htf.at[htf_last_idx, 'close'])
        htf_mme20 = float(df_htf.at[htf_last_idx, 'mme20'])
        htf_mme100 = float(df_htf.at[htf_last_idx, 'mme100'])
        htf_mme200 = float(df_htf.at[htf_last_idx, 'mme200'])
        htf_rsi = float(df_htf.at[htf_last_idx, 'rsi'])
        is_htf_lta = htf_price > htf_mme100

        # Coordenadas Táticas baseadas em ATR
        dynamic_stop = current_price - (current_atr * 1.5) if is_lta else current_price + (current_atr * 1.5)
        dynamic_target = current_price + (current_atr * 3.0) if is_lta else current_price - (current_atr * 3.0)

        confluence_score = 0.0
        signals = [f"📊 Profundidade: {total_candles_loaded} velas ({req.timeframe})"]
        knowledge_applied = False

        break_tol_up = 0.9997 if fx_mode else 0.999
        break_tol_dn = 1.0003 if fx_mode else 1.001

        # ======================================================================
        # 1. ESTRUTURA PROFUNDA (MME200 + VOLUME PROFILE POC + PRICE ACTION)
        # ======================================================================
        if is_lta:
            if df.at[last_idx, 'mme5'] > df.at[last_idx, 'mme20']:
                confluence_score += 15; signals.append(f"Médias {req.timeframe} Alinhadas (Alta)")
            if mme100_val > mme200_val and current_price > mme200_val:
                confluence_score += 10; signals.append("Acima da MME200 Institucional (+10%)")
            if current_price > poc_macro_price:
                confluence_score += 10; signals.append(f"Acima da POC (${poc_macro_price:.{decimals}f}) (+10%)")
            if 40 <= current_rsi <= 72:
                confluence_score += 10
            if current_price >= res_zone * break_tol_up:
                confluence_score += 15; signals.append("Pressão / Fuga de Resistência")
        else:
            if df.at[last_idx, 'mme5'] < df.at[last_idx, 'mme20']:
                confluence_score += 15; signals.append(f"Médias {req.timeframe} Alinhadas (Baixa)")
            if mme100_val < mme200_val and current_price < mme200_val:
                confluence_score += 10; signals.append("Abaixo da MME200 Institucional (+10%)")
            if current_price < poc_macro_price:
                confluence_score += 10; signals.append(f"Abaixo da POC (${poc_macro_price:.{decimals}f}) (+10%)")
            if 28 <= current_rsi <= 60:
                confluence_score += 10
            if current_price <= sup_zone * break_tol_dn:
                confluence_score += 15; signals.append("Pressão / Quebra de Suporte")

        if vol_sma > 0 and current_vol > (vol_sma * 1.15):
            confluence_score += 10; signals.append("Volume Institucional Ativo")

        H_all, L_all, C_all, O_all = df['high'].values, df['low'].values, df['close'].values, df['open'].values
        H, L, C, O = H_all[-300:], L_all[-300:], C_all[-300:], O_all[-300:]

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
        # 2C. PILAR MACRO-GEOMÉTRICO (BULKOWSKI CALIBRADO P/ CRIPTO E FOREX)
        # ======================================================================
        if HAS_MATH:
            try:
                cal_p = get_calibrated_params(req.timeframe, req.symbol)
                found_pattern = False
                pattern_name_for_csv = None

                ch = cpm.fit_channel(H, L, max(0, len(C) - 80), len(C) - 1, p=cal_p)

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

            if (is_lta and htf_mme20 > htf_mme100 and htf_price > htf_mme200) or (not is_lta and htf_mme20 < htf_mme100 and htf_price < htf_mme200):
                confluence_score += 5
                signals.append(f"⚡ MME200 Macro ({htf_timeframe}) Confirmada (+5%)")
        else:
            confluence_score -= 20
            htf_dir = "ALTA (LTA)" if is_htf_lta else "QUEDA (LTB)"
            signals.append(f"🛑 Divergência: Macro {htf_timeframe} está em {htf_dir} (-20%)")

        # ======================================================================
        # 4. FILTRO L2 ADAPTATIVO & TRAVA DE SEGURANÇA INSTITUCIONAL
        # ======================================================================
        l2_div = calculate_l2_divergence(df['close'], df['mme20'])
        base_l2_max = L2_NOISE_THRESHOLD.get(req.timeframe, 0.025)
        max_l2_allowed = base_l2_max * (0.45 if fx_mode else 1.0)
        is_stable = l2_div < max_l2_allowed

        if not is_stable:
            confluence_score *= 0.65
            signals.append("⚠️ Volatilidade Esticada (Aguardar Pullback)")

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
                "price": round(current_price, decimals),
                "rsi_14": round(current_rsi, 2),
                "atr_14": round(current_atr, decimals),
                "poc_3000": round(poc_macro_price, decimals),
                "candles_analyzed": total_candles_loaded,
                "l2_divergence": round(l2_div, 6),
                "market_state": "ESTÁVEL" if is_stable else "ESTI-CADO",
                "knowledge_applied": knowledge_applied
            },
            "tactical_coordinates": {
                "atr_stop_loss": round(dynamic_stop, decimals),
                "atr_take_profit": round(dynamic_target, decimals)
            },
            "bayesian_oracle": {
                "confluence_score_pct": confluence_score,
                "active_signals": signals,
                "final_verdict": verdict
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
