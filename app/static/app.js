let selectedFile = null;
let lastAnalyzedFile = null; // re-sent to /api/export/figure, which recomputes server-side

const statusEl = document.getElementById("status");
const analyzeBtn = document.getElementById("analyzeBtn");
const fileInput = document.getElementById("fileInput");
const exampleBtn = document.getElementById("exampleBtn");

function setStatus(msg, isError) {
  statusEl.textContent = msg || "";
  statusEl.classList.toggle("error", Boolean(isError));
}

fileInput.addEventListener("change", () => {
  selectedFile = fileInput.files[0] || null;
  analyzeBtn.disabled = !selectedFile;
  setStatus(selectedFile ? `Selected: ${selectedFile.name}` : "");
});

analyzeBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  await runAnalysis(selectedFile);
});

exampleBtn.addEventListener("click", async () => {
  setStatus("Fetching example data...");
  try {
    const resp = await fetch("/api/example");
    if (!resp.ok) throw new Error(`Failed to load example data (${resp.status})`);
    const rows = await resp.json();
    const blob = new Blob([JSON.stringify(rows)], { type: "application/json" });
    const file = new File([blob], "cifar10_benchmark.json", { type: "application/json" });
    await runAnalysis(file);
  } catch (err) {
    setStatus(String(err), true);
  }
});

async function runAnalysis(file) {
  setStatus("Running DERMS-R analysis...");
  const form = new FormData();
  form.append("file", file);
  try {
    const resp = await fetch("/api/analyze", { method: "POST", body: form });
    const payload = await resp.json();
    if (!resp.ok) throw new Error(payload.detail || `Request failed (${resp.status})`);
    lastAnalyzedFile = file;
    render(payload);
    setDownloadsEnabled(true);
    setStatus(`Analyzed ${payload.rows.length} rows across ${payload.optimal.length} architecture(s).`);
  } catch (err) {
    setStatus(String(err), true);
  }
}

function render(payload) {
  renderTable(payload.rows);
  renderRadar(payload.radar);
  renderPerArchitecture(payload.rows);
  renderOptimal(payload.optimal);
  renderStatistics(payload.statistics);
}

// ---------------------------------------------------------------------
// 2. Results table
// ---------------------------------------------------------------------
const TABLE_COLUMNS = [
  { key: "architecture", label: "Architecture" },
  { key: "dataset_ratio", label: "Ratio" },
  { key: "mean_val_accuracy", label: "Mean Val. Accuracy", fmt: pct },
  { key: "n_parameters", label: "Parameters", fmt: compact },
  { key: "std_val_accuracy", label: "Std. Dev. Accuracy", fmt: (v) => pct(v, 3) },
  { key: "derms_r_raw", label: "DERMS-R (raw)", fmt: (v) => v.toFixed(4) },
  { key: "derms_r_normalized", label: "DERMS-R (normalized)", fmt: (v) => v.toFixed(4) },
];

let tableRows = [];
let sortState = { key: "architecture", asc: true };

function pct(v, digits = 2) { return `${(v * 100).toFixed(digits)}%`; }
function compact(v) {
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(v);
}

function renderTable(rows) {
  tableRows = rows;
  document.getElementById("tableSection").classList.remove("hidden");
  const thead = document.querySelector("#resultsTable thead tr");
  thead.innerHTML = "";
  TABLE_COLUMNS.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    th.addEventListener("click", () => {
      sortState = sortState.key === col.key ? { key: col.key, asc: !sortState.asc } : { key: col.key, asc: true };
      drawTableBody();
    });
    thead.appendChild(th);
  });
  drawTableBody();
}

