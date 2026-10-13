# Padrões gráficos em forma matemática

Formalização própria (notação, estrutura e código originais) das regras de identificação, rompimento e medição de desempenho dos padrões gráficos, construída a partir da leitura de *Encyclopedia of Chart Patterns*, 2ª ed. (T. Bulkowski, 2005).

## 0. Como isto respeita os direitos autorais

- **Ideias, regras e fatos não são protegidos; a expressão é.** Aqui estão regras geométricas reescritas como desigualdades, limiares numéricos, fórmulas e algoritmos. Não há texto, figura, exemplo de ação, exemplo de negociação nem tabela reproduzida.
- **Estatísticas:** `pattern_stats.csv` guarda só quatro números por padrão (movimento médio, taxa de falha, mudança após o fim da tendência, ocorrência de throwback/pullback). São resultados empíricos, ou seja, fatos. Cite a fonte se for usá-los publicamente.
- **Sem o texto do livro:** o código e este documento funcionam sozinhos. Todos os limiares são parâmetros (`Params`) que você deve recalibrar com seus próprios dados.

Arquivos:

| Arquivo | Conteúdo |
|---|---|
| `chart_patterns_formal.md` | este documento (definições e fórmulas) |
| `chart_patterns_math.py` | implementação em Python/NumPy dos detectores e métricas |
| `pattern_stats.csv` | priors empíricos (alta/baixa de mercado; 176 linhas) |

---

## 1. Primitivas

Série por barra $t=0,\dots,n-1$: $O_t,H_t,L_t,C_t,V_t$.

**Pivôs (zigzag).** Um pivô alto em $i$ é confirmado quando, depois dele, o preço cai pelo menos $\theta$ em fração: $H_i - L_j \ge \theta |H_i|$ para algum $j>i$ antes de um novo máximo. Simetricamente para pivôs baixos. Os pivôs alternam. Pivôs adjacentes do mesmo lado devem ficar a pelo menos ~5 barras (≈ 1 semana). Padrão: $\theta=5\%$.

**Retas de suporte e resistência.** Sobre os pivôs altos da janela $[s,e]$ e sobre os baixos, ajustam-se por mínimos quadrados:

$$U(t)=a_u t+b_u,\qquad L(t)=a_l t+b_l$$

**Largura e convergência.** $w(t)=U(t)-L(t)$, logo $\dot w = a_u-a_l$. Há divergência se $a_u>a_l$ e convergência se $a_u<a_l$. O ápice de um padrão convergente está em

$$t^*=\frac{b_l-b_u}{a_u-a_l}.$$

**Deriva e "horizontal".** Com $N=e-s+1$ e $\bar p$ o preço médio da janela, a deriva fracionária de uma reta é $\delta(a)=aN/\bar p$. Considera-se a reta horizontal se $|\delta(a)|\le\varepsilon_h$ (padrão 3%). O sinal é $\sigma(a)\in\{-1,0,+1\}$.

**Toque.** O pivô $(i,v)$ toca a reta se $|v-U(i)|\le \tau\bar p$ (padrão $\tau=2\%$). Exige-se um mínimo de toques por lado (em geral 2).

**Gap.** Alta: $L_t>H_{t-1}$. Baixa: $H_t<L_{t-1}$.

**Altura do padrão.** $h=\max H-\min L$ na janela. Altura relativa: $h/P_{bo}$.

---

## 2. Família de duas retas

Toda a família se classifica pelos sinais $(\sigma(a_u),\sigma(a_l))$ e por $\operatorname{sgn}(a_u-a_l)$.

| Condição | Padrão |
|---|---|
| $\sigma_u=\sigma_l=0$ | Retângulo (fundo ou topo conforme a tendência anterior) |
| diverge, $\sigma_u>0,\ \sigma_l<0$ | Alargamento (megafone) — "fundo" se a tendência anterior é de baixa, "topo" se de alta |
| diverge, $\sigma_u>0,\ \sigma_l=0$ | Alargamento em ângulo reto, ascendente |
| diverge, $\sigma_u=0,\ \sigma_l<0$ | Alargamento em ângulo reto, descendente |
| diverge, $\sigma_u>0,\ \sigma_l>0$ | Cunha de alargamento ascendente ($a_u>a_l>0$) |
| diverge, $\sigma_u<0,\ \sigma_l<0$ | Cunha de alargamento descendente ($a_l<a_u<0$) |
| converge, $\sigma_u<0,\ \sigma_l>0$ | Triângulo simétrico |
| converge, $\sigma_u=0,\ \sigma_l>0$ | Triângulo ascendente |
| converge, $\sigma_u<0,\ \sigma_l=0$ | Triângulo descendente |
| converge, $\sigma_u>0,\ \sigma_l>0$ | Cunha ascendente (*rising wedge*) |
| converge, $\sigma_u<0,\ \sigma_l<0$ | Cunha descendente (*falling wedge*) |
| paralelas inclinadas, $N\le 15$ barras, após movimento íngreme | Flag |
| convergentes, $N\le 15$ barras, após movimento íngreme | Pennant |

