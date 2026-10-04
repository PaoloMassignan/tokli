// Tokli dashboard v0 (SPEC 016). Everything shown comes from /tokli/api; this file knows API
// field names only, never compressor identities (UI-001). Every token figure is rendered with
// its method label, and unknown values as "—" with the reason (UI-002).

const SVG_NS = "http://www.w3.org/2000/svg";
const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const TABS = ["overview", "compressors", "requests", "settings"];
const SIZE_BUCKETS = [
  ["lt_10k", "small (< 10k tokens)"],
  ["10k_50k", "medium (10k–50k)"],
  ["50k_200k", "large (50k–200k)"],
  ["gt_200k", "very large (> 200k)"],
  ["unknown", "size unknown"],
];
const EQUIVALENCE = {
  exact: "lossless · exact",
  structural: "lossless · structural",
  reference: "lossless · by reference",
};

const state = { tab: "overview", version: 0, loaded: {}, cursor: null };

// -- small DOM helpers -------------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined && value !== false) node.setAttribute(name, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function svg(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  if (text !== null) node.textContent = text;
  return node;
}

function fmt(value, digits = 0) {
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: digits });
}

async function apiPatch(changes) {
  const response = await fetch(new URL("/tokli/api/config", window.location.origin), {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ changes }),
  });
  const body = await response.json();
  if (!response.ok) {
    const error = body.error || {};
    const detail = error.source ? ` (locked by ${error.source})` : error.fields ? `: ${Object.values(error.fields).join("; ")}` : "";
    throw new Error((error.type || `HTTP ${response.status}`) + detail);
  }
  return body;
}

async function api(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [name, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") url.searchParams.set(name, value);
  }
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) {
    const error = body.error || {};
    const fields = error.fields ? ": " + Object.entries(error.fields).map(([k, v]) => `${k} ${v}`).join("; ") : "";
    throw new Error((error.type || `HTTP ${response.status}`) + fields);
  }
  return body;
}

// -- figures -----------------------------------------------------------------------------------

// Plain words for the most common reasons; the code stays visible in brackets (UI-002).
const REASONS = {
  no_price_book: "prices not set up yet",
  no_data: "no data in this range",
  not_measured: "not measured",
  no_applicable_invocations: "never applied",
  usage_unavailable: "provider gave no figure",
};

function reasonText(code) {
  return REASONS[code] ? `${REASONS[code]} (${code})` : code;
}

function methodText(f) {
  let text = f.method;
  if (f.calibrated_share) text += ` · ${Math.round(f.calibrated_share * 100)} % calibrated`;
  if (f.exact_share) text += ` · ${Math.round(f.exact_share * 100)} % exact`;
  if (f.partial) text += " · partial";
  return text;
}

/** A token figure: the number with its method, or "—" with the reason (UI-002). */
function figure(f, suffix = "") {
  if (!f || f.value === null || f.value === undefined) {
    return el("span", { class: "figure unavailable" },
      el("span", { class: "num" }, "—"),
      el("span", { class: "reason" }, reasonText((f && f.reason) || "unavailable")));
  }
  const digits = suffix ? 2 : 0;
  return el("span", { class: "figure" },
    el("span", { class: "num" }, fmt(f.value, digits) + suffix),
    el("span", { class: "method" }, methodText(f)));
}

/** A ratio or a duration (not a token figure): the number, or "—" with the reason. */
function rate(r, { percent = false, unit = "" } = {}) {
  if (!r || r.value === null || r.value === undefined) {
    return el("span", { class: "rate unavailable" }, "—", el("span", { class: "reason" }, " " + reasonText((r && r.reason) || "")));
  }
  const value = percent ? fmt(r.value * 100, 1) + " %" : fmt(r.value, 3) + unit;
  return el("span", { class: "rate" }, value);
}

function filterParams() {
  const form = document.getElementById("filters");
  const days = Number(form.range.value);
  const to = new Date();
  const from = new Date(to.getTime() - days * 24 * 3600 * 1000);
  return {
    days,
    params: {
      from: from.toISOString(),
      to: to.toISOString(),
      tz: TZ,
      provider: form.provider.value.trim(),
      model: form.model.value.trim(),
      kind: form.kind.value,
    },
  };
}

