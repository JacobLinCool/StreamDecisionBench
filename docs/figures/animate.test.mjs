import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
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
  assert.match(final, /translate\(0,354\)" opacity="1"/);
  assert.match(final, /translate\(0,446\)" opacity="1"/);
  assert.match(final, />#1<\/text>/);
  assert.match(final, />63\.37%<\/text>/);
  assert.doesNotMatch(final, />New<\/text>/);
  assert.match(renderFrame(payload, 0), /translate\(0,446\)" opacity="0"/);
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

test('insertion crosses the destination without stopping and settles continuously', () => {
  const payload = animationData(data, 'Perplexity', 6);
  const positions = Array.from({length: 360}, (_, frame) => {
    const groups = [...renderFrame(payload, frame / 60).matchAll(/translate\(0,([\d.e+-]+)\)/g)];
    return Number(groups.at(-1)[1]);
  });
  const steps = positions.slice(1).map((y, i) => y - positions[i]);
  const crossing = positions.findIndex(y => y < 354);
  assert.ok(crossing > 0, 'arrival flows directly into overshoot');
  assert.ok(steps[crossing - 1] < -.001 * (positions[0] - 354), 'arrival retains velocity across the destination');
  assert.ok(Math.min(...positions) > 336, 'overshoot stays restrained');
  assert.ok(Math.max(...steps.slice(1).map((v, i) => Math.abs(v - steps[i]))) < 1,
    'velocity changes continuously across every frame, including landing');
  assert.equal(positions.at(-1), 354);
});


test('every published setting has a full nearby window and enters at its true rank', () => {
  const published = JSON.parse(readFileSync(new URL('./data.json', import.meta.url), 'utf8'));
  for (const item of published.series) {
    const payload = animationData(published, item.id, 6);
    assert.equal(payload.previous.length, 5);
    const ranks = [...payload.previous, payload.featured].map(row => row.rank).sort((a, b) => a - b);
    assert.deepEqual(ranks, Array.from({length: 6}, (_, i) => payload.start + i + 1));
    const targetY = 354 + 92 * (payload.featured.rank - 1 - payload.start);
    const position = t => Number([...renderFrame(payload, t).matchAll(/translate\(0,([\d.e+-]+)\)/g)].at(-1)[1]);
    assert.equal(position(6), targetY);
    assert.ok(position(2) > targetY, 'even the final rank has an entrance');
    assert.ok(position(2) < 880, 'entry stays above the metric footer');
  }
});
