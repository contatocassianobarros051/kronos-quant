from IPython.display import display, HTML
import html

# Código HTML exato
codigo_html = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>KRONOS QUANT // Confirmação Perfeita (Live WSS)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'JetBrains Mono', monospace; background-color: #04101d; color: #fff; margin: 0; padding: 0; overflow: hidden; height: 700px; }
    .header-bar { background-color: #02080f; border-bottom: 2px solid #00f2fe; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; }
    .badge { background: #ffe600; color: #000; padding: 4px 10px; font-weight: bold; border-radius: 4px; font-size: 14px; text-transform: uppercase; }
    .panel { background-color: rgba(10, 20, 35, 0.9); border: 1px solid #1e3a5f; padding: 15px; border-radius: 8px; }
    #chart-container { width: 100%; height: 600px; position: relative; } 
    .status-pulse { display: inline-block; width: 10px; height: 10px; background-color: #10b981; border-radius: 50%; animation: pulse 1.5s infinite; }
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); } 70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
  </style>
</head>
<body>
  <div class="header-bar flex-wrap gap-4">
    <div class="flex items-center gap-4">
      <span class="badge">CONFIRMAÇÃO PERFEITA</span>
      <h1 class="text-sm md:text-lg font-bold text-cyan-400">KRONOS <span class="text-white">| LIVE</span></h1>
    </div>
    <div class="flex items-center gap-4 text-xs md:text-sm">
      <select id="symbol" class="bg-slate-800 text-white border border-slate-600 rounded px-2 py-1 outline-none">
        <option value="BTCUSDT" selected>BTC/USDT</option>
        <option value="ETHUSDT">ETH/USDT</option>
      </select>
      <select id="timeframe" class="bg-slate-800 text-white border border-slate-600 rounded px-2 py-1 outline-none">
        <option value="5m" selected>5 Minutos</option>
        <option value="15m">15 Min</option>
      </select>
      <div class="flex items-center gap-2">
        <span class="status-pulse"></span> <span id="ws-status" class="text-emerald-400 font-bold">ONLINE</span>
      </div>
    </div>
  </div>

  <div id="chart-container">
    <div class="absolute top-4 right-4 z-10 w-64 panel shadow-2xl shadow-cyan-900/20 text-xs">
      <h3 class="text-cyan-400 font-bold mb-2 border-b border-slate-700 pb-1">DIAGNÓSTICO VETORIAL</h3>
      <div class="space-y-1 text-slate-300">
        <div class="flex justify-between"><span>Preço Atual:</span> <span id="lbl-price" class="text-white font-bold">--</span></div>
        <div class="flex justify-between"><span>Alvo (Target):</span> <span id="lbl-target" class="text-emerald-400 font-bold">--</span></div>
        <div class="flex justify-between"><span>Entrada (Buy):</span> <span id="lbl-entry" class="text-yellow-400 font-bold">--</span></div>
        <div class="flex justify-between"><span>Stop-Loss:</span> <span id="lbl-stop" class="text-red-400 font-bold">--</span></div>
        <div class="mt-2 pt-2 border-t border-slate-700">
          <span class="text-cyan-500 font-bold block mb-1">Ação Algoritmo:</span>
          <span id="lbl-status" class="text-slate-300">Aguardando dados...</span>
        </div>
      </div>
    </div>
  </div>

  <script>
    const chartOptions = {
      layout: { background: { type: 'solid', color: '#051c2a' }, textColor: '#d1d5db' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.05)' }, horzLines: { color: 'rgba(255,255,255,0.05)' } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      timeScale: { timeVisible: true, borderColor: '#1e3a5f' },
      rightPriceScale: { borderColor: '#1e3a5f' }
    };

    const chart = LightweightCharts.createChart(document.getElementById('chart-container'), chartOptions);

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#00ff00', downColor: '#ff0000', 
      borderVisible: false, wickUpColor: '#00ff00', wickDownColor: '#ff0000'
    });

    const resistanceLine = chart.addLineSeries({ color: '#0ea5e9', lineWidth: 6 });
    const supportLine = chart.addLineSeries({ color: '#0ea5e9', lineWidth: 6 });
    const channelTop = chart.addLineSeries({ color: '#ffffff', lineWidth: 1 });
    const channelBot = chart.addLineSeries({ color: '#ffffff', lineWidth: 1 });
    const targetLine = chart.addLineSeries({ color: '#10b981', lineWidth: 2, lineStyle: 2 });
    const entryLine = chart.addLineSeries({ color: '#facc15', lineWidth: 2, lineStyle: 2 });
    const stopLine = chart.addLineSeries({ color: '#ef4444', lineWidth: 2, lineStyle: 2 });

    let binanceWs = null;
    let klinesData = [];
    let currentSymbol = 'BTCUSDT';
    let currentInterval = '5m';

    function analyzeAndDraw(data) {
      if (data.length < 60) return;
      const recent = data.slice(-60);
      const times = recent.map(d => d.time);
      const highs = recent.map(d => d.high);
      const lows = recent.map(d => d.low);
      const currentPrice = recent[recent.length - 1].close;

      const highestHigh = Math.max(...highs);
      const lowestLow = Math.min(...lows);
      const highestIndex = highs.indexOf(highestHigh);
      const lowestIndex = lows.indexOf(lowestLow);

      resistanceLine.setData([
        { time: times[Math.max(0, highestIndex - 5)], value: highestHigh },
        { time: times[Math.min(times.length - 1, highestIndex + 15)], value: highestHigh }
      ]);
      
      supportLine.setData([
        { time: times[Math.max(0, lowestIndex - 10)], value: lowestLow },
        { time: times[times.length - 1], value: lowestLow }
      ]);

      const slope = (lowestLow - highestHigh) / (times.length * 0.8);
      channelTop.setData([
        { time: times[highestIndex], value: highestHigh },
        { time: times[times.length - 5], value: highestHigh + (slope * (times.length - 5 - highestIndex)) }
      ]);
      channelBot.setData([
        { time: times[highestIndex], value: highestHigh - (highestHigh - lowestLow)*0.6 },
        { time: times[times.length - 5], value: (highestHigh - (highestHigh - lowestLow)*0.6) + (slope * (times.length - 5 - highestIndex)) }
      ]);

      const structHeight = highestHigh - lowestLow;
      const entryPrice = lowestLow + (structHeight * 0.35); 
      const stopPrice = lowestLow - (structHeight * 0.05);  
      const targetPrice = entryPrice + structHeight;        

      targetLine.setData([{ time: times[times.length - 10], value: targetPrice }, { time: times[times.length - 1], value: targetPrice }]);
      entryLine.setData([{ time: times[times.length - 10], value: entryPrice }, { time: times[times.length - 1], value: entryPrice }]);
      stopLine.setData([{ time: times[times.length - 10], value: stopPrice }, { time: times[times.length - 1], value: stopPrice }]);

      const markers = [];
      markers.push({ time: times[highestIndex], position: 'aboveBar', color: '#fff', shape: 'arrowDown', text: 'Forte resistência' });
      markers.push({ time: times[lowestIndex], position: 'belowBar', color: '#fff', shape: 'arrowUp', text: 'Múltiplos pavios' });
      
      if (currentPrice > entryPrice) {
        markers.push({ time: times[times.length - 2], position: 'belowBar', color: '#00ff00', shape: 'arrowUp', text: 'Forte fuga' });
        document.getElementById('lbl-status').innerHTML = '<span class="text-emerald-400 font-bold">ROMPIMENTO! Tendência de Alta.</span>';
      } else {
        document.getElementById('lbl-status').innerHTML = 'Testando liquidez. Aguardando fuga...';
      }
      candleSeries.setMarkers(markers);

      document.getElementById('lbl-price').textContent = currentPrice.toFixed(2);
      document.getElementById('lbl-target').textContent = targetPrice.toFixed(2);
      document.getElementById('lbl-entry').textContent = entryPrice.toFixed(2);
      document.getElementById('lbl-stop').textContent = stopPrice.toFixed(2);
    }

    async function loadHistoryAndStartLive() {
      const url = `https://api.binance.com/api/v3/klines?symbol=${currentSymbol}&interval=${currentInterval}&limit=150`;
      try {
        const res = await fetch(url);
        const data = await res.json();
        klinesData = data.map(d => ({
          time: d[0] / 1000, open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
        }));
        candleSeries.setData(klinesData);
        analyzeAndDraw(klinesData);
        connectWebSocket();
      } catch (e) { console.error("Erro Binance API:", e); }
    }

    function connectWebSocket() {
      if (binanceWs) binanceWs.close();
      binanceWs = new WebSocket(`wss://stream.binance.com:9443/ws/${currentSymbol.toLowerCase()}@kline_${currentInterval}`);
      binanceWs.onmessage = (event) => {
        const kline = JSON.parse(event.data).k;
        const candle = { time: kline.t / 1000, open: parseFloat(kline.o), high: parseFloat(kline.h), low: parseFloat(kline.l), close: parseFloat(kline.c) };
        candleSeries.update(candle);
        
        if (klinesData.length > 0 && klinesData[klinesData.length - 1].time === candle.time) {
          klinesData[klinesData.length - 1] = candle;
        } else {
          klinesData.push(candle);
          if (klinesData.length > 200) klinesData.shift();
        }
        analyzeAndDraw(klinesData);
      };
    }

    document.getElementById('symbol').addEventListener('change', (e) => { currentSymbol = e.target.value; loadHistoryAndStartLive(); });
    document.getElementById('timeframe').addEventListener('change', (e) => { currentInterval = e.target.value; loadHistoryAndStartLive(); });

    setTimeout(() => {
      chart.applyOptions({ width: document.getElementById('chart-container').clientWidth, height: document.getElementById('chart-container').clientHeight });
    }, 500);

    loadHistoryAndStartLive();
  </script>
</body>
</html>
"""

# Escapa as aspas duplas do HTML para não quebrar o srcdoc
html_escapado = html.escape(codigo_html)

# Exibe o iframe com tamanho garantido
display(HTML(f'<iframe srcdoc="{html_escapado}" width="100%" height="720px" style="border:none; border-radius: 8px; overflow: hidden;"></iframe>'))