// -- overview ----------------------------------------------------------------------------------

function card(key, label, content) {
  return el("div", { class: "card", "data-card": key }, el("div", { class: "label" }, label), content);
}

// Charts are drawn at the container's pixel width, so labels keep their size on any screen.
function chartWidth(id) {
  return Math.max(280, Math.round(document.getElementById(id).clientWidth || 600));
}

function savedChart(series, width) {
  const height = 170, pad = 28;
  const values = series.buckets.map((b) => (b.saved.value === null ? 0 : b.saved.value));
  const max = Math.max(1, ...values);
  const chart = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Saved tokens per bucket" });
  chart.append(svg("line", { class: "axis", x1: pad, y1: height - pad, x2: width, y2: height - pad }));
  const step = (width - pad) / Math.max(1, values.length);
  values.forEach((value, i) => {
    const h = ((height - 2 * pad) * value) / max;
    chart.append(svg("rect", {
      class: "bar", x: pad + i * step + 1, y: height - pad - h,
      width: Math.max(1, step - 2), height: h,
    }));
  });
  chart.append(svg("text", { x: pad, y: 12 }, `max ${fmt(max)} tokens per ${series.bucket}`));
  if (series.buckets.length) {
    const first = new Date(series.buckets[0].start).toLocaleDateString();
    const last = new Date(series.buckets[series.buckets.length - 1].start).toLocaleDateString();
    chart.append(svg("text", { x: pad, y: height - 8 }, first));
    chart.append(svg("text", { x: width - 4, y: height - 8, "text-anchor": "end" }, last));
  }
  return chart;
}

