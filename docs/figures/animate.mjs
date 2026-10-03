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
  const start = Math.max(0, Math.min(featured.rank - 3, rows.length - 6));
  const previous = rows.filter(row => row.id !== setting)
    .map((row, index) => ({...row, previousRank: index + 1})).slice(start, start + 5);
  return {benchmark: data.benchmark, seconds, total: rows.length, featured, previous, start};
}

const clamp = x => Math.max(0, Math.min(1, x));
const smooth = x => { x = clamp(x); return x * x * (3 - 2 * x); };
// One continuous trajectory crosses the destination before settling. Its first
// two derivatives vanish at the endpoints; crossing the destination retains velocity.
export function arrivalProgress(t, start, duration) {
  const u = clamp((t - start) / duration);
  return u ** 3 * (10 - 15 * u + 6 * u ** 2) +
    28 * u ** 3 * (1 - u) ** 3 * (u - .2);
}
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const text = (x, y, value, size = 28, fill = '#253e50', weight = 500, anchor = 'start') =>
  `<text x="${x}" y="${y}" fill="${fill}" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}">${escape(value)}</text>`;
const rect = (x, y, width, height, fill, radius = 0) =>
  `<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="${fill}" rx="${radius}"/>`;

export function renderFrame(data, seconds) {
  const t = clamp(seconds / data.seconds);
  const move = arrivalProgress(t, .34, .40);
  const grow = 1 - (1 - clamp((t - .24) / .17)) ** 3;
  const row = (item, y, rank, featured = false, previousRank = rank) => {
    const labelMix = smooth((t - .59) / .06);
    const rankColor = featured ? item.color : '#71818f';
    const oldLabel = featured ? rect(58, -25, 72, 36, '#d4edf1', 8) +
      text(94, 1, 'New', 19, rankColor, 600, 'middle') :
      text(94, 1, '#' + previousRank, 25, rankColor, 600, 'middle');
    return `<g transform="translate(0,${y})" opacity="${featured ? smooth((t - .17) / .13) : 1}">` +
      (featured ? rect(48, -42, 984, 86, '#eaf6f8', 14) : '') +
      (labelMix < 1 ? `<g opacity="${1 - labelMix}" transform="translate(0 ${-30 * labelMix})">${oldLabel}</g>` : '') +
      (labelMix > 0 ? `<g opacity="${labelMix}" transform="translate(0 ${30 * (1 - labelMix)})">` +
        text(94, 1, '#' + rank, 25, rankColor, 600, 'middle') + '</g>' : '') +
      text(152, 0, item.name, 34, '#253e50', 600) +
      rect(152, 21, item.score * 7.5 * (featured ? grow : 1), 8, item.color, 4) +
      text(994, 0, item.score.toFixed(2) + '%', 36, '#253e50', 700, 'end') + '</g>';
  };
  const existing = data.previous.map((item, index) => {
    const initial = item.previousRank - 1 - data.start;
    const target = item.rank - 1 - data.start;
    const shift = arrivalProgress(t, .35 + index * .004, .37);
    return row(item, 354 + 92 * (initial + (target - initial) * shift),
      item.rank, false, item.previousRank);
  }).join('');
  const targetSlot = data.featured.rank - 1 - data.start;
  // Even a new last-place result enters with motion, within the six-row viewport.
  const entrySlot = Math.max(data.previous.length, targetSlot + .35);
  const incomingY = 354 + 92 * (entrySlot + (targetSlot - entrySlot) * move);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080" font-family="Arial, sans-serif">` +
    rect(0, 0, 1080, 1080, '#ffffff') +
    text(64, 133, 'StreamDecisionBench', 76, '#142536', 700) +
    text(68, 193, data.featured.name, 36, data.featured.color, 600) +
    text(64, 277, 'New result', 26, '#516271', 500) +
    `<line x1="64" y1="302" x2="1016" y2="302" stroke="#dae3e8"/>` +
    existing + row(data.featured, incomingY, data.featured.rank, true) +
    `<line x1="64" y1="925" x2="1016" y2="925" stroke="#dae3e8"/>` +
    text(64, 976, 'Log-AUC · higher is better', 26, '#516271') + '</svg>';
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
    out: {type: 'string'}, data: {type: 'string'},
  }});
  const input = values.data ? resolve(values.data) : new URL('./data.json', import.meta.url);
  const data = JSON.parse(readFileSync(input, 'utf8'));
  const output = values.out ? resolve(values.out) : fileURLToPath(new URL('./leaderboard-update.mp4', import.meta.url));
  const payload = animationData(data, values.setting, Number(values.seconds));
  await renderVideo(payload, output);
  console.log(`Wrote ${output}: ${payload.seconds}s at 60 fps, ${payload.featured.name} enters at #${payload.featured.rank}`);
}
