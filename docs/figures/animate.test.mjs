import test from 'node:test';
import assert from 'node:assert/strict';
import {animationData, renderFrame} from './animate.mjs';

const row = (id, score) => ({id, log_auc_pct: score, log_auc_sd_pct: .27,
  untimed_pct: 70, passes: 3, deployment: 'hosted'});
const data = {benchmark: 'StreamDecisionBench', series: [row('Perplexity', 63.37), row('Jev', 58.5)]};

test('animation ranks and displays the published measurement', () => {
  const payload = animationData(data, 'Perplexity', 6);
  assert.equal(payload.featured.rank, 1);
  assert.equal(payload.featured.score, data.series[0].log_auc_pct);
  assert.equal(payload.previous[0].rank, 2);
  assert.equal(payload.previous[0].previousRank, 1);
  const final = renderFrame(payload, 6);
  assert.match(final, /translate\(0,278\)" opacity="1"/);
  assert.match(final, /translate\(0,348\)" opacity="1"/);
  assert.match(final, />#1<\/text>/);
  assert.match(final, />63\.37%<\/text>/);
  assert.doesNotMatch(final, />New<\/text>/);
  assert.match(renderFrame(payload, 0), /translate\(0,838\)" opacity="0"/);
  assert.match(renderFrame(payload, 2), />New<\/text>/);
});

test('another registered setting enters at its measured rank', () => {
  const payload = animationData(data, 'Jev', 5);
  assert.equal(payload.featured.rank, 2);
  assert.equal(payload.previous[0].rank, 1);
});

test('invalid duration, missing setting and reordered scores are rejected', () => {
  for (const seconds of [0, 4.99, 6.01, NaN, Infinity]) {
    assert.throws(() => animationData(data, 'Perplexity', seconds), /Duration/);
  }
  assert.throws(() => animationData(data, 'missing', 6), /absent/);
  assert.throws(() => animationData({...data, series: [...data.series].reverse()}, 'Perplexity', 6), /Invalid/);
});

test('60 fps insertion has bounded frame movement and settles exactly', () => {
  const payload = animationData(data, 'Perplexity', 6);
  const positions = Array.from({length: 360}, (_, frame) => {
    const groups = [...renderFrame(payload, frame / 60).matchAll(/translate\(0,([\d.e+-]+)\)/g)];
    return Number(groups.at(-1)[1]);
  });
  const steps = positions.slice(1).map((y, i) => y - positions[i]);
  assert.ok(Math.max(...steps.map(Math.abs)) < 10, 'travel stays below ten pixels per frame');
  for (const boundary of [.34, .40, .64, .80]) {
    const frame = Math.round(boundary * 360);
    assert.ok(Math.abs(steps[frame] - steps[frame - 1]) < 1, 'phase transitions keep velocity continuous');
  }
  assert.equal(positions.at(-1), 278);
});
