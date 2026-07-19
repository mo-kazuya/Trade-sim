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

  window.drawLineChart = drawLineChart;
  window.CHART_COLORS = COLORS;
})();
