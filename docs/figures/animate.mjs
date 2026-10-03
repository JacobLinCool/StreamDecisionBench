/** Build a self-contained 5–10 second leaderboard insertion animation. */
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {names, colors} from './identity.mjs';

export function animationData(data, setting, seconds) {
  if (!Number.isFinite(seconds) || seconds < 5 || seconds > 10) {
    throw new Error('Duration must be between 5 and 10 seconds');
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

export function renderAnimation(payload) {
  const encoded = JSON.stringify(payload).replaceAll('<', '\\u003c');
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StreamDecisionBench · leaderboard update</title>
<style>
*{box-sizing:border-box}body{margin:0;padding:24px;background:#edf2f6;color:#142536;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1440px;margin:auto}svg{display:block;width:100%;height:auto;border-radius:20px;box-shadow:0 16px 65px #18334d15;background:white}
.controls{display:flex;align-items:center;gap:16px;padding:18px 0}button{border:0;border-radius:10px;background:#0e7490;color:white;padding:10px 20px;font:600 15px inherit;cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid #14b8a6;outline-offset:3px}input{flex:1;accent-color:#0e7490}.time{font-variant-numeric:tabular-nums;min-width:75px}p{margin:0;color:#516271;font-size:14px}
</style></head><body><main>
<svg id="scene" viewBox="0 0 1440 1080" role="img" aria-labelledby="scene-title scene-description">
<title id="scene-title">StreamDecisionBench leaderboard update</title>
<desc id="scene-description">A new measured result enters the published leaderboard, then moves to its ranked position.</desc>
</svg>
<div class="controls"><button id="play" type="button">Pause</button><label for="seek">Timeline</label><input id="seek" type="range" min="0" max="${payload.seconds}" step="0.01" value="0"><span class="time" id="time"></span></div>
<p>Watch the new result enter the board. Replay or scrub to explore the transition.</p>
</main><script>
const data=${encoded};
const svg=document.querySelector('#scene');
const NS='http://www.w3.org/2000/svg';
function node(tag,attrs={},value,parent=svg){const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(value!==undefined)e.textContent=value;parent.append(e);return e;}
function text(x,y,value,size=28,fill='#253e50',weight=500,parent=svg){return node('text',{x,y,fill,'font-size':size,'font-weight':weight,'font-family':'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif'},value,parent);}
function rect(x,y,width,height,fill,radius=0,parent=svg){return node('rect',{x,y,width,height,fill,rx:radius},undefined,parent);}
rect(0,0,1440,1080,'#ffffff');rect(80,52,8,100,data.featured.color,4);
text(112,79,'STREAMDECISIONBENCH',22,'#647687',700);
text(112,136,'A new result joins the leaderboard',46,'#142536',700);
text(80,207,'PUBLISHED SINGLE-MODEL MEASUREMENTS',20,'#647687',700);
text(1350,207,'LOG-AUC',20,'#647687',700).setAttribute('text-anchor','end');
for(const value of [0,50,100]){const x=590+value*6.2;node('line',{x1:x,y1:237,x2:x,y2:918,stroke:'#e8edf1','stroke-width':2});text(x,957,String(value)+'%',20,'#71818f').setAttribute('text-anchor','middle');}
const layer=node('g');
function makeRow(row){const g=node('g',{},undefined,layer);const bg=rect(80,-39,1280,62,'transparent',12,g);const tag=rect(92,-27,76,40,'#d4edf1',8,g);tag.setAttribute('opacity',0);const rank=text(130,3,'',25,'#71818f',600,g);rank.setAttribute('text-anchor','middle');text(196,3,row.name,26,'#253e50',600,g);const bar=rect(590,-25,0,38,row.color,8,g);text(1336,3,row.score.toFixed(2)+'%',30,'#253e50',700,g).setAttribute('text-anchor','end');return {row,g,bg,tag,rank,bar};}
const existing=data.previous.map(makeRow);
const incoming=makeRow(data.featured);
incoming.bg.setAttribute('fill','#eaf6f8');
text(80,1020,'0.5–8 s · logarithmic interval weighting · higher is better',25,'#516271');
const clamp=x=>Math.max(0,Math.min(1,x));const smooth=x=>{x=clamp(x);return x*x*(3-2*x);};
const accelerate=x=>{x=clamp(x);return x<.5?16*x**5:1-(-2*x+2)**5/2;};
function settle(t,start,duration,amplitude){const x=(t-start)/duration;if(x<=0||x>=1)return 0;return -amplitude*Math.sin(x*Math.PI*4)*Math.exp(-5*x)*(1-smooth(x));}
function draw(seconds){const t=seconds/data.seconds;const appear=smooth((t-.17)/.13);const grow=1-(1-clamp((t-.24)/.17))**3;const move=accelerate((t-.43)/.14);
 for(const [index,item] of existing.entries()){const initial=item.row.previousRank-1-data.start;const target=item.row.rank-1-data.start;const start=.44+index*.006;const shift=accelerate((t-start)/.10);const bounce=initial===target?0:settle(t,start+.10,.14,6);item.g.setAttribute('transform','translate(0,'+(278+70*(initial+(target-initial)*shift)+bounce)+')');item.rank.textContent='#'+(shift>.5?item.row.rank:item.row.previousRank);item.bar.setAttribute('width',item.row.score*6.2);}
 const anticipation=12*Math.sin(clamp((t-.37)/.06)*Math.PI);const landing=settle(t,.57,.17,24);const ranked=move>.8;
 incoming.g.setAttribute('opacity',appear);incoming.g.setAttribute('transform','translate(0,'+(278+70*(8+(data.featured.rank-1-data.start-8)*move)+anticipation+landing)+')');incoming.rank.textContent=ranked?'#'+data.featured.rank:'NEW';incoming.rank.setAttribute('font-size',ranked?25:19);incoming.tag.setAttribute('opacity',ranked?0:1);incoming.rank.setAttribute('fill',data.featured.color);incoming.bar.setAttribute('width',data.featured.score*6.2*grow);
 document.querySelector('#seek').value=seconds;document.querySelector('#time').textContent=seconds.toFixed(1)+' / '+data.seconds+' s';}
let running=!matchMedia('(prefers-reduced-motion: reduce)').matches;let current=running?0:data.seconds;let anchor=performance.now()-current*1000;
const play=document.querySelector('#play');function syncButton(){play.textContent=running?'Pause':current>=data.seconds?'Replay':'Play';}
play.addEventListener('click',()=>{if(running){running=false;}else{if(current>=data.seconds)current=0;anchor=performance.now()-current*1000;running=true;}syncButton();});
document.querySelector('#seek').addEventListener('input',e=>{current=Number(e.target.value);running=false;draw(current);syncButton();});
function frame(now){if(running){current=Math.min(data.seconds,(now-anchor)/1000);if(current>=data.seconds){running=false;syncButton();}}draw(current);requestAnimationFrame(frame);}draw(current);syncButton();requestAnimationFrame(frame);
</script></body></html>\n`;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const {values} = parseArgs({options: {
    setting: {type: 'string', default: 'Perplexity'}, seconds: {type: 'string', default: '8'},
    out: {type: 'string'},
  }});
  const data = JSON.parse(readFileSync(new URL('./data.json', import.meta.url), 'utf8'));
  const output = values.out ? resolve(values.out) : fileURLToPath(new URL('./leaderboard-update.html', import.meta.url));
  const payload = animationData(data, values.setting, Number(values.seconds));
  writeFileSync(output, renderAnimation(payload));
  console.log(`Wrote ${output}: ${payload.seconds}s, ${payload.featured.name} enters at #${payload.featured.rank}`);
}
