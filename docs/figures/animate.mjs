/** Render a deterministic 5–6 second leaderboard insertion MP4. */
import {readFileSync} from 'node:fs';
import {mkdtemp, rename, rm} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {Resvg} from '@resvg/resvg-js';
import {fileURLToPath} from 'node:url';
import {dirname, extname, join, resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {names, colors} from './identity.mjs';

export function animationData(data, setting, seconds) {
  if (!Number.isFinite(seconds) || seconds < 5 || seconds > 6) {
    throw new Error('Duration must be between 5 and 6 seconds');
  }
  if (!Array.isArray(data.series) || !data.series.length) throw new Error('No published settings');
  const ids = new Set();
  const rows = data.series.map((row, index) => {
    if (ids.has(row.id) || !(row.id in names) || !(row.id in colors) ||
        !Number.isFinite(row.log_auc_pct) || row.log_auc_pct < 0 || row.log_auc_pct > 100 ||
        !Number.isFinite(row.untimed_pct) || !Number.isInteger(row.passes) || row.passes < 1 ||
        (index && row.log_auc_pct > data.series[index - 1].log_auc_pct)) {
      throw new Error(`Invalid published leaderboard row: ${row.id}`);
    }
    ids.add(row.id);
    return {id: row.id, name: names[row.id], color: colors[row.id],
      score: row.log_auc_pct, sd: row.log_auc_sd_pct, untimed: row.untimed_pct,
      passes: row.passes, deployment: row.deployment, rank: index + 1};
  });
  const featured = rows.find(row => row.id === setting);
  if (!featured) throw new Error(`Setting is absent from the published leaderboard: ${setting}`);
  const start = Math.max(0, featured.rank - 4);
  const previous = rows.filter(row => row.id !== setting)
    .map((row, index) => ({...row, previousRank: index + 1})).slice(start, start + 8);
  return {benchmark: data.benchmark, seconds, total: rows.length, featured, previous, start};
}

const clamp = x => Math.max(0, Math.min(1, x));
const smooth = x => { x = clamp(x); return x * x * (3 - 2 * x); };
function settle(t, start, duration, amplitude) {
  const x = (t - start) / duration;
  return x <= 0 || x >= 1 ? 0 : -amplitude * Math.sin(x * Math.PI * 2) ** 3 * Math.exp(-4 * x) * (1 - smooth(x));
}
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const text = (x, y, value, size = 28, fill = '#253e50', weight = 500, anchor = 'start') =>
  `<text x="${x}" y="${y}" fill="${fill}" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}">${escape(value)}</text>`;
const rect = (x, y, width, height, fill, radius = 0) =>
  `<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="${fill}" rx="${radius}"/>`;

export function renderFrame(data, seconds) {
  const t = clamp(seconds / data.seconds);
  const move = smooth((t - .40) / .24);
  const grow = 1 - (1 - clamp((t - .24) / .17)) ** 3;
  const row = (item, y, rank, featured = false) => {
    const isNew = featured && move <= .8;
    return `<g transform="translate(0,${y})" opacity="${featured ? smooth((t - .17) / .13) : 1}">` +
      (featured ? rect(80, -39, 1280, 62, '#eaf6f8', 12) : '') +
      (isNew ? rect(92, -27, 76, 40, '#d4edf1', 8) : '') +
      text(130, 3, isNew ? 'New' : '#' + rank, isNew ? 19 : 25,
        featured ? item.color : '#71818f', 600, 'middle') +
      text(196, 3, item.name, 26, '#253e50', 600) +
      rect(590, -25, item.score * 6.2 * (featured ? grow : 1), 38, item.color, 8) +
      text(1336, 3, item.score.toFixed(2) + '%', 30, '#253e50', 700, 'end') + '</g>';
  };
  const existing = data.previous.map((item, index) => {
    const initial = item.previousRank - 1 - data.start;
    const target = item.rank - 1 - data.start;
    const start = .41 + index * .004;
    const shift = smooth((t - start) / .22);
    const bounce = initial === target ? 0 : settle(t, start + .22, .14, 6);
    return row(item, 278 + 70 * (initial + (target - initial) * shift) + bounce,
      shift > .5 ? item.rank : item.previousRank);
  }).join('');
  const incomingY = 278 + 70 * (8 + (data.featured.rank - 1 - data.start - 8) * move) +
    8 * Math.sin(clamp((t - .34) / .06) * Math.PI) ** 2 + settle(t, .64, .16, 16);
  const axis = [0, 50, 100].map(value => {
    const x = 590 + value * 6.2;
    return `<line x1="${x}" y1="237" x2="${x}" y2="918" stroke="#e8edf1" stroke-width="2"/>` +
      text(x, 957, value + '%', 20, '#71818f', 500, 'middle');
  }).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1080" viewBox="0 0 1440 1080" font-family="Arial, sans-serif">` +
    rect(0, 0, 1440, 1080, '#ffffff') + rect(80, 52, 8, 100, data.featured.color, 4) +
    text(112, 79, 'StreamDecisionBench', 22, '#647687', 700) +
    text(112, 136, 'A new result joins the leaderboard', 46, '#142536', 700) +
    text(80, 207, 'Published single-model measurements', 20, '#647687', 700) +
    text(1350, 207, 'Log-AUC', 20, '#647687', 700, 'end') + axis + existing +
    row(data.featured, incomingY, data.featured.rank, true) +
    text(80, 1020, '0.5–8 s · logarithmic interval weighting · higher is better', 25, '#516271') + '</svg>';
}

export async function renderVideo(payload, output) {
  if (extname(output).toLowerCase() !== '.mp4') throw new Error('Output must have an .mp4 extension');
  const fps = 60;
  const frames = Math.round(payload.seconds * fps);
  const directory = await mkdtemp(join(dirname(output), '.animation-'));
  const temporary = join(directory, 'video.mp4');
  const encoder = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'image2pipe', '-vcodec', 'png', '-framerate', String(fps), '-i', 'pipe:0',
    '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart', temporary], {stdio: ['pipe', 'ignore', 'pipe']});
  let diagnostic = '';
  encoder.stderr.setEncoding('utf8');
  encoder.stderr.on('data', chunk => { diagnostic = (diagnostic + chunk).slice(-8000); });
  const exited = new Promise((resolveExit, reject) => {
    encoder.once('error', reject);
    encoder.once('close', code => code === 0 ? resolveExit() : reject(new Error(`FFmpeg exited ${code}: ${diagnostic}`)));
  });
  async function* images() {
    for (let frame = 0; frame < frames; frame++) {
      yield new Resvg(renderFrame(payload, frame / fps), {font: {defaultFontFamily: 'Arial'}}).render().asPng();
    }
  }
  try {
    await Promise.all([pipeline(Readable.from(images()), encoder.stdin), exited]);
    await rename(temporary, output);
  } finally {
    if (encoder.exitCode === null) encoder.kill();
    await rm(directory, {recursive: true, force: true});
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const {values} = parseArgs({options: {
    setting: {type: 'string', default: 'Perplexity'}, seconds: {type: 'string', default: '6'},
    out: {type: 'string'},
  }});
  const data = JSON.parse(readFileSync(new URL('./data.json', import.meta.url), 'utf8'));
  const output = values.out ? resolve(values.out) : fileURLToPath(new URL('./leaderboard-update.mp4', import.meta.url));
  const payload = animationData(data, values.setting, Number(values.seconds));
  await renderVideo(payload, output);
  console.log(`Wrote ${output}: ${payload.seconds}s at 60 fps, ${payload.featured.name} enters at #${payload.featured.rank}`);
}