function drawTableBody() {
  const sorted = [...tableRows].sort((a, b) => {
    const va = a[sortState.key], vb = b[sortState.key];
    const cmp = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return sortState.asc ? cmp : -cmp;
  });
  const tbody = document.querySelector("#resultsTable tbody");
  tbody.innerHTML = "";
  sorted.forEach((row) => {
    const tr = document.createElement("tr");
    TABLE_COLUMNS.forEach((col) => {
      const td = document.createElement("td");
      const v = row[col.key];
      td.textContent = col.fmt ? col.fmt(v) : v;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------
// 3. Radar grid (small multiples via one polar subplot per architecture)
// ---------------------------------------------------------------------
function renderRadar(radar) {
  document.getElementById("radarSection").classList.remove("hidden");
  const n = radar.panels.length;
  const cols = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(n))));
  const rows = Math.ceil(n / cols);
  // Horizontal gap is wider than vertical: adjacent panels' "Accuracy"
  // (0 deg) and "Stability" (180 deg) angular-axis labels sit right at the
  // domain edge and collide with their neighbor's label otherwise.
  const gapX = 0.16;
  const gapY = 0.10;

  const traces = [];
  const layout = { height: 290 * rows, margin: { t: 30, b: 10 }, showlegend: false };

  radar.panels.forEach((panel, i) => {
    const r = Math.floor(i / cols), c = i % cols;
    const colWidth = (1 - gapX * (cols - 1)) / cols;
    const rowHeight = (1 - gapY * (rows - 1)) / rows;
    const domainKey = i === 0 ? "polar" : `polar${i + 1}`;
    const axisRef = i === 0 ? "polar" : `polar${i + 1}`;

    traces.push({
      type: "scatterpolar",
      r: [...panel.values, panel.values[0]],
      theta: [...radar.axes, radar.axes[0]],
      fill: "toself",
      name: panel.architecture,
      subplot: axisRef,
      line: { color: "#1b5e4f" },
      fillcolor: "rgba(27,94,79,0.25)",
    });

    layout[domainKey] = {
      domain: {
        x: [c * (colWidth + gapX), c * (colWidth + gapX) + colWidth],
        y: [1 - (r + 1) * (rowHeight + gapY) + gapY, 1 - r * (rowHeight + gapY)],
      },
      radialaxis: { visible: true, range: [0, 1], showticklabels: false, ticks: "" },
      angularaxis: { tickfont: { size: 8 } },
    };
    layout.annotations = layout.annotations || [];
    layout.annotations.push({
      text: panel.architecture,
      showarrow: false,
      x: c * (colWidth + gapX) + colWidth / 2,
      y: 1 - r * (rowHeight + gapY) + 0.02,
      xref: "paper",
      yref: "paper",
      font: { size: 11, color: "#1f2321" },
    });
  });

  Plotly.newPlot("radarGrid", traces, layout, { displaylogo: false, responsive: true });
}

// ---------------------------------------------------------------------
// 4. DERMS-R per architecture, across all evaluated ratios
// ---------------------------------------------------------------------
function renderPerArchitecture(rows) {
  document.getElementById("perArchSection").classList.remove("hidden");
  const ratios = [...new Set(rows.map((r) => r.dataset_ratio))].sort((a, b) => a - b);
  const architectures = [...new Set(rows.map((r) => r.architecture))];

  const traces = ratios.map((ratio) => ({
    type: "bar",
    name: `r = ${ratio}`,
    x: architectures,
    y: architectures.map((a) => {
      const row = rows.find((r) => r.architecture === a && r.dataset_ratio === ratio);
      return row ? row.derms_r_raw : null;
    }),
  }));

  Plotly.newPlot(
    "perArchChart",
    traces,
    {
      barmode: "group",
      height: 420,
      yaxis: { title: "DERMS-R (raw)" },
      margin: { t: 20, b: 80 },
      legend: { orientation: "h", y: -0.2 },
    },
    { displaylogo: false, responsive: true }
  );
}

// ---------------------------------------------------------------------
// 5. DERMS-R at each architecture's optimal ratio
// ---------------------------------------------------------------------
function renderOptimal(optimal) {
  document.getElementById("optimalSection").classList.remove("hidden");
  const trace = {
    type: "scatter",
    mode: "markers+text",
    x: optimal.map((o) => o.n_parameters),
    y: optimal.map((o) => o.mean_val_accuracy * 100),
    text: optimal.map((o) => o.architecture),
    textposition: "top center",
    textfont: { size: 9, color: "#555" },
    marker: {
      size: optimal.map((o) => o.derms_r_raw),
      sizemode: "area",
      sizeref: (2.0 * Math.max(...optimal.map((o) => o.derms_r_raw))) / 40 ** 2,
      sizemin: 6,
      color: optimal.map((o) => o.derms_r_raw),
      colorscale: "Viridis",
      showscale: true,
      colorbar: { title: "DERMS-R" },
      line: { color: "white", width: 1 },
    },
    hovertemplate:
      "%{text}<br>Params: %{x:,.0f}<br>Accuracy: %{y:.2f}%<br>DERMS-R: %{marker.color:.4f}<extra></extra>",
  };
  Plotly.newPlot(
    "optimalChart",
    [trace],
    {
      height: 460,
      xaxis: { title: "Trainable parameters (log scale)", type: "log" },
      yaxis: { title: "Mean validation accuracy (%)" },
      margin: { t: 20 },
    },
    { displaylogo: false, responsive: true }
  );
}

// ---------------------------------------------------------------------
// 6. Statistical analysis: Friedman test + Nemenyi critical difference
// ---------------------------------------------------------------------
function renderStatistics(stats) {
  document.getElementById("statsSection").classList.remove("hidden");
  const container = document.getElementById("statsContent");
  container.innerHTML = "";

  if (!stats.available) {
    const p = document.createElement("p");
    p.className = "note";
    p.textContent = stats.reason;
    container.appendChild(p);
    return;
  }

  const statGrid = document.createElement("div");
  statGrid.className = "stat-grid";
  const boxes = [
    ["Friedman chi-sq", stats.chi2_f.toFixed(2)],
    ["Degrees of freedom", stats.df],
    ["p-value", stats.p_value != null ? stats.p_value.toExponential(2) : "n/a"],
    ["Nemenyi CD", stats.critical_difference.toFixed(2)],
  ];
  boxes.forEach(([label, value]) => {
    const box = document.createElement("div");
    box.className = "stat-box";
    box.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
    statGrid.appendChild(box);
  });
  container.appendChild(statGrid);

  const note = document.createElement("p");
  note.className = "note";
  note.textContent =
    `Based on ${stats.k} architectures compared across ${stats.n} dataset-ratio blocks. ` +
    (stats.critical_pairs.length
      ? `${stats.critical_pairs.length} architecture pair(s) differ by more than the critical difference.`
      : "No architecture pair differs by more than the critical difference at this sample size.");
  container.appendChild(note);

  container.appendChild(chartHead("Average rank", "ranks"));
  const rankDiv = document.createElement("div");
  rankDiv.id = "rankChart";
  container.appendChild(rankDiv);

  container.appendChild(chartHead("Critical-difference diagram", "cd"));
  const cdDiv = document.createElement("div");
  cdDiv.id = "cdDiagram";
  container.appendChild(cdDiv);

  const sortedRanks = [...stats.average_ranks].sort((a, b) => a.average_rank - b.average_rank);
  Plotly.newPlot(
    "rankChart",
    [
      {
        type: "bar",
        x: sortedRanks.map((r) => r.architecture),
        y: sortedRanks.map((r) => r.average_rank),
        marker: { color: "#1b5e4f" },
      },
    ],
    { height: 320, yaxis: { title: "Average rank (lower = better)" }, margin: { t: 30, b: 100 } },
    { displaylogo: false, responsive: true }
  );

  renderCdDiagram(sortedRanks, stats.critical_difference, stats.k);
}

function renderCdDiagram(sortedRanks, cd, k) {
  const shapes = [];
  const annotations = [];
  const y0 = 1.0;

  shapes.push({ type: "line", x0: 1, x1: k, y0, y1: y0, line: { color: "black", width: 1.5 } });
  for (let t = 1; t <= k; t++) {
    shapes.push({ type: "line", x0: t, x1: t, y0: y0 - 0.03, y1: y0 + 0.03, line: { color: "black", width: 1 } });
    annotations.push({ x: t, y: y0 - 0.12, text: String(t), showarrow: false, font: { size: 10 } });
  }

  const cdY = y0 + 0.4;
  shapes.push({ type: "line", x0: 1, x1: 1 + cd, y0: cdY, y1: cdY, line: { color: "black", width: 2 } });
  shapes.push({ type: "line", x0: 1, x1: 1, y0: cdY - 0.04, y1: cdY + 0.04, line: { color: "black", width: 1.5 } });
  shapes.push({ type: "line", x0: 1 + cd, x1: 1 + cd, y0: cdY - 0.04, y1: cdY + 0.04, line: { color: "black", width: 1.5 } });
  annotations.push({ x: 1 + cd / 2, y: cdY + 0.12, text: `CD = ${cd.toFixed(2)}`, showarrow: false, font: { size: 11 } });

  const ranks = sortedRanks.map((r) => r.average_rank);
  const groups = [];
  let i = 0;
  while (i < ranks.length) {
    let j = i;
    while (j + 1 < ranks.length && ranks[j + 1] - ranks[i] <= cd) j += 1;
    if (j > i) groups.push([ranks[i], ranks[j]]);
    i += 1;
  }
  groups.forEach(([lo, hi], gi) => {
    const barY = y0 - 0.2 - 0.1 * gi;
    shapes.push({ type: "line", x0: lo, x1: hi, y0: barY, y1: barY, line: { color: "black", width: 3 } });
  });

  sortedRanks.forEach((r, i) => {
    const side = i % 2 === 0 ? 1 : -1;
    const labelY = y0 + side * (0.6 + 0.14 * Math.floor(i / 2));
    shapes.push({
      type: "line",
      x0: r.average_rank,
      x1: r.average_rank,
      y0,
      y1: labelY,
      line: { color: "gray", width: 0.6 },
    });
    annotations.push({
      x: r.average_rank,
      y: labelY,
      text: `${r.architecture} (${r.average_rank.toFixed(1)})`,
      showarrow: false,
      font: { size: 10 },
      yanchor: side > 0 ? "bottom" : "top",
    });
  });

  // Label rows stack above/below the axis (0.14 apart, starting 0.6 away);
  // give the y-range and plot height enough headroom for however many rows
  // this architecture count actually needs, so the title never collides
  // with the topmost label.
  const maxLabelOffset = 0.6 + 0.14 * Math.floor((sortedRanks.length - 1) / 2);
  const yPad = maxLabelOffset + 0.3;

  Plotly.newPlot(
    "cdDiagram",
    [{ type: "scatter", mode: "markers", x: ranks, y: ranks.map(() => y0), marker: { color: "#8c2f2f", size: 6 } }],
    {
      height: 320 + 40 * Math.ceil(sortedRanks.length / 2),
      showlegend: false,
      xaxis: { range: [0.5, k + 0.5], showticklabels: false, zeroline: false, showgrid: false },
      yaxis: { range: [y0 - 0.3, y0 + yPad], showticklabels: false, zeroline: false, showgrid: false },
      shapes,
      annotations,
      margin: { t: 60, b: 10, l: 10, r: 10 },
      title: { text: "Nemenyi critical-difference diagram", y: 0.98 },
    },
    { displaylogo: false, responsive: true }
  );
}

// ---------------------------------------------------------------------
// Downloads: table as CSV/XLSX (client-side), charts as 300 DPI PNG /
// vector PDF (server-side matplotlib re-render via /api/export/figure,
// so the file is actually paper-quality, not a screenshot of the
// on-screen interactive chart).
// ---------------------------------------------------------------------
function setDownloadsEnabled(enabled) {
  document.querySelectorAll(".dl-btn").forEach((btn) => (btn.disabled = !enabled));
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function tableExportRows() {
  // Raw values, not the table's display formatting (percent strings etc.)
  // -- a CSV/XLSX meant for further analysis should stay numeric.
  return tableRows.map((row) => {
    const out = {};
    TABLE_COLUMNS.forEach((col) => (out[col.label] = row[col.key]));
    return out;
  });
}

function downloadCsv() {
  const rows = tableExportRows();
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(",")];
  rows.forEach((row) => {
    lines.push(headers.map((h) => row[h]).join(","));
  });
  triggerDownload(new Blob([lines.join("\n")], { type: "text/csv" }), "dermsr_results.csv");
}

function downloadXlsx() {
  const rows = tableExportRows();
  if (!rows.length) return;
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "DERMS-R results");
  XLSX.writeFile(wb, "dermsr_results.xlsx");
}

async function downloadFigure(name, fmt, btn) {
  if (!lastAnalyzedFile) return;
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "...";
  try {
    const form = new FormData();
    form.append("file", lastAnalyzedFile);
    const resp = await fetch(`/api/export/figure?name=${name}&format=${fmt}`, { method: "POST", body: form });
    if (!resp.ok) {
      const payload = await resp.json().catch(() => ({}));
      throw new Error(payload.detail || `Export failed (${resp.status})`);
    }
    const blob = await resp.blob();
    triggerDownload(blob, `dermsr_${name}.${fmt}`);
  } catch (err) {
    setStatus(String(err), true);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

function figureButtons(name) {
  const frag = document.createDocumentFragment();
  ["png", "pdf"].forEach((fmt) => {
    const btn = document.createElement("button");
    btn.className = "dl-btn";
    btn.disabled = !lastAnalyzedFile;
    btn.textContent = fmt === "png" ? "PNG (300 dpi)" : "PDF (vector)";
    btn.addEventListener("click", () => downloadFigure(name, fmt, btn));
    frag.appendChild(btn);
  });
  return frag;
}

function chartHead(title, figureName) {
  const head = document.createElement("div");
  head.className = "chart-head";
  const h = document.createElement("h3");
  h.textContent = title;
  const row = document.createElement("div");
  row.className = "dl-row";
  row.appendChild(figureButtons(figureName));
  head.appendChild(h);
  head.appendChild(row);
  return head;
}

document.querySelectorAll("[data-download]").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.download === "csv") downloadCsv();
    if (btn.dataset.download === "xlsx") downloadXlsx();
  });
});

document.querySelectorAll(".dl-row[data-figure]").forEach((row) => {
  row.appendChild(figureButtons(row.dataset.figure));
});
