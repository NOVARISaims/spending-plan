// Dependency-free SVG charts: line (with optional average series and target
// rule) and bars (with optional target rule). Dates on x, values on y.

const NS = 'http://www.w3.org/2000/svg';
const W = 340;
const H = 150;
const PAD = { l: 34, r: 8, t: 10, b: 20 };

function el(name, attrs = {}) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function scale(domainMin, domainMax, rangeMin, rangeMax) {
  const d = domainMax - domainMin || 1;
  return (v) => rangeMin + ((v - domainMin) / d) * (rangeMax - rangeMin);
}

function niceTicks(min, max, n = 4) {
  const span = max - min || 1;
  const step = 10 ** Math.floor(Math.log10(span / n));
  const err = span / n / step;
  const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const s = mult * step;
  const ticks = [];
  for (let v = Math.ceil(min / s) * s; v <= max + 1e-9; v += s) ticks.push(v);
  return ticks;
}

function dateLabel(iso) {
  const d = new Date(iso + 'T12:00:00');
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

function frame(container, yMin, yMax, yFmt) {
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'plot' });
  const y = scale(yMin, yMax, H - PAD.b, PAD.t);
  for (const t of niceTicks(yMin, yMax)) {
    svg.appendChild(el('line', {
      x1: PAD.l, x2: W - PAD.r, y1: y(t), y2: y(t),
      stroke: 'rgba(143,160,191,0.16)', 'stroke-width': 1,
    }));
    const label = el('text', { x: PAD.l - 5, y: y(t) + 3, 'text-anchor': 'end', class: 'axis' });
    label.textContent = yFmt ? yFmt(t) : String(Math.round(t));
    svg.appendChild(label);
  }
  container.appendChild(svg);
  return { svg, y };
}

// series: [{points: [{x: 'YYYY-MM-DD', y}], color, width?, dashed?, label}]
export function lineChart(container, { series, target, yFmt, empty = 'No data yet' }) {
  container.classList.add('chart');
  const allPts = series.flatMap((s) => s.points);
  if (!allPts.length) {
    container.innerHTML = `<p class="muted small" style="text-align:center;padding:22px 0">${empty}</p>`;
    return;
  }
  const xs = [...new Set(allPts.map((p) => p.x))].sort();
  const ys = allPts.map((p) => p.y).concat(target != null ? [target] : []);
  let yMin = Math.min(...ys);
  let yMax = Math.max(...ys);
  const margin = (yMax - yMin || Math.abs(yMax) * 0.1 || 1) * 0.12;
  yMin -= margin; yMax += margin;

  const { svg, y } = frame(container, yMin, yMax, yFmt);
  const x = scale(0, xs.length - 1, PAD.l + 4, W - PAD.r - 4);
  const xi = new Map(xs.map((v, i) => [v, i]));

  const labelEvery = Math.max(1, Math.ceil(xs.length / 5));
  xs.forEach((iso, i) => {
    if (i % labelEvery !== 0 && i !== xs.length - 1) return;
    const t = el('text', { x: x(i), y: H - 6, 'text-anchor': 'middle', class: 'axis' });
    t.textContent = dateLabel(iso);
    svg.appendChild(t);
  });

  if (target != null) {
    svg.appendChild(el('line', {
      x1: PAD.l, x2: W - PAD.r, y1: y(target), y2: y(target),
      stroke: '#FBBF24', 'stroke-width': 1.2, 'stroke-dasharray': '5 4', opacity: 0.8,
    }));
  }

  for (const s of series) {
    const pts = [...s.points].sort((a, b) => (a.x < b.x ? -1 : 1));
    if (!pts.length) continue;
    const d = pts.map((p, i) =>
      `${i ? 'L' : 'M'}${x(xi.get(p.x)).toFixed(1)},${y(p.y).toFixed(1)}`).join(' ');
    svg.appendChild(el('path', {
      d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      ...(s.dashed ? { 'stroke-dasharray': '4 4' } : {}),
    }));
    if (pts.length <= 40) {
      for (const p of pts) {
        svg.appendChild(el('circle', {
          cx: x(xi.get(p.x)), cy: y(p.y), r: 2.1, fill: s.color,
        }));
      }
    }
  }
  const withLabels = series.filter((s) => s.label);
  if (withLabels.length) {
    const legend = document.createElement('div');
    legend.className = 'legend';
    legend.innerHTML = withLabels.map((s) =>
      `<span><i style="background:${s.color}"></i>${s.label}</span>`).join('');
    container.appendChild(legend);
  }
}

// bars: [{x: label or date, y, color?}]
export function barChart(container, { bars, target, yFmt, dateX = true, empty = 'No data yet' }) {
  container.classList.add('chart');
  if (!bars.length) {
    container.innerHTML = `<p class="muted small" style="text-align:center;padding:22px 0">${empty}</p>`;
    return;
  }
  const ys = bars.map((b) => b.y).concat(target != null ? [target] : [], [0]);
  const yMax = Math.max(...ys) * 1.1 || 1;
  const { svg, y } = frame(container, 0, yMax, yFmt);
  const x = scale(0, bars.length, PAD.l + 2, W - PAD.r - 2);
  const bw = Math.min(26, Math.max(3, (W - PAD.l - PAD.r) / bars.length - 3));

  bars.forEach((b, i) => {
    const cx = x(i) + (x(1) - x(0)) / 2;
    const barY = y(Math.max(0, b.y));
    svg.appendChild(el('rect', {
      x: cx - bw / 2, y: barY, width: bw, height: Math.max(1, y(0) - barY),
      rx: Math.min(4, bw / 2), fill: b.color || '#38BDF8', opacity: 0.9,
    }));
  });
  const labelEvery = Math.max(1, Math.ceil(bars.length / 5));
  bars.forEach((b, i) => {
    if (i % labelEvery !== 0 && i !== bars.length - 1) return;
    const t = el('text', {
      x: x(i) + (x(1) - x(0)) / 2, y: H - 6, 'text-anchor': 'middle', class: 'axis',
    });
    t.textContent = dateX ? dateLabel(b.x) : String(b.x);
    svg.appendChild(t);
  });
  if (target != null) {
    svg.appendChild(el('line', {
      x1: PAD.l, x2: W - PAD.r, y1: y(target), y2: y(target),
      stroke: '#FBBF24', 'stroke-width': 1.2, 'stroke-dasharray': '5 4', opacity: 0.85,
    }));
  }
}

// Big calories-left ring for Today.
export function ring(el2, { value, max, label, sub }) {
  const r = 56;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, max > 0 ? value / max : 0));
  el2.innerHTML = `
  <svg class="ring" viewBox="0 0 132 132">
    <defs><linearGradient id="ringg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#34D399"/><stop offset="1" stop-color="#38BDF8"/>
    </linearGradient></defs>
    <circle cx="66" cy="66" r="${r}" fill="none" stroke="#1E2A4A" stroke-width="11"/>
    <circle cx="66" cy="66" r="${r}" fill="none" stroke="url(#ringg)" stroke-width="11"
      stroke-linecap="round" stroke-dasharray="${(pct * c).toFixed(1)} ${c.toFixed(1)}"
      transform="rotate(-90 66 66)"/>
    <text class="big" x="66" y="63" text-anchor="middle">${label}</text>
    <text class="lbl" x="66" y="80" text-anchor="middle">${sub}</text>
  </svg>`;
}