function overheadChart(overhead, width) {
  const height = 220, pad = 32;
  const groups = overhead.groups;
  let group = null;
  for (const g of groups) {
    const n = Object.values(g.buckets).reduce((sum, b) => sum + b.n, 0);
    if (!group || n > group.n) group = { ...g, n };
  }
  const target = overhead.target.value;
  const values = group ? SIZE_BUCKETS.flatMap(([key]) => [group.buckets[key].p50 || 0, group.buckets[key].p95 || 0]) : [];
  const max = Math.max(target * 1.4, ...values);
  const y = (v) => height - pad - ((height - 2 * pad) * v) / max;
  const chart = svg("svg", { id: "overhead-chart", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Overhead per request size" });
  chart.append(svg("line", { class: "axis", x1: pad, y1: height - pad, x2: width, y2: height - pad }));
  const slot = (width - pad) / SIZE_BUCKETS.length;
  SIZE_BUCKETS.forEach(([key, label], i) => {
    const b = group ? group.buckets[key] : { n: 0, p50: null, p95: null };
    const x = pad + i * slot + slot * 0.15;
    const w = slot * 0.3;
    if (b.n) {
      chart.append(svg("rect", { class: "bar2", x, y: y(b.p50), width: w, height: height - pad - y(b.p50) }));
      chart.append(svg("rect", { class: "bar", x: x + w, y: y(b.p95), width: w, height: height - pad - y(b.p95) }));
      chart.append(svg("text", { x: x + w / 2, y: y(b.p50) - 4, "text-anchor": "middle" }, `${fmt(b.p50, 1)}`));
      chart.append(svg("text", { x: x + 1.5 * w, y: y(b.p95) - 4, "text-anchor": "middle" }, `${fmt(b.p95, 1)} ms`));
    }
    chart.append(svg("text", { x: x + w, y: height - 16, "text-anchor": "middle" }, label));
    chart.append(svg("text", { x: x + w, y: height - 4, "text-anchor": "middle" }, `${fmt(b.n)} requests`));
  });
  chart.append(svg("line", { class: "target", x1: pad, y1: y(target), x2: width, y2: y(target) }));
  chart.append(svg("text", { class: "target-label", x: width - 4, y: y(target) - 4, "text-anchor": "end" },
    `goal ${fmt(target)} ms — target (not a limit)`));
  const box = el("div");
  box.append(chart);
  if (group) {
    box.append(el("p", { class: "note" },
      el("span", { class: "swatch light" }), " typical  ",
      el("span", { class: "swatch dark" }), " slowest (1 in 20 is slower)",
      groups.length > 1
        ? `. Showing the most used configuration; ${groups.length - 1} other configuration(s) in this range.`
        : ""));
  }
  return box;
}

async function loadOverview() {
  const { days, params } = filterParams();
  const [summary, series, perCompressor, registry] = await Promise.all([
    api("/tokli/api/metrics/summary", params),
    api("/tokli/api/metrics/timeseries", { ...params, bucket: days > 2 ? "day" : "hour" }),
    api("/tokli/api/metrics/compressors", params),
    api("/tokli/api/compressors"),
  ]);
  const names = Object.fromEntries(registry.compressors.map((c) => [c.id, c]));
  document.getElementById("per-compressor").replaceChildren(
    el("thead", {}, el("tr", {}, ["Compressor", "Kind", "Tokens saved", "Share of all savings"].map((h) => el("th", {}, h)))),
    el("tbody", {}, perCompressor.compressors.length
      ? perCompressor.compressors.map((m) => {
        const c = names[m.compressor_id];
        return el("tr", {},
          el("td", {}, c ? c.name : m.compressor_id),
          el("td", {}, c ? kindBadge(c) : m.kind.toLowerCase()),
          el("td", { class: "n" }, figure(m.marginal_saved)),
          el("td", { class: "n" }, rate(m.share_of_saving, { percent: true })));
      })
      : [el("tr", {}, el("td", { colspan: "4" }, figure({ value: null, reason: "no_data" })))]),
  );
  const t = summary.tokens;
  const requests = summary.requests;
  document.getElementById("cards").replaceChildren(
    card("requests", "Requests", el("div", { class: "stat" },
      el("span", { class: "big" }, fmt(requests.total)),
      el("div", { class: "note" }, `${fmt(requests.measured)} with token figures`))),
    card("original", "Original tokens", figure(t.original)),
    card("forwarded", "Forwarded tokens", figure(t.forwarded)),
    card("saved", "Saved tokens", figure(t.saved)),
    card("saving_pct", "Saving", figure(t.saving_pct, " %")),
    card("cost", "Money saved", figure(summary.cost)),
  );
  document.getElementById("saved-chart").replaceChildren(savedChart(series, chartWidth("saved-chart")));
  document.getElementById("overhead-box").replaceChildren(
    overheadChart(summary.overhead, chartWidth("overhead-box")));
}

// -- compressors -------------------------------------------------------------------------------

function kindBadge(c) {
  const text = c.kind === "LOSSLESS" ? EQUIVALENCE[c.equivalence] || "lossless" : c.kind.toLowerCase();
  return el("span", { class: `badge ${c.kind.toLowerCase()}` }, text);
}

async function loadCompressors() {
  const { params } = filterParams();
  const [registry, metrics] = await Promise.all([
    api("/tokli/api/compressors"),
    api("/tokli/api/metrics/compressors", params),
  ]);
  document.getElementById("budget").textContent =
    `Compression may spend at most ${fmt(metrics.budget_ms)} ms per request (setting compression.request_budget_ms). ` +
    `Policy: ${registry.policy === "LOSSLESS_ONLY" ? "lossless only" : registry.policy}. Hover a column title for its meaning.`;
  const empty = { value: null, reason: "no_data" };
  const columns = [
    ["Compressor", "Name, version and the assumptions it relies on"],
    ["Kind", "Lossless: nothing in the request is lost. Selective or lossy: some information is dropped"],
    ["On", "Whether the compressor is switched on"],
    ["Available", "Whether it can run on this machine"],
    ["Speed class", "Declared cost: cheap, moderate or expensive"],
    ["Looked at", "Pieces of text it was offered"],
    ["Could apply", "Pieces where it could do something (for example, the text was JSON)"],
    ["Shortened", "Pieces it actually made shorter"],
    ["Tokens read", "Tokens in the pieces it could apply to"],
    ["Tokens saved", "Tokens removed by this compressor"],
    ["Share of all savings", "Its part of the total saving"],
    ["Saving when it shortens", "Average reduction of a piece it shortened"],
    ["Tried, no saving", "Of the pieces it could apply to, how many it could not shorten"],
    ["Errors", "Pieces where it failed or took too long (the original text was kept)"],
    ["Skipped for time", "Pieces skipped because the request's time budget was used up"],
    ["Time (total)", "Total time spent, in milliseconds"],
    ["Time per piece", "Average time per piece it could apply to"],
    ["Tokens saved per ms", "Efficiency: tokens saved for each millisecond spent"],
    ["", "Warning when it costs time but almost never saves anything"],
  ];
  const head = el("thead", {}, el("tr", {}, columns.map(([h, title]) => el("th", { title }, h))));
  const body = el("tbody");
  for (const c of registry.compressors) {
    const m = metrics.compressors.find((row) => row.compressor_id === c.id) || null;
    const n = (name) => (m ? fmt(m[name]) : "0");
    body.append(el("tr", {},
      el("td", {}, el("strong", {}, c.name), ` v${c.version}`,
        el("ul", { class: "assumptions" }, c.assumptions.map((a) => el("li", {}, a)))),
      el("td", {}, kindBadge(c)),
      el("td", {}, c.enabled ? "yes" : "no"),
      el("td", {}, c.availability),
      el("td", {}, c.cost_class),
      el("td", { class: "n" }, n("considered")),
      el("td", { class: "n" }, n("applicable")),
      el("td", { class: "n" }, n("accepted")),
      el("td", { class: "n" }, figure(m ? m.tokens_in : empty)),
      el("td", { class: "n" }, figure(m ? m.marginal_saved : empty)),
      el("td", { class: "n" }, rate(m ? m.share_of_saving : empty, { percent: true })),
      el("td", { class: "n" }, rate(m ? m.avg_saving_pct_per_accepted : empty, { unit: " %" })),
      el("td", { class: "n" }, rate(m ? m.zero_benefit_rate : empty, { percent: true })),
      el("td", { class: "n" }, rate(m ? m.failure_rate : empty, { percent: true })),
      el("td", { class: "n" }, rate(m ? m.skipped_budget_rate : empty, { percent: true })),
      el("td", { class: "n" }, m ? fmt(m.ms_total, 3) : "0"),
      el("td", { class: "n" }, rate(m ? m.avg_ms : empty, { unit: " ms" })),
      el("td", { class: "n" }, figure(m ? m.tokens_saved_per_ms : empty)),
      el("td", {}, m && m.latency_without_benefit
        ? el("span", { class: "flag", title: "≥ 90 % zero-benefit, ≥ 1 ms average, ≥ 100 invocations" }, "latency without benefit")
        : ""),
    ));
  }
  document.getElementById("compressors-table").replaceChildren(head, body);
}

// -- recent requests ---------------------------------------------------------------------------

async function loadRequests(append = false) {
  const body = await api("/tokli/api/requests", { limit: 50, cursor: append ? state.cursor : null });
  const table = document.getElementById("requests-table");
  if (!append) {
    table.replaceChildren(
      el("thead", {}, el("tr", {}, ["Time", "Model", "Outcome", "Status", "Saved", "Forwarded", "Overhead"].map((h) => el("th", {}, h)))),
      el("tbody"),
    );
  }
  const tbody = table.querySelector("tbody");
  for (const r of body.requests) {
    const row = el("tr", { tabindex: "0" },
      el("td", {}, new Date(r.ts_start).toLocaleString()),
      el("td", {}, r.model || "—"),
      el("td", {}, r.outcome + (r.reason ? ` (${r.reason})` : "")),
      el("td", { class: "n" }, r.status_code === null ? "—" : String(r.status_code)),
      el("td", { class: "n" }, figure(r.tokens.saved)),
      el("td", { class: "n" }, figure(r.tokens.forwarded)),
      el("td", { class: "n" }, r.overhead_ms === null ? "—" : `${fmt(r.overhead_ms, 1)} ms`),
    );
    row.addEventListener("click", () => showDetail(r.request_id));
    row.addEventListener("keydown", (event) => { if (event.key === "Enter") showDetail(r.request_id); });
    tbody.append(row);
  }
  state.cursor = body.next_cursor;
  document.getElementById("more").hidden = !body.next_cursor;
}

async function showDetail(requestId) {
  const box = document.getElementById("request-detail");
  const d = await api(`/tokli/api/requests/${encodeURIComponent(requestId)}`);
  const parts = [el("h2", {}, `Request ${d.request_id}`)];
  const record = d.record;
  parts.push(el("p", {}, "Saved: ", figure(record.saving), " · forwarded input (provider): ",
    figure(record.usage_input), " · k: ", record.calibration_k === null ? "—" : fmt(record.calibration_k, 3)));
  if (d.trace) {
    const lines = d.trace.spans.map((s) => {
      const attrs = Object.keys(s.attrs).length ? " " + JSON.stringify(s.attrs) : "";
      return `${s.ms.toFixed(2).padStart(9)} ms  ${s.name.padEnd(22)} ${s.status}${attrs}`;
    });
    const decisions = d.trace.decisions.map((x) => `decision ${x.decision}: ${x.reason}`);
    parts.push(el("pre", {}, [...lines, ...decisions].join("\n")));
  } else {
    parts.push(el("p", { class: "note" }, "The trace is no longer in memory (only the most recent requests keep one); the record above comes from the database."));
  }
  box.replaceChildren(...parts);
  box.hidden = false;
  box.scrollIntoView({ block: "nearest" });
}

// -- tabs, filters, startup --------------------------------------------------------------------

// -- settings (UI-003…UI-005, UI-010; S4 SCR-001: enabling is the only control) -------------

const settingsState = { registry: null, config: null };

function settingOf(config, key) {
  return config.settings.find((s) => s.key === key) || null;
}

function evaluationText(e) {
  if (!e || e.status === "none") return "not evaluated";
  const text = [e.tier, (e.verdict || "").replaceAll("_", " "), e.model, e.date].filter(Boolean).join(" · ");
  return e.status === "outdated" ? `evaluation outdated (${text})` : text;
}

function isOn(c, config) {
  const s = settingOf(config, `compressors.${c.id}.enabled`);
  return s ? Boolean(s.value) : Boolean(c.enabled);
}

// UI-012 (S8a SCR-001): the per-compressor opt-in for verbatim tools, where a compressor declares it.
function verbatimOptIn(c, config) {
  const key = `compressors.${c.id}.apply_to_verbatim_tools`;
  const s = settingOf(config, key);
  if (!s) return null;
  const tools = settingOf(config, "compression.verbatim_tools");
  const names = tools && Array.isArray(tools.value) ? tools.value.join(", ") : "verbatim tools";
  const input = el("input", { type: "checkbox", "data-toggle": "verbatim", "aria-label": `${c.name} also on ${names}` });
  input.checked = Boolean(s.value);
  input.disabled = Boolean(s.locked_by);
  input.addEventListener("change", () => changeSettings({ [key]: input.checked }));
  return el("div", { class: "verbatim-opt-in" },
    el("label", { class: "switch" }, input, `Also on ${names}`),
    el("div", { class: "warn" },
      "These tools' output is often copied back exactly by the agent (for example as an edit anchor). " +
      "Changing it can make the agent's next tool call fail."),
    s.locked_by ? el("div", { class: "lock" }, `locked by ${s.locked_by}`) : null);
}

function renderSettings() {
  const { registry, config } = settingsState;
  document.getElementById("config-hash").textContent = config.config_hash.slice(0, 12);
  const cards = registry.compressors.map((c) => {
    const key = `compressors.${c.id}.enabled`;
    const s = settingOf(config, key);
    const locked = (s && s.locked_by) || c.locked_by;
    const input = el("input", { type: "checkbox", "data-toggle": "enabled", "aria-label": `${c.name} on/off` });
    input.checked = isOn(c, config);
    input.disabled = Boolean(locked);
    input.addEventListener("change", () => changeSettings({ [key]: input.checked }));
    return el("div", { class: "compressor-card", "data-compressor": c.id },
      el("h3", {}, el("span", {}, c.name, " ", el("span", { class: "note" }, `v${c.version}`)),
        el("label", { class: "switch" }, input, input.checked ? "on" : "off")),
      el("div", {}, kindBadge(c), " ", el("span", { class: "meta" }, c.availability)),
      c.kind !== "LOSSLESS" ? el("div", { class: "warn" }, "drops information") : null,
      verbatimOptIn(c, config),
      el("div", { class: "meta" }, "Evaluation: ", evaluationText(c.evaluation)),
      el("div", { class: "meta" }, "Assumptions:"),
      el("ul", { class: "assumptions" }, c.assumptions.map((a) => el("li", {}, a))),
      locked ? el("div", { class: "lock" }, `locked by ${locked}`) : null);
  });
  document.getElementById("compressor-cards").replaceChildren(...cards);
  const retention = settingOf(config, "telemetry.retention_days");
  const input = document.getElementById("retention");
  input.value = retention ? retention.value : "";
  input.disabled = Boolean(retention && retention.locked_by);
  document.getElementById("retention-lock").textContent = retention && retention.locked_by ? `locked by ${retention.locked_by}` : "";
}

async function changeSettings(changes) {
  const status = document.getElementById("settings-status");
  try {
    settingsState.config = await apiPatch(changes);
    status.textContent = "Saved. The next request uses the new settings.";
    state.version += 1;
    state.loaded = { settings: state.version };
  } catch (error) {
    status.textContent = `Not saved: ${error.message}`;
  }
  renderSettings();
}

async function loadSettings() {
  const [registry, config] = await Promise.all([api("/tokli/api/compressors"), api("/tokli/api/config")]);
  settingsState.registry = registry;
  settingsState.config = config;
  renderSettings();
}

document.getElementById("lossless-only").addEventListener("click", () => {
  const { registry, config } = settingsState;
  if (!registry) return;
  const changes = {};
  for (const c of registry.compressors) {
    const s = settingOf(config, `compressors.${c.id}.enabled`);
    const locked = (s && s.locked_by) || c.locked_by;
    if (c.kind !== "LOSSLESS" && isOn(c, config) && !locked) changes[`compressors.${c.id}.enabled`] = false;
  }
  if (Object.keys(changes).length) {
    changeSettings(changes);
  } else {
    document.getElementById("settings-status").textContent = "Every compressor that is on is already lossless.";
  }
});

document.getElementById("retention-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const value = Number(document.getElementById("retention").value);
  changeSettings({ "telemetry.retention_days": value });
});

const LOADERS = {
  overview: loadOverview,
  compressors: loadCompressors,
  requests: () => loadRequests(false),
  settings: loadSettings,
};

async function show(tab) {
  state.tab = tab;
  for (const name of TABS) {
    document.querySelector(`[data-tab="${name}"]`).setAttribute("aria-pressed", String(name === tab));
    document.querySelector(`section[data-panel="${name}"]`).hidden = name !== tab;
  }
  if (state.loaded[tab] === state.version) return;
  const status = document.getElementById("status");
  const body = document.getElementById(`${tab}-body`);
  body.removeAttribute("data-loaded");
  try {
    await LOADERS[tab]();
    status.textContent = "";
    state.loaded[tab] = state.version;
    body.setAttribute("data-loaded", "");
  } catch (error) {
    status.textContent = `Could not load: ${error.message}`;
  }
}

for (const name of TABS) {
  document.querySelector(`[data-tab="${name}"]`).addEventListener("click", () => show(name));
}
document.getElementById("filters").addEventListener("change", () => {
  state.version += 1;
  show(state.tab);
});
document.getElementById("filters").addEventListener("submit", (event) => event.preventDefault());
document.getElementById("more").addEventListener("click", () => loadRequests(true));
show("overview");
