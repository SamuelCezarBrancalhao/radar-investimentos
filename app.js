'use strict';

/* =====================================================================
   Radar de Investimentos: app do celular
   Lê os arquivos em dados/ (gerados pelo robô) e mostra tudo.
   ===================================================================== */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const E = { mercado: null, analise: null, noticias: null, historico: null, idx: {}, carregadoEm: 0 };

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* ---------- utilidades ---------- */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function urlSegura(u) {
  try { const x = new URL(u); return (x.protocol === 'https:' || x.protocol === 'http:') ? x.href : null; } catch { return null; }
}
const num = (v, f = nf2) => (v == null || Number.isNaN(v)) ? '–' : f.format(v);
const pct = (v, sinal = true, f = nf1) => (v == null) ? '–' : `${sinal && v > 0 ? '+' : ''}${f.format(v)}%`;
const reais = v => (v == null) ? '–' : `R$ ${nf2.format(v)}`;
function compacto(v) {
  if (v == null) return '–';
  if (v >= 1e9) return `R$ ${nf1.format(v / 1e9)} bi`;
  if (v >= 1e6) return `R$ ${nf1.format(v / 1e6)} mi`;
  if (v >= 1e3) return `R$ ${nf0.format(v / 1e3)} mil`;
  return `R$ ${nf0.format(v)}`;
}
const classeVar = v => v == null ? '' : v > 0 ? 'alta' : v < 0 ? 'queda' : '';
function quando(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const min = Math.round((Date.now() - d.getTime()) / 60000);
  if (min < 1) return 'agora';
  if (min < 60) return `há ${min} min`;
  if (min < 24 * 60) return `há ${Math.round(min / 60)} h`;
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}
function horaBr(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
const guardar = (k, v) => { try { localStorage.setItem('radar:' + k, v); } catch { /* sem armazenamento */ } };
const lembrar = (k, padrao) => { try { return localStorage.getItem('radar:' + k) ?? padrao; } catch { return padrao; } };
const naLista = a => (E.mercado?.minha_lista || []).includes(a.ticker);

/* ---------- textos de ajuda ---------- */
const DESCR = {
  preco: 'Último preço negociado (com atraso).',
  var_7d: 'Quanto o preço mudou na última semana.',
  var_30d: 'Quanto o preço mudou no último mês.',
  var_12m: 'Quanto o preço mudou em 1 ano (sem contar dividendos).',
  min_12m: 'Menor preço dos últimos 12 meses.',
  max_12m: 'Maior preço dos últimos 12 meses.',
  pl: 'Preço ÷ lucro por ação. Em quantos anos o lucro atual "pagaria" a ação. Menor = mais barata, mas lucro pode cair.',
  pvp: 'Preço ÷ patrimônio por ação. Abaixo de 1 = negociada por menos do que vale no balanço.',
  dy: 'Dividendos pagos nos últimos 12 meses ÷ preço. Quanto ela rendeu em proventos.',
  roe: 'Lucro ÷ patrimônio. O quanto a empresa ganha com o dinheiro dos sócios. Acima de 15% é bom.',
  margem_liq: 'De cada R$ 100 vendidos, quanto sobra de lucro.',
  div_liq_pl: 'Dívida líquida ÷ patrimônio. Acima de 2 é dívida alta. Negativo = tem mais caixa que dívida.',
  cresc_5a: 'Crescimento médio da receita por ano nos últimos 5 anos.',
  ev_ebitda: 'Valor da empresa ÷ geração de caixa operacional. Menor = mais barata.',
  liquidez: 'Valor negociado por dia, em média. Mais liquidez = mais fácil comprar e vender.',
  nota: 'Nota de 0 a 10 calculada por fórmula com os indicadores. Não é previsão.',
  vacancia: 'Parte dos imóveis do fundo que está vazia.',
  imoveis: 'Quantidade de imóveis do fundo. Mais imóveis = mais diversificado.',
  cap_rate: 'Aluguel anual ÷ valor dos imóveis.',
  segmento: 'Tipo de fundo: logística, shoppings, lajes, papel (recebíveis)…',
};

const AJUDA = {
  solida: () => {
    const r = E.mercado?.regras?.caiu_mas_solida || {};
    return `<h3>Caíram, mas os números são bons</h3>
      <p>Ações que caíram pelo menos <b>${pct(r.queda_30_dias ?? -12, false)}</b> em 30 dias, mas que continuam com nota de fundamentos de pelo menos <b>${num(r.nota_minima ?? 7, nf1)}</b>.</p>
      <p>Às vezes o mercado exagera numa queda e isso vira oportunidade. Outras vezes a queda é o começo de um problema que ainda não aparece nos números, já que eles vêm do último balanço.</p>
      <p>Use a lista como ponto de partida: abra o ativo, leia as notícias e entenda o motivo antes de decidir qualquer coisa.</p>`;
  },
  fiidesc: () => {
    const r = E.mercado?.regras?.fii_com_desconto || {};
    return `<h3>FIIs com desconto</h3>
      <p>Fundos imobiliários negociados abaixo do valor dos seus imóveis (P/VP até <b>${num(r.pvp_maximo ?? 0.92)}</b>) e que pagaram pelo menos <b>${pct(r.dy_minimo ?? 9, false)}</b> nos últimos 12 meses.</p>
      <p>Desconto pode ser oportunidade, ou um sinal de risco: inquilino deixando de pagar, imóveis vazios, imóveis antigos ou dívidas do fundo.</p>`;
  },
  notas: () => `<h3>Como as notas são calculadas</h3>
    <p>As notas vão de 0 a 10 e usam só os indicadores públicos de cada ativo. Servem para filtrar e comparar, não para prever o preço.</p>
    <dl>
      <dt>Ações (até 10 pontos)</dt>
      <dd>P/L entre 3 e 6: 2 pts (abaixo de 3: 1; até 10: 1,5; até 15: 1; até 25: 0,5) · P/VP até 1: 1,5 (até 2: 1; até 3: 0,5) · Dividendos entre 8% e 15%: 2 (acima de 15%: 1; ≥ 5%: 1,5; ≥ 3%: 1) · ROE ≥ 20%: 2 (≥ 15%: 1,5; ≥ 10%: 1) · Dívida líquida/patrimônio até 0,5: 1,5 (até 1: 1; até 2: 0,5) · Receita crescendo ≥ 10% ao ano: 1 (> 0: 0,5).</dd>
      <dt>Fundos imobiliários (até 10 pontos)</dt>
      <dd>Rendimento entre 8% e 13% ao ano: 3 pts · P/VP entre 0,85 e 1,00: 3 (0,70–0,85 ou 1,00–1,10: 2) · Liquidez ≥ R$ 5 mi/dia: 2 · Vacância até 5%: 2 (fundos de papel ganham 1,5 fixo).</dd>
    </dl>
    <p>P/L muito baixo e rendimentos altos demais perdem pontos e ganham um aviso, porque costumam ser lucros ou pagamentos que não se repetem.</p>`,
  glossario: () => `<h3>O que significa cada indicador</h3><dl>${
    Object.entries({ 'P/L': DESCR.pl, 'P/VP': DESCR.pvp, 'DY (dividend yield)': DESCR.dy, ROE: DESCR.roe,
      'Margem líquida': DESCR.margem_liq, 'Dív. líq./patrimônio': DESCR.div_liq_pl, 'EV/EBITDA': DESCR.ev_ebitda,
      Liquidez: DESCR.liquidez, Vacância: DESCR.vacancia, 'Cap rate': DESCR.cap_rate,
      ETF: 'Fundo que copia um índice (ex.: BOVA11 copia o Ibovespa, IVVB11 copia o S&P 500 dos EUA).',
      BDR: 'Recibo negociado na B3 que representa ações de empresas de fora (ex.: AAPL34 = Apple).' })
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`,
};

function abrirAjuda(chave) {
  const f = AJUDA[chave];
  if (!f) return;
  $('#dialogo-corpo').innerHTML = f();
  $('#dialogo').showModal();
}

/* ---------- carregamento ---------- */
async function obter(nome) {
  try {
    const r = await fetch(`dados/${nome}.json?v=${Date.now()}`, { cache: 'no-store' });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

async function carregar() {
  const btn = $('#atualizar');
  btn.classList.add('girando');
  const [m, a, n] = await Promise.all([obter('mercado'), obter('analise'), obter('noticias')]);
  btn.classList.remove('girando');
  if (!m) {
    $('#atualizado').textContent = 'Ainda não há dados. Rode o robô no GitHub (aba Actions).';
    return;
  }
  E.mercado = m; E.analise = a; E.noticias = n; E.carregadoEm = Date.now();
  E.idx = {};
  for (const cat of ['acoes', 'fiis', 'etfs', 'bdrs']) for (const it of (m[cat] || [])) E.idx[it.ticker] = { ...it, cat };
  $('#atualizado').textContent = `Cotações de ${horaBr(m.atualizado)}${a ? ` · IA ${quando(a.gerado)}` : ''}`;
  renderTudo();
}

async function carregarHistorico() {
  if (E.historico) return E.historico;
  const h = await obter('historico');
  E.historico = h?.semanal || {};
  return E.historico;
}

/* ---------- componentes ---------- */
function logo(a) {
  const u = urlSegura(a.logo);
  const ini = esc(a.ticker.slice(0, 4));
  return `<span class="logo">${u ? `<img src="${esc(u)}" alt="" loading="lazy" onerror="this.replaceWith(document.createTextNode('${ini}'))">` : ini}</span>`;
}
function notaHtml(a) {
  if (a.nota == null) return '';
  return `<span class="nota ${a.nota >= 7 ? 'boa' : ''}">${nf1.format(a.nota)}</span>`;
}
function extraLinha(a) {
  if (a.cat === 'acoes') return `P/L ${num(a.pl, nf1)} · DY ${pct(a.dy, false)} · 30d ${pct(a.var_30d)}`;
  if (a.cat === 'fiis') return `DY ${pct(a.dy, false)} · P/VP ${num(a.pvp)} · 30d ${pct(a.var_30d)}`;
  return `30d ${pct(a.var_30d)} · 12m ${pct(a.var_12m)}`;
}
function linhaAtivo(a, extra) {
  const nome = a.cat === 'fiis' && a.segmento ? `${a.nome} · ${a.segmento}` : a.nome;
  return `<div class="item" data-ticker="${esc(a.ticker)}">
    <button class="linha-ativo" aria-expanded="false">
      ${logo(a)}
      <span class="nome-ativo"><b>${esc(a.ticker)}</b>${notaHtml(a)}${naLista(a) ? '<span class="estrela">★</span>' : ''}
        <small>${esc(nome)}</small><span class="extra">${esc(extra ?? extraLinha(a))}</span></span>
      <span class="direita"><span class="preco">${reais(a.preco)}</span><br><span class="pilula ${classeVar(a.var_dia)}">${pct(a.var_dia)}</span></span>
    </button>
  </div>`;
}
function listaHtml(itens, vazio, extra) {
  if (!itens.length) return `<div class="vazio">${esc(vazio)}</div>`;
  return itens.map(a => linhaAtivo(a, extra?.(a))).join('');
}

function indicadores(a) {
  const base = [
    ['preco', 'Preço', reais(a.preco)], ['var_7d', '7 dias', pct(a.var_7d)], ['var_30d', '30 dias', pct(a.var_30d)],
    ['var_12m', '12 meses', pct(a.var_12m)], ['min_12m', 'Mínima 12m', reais(a.min_12m)], ['max_12m', 'Máxima 12m', reais(a.max_12m)],
  ];
  if (a.cat === 'acoes') return [...base,
    ['pl', 'P/L', num(a.pl, nf1)], ['pvp', 'P/VP', num(a.pvp)], ['dy', 'Dividendos 12m', pct(a.dy, false)],
    ['roe', 'ROE', pct(a.roe, false)], ['margem_liq', 'Margem líquida', pct(a.margem_liq, false)],
    ['div_liq_pl', 'Dív. líq./patrim.', num(a.div_liq_pl)], ['cresc_5a', 'Receita 5 anos', pct(a.cresc_5a)],
    ['ev_ebitda', 'EV/EBITDA', num(a.ev_ebitda, nf1)], ['liquidez', 'Liquidez/dia', compacto(a.liquidez)],
    ['nota', 'Nota', a.nota == null ? '–' : `${nf1.format(a.nota)}/10`]];
  if (a.cat === 'fiis') return [...base,
    ['dy', 'Rendimento 12m', pct(a.dy, false)], ['pvp', 'P/VP', num(a.pvp)], ['vacancia', 'Vacância', pct(a.vacancia, false)],
    ['imoveis', 'Imóveis', a.imoveis ? nf0.format(a.imoveis) : '–'], ['cap_rate', 'Cap rate', pct(a.cap_rate, false)],
    ['liquidez', 'Liquidez/dia', compacto(a.liquidez)], ['nota', 'Nota', a.nota == null ? '–' : `${nf1.format(a.nota)}/10`]];
  return [...base, ['liquidez', 'Liquidez/dia', compacto(a.liquidez)]];
}

function grafico(serie, a) {
  if (!serie || serie.length < 3) return '';
  const w = 300, h = 70, p = 4;
  const vals = serie.filter(v => v != null);
  const min = Math.min(...vals), max = Math.max(...vals);
  const x = i => p + (i * (w - 2 * p)) / (serie.length - 1);
  const y = v => h - p - ((v - min) / (max - min || 1)) * (h - 2 * p);
  const pts = serie.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean).join(' ');
  const cor = (vals[vals.length - 1] >= vals[0]) ? 'var(--alta)' : 'var(--queda)';
  return `<div class="grafico"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Preço semanal de ${esc(a.ticker)} em 12 meses">
    <polyline points="${pts}" fill="none" stroke="${cor}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>
    <div class="legenda"><span>12 meses atrás</span><span>preço semanal</span><span>hoje</span></div></div>`;
}

function linkStatusInvest(a) {
  const tipo = { acoes: 'acoes', fiis: 'fundos-imobiliarios', etfs: 'etfs', bdrs: 'bdrs' }[a.cat];
  return `https://statusinvest.com.br/${tipo}/${a.ticker.toLowerCase()}`;
}

async function detalhe(a) {
  const ind = indicadores(a).map(([k, r, v]) => `<div class="ind"><div class="r">${esc(r)}</div><div class="v">${v}</div><div class="d">${esc(DESCR[k] || '')}</div></div>`).join('');
  const avisos = (a.avisos || []).length ? `<ul class="avisos">${a.avisos.map(t => `<li>⚠️ ${esc(t)}</li>`).join('')}</ul>` : '';
  const poss = (E.analise?.possibilidades || []).filter(p => p.ativo === a.ticker);
  const possHtml = poss.map(p => `<p><b>${p.direcao === 'queda' ? '📉' : p.direcao === 'alta' ? '📈' : '❔'} ${esc(p.titulo)}</b> <span class="meta">(chance ${esc(NOME_CHANCE[p.chance] || p.chance)})</span></p>`).join('');
  const hist = await carregarHistorico();
  const busca = encodeURIComponent(`${a.ticker} ${a.nome}`);
  return `<div class="detalhe">
    ${possHtml ? `<div class="cartao" style="margin:0 0 10px">${possHtml}</div>` : ''}
    <div class="grade">${ind}</div>
    ${avisos}
    ${grafico(hist[a.ticker], a)}
    <div class="acoes-detalhe">
      <button type="button" data-explicar>O que significa?</button>
      <a href="https://news.google.com/search?q=${busca}&hl=pt-BR&gl=BR&ceid=BR:pt-419" target="_blank" rel="noopener">Notícias</a>
      <a href="${linkStatusInvest(a)}" target="_blank" rel="noopener">Status Invest</a>
    </div>
  </div>`;
}

async function alternar(item) {
  const btn = $('.linha-ativo', item);
  const aberto = $('.detalhe', item);
  if (aberto) { aberto.remove(); btn.setAttribute('aria-expanded', 'false'); return; }
  const a = E.idx[item.dataset.ticker];
  if (!a) return;
  btn.setAttribute('aria-expanded', 'true');
  item.insertAdjacentHTML('beforeend', await detalhe(a));
}

document.addEventListener('click', ev => {
  const ajuda = ev.target.closest('[data-ajuda]');
  if (ajuda) { abrirAjuda(ajuda.dataset.ajuda); return; }
  const exp = ev.target.closest('[data-explicar]');
  if (exp) { exp.closest('.detalhe').classList.toggle('explicar'); return; }
  const linha = ev.target.closest('.linha-ativo');
  if (linha) { alternar(linha.closest('.item')); return; }
  const aba = ev.target.closest('.abas button');
  if (aba) { mostrarVista(aba.dataset.vista); return; }
  const ir = ev.target.closest('[data-ir]');
  if (ir) { mostrarVista(ir.dataset.ir); }
});

/* ---------- INÍCIO ---------- */
function renderInicio() {
  const m = E.mercado.macro || {};
  const blocos = [
    ['Ibovespa', m.ibov ? `${nf0.format(m.ibov.valor)} pts` : '–', m.ibov?.var_dia],
    ['Dólar', m.dolar ? reais(m.dolar.valor) : '–', m.dolar?.var_dia],
    ['Selic', m.selic != null ? `${nf2.format(m.selic)}%` : '–', null, 'ao ano'],
    ['IPCA 12 meses', m.ipca_12m != null ? `${nf2.format(m.ipca_12m)}%` : '–', null, 'inflação'],
  ];
  $('#macro').innerHTML = blocos.map(([r, v, vr, sub]) => `<div class="bloco"><div class="rotulo">${r}</div><div class="valor">${v}</div>
    <div class="var ${classeVar(vr)}" style="color:${vr == null ? 'var(--texto-3)' : vr >= 0 ? 'var(--alta)' : 'var(--queda)'}">${vr == null ? (sub || '') : pct(vr)}</div></div>`).join('');

  const an = E.analise;
  $('#panorama').innerHTML = an ? `<div class="cartao">
      <h3>Panorama da IA <span class="humor ${esc(an.humor_mercado)}">${esc(an.humor_mercado || '')}</span></h3>
      <p>${esc(an.resumo)}</p>
      <p class="meta">Lido de ${E.noticias?.noticias?.length || 'várias'} notícias · ${quando(an.gerado)}</p>
      <button class="btn sec" data-ir="ia">Ver ${an.possibilidades.length} possibilidades</button>
    </div>`
    : `<div class="cartao"><h3>Panorama da IA</h3><p>A análise de notícias com IA ainda não rodou. Veja no guia como colocar a chave da Anthropic (opcional).</p></div>`;

  const lista = (E.mercado.minha_lista || []).map(t => E.idx[t]).filter(Boolean);
  $('#lista-minha').innerHTML = listaHtml(lista, 'Sua lista está vazia. Adicione ativos no config.yaml.');

  const acoes = (E.mercado.acoes || []).filter(a => a.var_dia != null).map(a => E.idx[a.ticker]);
  $('#lista-altas').innerHTML = listaHtml([...acoes].sort((a, b) => b.var_dia - a.var_dia).slice(0, 5), 'Sem dados.');
  $('#lista-quedas').innerHTML = listaHtml([...acoes].sort((a, b) => a.var_dia - b.var_dia).slice(0, 5), 'Sem dados.');

  const rs = E.mercado.regras?.caiu_mas_solida || {};
  const solidas = (E.mercado.acoes || []).map(a => E.idx[a.ticker])
    .filter(a => a.var_30d != null && a.var_30d <= (rs.queda_30_dias ?? -12) && (a.nota ?? 0) >= (rs.nota_minima ?? 7))
    .sort((a, b) => (b.nota - a.nota) || (a.var_30d - b.var_30d)).slice(0, 5);
  $('#lista-solidas').innerHTML = listaHtml(solidas, 'Nenhuma ação no filtro agora.',
    a => `Caiu ${pct(a.var_30d)} em 30d · nota ${num(a.nota, nf1)} · P/L ${num(a.pl, nf1)}`);

  const rf = E.mercado.regras?.fii_com_desconto || {};
  const fiis = (E.mercado.fiis || []).map(a => E.idx[a.ticker])
    .filter(a => a.pvp && a.pvp <= (rf.pvp_maximo ?? 0.92) && (a.dy ?? 0) >= (rf.dy_minimo ?? 9) && (a.nota ?? 0) >= (rf.nota_minima ?? 7))
    .sort((a, b) => (b.nota - a.nota) || (a.pvp - b.pvp)).slice(0, 5);
  $('#lista-fiidesc').innerHTML = listaHtml(fiis, 'Nenhum FII no filtro agora.');
}

/* ---------- IA ---------- */
const NOME_CHANCE = { baixa: 'baixa', media: 'média', alta: 'alta' };
const NOME_PRAZO = { dias: 'próximos dias', semanas: 'próximas semanas', meses: 'próximos meses' };
const NOME_NO_PRECO = { sim: 'O preço provavelmente já reagiu.', talvez: 'O preço pode já ter reagido em parte.', nao: 'O preço ainda não parece ter reagido.', nao_sei: '' };
const FILTROS_IA = [
  ['todas', 'Todas', () => true],
  ['lista', '⭐ Sua lista', p => p.na_minha_lista],
  ['alta', '📈 Possível alta', p => p.direcao === 'alta'],
  ['queda', '📉 Possível queda', p => p.direcao === 'queda'],
  ['forte', 'Chance alta', p => p.chance === 'alta'],
];

function cartaoPossibilidade(p) {
  const alvo = p.ativo ? `<span class="alvo">${esc(p.ativo)}</span> · ${esc(p.nome)}` : `<span class="alvo">${esc(p.nome)}</span>`;
  const mk = p.mercado ? `<p class="meta">Hoje ${pct(p.mercado.var_dia)} · 30 dias ${pct(p.mercado.var_30d)} · ${reais(p.mercado.preco)}${p.mercado.nota != null ? ` · nota ${nf1.format(p.mercado.nota)}` : ''}</p>` : '';
  const fontes = (p.fontes || []).map(f => {
    const u = urlSegura(f.link);
    return u ? `<a href="${esc(u)}" target="_blank" rel="noopener" title="${esc(f.titulo)}">${esc(f.fonte)}</a>` : esc(f.fonte);
  }).join('');
  return `<article class="poss ${esc(p.direcao)}">
    <div class="cab">
      <span class="tag ${esc(p.direcao)}">${p.direcao === 'alta' ? '📈 possível alta' : p.direcao === 'queda' ? '📉 possível queda' : '❔ incerto'}</span>
      <span class="tag ${p.chance === 'alta' ? 'chance-alta' : ''}">chance ${esc(NOME_CHANCE[p.chance] || p.chance)}</span>
      <span class="tag">${esc(NOME_PRAZO[p.prazo] || p.prazo)}</span>
      ${p.na_minha_lista ? '<span class="tag lista">★ sua lista</span>' : ''}
    </div>
    <h3>${esc(p.titulo)}</h3>
    <p class="meta">${alvo}</p>
    <p>${esc(p.explicacao)}</p>
    <p class="contra">⚖️ <b>Contraponto:</b> ${esc(p.contraponto)}</p>
    ${p.o_que_observar ? `<p>👀 <b>O que observar:</b> ${esc(p.o_que_observar)}</p>` : ''}
    ${NOME_NO_PRECO[p.ja_no_preco] ? `<p class="meta">${NOME_NO_PRECO[p.ja_no_preco]}</p>` : ''}
    ${mk}
    <div class="fontes">📰 ${fontes}</div>
  </article>`;
}

function renderIA() {
  const an = E.analise;
  if (!an) {
    $('#ia-cabecalho').innerHTML = `<div class="cartao"><h3>IA ainda não configurada</h3>
      <p>As tabelas e os alertas por regras funcionam sem IA. Para receber possibilidades a partir das notícias, coloque a chave da Anthropic nos segredos do GitHub (veja o guia).</p></div>`;
    $('#chips-ia').innerHTML = ''; $('#ia-lista').innerHTML = '';
    $('#ia-agenda').innerHTML = '<p class="meta">Sem agenda.</p>';
  } else {
    $('#ia-cabecalho').innerHTML = `<div class="cartao"><h3>Panorama <span class="humor ${esc(an.humor_mercado)}">${esc(an.humor_mercado || '')}</span></h3>
      <p>${esc(an.resumo)}</p><p class="meta">Analisado ${quando(an.gerado)} · ${esc(an.modelo || '')} · cada possibilidade cita as notícias de onde veio.</p></div>`;
    const atual = lembrar('filtro-ia', 'todas');
    $('#chips-ia').innerHTML = FILTROS_IA.map(([k, r]) => `<button class="chip ${k === atual ? 'ativo' : ''}" data-filtro-ia="${k}">${r}</button>`).join('');
    const f = (FILTROS_IA.find(x => x[0] === atual) || FILTROS_IA[0])[2];
    const itens = an.possibilidades.filter(f);
    $('#ia-lista').innerHTML = itens.length ? itens.map(cartaoPossibilidade).join('') : '<div class="vazio" style="margin-top:10px">Nenhuma possibilidade neste filtro.</div>';
    $('#ia-agenda').innerHTML = (an.agenda || []).length
      ? an.agenda.map(e => `<div class="agenda-item"><b>${esc(e.quando)}</b><span>${esc(e.evento)}</span></div>`).join('')
      : '<p class="meta">Nenhum evento citado nas notícias.</p>';
  }
  const ns = (E.noticias?.noticias || []).slice(0, 40);
  $('#ia-noticias').innerHTML = ns.length ? ns.map(n => {
    const u = urlSegura(n.link);
    return `<a class="noticia" href="${esc(u || '#')}" target="_blank" rel="noopener">${esc(n.titulo)}<small>${esc(n.fonte)} · ${quando(n.quando)}${n.sobre ? ` · ${esc(n.sobre)}` : ''}</small></a>`;
  }).join('') : '<div class="vazio">Sem notícias coletadas ainda.</div>';
}

document.addEventListener('click', ev => {
  const c = ev.target.closest('[data-filtro-ia]');
  if (c) { guardar('filtro-ia', c.dataset.filtroIa); renderIA(); }
});

/* ---------- TABELAS ---------- */
const desc = k => (a, b) => (b[k] ?? -Infinity) - (a[k] ?? -Infinity);
const asc = k => (a, b) => (a[k] ?? Infinity) - (b[k] ?? Infinity);
const ascPositivo = k => (a, b) => ((a[k] > 0 ? a[k] : Infinity) - (b[k] > 0 ? b[k] : Infinity));

const TABELAS = {
  acoes: {
    fontes: ['acoes'],
    ordens: [['liquidez', 'Mais negociadas', desc('liquidez')], ['nota', 'Maior nota', desc('nota')],
      ['alta', 'Maior alta hoje', desc('var_dia')], ['queda', 'Maior queda hoje', asc('var_dia')],
      ['alta30', 'Maior alta em 30 dias', desc('var_30d')], ['queda30', 'Maior queda em 30 dias', asc('var_30d')],
      ['alta12', 'Maior alta em 12 meses', desc('var_12m')], ['dy', 'Maiores dividendos', desc('dy')],
      ['pl', 'Menor P/L', ascPositivo('pl')], ['pvp', 'Menor P/VP', ascPositivo('pvp')], ['roe', 'Maior ROE', desc('roe')]],
    filtros: [['todas', 'Todas', () => true], ['lista', '⭐ Sua lista', naLista], ['nota', 'Nota ≥ 7', a => a.nota >= 7],
      ['caiu', 'Caiu 10%+ em 30d', a => a.var_30d <= -10], ['div', 'Dividendos ≥ 6%', a => a.dy >= 6],
      ['min', 'Perto da mínima', a => (a.avisos || []).some(t => t.includes('mínima'))],
      ['prej', 'Sem prejuízo', a => a.pl > 0]],
  },
  fiis: {
    fontes: ['fiis'],
    ordens: [['liquidez', 'Mais negociados', desc('liquidez')], ['nota', 'Maior nota', desc('nota')],
      ['dy', 'Maior rendimento', desc('dy')], ['pvp', 'Menor P/VP', ascPositivo('pvp')],
      ['alta', 'Maior alta hoje', desc('var_dia')], ['queda', 'Maior queda hoje', asc('var_dia')],
      ['queda30', 'Maior queda em 30 dias', asc('var_30d')], ['alta12', 'Maior alta em 12 meses', desc('var_12m')]],
    filtros: [['todas', 'Todos', () => true], ['lista', '⭐ Sua lista', naLista], ['nota', 'Nota ≥ 7', a => a.nota >= 7],
      ['desc', 'P/VP abaixo de 1', a => a.pvp > 0 && a.pvp < 1], ['dy', 'Rendimento ≥ 10%', a => a.dy >= 10],
      ['tijolo', 'Com imóveis', a => a.imoveis > 0], ['papel', 'Papel/recebíveis', a => !a.imoveis]],
  },
  outros: {
    fontes: ['etfs', 'bdrs'],
    ordens: [['liquidez', 'Mais negociados', desc('liquidez')], ['alta', 'Maior alta hoje', desc('var_dia')],
      ['queda', 'Maior queda hoje', asc('var_dia')], ['alta30', 'Maior alta em 30 dias', desc('var_30d')],
      ['queda30', 'Maior queda em 30 dias', asc('var_30d')], ['alta12', 'Maior alta em 12 meses', desc('var_12m')]],
    filtros: [['etfs', 'ETFs', a => a.cat === 'etfs'], ['bdrs', 'BDRs (empresas de fora)', a => a.cat === 'bdrs'],
      ['lista', '⭐ Sua lista', naLista]],
  },
};
const POR_PAGINA = 50;
const limites = {};

function renderTabela(chave) {
  const T = TABELAS[chave];
  const sec = $(`#v-${chave}`);
  if (!sec.dataset.montada) {
    sec.innerHTML = `<div class="controles">
        <input class="busca" type="search" placeholder="Buscar por código ou nome" autocomplete="off" autocapitalize="characters">
        <div class="linha-ctrl"><label>Ordenar por</label><select>${T.ordens.map(([k, r]) => `<option value="${k}">${r}</option>`).join('')}</select></div>
        <div class="chips">${T.filtros.map(([k, r]) => `<button class="chip" data-filtro="${k}">${r}</button>`).join('')}</div>
      </div>
      <p class="contagem"></p><div class="lista"></div>
      <button class="btn sec mais" hidden>Mostrar mais</button>`;
    sec.dataset.montada = '1';
    $('select', sec).value = lembrar(`ordem-${chave}`, T.ordens[0][0]);
    $('.busca', sec).addEventListener('input', () => { limites[chave] = POR_PAGINA; renderTabela(chave); });
    $('select', sec).addEventListener('change', e => { guardar(`ordem-${chave}`, e.target.value); limites[chave] = POR_PAGINA; renderTabela(chave); });
    sec.addEventListener('click', e => {
      const c = e.target.closest('[data-filtro]');
      if (c) { guardar(`filtro-${chave}`, c.dataset.filtro); limites[chave] = POR_PAGINA; renderTabela(chave); }
      if (e.target.closest('.mais')) { limites[chave] = (limites[chave] || POR_PAGINA) + POR_PAGINA; renderTabela(chave); }
    });
  }
  const filtroAtual = lembrar(`filtro-${chave}`, T.filtros[0][0]);
  $$('.chip', sec).forEach(c => c.classList.toggle('ativo', c.dataset.filtro === filtroAtual));
  const filtro = (T.filtros.find(f => f[0] === filtroAtual) || T.filtros[0])[2];
  const ordem = (T.ordens.find(o => o[0] === $('select', sec).value) || T.ordens[0])[2];
  const termo = $('.busca', sec).value.trim().toUpperCase();
  let itens = T.fontes.flatMap(c => (E.mercado[c] || []).map(a => E.idx[a.ticker]));
  itens = itens.filter(filtro);
  if (termo) itens = itens.filter(a => a.ticker.includes(termo) || (a.nome || '').toUpperCase().includes(termo) || (a.setor || '').toUpperCase().includes(termo));
  itens.sort(ordem);
  const lim = limites[chave] || POR_PAGINA;
  $('.contagem', sec).textContent = `${itens.length} ${itens.length === 1 ? 'ativo' : 'ativos'} · toque para ver detalhes`;
  $('.lista', sec).innerHTML = listaHtml(itens.slice(0, lim), 'Nada encontrado.');
  $('.mais', sec).hidden = itens.length <= lim;
}

/* ---------- navegação ---------- */
const VISTAS = ['inicio', 'ia', 'acoes', 'fiis', 'outros'];
function mostrarVista(v) {
  if (!VISTAS.includes(v)) v = 'inicio';
  for (const x of VISTAS) $(`#v-${x}`).hidden = x !== v;
  $$('.abas button').forEach(b => b.classList.toggle('ativa', b.dataset.vista === v));
  $('#titulo').textContent = $(`#v-${v}`).dataset.titulo;
  guardar('vista', v);
  if (E.mercado && TABELAS[v]) renderTabela(v);
  window.scrollTo({ top: 0 });
}

function renderTudo() {
  renderInicio();
  renderIA();
  for (const k of Object.keys(TABELAS)) if (!$(`#v-${k}`).hidden) renderTabela(k);
}

$('#atualizar').addEventListener('click', carregar);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && E.carregadoEm && Date.now() - E.carregadoEm > 5 * 60 * 1000) carregar();
});
mostrarVista(lembrar('vista', 'inicio'));
carregar();