**Restrições adicionais**

- **Duração mínima:** cunhas e triângulos têm $N\ge 15$ barras (≈ 3 semanas). Abaixo disso são pennants. Cunhas raramente passam de ~4 meses.
- **Toques:** cunhas bem formadas têm ≥ 5 toques (3 + 2). A cunha de alargamento ascendente pede ≥ 3 por lado.
- **"Cruzamento" nos triângulos:** o preço deve atravessar a figura várias vezes, sem grandes áreas vazias. Operacionalmente, $\#\{t:\,L(t)<C_t<U(t)\}/N$ próximo de 1 e alternância frequente de lado.
- **Flag de alta e compacta (*high & tight*):** alta ≥ 90% em < 2 meses, seguida de consolidação.
- **Diamante:** $w(t)$ primeiro cresce e depois decresce. Ajusta-se $w_t\approx q_2t^2+q_1t+q_0$ e exige-se $q_2<0$ com vértice em $s+0.25N<t_v<s+0.75N$. A tendência anterior define "topo" ou "fundo".
- **Volume típico:** decrescente para triângulos, cunhas, flags, pennants e diamantes. Não é pré-requisito.

**Rompimento da família:** primeiro $t>e$ com $C_t>U(t)$ (alta) ou $C_t<L(t)$ (baixa).

**Pistas de direção antes do rompimento**

- *Partial rise / partial decline:* o preço toca uma reta, vai em direção à oposta e não chega perto dela, formando um novo pico (ou vale) distinto. Costuma antecipar rompimento no sentido contrário ao movimento parcial.
- *Internal partial rise / decline:* o mesmo desenho, mas sem rompimento depois; a figura segue se formando.

---

## 3. Padrões definidos por pivôs

### 3.1 Fundo duplo (topo duplo = espelho)

Pivôs $(P_1\downarrow, M\uparrow, P_2\downarrow)$ em $(t_1,t_m,t_2)$:

$$\frac{|P_1-P_2|}{\overline{P}}\le\tau_{tw}\ (\approx 6\%),\qquad \frac{M-\min(P_1,P_2)}{\min(P_1,P_2)}\ge 10\%,\qquad t_2-t_1\in[10,40]\ \text{barras}.$$

- **Nível de confirmação:** $M$, a maior máxima entre os dois vales.
- **Rompimento:** primeiro $t>t_2$ com $C_t>M$, sem nenhum $C<P_2$ antes.
- **Medida:** $T=M+(M-\min(P_1,P_2))$.
- **Adam / Eve:** o vértice é *Adam* (estreito, em V) se a largura $W_i=\#\{j\in[i\pm10]:L_j\le L_i(1+1.5\%)\}<4$, e *Eve* (largo, arredondado) caso contrário. Os 4 subtipos são $\{A,E\}\times\{A,E\}$.
- **Topo duplo:** o mesmo, com os sinais invertidos. A confirmação é a menor mínima entre os picos.

### 3.2 Triplo fundo (triplo topo = espelho)

Três vales com $\dfrac{\max-\min}{\text{média}}\le\tau_{tw}$. O vale central não pode ficar claramente abaixo dos outros (senão é cabeça e ombros). Confirmação: $C>\max H$ de toda a formação. Medida: confirmação $+$ (confirmação $-$ vale médio).

### 3.3 Cabeça e ombros (fundo; topo = espelho)

Pivôs $(S_L\downarrow, T_1\uparrow, H\downarrow, T_2\uparrow, S_R\downarrow)$:

$$H<\min(S_L,S_R),\quad \frac{|S_L-S_R|}{|H|}\le 10\%,\quad \frac{|(t_H-t_{S_L})-(t_{S_R}-t_H)|}{t_{S_R}-t_{S_L}}\le 0.5.$$

- **Linha de pescoço:** $N(t)$, reta pelos topos $T_1,T_2$.
- **Rompimento:** $C_t>N(t)$ com $t>t_{S_R}$. Se o pescoço for ascendente, usa-se a maior máxima entre a cabeça e o ombro direito como nível.
- **Altura:** $h=N(t_H)-H$.
- **Alvo:** $N(t_{bo})+h$.
- **Volume típico:** maior à esquerda do que à direita.
- **Versão complexa:** múltiplos ombros e/ou duas cabeças, com a mesma simetria em torno do centro. O pescoço liga o menor vale esquerdo ao menor vale direito.

