/** Render the README figures with Apache ECharts' SVG server renderer. */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import * as echarts from 'echarts';

const directory = new URL('./', import.meta.url);
const root = new URL('../../', directory);
const data = JSON.parse(readFileSync(new URL('data.json', directory), 'utf8'));
const FONT = 'Arial, Helvetica, sans-serif';
const INK = '#15253B';
const MUTED = '#627187';
const GRID = '#E8EDF4';
const WIDTH = 1240;
const HEIGHT = Math.max(950, 340 + data.series.length * 36);

const names = {
  Jev: 'Jev', TerraNone: 'GPT-5.6-Terra · none', Terra: 'GPT-5.6-Terra · low',
  Luna: 'GPT-5.6-Luna · low', Astra: 'GPT-6-Astra · low', LunaNone: 'GPT-5.6-Luna · none',
  Clef: 'Cloudflare Clef', ClefFlash: 'Cloudflare Clef Flash',
  Winnow12B: 'Winnow-12B', WinnowE4B: 'Winnow-E4B',
  DJev: 'DJev / DiffusionGemma', Kev: 'Kev-4B', KevNine: 'Kev-9B', KevTwentySeven: 'Kev-27B', QwenLogits: 'Qwen3.5-4B · direct logits',
  Nimble: 'Bespoke Nimble-9B', LayaTyped: 'Laya · typed decisions',
  LayaEnglish: 'Laya · English', LayaMultilingual: 'Laya · multilingual',
};
const colors = {
  Jev: '#0F766E', TerraNone: '#2563EB', Terra: '#6387CA',
  Luna: '#7C3AED', Astra: '#475569', LunaNone: '#A17CC5',
  Clef: '#E27602', ClefFlash: '#D94A21',
  Winnow12B: '#087F8C', WinnowE4B: '#9564A8',
  DJev: '#B45309', Kev: '#CA8A04', KevNine: '#0891B2', KevTwentySeven: '#DC2626', QwenLogits: '#BE185D', Nimble: '#60813B',
  LayaTyped: '#8A9CAF', LayaEnglish: '#64748B', LayaMultilingual: '#334155',
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const ids = new Set(data.series.map(row => row.id));
const hostedCount = data.series.filter(row => row.deployment === 'hosted').length;
const localCount = data.series.filter(row => row.deployment === 'self-hosted').length;
assert(ids.size === data.series.length && ids.size === Object.keys(data.provenance).length
  && Object.keys(data.provenance).every(id => ids.has(id)),
  'Every verified setting must be rendered exactly once');
assert(hostedCount > 0 && localCount > 0 && hostedCount + localCount === ids.size,
  'Every setting must have a known deployment');
assert(data.intervals_s[0] === 0.5 && data.intervals_s.at(-1) === 8, 'Interval range must be 0.5–8 s');
for (const [path, expected] of Object.entries(data.sources_sha256)) {
  const hash = createHash('sha256').update(readFileSync(new URL(path, root))).digest('hex');
  assert(hash === expected, `Stale chart data: ${path}; rerun prepare.py`);
}
assert(createHash('sha256').update(readFileSync(new URL(data.summary.path, root))).digest('hex')
  === data.summary.sha256, 'The verified analysis changed; rerun prepare.py');
assert(createHash('sha256').update(readFileSync(new URL(data.hosted_summary.path, root))).digest('hex')
  === data.hosted_summary.sha256, 'The hosted repeat analysis changed; rerun prepare.py');
for (const row of data.series) {
  assert(row.id in names && row.id in colors, `Missing visual identity: ${row.id}`);
  assert(Number.isFinite(row.log_auc_pct) && row.log_auc_pct >= 0 && row.log_auc_pct <= 100,
    `Invalid log-AUC: ${row.id}`);
  assert(row.accuracy_pct.length === data.intervals_s.length
    && row.accuracy_pct.every(value => Number.isFinite(value) && value >= 0 && value <= 100),
    `Invalid curve: ${row.id}`);
}
assert(data.series.every((row, index) => !index || row.log_auc_pct <= data.series[index - 1].log_auc_pct),
  'Leaderboard order must follow descending log-AUC');

function text(x, y, value, size = 16, color = MUTED, weight = 400) {
  return { type: 'text', x, y, silent: true,
    style: { text: value, fontFamily: FONT, fontSize: size, fill: color, fontWeight: weight } };
}

function base(subtitle, description) {
  return {
    animation: false, backgroundColor: '#FFFFFF', textStyle: { fontFamily: FONT, color: INK },
    title: { text: 'StreamDecisionBench', subtext: subtitle, left: 40, top: 31,
      textStyle: { fontSize: 34, fontWeight: 700, color: INK, fontFamily: FONT },
      subtextStyle: { fontSize: 21, color: MUTED, fontFamily: FONT }, itemGap: 13 },
    graphic: [
      { type: 'rect', x: 1, y: 1, silent: true, z: -10,
        shape: { width: WIDTH - 2, height: HEIGHT - 2, r: 18 },
        style: { fill: '#FFFFFF', stroke: '#DCE4EE', lineWidth: 1 } },
      text(43, 121, description, 16),
      text(989, 45, `${hostedCount} CLOUD API`, 14, MUTED, 700),
      text(989, 70, `${localCount} SELF-HOSTED`, 14, MUTED, 700),
    ],
  };
}

function leaderboard() {
  const option = base('Single-model leaderboard', 'Normalized log-AUC over 0.5–8 s  ·  Higher is better');
  option.grid = { left: 373, right: 77, top: 178, bottom: 86 };
  option.xAxis = {
    type: 'value', min: 0, max: 100, interval: 20,
    name: 'Normalized log-AUC (%)', nameLocation: 'middle', nameGap: 44,
    nameTextStyle: { fontSize: 16, color: MUTED },
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { fontSize: 15, color: MUTED, margin: 14 },
    splitLine: { lineStyle: { color: GRID } },
  };
  option.yAxis = {
    type: 'category', inverse: true, data: data.series.map(row => row.id),
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: {
      margin: 330, interval: 0, align: 'left',
      formatter: (id, index) => {
        const row = data.series[index];
        const tag = row.deployment === 'hosted' ? 'api' : 'ow';
        return `{rank|${String(index + 1).padStart(2, '0')}}  {model|${names[id]}}  {${tag}|${tag === 'api' ? 'API' : 'OW'}}`;
      },
      rich: {
        rank: { width: 22, color: '#91A0B1', fontSize: 14, align: 'left' },
        model: { width: 234, color: INK, fontSize: 16, align: 'left', fontWeight: 500 },
        api: { color: '#2563EB', backgroundColor: '#EEF4FF', borderRadius: 4,
          padding: [4, 5], fontSize: 11, width: 25, align: 'center', fontWeight: 700 },
        ow: { color: '#A45A16', backgroundColor: '#FFF3E6', borderRadius: 4,
          padding: [4, 5], fontSize: 11, width: 25, align: 'center', fontWeight: 700 },
      },
    },
  };
  option.series = [{
    type: 'bar', barWidth: 24, showBackground: true,
    backgroundStyle: { color: '#F3F6FA', borderRadius: 5 },
    data: data.series.map(row => ({ value: row.log_auc_pct,
      itemStyle: { color: colors[row.id], borderRadius: [0, 5, 5, 0] } })),
    label: { show: true, position: 'right', distance: 10, color: INK, fontSize: 17,
      fontWeight: 700, formatter: ({ value }) => value.toFixed(2) },
    silent: true,
  }];
  return option;
}

function intervalCurves() {
  const option = base('Accuracy across update intervals',
    'The curves beneath the leaderboard score  ·  Logarithmic interval weighting from 0.5 to 8 s');
  option.grid = { left: 98, right: 373, top: 179, bottom: 86 };
  option.xAxis = {
    type: 'log', min: 0.5, max: 8, logBase: 2,
    name: 'Time-step interval (s) · logarithmic scale', nameLocation: 'middle', nameGap: 47,
    nameTextStyle: { fontSize: 16, color: MUTED },
    axisLine: { lineStyle: { color: '#CBD5E1' } },
    axisTick: { customValues: [0.5, 1, 2, 4, 8] },
    axisLabel: { customValues: [0.5, 1, 2, 4, 8], fontSize: 15, color: MUTED,
      margin: 14, showMinLabel: true, showMaxLabel: true, formatter: value => String(value) },
    splitLine: { lineStyle: { color: GRID } },
    minorTick: { show: false }, minorSplitLine: { show: false },
  };
  option.yAxis = {
    type: 'value', min: 0, max: 100, interval: 20,
    name: 'In-force accuracy (%)', nameLocation: 'middle', nameGap: 58,
    nameTextStyle: { fontSize: 16, color: MUTED },
    axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { fontSize: 15, color: MUTED, margin: 13 },
    splitLine: { lineStyle: { color: GRID } },
  };
  const symbols = ['circle', 'rect', 'triangle', 'diamond', 'roundRect', 'pin', 'arrow'];
  option.series = data.series.map((row, index) => ({
    name: row.id, type: 'line', smooth: false, showSymbol: false,
    symbol: symbols[index % symbols.length], symbolSize: 7,
    data: data.intervals_s.map((interval, i) => [interval, row.accuracy_pct[i]]),
    itemStyle: { color: colors[row.id] },
    lineStyle: { color: colors[row.id], width: 2.7,
      type: row.deployment === 'hosted' ? 'solid' : 'dashed' },
    silent: true, clip: true,
  }));
  option.graphic.push(text(903, 180, 'CLOUD API  /  SOLID', 14, MUTED, 700));
  const localHeaderTop = 222 + hostedCount * 33;
  option.graphic.push(text(903, localHeaderTop, 'SELF-HOSTED  /  DASHED', 14, MUTED, 700));
  option.legend = [
    { deployment: 'hosted', top: 211 },
    { deployment: 'self-hosted', top: localHeaderTop + 31 },
  ].map(({ deployment, top }) => ({
    data: data.series.filter(row => row.deployment === deployment).map(row => row.id),
    orient: 'vertical', left: 894, top, itemGap: 18, itemWidth: 27, itemHeight: 9,
    textStyle: { color: INK, fontSize: 15, fontFamily: FONT },
    formatter: id => names[id], selectedMode: false,
  }));
  return option;
}

function save(name, option, description) {
  const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: WIDTH, height: HEIGHT });
  try {
    chart.setOption(option);
    let svg = chart.renderToSVGString();
    svg = svg.replace(/<svg\b/, '<svg role="img" aria-labelledby="chart-title chart-description"')
      .replace(/(<svg\b[^>]*>)/,
        `$1\n<title id="chart-title">StreamDecisionBench — ${description}</title>\n`
        + `<desc id="chart-description">${ids.size} single-model settings, ${hostedCount} cloud APIs and ${localCount} self-hosted open-weight settings. `
        + 'Normalized log-AUC over update intervals of 0.5–8 seconds; one pass per hosted setting and means of three passes per self-hosted setting.</desc>');
    assert(!svg.includes('NaN'), `${name}: invalid SVG geometry`);
    writeFileSync(new URL(name, directory), svg + '\n');
    console.log(`Rendered ${fileURLToPath(new URL(name, directory))}`);
  } finally {
    chart.dispose();
  }
}

save('leaderboard.svg', leaderboard(), 'single-model leaderboard');
save('interval-curves.svg', intervalCurves(), 'in-force accuracy across update intervals');
