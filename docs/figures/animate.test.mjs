import test from 'node:test';
import assert from 'node:assert/strict';
import {animationData, renderAnimation} from './animate.mjs';

const row = (id, score) => ({id, log_auc_pct: score, log_auc_sd_pct: .27,
  untimed_pct: 70, passes: 3, deployment: 'hosted'});
const data = {benchmark: 'StreamDecisionBench', series: [row('Perplexity', 63.37), row('Jev', 58.5)]};

test('animation ranks and displays the published measurement', () => {
  const payload = animationData(data, 'Perplexity', 8);
  assert.equal(payload.featured.rank, 1);
  assert.equal(payload.featured.score, data.series[0].log_auc_pct);
  assert.equal(payload.previous[0].rank, 2);
  assert.equal(payload.previous[0].previousRank, 1);
  const html = renderAnimation(payload);
  assert.match(html, /requestAnimationFrame/);
  assert.match(html, /prefers-reduced-motion/);
  assert.match(html, /"score":63.37/);
  assert.doesNotMatch(html, /<script[^>]+src=/);
});

test('another registered setting enters at its measured rank', () => {
  const payload = animationData(data, 'Jev', 5);
  assert.equal(payload.featured.rank, 2);
  assert.equal(payload.previous[0].rank, 1);
});

test('invalid duration, missing setting and reordered scores are rejected', () => {
  for (const seconds of [0, 4.99, 10.01, NaN, Infinity]) {
    assert.throws(() => animationData(data, 'Perplexity', seconds), /Duration/);
  }
  assert.throws(() => animationData(data, 'missing', 8), /absent/);
  assert.throws(() => animationData({...data, series: [...data.series].reverse()}, 'Perplexity', 8), /Invalid/);
});