### 3.4 Três picos descendentes / três vales ascendentes

Três picos $A_1>A_2>A_3$ de aparência semelhante (largos com largos), após tendência de alta. Rompimento: fechamento abaixo da menor mínima da formação. Três vales ascendentes é o espelho.

---

## 4. Gaps, ilhas e espigas

**Ilha de topo.** Há $t_1<t_2$ com gap de alta em $t_1$ e gap de baixa em $t_2$, e os intervalos dos gaps se intersectam:

$$[H_{t_1-1},L_{t_1}]\cap[H_{t_2},L_{t_2-1}]\neq\emptyset.$$

O rompimento é o dia do segundo gap. Pode durar de 1 dia a vários meses.

**Ilha longa.** Os dois gaps não ficam no mesmo nível, ambos têm largura relevante, e o intervalo entre eles é < ~4 meses.

**Espiga semanal.** Pavio superior: $u_k=H_k-\max(O_k,C_k)$. Pavio inferior: $d_k=\min(O_k,C_k)-L_k$.

- **Pipe (topo):** duas semanas adjacentes $k,k+1$ com $u_k,u_{k+1}\ge Q_{0.75}(u_{k-52:k})$, sobreposição de faixas $\ge 50\%$ e $|H_k-H_{k+1}|/H_k$ pequeno. Confirmação: $C<\min(L_k,L_{k+1})$.
- **Horn (topo):** duas espigas nas semanas $k$ e $k+2$, com a semana central de máxima bem menor. Confirmação: $C<\min L_{k:k+2}$.
- **Fundos:** espelho.

---

## 5. Padrões de pernas e curvos

**Movimento medido (alta).** Com início $S$, topo da 1ª perna $A$ e fundo corretivo $B$:

$$r=\frac{A-B}{A-S}\in[0.38,0.62],\ r<0.8,\qquad T=B+(A-S).$$

A baixa é o espelho. A 2ª perna tende a replicar a 1ª.

**Copa com alça (*cup with handle*).** Com bordas $R_L,R_R$, fundo da copa $c$ e fundo da alça $g$:

$$\frac{|R_L-R_R|}{\max(R_L,R_R)}<6\%,\quad g>c,\quad \text{retração da alça}=\frac{R_R-g}{R_R-c}.$$

- Subida anterior ≥ 30%.
- Copa de 7 a 65 semanas, em forma de U.
- Alça de pelo menos 1 semana.
- Rompimento: $C>R_R$.
- A versão invertida é o espelho.

**Bump-and-run.** Usa escala aritmética. Há uma linha de tendência inclinada (≈ 30°–45°).

- Altura do *lead-in* $h_1$: medida na 1ª quarta parte da formação.
- Altura da protuberância: $h_b\ge 2h_1$.
- Duração do lead-in ≥ ~1 mês.
- Rompimento: fechamento além da linha de tendência.

**Arredondado (fundo; topo = espelho).** Ajuste parabólico $C_t\approx\alpha t^2+\beta t+\gamma$:

- Fundo: $\alpha>0$.
- Vértice em $0.25<t_v/N<0.75$.
- $R^2$ alto.
- Pontas parecidas (diferença média ~3%).
- Rompimento: fechamento acima da borda direita.

**Scallop (formato de J).** Métricas de proporção:

- Retração $=\dfrac{E-X}{E-S}$, com $S$ início, $E$ extremo e $X$ fim.
- Razão do bojo $=|E-S|/|\text{movimento seguinte}|$.
- Retrações típicas: ≈ 50% (ascendente invertida), ≈ 60% (descendente).

---

## 6. Padrões de evento

Seja $a$ o dia do anúncio. A faixa $R_a=H_a-L_a$ deve exceder a média das últimas ~21 faixas, ou haver gap nesse dia (ou no seguinte).

- **Rompimento de alta:** $C_t>H_a$.
- **Rompimento de baixa:** $C_t<L_a$.
- **Direção por tipo:**
  - Resultado ruim, vendas ruins, rebaixamento: baixa.
  - Resultado bom, vendas boas, elevação: alta.
  - Aprovação de medicamento: ambas.
- **Volume:** esperado alto no dia do anúncio.
- **Dead-cat bounce:** queda inicial de 25–40% (até ~70%), recuperação de 15–35% e nova queda de 15–30%.

---

## 7. Nível de rompimento por padrão (resumo)

| Padrão | Rompimento |
|---|---|
| Alargamentos, triângulos, cunhas, retângulos, flags, pennants, diamantes | Fechamento fora da reta |
| Fundos duplos / triplos | $C>$ maior máxima entre os fundos / da formação |
| Topos duplos / triplos | $C<$ menor mínima entre os topos / da formação |
| Cabeça e ombros | $C$ além da linha de pescoço |
| Horn / pipe / 3 picos / 3 vales | $C$ além do extremo da formação |
| Copa com alça | $C>R_R$ |
| Ilhas | Dia do 2º gap |

