// Minimal dependency-free line chart on a <canvas>.
// Usage: drawLineChart(canvas, series, options)
//   series = [{ label, color, points: [{date, value}] }]
(function () {
  const COLORS = ["#38bdf8", "#22c55e", "#f59e0b", "#a78bfa", "#ef4444", "#ec4899"];

  function drawLineChart(canvas, series, options) {
    options = options || {};
    const ratio = window.devicePixelRatio || 1;
    const cssWidth = canvas.clientWidth || 640;
    const cssHeight = options.height || 320;
    canvas.width = cssWidth * ratio;
    canvas.height = cssHeight * ratio;
    canvas.style.height = cssHeight + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);

    const padL = 62, padR = 16, padT = 16, padB = 34;
    const W = cssWidth, H = cssHeight;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    // Determine bounds across all series.
    let maxLen = 0, minV = Infinity, maxV = -Infinity;
    series.forEach((s) => {
      maxLen = Math.max(maxLen, s.points.length);
      s.points.forEach((p) => {
        if (p.value < minV) minV = p.value;
        if (p.value > maxV) maxV = p.value;
      });
    });
    if (!isFinite(minV)) { minV = 0; maxV = 1; }
    if (minV === maxV) { maxV = minV + 1; }
    const pad = (maxV - minV) * 0.05;
    minV -= pad; maxV += pad;

    const xAt = (i, len) => padL + (len <= 1 ? 0 : (i / (len - 1)) * plotW);
    const yAt = (v) => padT + plotH - ((v - minV) / (maxV - minV)) * plotH;

    // Grid + y labels.
    ctx.strokeStyle = "#334155";
    ctx.fillStyle = "#94a3b8";
    ctx.lineWidth = 1;
    ctx.font = "11px sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const ticks = 5;
    for (let t = 0; t <= ticks; t++) {
      const v = minV + (t / ticks) * (maxV - minV);
      const y = yAt(v);
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(W - padR, y);
      ctx.stroke();
      ctx.fillText(formatNum(v), padL - 8, y);
    }

    // X labels (first / middle / last date).
    const ref = series[0] && series[0].points.length ? series[0].points : null;
    if (ref) {
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      [0, Math.floor(ref.length / 2), ref.length - 1].forEach((i) => {
        if (ref[i]) {
          ctx.fillText(ref[i].date, xAt(i, ref.length), H - padB + 8);
        }
      });
    }

    // Series lines.
    series.forEach((s, si) => {
      ctx.strokeStyle = s.color || COLORS[si % COLORS.length];
      ctx.lineWidth = 2;
      ctx.beginPath();
      s.points.forEach((p, i) => {
        const x = xAt(i, s.points.length);
        const y = yAt(p.value);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });

    // Optional trade markers on first series.
    if (options.markers) {
      options.markers.forEach((m) => {
        const s = series[0];
        const i = m.index;
        if (i == null || !s.points[i]) return;
        const x = xAt(i, s.points.length);
        const y = yAt(s.points[i].value);
        ctx.fillStyle = m.side === "BUY" ? "#22c55e" : "#ef4444";
        ctx.beginPath();
        ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fill();
      });
    }
  }

  function formatNum(v) {
    if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString();
    return v.toFixed(2);
  }

  // Fan chart: shaded percentile bands (p10-p90, p25-p75) plus a median line.
  // bands = { days:[...], p10:[...], p25:[...], p50:[...], p75:[...], p90:[...] }
  // options.threshold = price level drawn as a dashed reference line.
  function drawFanChart(canvas, bands, options) {
    options = options || {};
    const ratio = window.devicePixelRatio || 1;
    const W = canvas.clientWidth || 640;
    const H = options.height || 320;
    canvas.width = W * ratio;
    canvas.height = H * ratio;
    canvas.style.height = H + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);

    const padL = 62, padR = 16, padT = 16, padB = 28;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const n = bands.days.length;

    let minV = Infinity, maxV = -Infinity;
    ["p10", "p90"].forEach((k) => bands[k].forEach((v) => {
      if (v < minV) minV = v; if (v > maxV) maxV = v;
    }));
    if (options.threshold != null) {
      minV = Math.min(minV, options.threshold);
      maxV = Math.max(maxV, options.threshold);
    }
    const pad = (maxV - minV) * 0.06 || 1;
    minV -= pad; maxV += pad;

    const xAt = (i) => padL + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
    const yAt = (v) => padT + plotH - ((v - minV) / (maxV - minV)) * plotH;

    // Grid + y labels.
    ctx.strokeStyle = "#334155";
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let t = 0; t <= 5; t++) {
      const v = minV + (t / 5) * (maxV - minV);
      const y = yAt(v);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      ctx.fillText(formatNum(v), padL - 8, y);
    }

    const bandFill = (lo, hi, color) => {
      ctx.beginPath();
      lo.forEach((v, i) => { const x = xAt(i), y = yAt(v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      for (let i = hi.length - 1; i >= 0; i--) ctx.lineTo(xAt(i), yAt(hi[i]));
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
    };
    bandFill(bands.p10, bands.p90, "rgba(56,189,248,0.15)");
    bandFill(bands.p25, bands.p75, "rgba(56,189,248,0.28)");

    // Median line.
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    bands.p50.forEach((v, i) => { const x = xAt(i), y = yAt(v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.stroke();

    // Threshold reference line.
    if (options.threshold != null) {
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      const y = yAt(options.threshold);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#f59e0b";
      ctx.textAlign = "left";
      ctx.fillText("+目標", padL + 4, y - 8);
    }

    // X labels (day numbers).
    ctx.fillStyle = "#94a3b8";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    [0, Math.floor((n - 1) / 2), n - 1].forEach((i) => {
      ctx.fillText(i + "日", xAt(i), H - padB + 6);
    });
  }

  // Simple histogram from {counts:[...], edges:[...]} (edges has counts.length+1).
  function drawHistogram(canvas, hist, options) {
    options = options || {};
    const ratio = window.devicePixelRatio || 1;
    const W = canvas.clientWidth || 640;
    const H = options.height || 220;
    canvas.width = W * ratio;
    canvas.height = H * ratio;
    canvas.style.height = H + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);

    const padL = 20, padR = 16, padT = 12, padB = 26;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const counts = hist.counts, edges = hist.edges;
    const maxC = Math.max.apply(null, counts) || 1;
    const lo = edges[0], hi = edges[edges.length - 1];
    const xAt = (v) => padL + ((v - lo) / (hi - lo || 1)) * plotW;
    const bw = plotW / counts.length;

    counts.forEach((c, i) => {
      const h = (c / maxC) * plotH;
      const mid = (edges[i] + edges[i + 1]) / 2;
      ctx.fillStyle = mid >= (options.threshold || 0) ? "#22c55e" : "#38bdf8";
      ctx.fillRect(padL + i * bw + 1, padT + plotH - h, bw - 2, h);
    });

    // Threshold marker.
    if (options.threshold != null && options.threshold >= lo && options.threshold <= hi) {
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      const x = xAt(options.threshold);
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
      ctx.setLineDash([]);
    }

    // X axis labels as percentages.
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    [lo, (lo + hi) / 2, hi].forEach((v) => {
      ctx.fillText((v * 100).toFixed(0) + "%", xAt(v), padT + plotH + 6);
    });
  }

  window.drawLineChart = drawLineChart;
  window.drawFanChart = drawFanChart;
  window.drawHistogram = drawHistogram;
  window.CHART_COLORS = COLORS;
})();
