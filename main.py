import sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(
    title="Kronos Quant - Autonomous Trading System",
    version="3.0.0",
    description="Sistema Autónomo com Base de Conhecimento Price Action para WDO e BTC."
)

DB_NAME = "kronos_quant.db"

# ==========================================
# 1. BASE DE DADOS E CONHECIMENTO
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabela de Sinais
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sinais_oraculo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ativo TEXT,
            preco REAL,
            atr REAL,
            tendencia_15m TEXT,
            padrao_detetado TEXT,
            viés TEXT,
            guidance TEXT,
            stop_loss REAL,
            take_profit REAL,
            timestamp TEXT
        )
    ''')

    # Tabela de Conhecimento (Baseada nos seus PDFs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS base_conhecimento_padroes (
            nome_padrao TEXT PRIMARY KEY,
            vies_mercado TEXT,
            taxa_sucesso_bull REAL,
            taxa_sucesso_bear REAL,
            media_ganho REAL,
            taticas_operacionais TEXT
        )
    ''')
    
    # Injetar o conhecimento extraído
    padroes_conhecimento = [
        ("Nenhum", "Depende do Fluxo", 50.0, 50.0, 2.0, "Operar a favor da tendência principal de 15m."),
        ("Cup with Handle", "Bullish Continuation", 95.0, 93.0, 34.0, "Operar breakouts de alta. Padrões altos e com alças curtas performam melhor. Stop abaixo da alça."),
        ("Bump-and-Run Reversal", "Bullish Reversal", 98.0, 99.0, 38.0, "Taxa de falha quase nula (2%). Evitar se houver throwback. Alvo no topo mais alto do padrão."),
        ("Broadening Bottoms", "Reversal", 90.0, 91.0, 27.0, "Padrões largos e altos performam melhor. Entrar com partial decline."),
        ("Ascending Broadening Wedge", "Bearish Reversal", 89.0, 86.0, 17.0, "Foco em downward breakouts. Partial rise avisa a queda 74% das vezes. Stop 0.15 acima do último minor high."),
        ("Broadening Tops", "Bearish Reversal", 85.0, 97.0, 29.0, "Tendência a reverter. Rompimento para baixo em Bear Market tem taxa de falha de apenas 3%.")
    ]
    
    cursor.executemany('''
        INSERT OR IGNORE INTO base_conhecimento_padroes 
        (nome_padrao, vies_mercado, taxa_sucesso_bull, taxa_sucesso_bear, media_ganho, taticas_operacionais)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', padroes_conhecimento)
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. MODELOS DE DADOS
# ==========================================
class AnaliseRequest(BaseModel):
    ativo: str
    preco_atual: float
    atr: float
    tendencia_15m: str
    padrao_grafico: str = "Nenhum"

# ==========================================
# 3. MOTOR DO ORÁCULO
# ==========================================
@app.post("/api/analisar")
def analisar_mercado(dados: AnaliseRequest):
    ativo = dados.ativo.upper()
    tendencia = dados.tendencia_15m.lower()
    
    if dados.atr <= 0 or dados.preco_atual <= 0:
        raise HTTPException(status_code=400, detail="Preço e ATR devem ser maiores que zero.")

    # Consultar o Conhecimento
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM base_conhecimento_padroes WHERE nome_padrao = ?', (dados.padrao_grafico,))
    conhecimento = cursor.fetchone()
    conn.close()

    vies = "Neutro"
    sl = dados.preco_atual
    tp = dados.preco_atual
    acao = "Aguardar"

    if conhecimento and dados.padrao_grafico != "Nenhum":
        taxa_acerto = conhecimento['taxa_sucesso_bull'] if tendencia == "alta" else conhecimento['taxa_sucesso_bear']
        projecao_ganho = conhecimento['media_ganho']
        taticas = conhecimento['taticas_operacionais']
        
        if "Bullish" in conhecimento['vies_mercado'] or (conhecimento['vies_mercado'] == "Reversal" and tendencia == "baixa"):
            vies = f"COMPRA FORTE (Padrão: {dados.padrao_grafico})"
            sl = dados.preco_atual - (dados.atr * 1.5)
            tp = dados.preco_atual * (1 + (projecao_ganho / 100)) # Usa a média de ganho do PDF
            acao = f"COMPRAR. Taxa de Acerto: {taxa_acerto}%. Tática: {taticas}"
        else:
            vies = f"VENDA FORTE (Padrão: {dados.padrao_grafico})"
            sl = dados.preco_atual + (dados.atr * 1.5)
            tp = dados.preco_atual * (1 - (projecao_ganho / 100))
            acao = f"VENDER. Taxa de Acerto: {taxa_acerto}%. Tática: {taticas}"
    else:
        # Padrão básico WDO/BTC
        if tendencia == "alta":
            vies = "Bullish (Fluxo de Alta)"
            sl = dados.preco_atual - (dados.atr * 1.5)
            tp = dados.preco_atual + (dados.atr * 3.0)
            acao = "COMPRAR - Baseado no fluxo direcional e ATR."
        elif tendencia == "baixa":
            vies = "Bearish (Fluxo de Baixa)"
            sl = dados.preco_atual + (dados.atr * 1.5)
            tp = dados.preco_atual - (dados.atr * 3.0)
            acao = "VENDER - Baseado no fluxo direcional e ATR."

    guidance = f"Oráculo detetou: {vies}. Stop Técnico: {sl:.2f}, Alvo Projetado: {tp:.2f}. {acao}"
    timestamp_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Guardar no Histórico
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sinais_oraculo (ativo, preco, atr, tendencia_15m, padrao_detetado, viés, guidance, stop_loss, take_profit, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ativo, dados.preco_atual, dados.atr, dados.tendencia_15m, dados.padrao_grafico, vies, guidance, sl, tp, timestamp_atual))
    conn.commit()
    conn.close()

    return {
        "status": "sucesso",
        "ativo": ativo,
        "vies": vies,
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "actionable_guidance": guidance
    }

@app.get("/api/historico")
def obter_historico():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sinais_oraculo ORDER BY id DESC LIMIT 15')
    linhas = cursor.fetchall()
    conn.close()
    return [dict(linha) for linha in linhas]

# ==========================================
# 4. FRONTEND VISUAL (DASHBOARD)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def dashboard_principal():
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Kronos Quant - Terminal do Oráculo</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-slate-100 font-sans min-h-screen p-6">
        <div class="max-w-6xl mx-auto space-y-6">
            <header class="flex justify-between items-center border-b border-slate-800 pb-4">
                <div>
                    <h1 class="text-3xl font-extrabold tracking-tight text-emerald-400">⚡ KRONOS QUANT</h1>
                    <p class="text-sm text-slate-400">Oráculo Quantitativo de Price Action | WDO & BTC</p>
                </div>
                <div class="bg-emerald-950 border border-emerald-800 px-4 py-2 rounded-lg text-emerald-300 text-sm font-semibold animate-pulse">
                    ● IA Online
                </div>
            </header>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl space-y-4 md:col-span-1">
                    <h2 class="text-xl font-bold text-slate-200">🤖 Solicitar Análise</h2>
                    <div>
                        <label class="block text-xs uppercase text-slate-400 mb-1">Ativo</label>
                        <select id="ativo" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-white">
                            <option value="WDO">Dólar Futuro (WDO)</option>
                            <option value="BTC">Bitcoin (BTC)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs uppercase text-slate-400 mb-1">Preço Atual</label>
                        <input type="number" id="preco" step="any" value="5420.50" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-white">
                    </div>
                    <div>
                        <label class="block text-xs uppercase text-slate-400 mb-1">Volatilidade (ATR)</label>
                        <input type="number" id="atr" step="any" value="12.5" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-white">
                    </div>
                    <div>
                        <label class="block text-xs uppercase text-slate-400 mb-1">Tendência 15m</label>
                        <select id="tendencia" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-white">
                            <option value="alta">Alta (Bullish)</option>
                            <option value="baixa">Baixa (Bearish)</option>
                            <option value="lateral">Lateral / Consolidado</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs uppercase text-amber-400 font-bold mb-1">Padrão Gráfico (PDFs)</label>
                        <select id="padrao_grafico" class="w-full bg-slate-950 border border-amber-700/50 rounded-lg p-2.5 text-amber-300">
                            <option value="Nenhum">Nenhum / Não sei</option>
                            <option value="Cup with Handle">Cup with Handle</option>
                            <option value="Bump-and-Run Reversal">Bump-and-Run Reversal</option>
                            <option value="Broadening Bottoms">Broadening Bottoms</option>
                            <option value="Broadening Tops">Broadening Tops</option>
                            <option value="Ascending Broadening Wedge">Ascending Broadening Wedge</option>
                        </select>
                    </div>
                    <button onclick="enviarAnalise()" class="w-full bg-emerald-600 hover:bg-emerald-500 font-bold py-3 rounded-lg transition duration-200">
                        Consultar Oráculo 🔮
                    </button>
                </div>

                <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl space-y-4 md:col-span-2 flex flex-col justify-between">
                    <div>
                        <h2 class="text-xl font-bold text-slate-200 mb-3">📊 Veredito do Oráculo</h2>
                        <div id="resultado" class="bg-slate-950 border border-slate-800 p-5 rounded-xl text-slate-300 min-h-[160px] flex items-center justify-center text-center text-sm">
                            Aguardando leitura de mercado...
                        </div>
                    </div>
                    <div class="grid grid-cols-3 gap-4 pt-4 border-t border-slate-800 text-center">
                        <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                            <span class="block text-xs text-slate-500">Viés Atual</span>
                            <span id="res-vies" class="font-bold text-emerald-400">-</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                            <span class="block text-xs text-slate-500">Stop Loss</span>
                            <span id="res-sl" class="font-bold text-rose-400">-</span>
                        </div>
                        <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                            <span class="block text-xs text-slate-500">Alvo (Take Profit)</span>
                            <span id="res-tp" class="font-bold text-cyan-400">-</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Histórico -->
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl space-y-4">
                <h2 class="text-xl font-bold text-slate-200">📜 Histórico de Sinais</h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm text-slate-300">
                        <thead class="bg-slate-950 text-slate-400 uppercase text-xs border-b border-slate-800">
                            <tr>
                                <th class="p-3">Data</th>
                                <th class="p-3">Ativo</th>
                                <th class="p-3">Padrão</th>
                                <th class="p-3">Viés</th>
                            </tr>
                        </thead>
                        <tbody id="tabela-historico">
                            <tr><td colspan="4" class="p-4 text-center text-slate-500">Carregando...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <script>
            async function enviarAnalise() {
                const dados = {
                    ativo: document.getElementById('ativo').value,
                    preco_atual: parseFloat(document.getElementById('preco').value),
                    atr: parseFloat(document.getElementById('atr').value),
                    tendencia_15m: document.getElementById('tendencia').value,
                    padrao_grafico: document.getElementById('padrao_grafico').value
                };

                const resDiv = document.getElementById('resultado');
                resDiv.innerHTML = '<span class="text-yellow-400 animate-pulse">Consultando Conhecimento da Enciclopédia...</span>';

                try {
                    const response = await fetch('/api/analisar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(dados)
                    });
                    const json = await response.json();

                    if (response.ok) {
                        resDiv.innerHTML = `<p class="text-left font-medium text-slate-200 leading-relaxed">${json.actionable_guidance}</p>`;
                        document.getElementById('res-vies').innerText = json.vies;
                        document.getElementById('res-sl').innerText = json.stop_loss;
                        document.getElementById('res-tp').innerText = json.take_profit;
                        carregarHistorico();
                    } else {
                        resDiv.innerHTML = `<span class="text-rose-400">Erro: Verifique os valores inseridos.</span>`;
                    }
                } catch (err) {
                    resDiv.innerHTML = `<span class="text-rose-400">Erro de ligação.</span>`;
                }
            }

            async function carregarHistorico() {
                try {
                    const response = await fetch('/api/historico');
                    const historico = await response.json();
                    const tbody = document.getElementById('tabela-historico');
                    
                    if (historico.length === 0) return;

                    tbody.innerHTML = historico.map(h => `
                        <tr class="border-b border-slate-800 hover:bg-slate-950/50">
                            <td class="p-3 text-xs text-slate-400">${h.timestamp}</td>
                            <td class="p-3 font-bold text-emerald-400">${h.ativo}</td>
                            <td class="p-3 text-amber-300 text-xs">${h.padrao_detetado}</td>
                            <td class="p-3 text-xs text-slate-200">${h.viés}</td>
                        </tr>
                    `).join('');
                } catch (e) { console.error("Erro histórico", e); }
            }
            carregarHistorico();
        </script>
    </body>
    </html>
    """