---

## 8. Metodologia de medição (como avaliar qualquer rompimento)

**Preço de rompimento.** $P_{bo}=L_{t_b}$ para rompimento de alta e $P_{bo}=H_{t_b}$ para baixa, onde $t_b$ é o dia do fechamento fora da formação.

**Extremo final (*ultimate*).** Para alta, com máxima corrente $M_t=\max_{t_b\le j\le t}H_j$:

$$t^{ult}=\arg\max H_j,\ \text{até o 1º } t:\ C_t\le(1-20\%)M_t\ \ \text{ou}\ \ C_t<\text{mínima da formação}.$$

A baixa é simétrica. Se a série acabou antes disso, usa-se o extremo até o fim dos dados.

**Movimento do padrão.**

$$\text{ARD}=\frac{\pm(H^{ult}-P_{bo})}{P_{bo}}.$$

Ele mede a operação perfeita: compra no rompimento e vende exatamente no topo. É um teto, não um retorno realista.

**Taxa de falha.** $F(x)=P(\text{ARD}<x)$. A falha *break-even* é $F(5\%)$. Estima-se a curva em $x=5\%,10\%,\dots,50\%$.

**Throwback / pullback.** Existe $t\in(t_b,t_b+30]$ em que o preço volta a $P_{bo}(1\pm0.5\%)$ depois de uma barra totalmente afastada do nível (o "espaço branco").

**Alcance do alvo.** Alvo $T=P_{bo}\pm h$ (altura somada ou subtraída). Mede-se $\Pr[\max H\ge T]$ até o extremo final.

**Mudança após o fim da tendência.** Variação do extremo final até o novo extremo oposto (também com a regra dos 20%).

**Início da tendência.** Andando para trás a partir do início da formação, é a máxima (ou mínima) antes de um fechamento 20% ou mais no sentido oposto.

**Classificação de tamanho.**

- Alto / baixo: $h/P_{bo}$ comparado à mediana.
- Largo / estreito: duração $N$ comparada à mediana.

**Volume.**

- Tendência: sinal da inclinação da regressão linear de $V$ de $s$ a $e$.
- Forma: ajusta-se $\tilde V=V/\bar V$ ao polinômio $q_2\tau^2+q_1\tau+q_0$ com $\tau\in[-1,1]$. $q_2>0$ é "U", $q_2<0$ é "domo", variação pequena é "plano", o resto é "outro".
- Rompimento pesado: $V_{t_b}/\overline{V}_{t_b-30:t_b}>1$.

**Mercado de alta × baixa.** A série de priors separa os dois regimes. Para regime próprio, use um índice de referência, por exemplo queda > 20% em relação à máxima.

---

## 9. Priors empíricos (`pattern_stats.csv`)

Colunas: `kind, market, pattern, breakout, avg_move_pct, break_even_failure_pct, change_after_trend_end_pct, throwback_pullback_pct, note`.

Uso: `prior(load_priors("pattern_stats.csv"), "Head-and-Shoulders Tops", "down", "Bull")`.

Ressalvas que mudam a leitura dos números:

1. `avg_move_pct` é o ARD da operação perfeita (seção 8). Não é retorno esperado, não inclui custos, e um sistema real ficará abaixo.
2. Flags e pennants (linhas com `note`) foram medidos de outro modo, então não são comparáveis aos demais.
3. Padrões com poucas amostras no mercado de baixa têm números instáveis.
4. Os valores são médias históricas de ações dos EUA, com a metodologia do autor. Reproduzir exige seguir a seção 8 à risca.

---

## 10. Limitações e próximos passos

- **Fidelidade geométrica:** os limiares (Adam/Eve, simetria de OCO, razão de sobreposição de pipe) são interpretações *minhas* das descrições qualitativas. Valide com dados rotulados.
- **Sensibilidade ao zigzag:** $\theta$ e a separação mínima dos pivôs mudam muito o que é detectado. Varra $\theta\in[3\%,8\%]$.
- **Padrões sem detector completo:** scallops, bump-and-run, arredondados e copa com alça têm *validadores* (dadas as âncoras), mas não busca automática.
- **Backtest:** use a seção 8 como protocolo e compare seus ARD e taxas de falha com o CSV.
- **Teste feito:** o classificador de duas retas acertou 11/11 tipos em dados sintéticos; fundo/topo duplo, triplo fundo, cabeça e ombros e ilha foram detectados em séries construídas. Não houve validação com dados reais de mercado.
