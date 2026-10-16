"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const palette = ["#3478e5", "#16a394", "#db9040", "#9170c4", "#d96980", "#559ab5", "#818b45", "#ba6d47"];
  const state = {
    config: {}, defaults: {}, signals: {}, diagrams: {}, snapshot: {}, metrics: {}, motorParameters: {},
    history: [], selected: new Set(), probe: "rr_est", diagram: "system", path: ["system"],
    running: false, done: false, busy: false, resetting: false, generation: 0,
    live: true, cursor: 0, timer: null, queue: Promise.resolve(), viewBox: null,
    zoom: 1, drag: null, runWall: 0, runSim: 0, lastPaint: 0, renderPending: false,
  };
  const number = (v) => typeof v === "number" && Number.isFinite(v);
  const asText = (v) => Array.isArray(v) ? v.join("\n") : typeof v === "object" && v !== null ? JSON.stringify(v, null, 2) : String(v ?? "");
  const format = (v, digits = 3) => !number(v) ? "—" : Math.abs(v) >= 1e5 || (Math.abs(v) > 0 && Math.abs(v) < 1e-4) ? v.toExponential(2) : v.toFixed(digits);
  const label = (key) => state.signals[key]?.label || key;
  const unit = (key) => state.signals[key]?.unit || "";
  const categoryNames = { timing: "时钟与采样", measurement: "传感器测量", control: "FOC 控制信号", estimate: "模型估计", truth: "独立评价 · 仿真真值" };
  const categoryLabel = (value) => categoryNames[value] || value || "可测信号";
  const color = (key) => palette[Math.max(0, Object.keys(state.signals).indexOf(key)) % palette.length];
  const selectedSample = () => state.live ? state.snapshot : state.history[state.cursor] || state.snapshot;
  const truthSignal = (key = "") => state.signals[key]?.category === "truth" || /(_true|^rr_error_pct$|flux_angle_error)/.test(key) || /真值|评价/.test(state.signals[key]?.category || "");
  const niceTime = (value) => value < 0.001 ? `${format(value * 1e6, 0)} μs` : `${format(value * 1000, value * 1000 < 1 ? 2 : 1)} ms`;

  function showError(error) {
    $("errorText").textContent = error instanceof Error ? error.message : String(error);
    $("errorBanner").hidden = false;
  }
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let data;
    try { data = await response.json(); } catch (_) { throw new Error(`服务返回了无法读取的响应（HTTP ${response.status}）。请检查 Python 终端。`); }
    if (!response.ok || data.error) throw new Error(asText(data.error || data.message || `请求失败：HTTP ${response.status}`));
    return data;
  }
  function queueMutation(task) {
    const next = state.queue.then(task, task);
    state.queue = next.catch(() => {});
    return next;
  }
  function updateControls() {
    $("runButton").disabled = state.resetting || (state.busy && !state.running) || !Object.keys(state.signals).length || state.done;
    $("runButton").innerHTML = state.running ? '<span aria-hidden="true">Ⅱ</span> 暂停' : '<span aria-hidden="true">▶</span> 运行';
    $("runButton").classList.toggle("paused", state.running);
    $("stepButton").disabled = state.running || state.busy || state.resetting || state.done || !Object.keys(state.signals).length;
    $("batchButton").disabled = $("stepButton").disabled;
    $("resetButton").disabled = !Object.keys(state.signals).length || state.resetting;
    $("settingsForm").querySelector('button[type="submit"]').disabled = state.resetting;
    $("statusLed").classList.toggle("running", state.running);
    $("statusText").textContent = state.resetting ? "正在重置" : state.running ? "仿真运行中" : state.busy ? "完成当前采样批次…" : state.done ? "实验完成" : "已暂停 · 可单步";
    $("scopeStatus").textContent = state.done ? "实验完成" : state.running ? "正在采样" : state.history.length > 1 ? "已暂停" : "等待采样";
  }
  function pause() {
    state.running = false;
    clearTimeout(state.timer);
    updateControls();
  }
  function acceptState(data, append = true) {
    if (data.config) state.config = { ...state.config, ...data.config };
    if (data.snapshot) state.snapshot = data.snapshot;
    if (data.metrics) state.metrics = data.metrics;
    if (data.motor_parameters) state.motorParameters = data.motor_parameters;
    state.done = !!data.done;
    const samples = data.samples || (append && data.snapshot ? [data.snapshot] : []);
    for (const sample of samples) {
      if (!number(sample.time)) continue;
      const previous = state.history[state.history.length - 1];
      if (previous && sample.time === previous.time) state.history[state.history.length - 1] = sample;
      else if (!previous || sample.time > previous.time) state.history.push(sample);
    }
    if (state.live) state.cursor = Math.max(0, state.history.length - 1);
    if (state.done) pause();
    scheduleRender();
  }
  async function advance(count) {
    const generation = state.generation;
    state.busy = true;
    updateControls();
    try {
      const result = await queueMutation(() => api("/api/step", { count }));
      if (generation === state.generation) acceptState(result);
    } catch (error) {
      if (generation === state.generation) { pause(); showError(error); }
    } finally {
      if (generation === state.generation) { state.busy = false; updateControls(); }
    }
  }
  async function runTick() {
    if (!state.running || state.resetting || state.done) return;
    const start = performance.now();
    const generation = state.generation;
    const speed = Number($("playSpeed").value);
    const sampleTime = Number(state.config.sample_time) || 0.0005;
    const count = Math.max(1, Math.min(1000, Math.round(speed * 0.03 / sampleTime)));
    await advance(count);
    if (generation !== state.generation) return;
    const wallElapsed = (performance.now() - state.runWall) / 1000;
    if (wallElapsed > 0) $("performance").textContent = `实际 ${format((Number(state.snapshot.time || 0) - state.runSim) / wallElapsed, 2)}× · 非硬实时`;
    if (state.running && !state.done) state.timer = setTimeout(runTick, Math.max(0, 30 - (performance.now() - start)));
  }
  function start() {
    if (state.busy || state.resetting || state.done) return;
    state.running = true;
    state.runWall = performance.now();
    state.runSim = Number(state.snapshot.time || 0);
    updateControls();
    runTick();
  }
  async function reset(config) {
    if (state.resetting) return;
    pause();
    state.generation += 1;
    state.resetting = true;
    updateControls();
    try {
      const result = await queueMutation(() => api("/api/reset", config));
      $("errorBanner").hidden = true;
      state.history = [];
      state.live = true;
      state.cursor = 0;
      state.snapshot = {};
      state.metrics = {};
      acceptState(result);
      renderSettings();
      $("performance").textContent = "按仿真采样步进";
    } catch (error) { showError(error); }
    finally { state.busy = false; state.resetting = false; updateControls(); scheduleRender(); }
  }
  function setProbe(key, ensureSelected = false) {
    if (!state.signals[key]) return;
    state.probe = key;
    if (ensureSelected) state.selected.add(key);
    renderSignals();
    renderChips();
    renderProbe();
    updateDiagramValues();
    drawScope();
  }

  function renderTree() {
    const container = $("modelTree");
    container.replaceChildren();
    const visited = new Set();
    function branch(id, depth, path) {
      const diagram = state.diagrams[id];
      if (!diagram || visited.has(id)) return;
      visited.add(id);
      const button = document.createElement("button");
      button.className = "tree-button" + (state.diagram === id ? " active" : "");
      button.style.paddingLeft = `${8 + depth * 13}px`;
      const icon = document.createElement("span"); icon.className = "tree-glyph"; icon.textContent = depth ? "⊞" : "▦";
      const name = document.createElement("span"); name.textContent = diagram.title;
      button.append(icon, name);
      button.addEventListener("click", () => navigate(id, path));
      container.append(button);
      for (const node of diagram.nodes || []) if (node.child) branch(node.child, depth + 1, [...path, node.child]);
    }
    branch("system", 0, ["system"]);
    for (const id of Object.keys(state.diagrams)) if (!visited.has(id)) branch(id, 1, ["system", id]);
  }
  function navigate(id, path) {
    if (!state.diagrams[id]) return;
    state.diagram = id;
    state.path = path || (state.path.includes(id) ? state.path.slice(0, state.path.indexOf(id) + 1) : [...state.path, id]);
    state.zoom = 1;
    state.viewBox = null;
    renderTree();
    renderBreadcrumbs();
    renderDiagram();
    renderInspector();
  }
  function renderBreadcrumbs() {
    const container = $("breadcrumbs"); container.replaceChildren();
    state.path.forEach((id, index) => {
      if (index) { const separator = document.createElement("span"); separator.className = "crumb-separator"; separator.textContent = "›"; container.append(separator); }
      const button = document.createElement("button"); button.textContent = state.diagrams[id]?.title || id;
      button.addEventListener("click", () => navigate(id, state.path.slice(0, index + 1)));
      container.append(button);
    });
  }
  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
    return element;
  }
  function diagramDimensions(diagram) {
    const nodes = diagram.nodes || [];
    return {
      width: diagram.width || Math.max(600, ...nodes.map((node) => (node.x || 0) + (node.w || 120) + 35)),
      height: diagram.height || Math.max(260, ...nodes.map((node) => (node.y || 0) + (node.h || 64) + 40)),
    };
  }
  function applyViewBox() {
    const diagram = state.diagrams[state.diagram]; if (!diagram) return;
    const size = diagramDimensions(diagram);
    if (!state.viewBox) state.viewBox = { x: -12, y: -10, w: size.width + 24, h: size.height + 20 };
    const v = state.viewBox;
    $("diagram").setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
    $("zoomValue").textContent = `${Math.round(state.zoom * 100)}%`;
  }
  function zoom(factor) {
    const next = Math.min(4, Math.max(0.5, state.zoom * factor));
    const ratio = state.zoom / next;
    const v = state.viewBox;
    if (!v) return;
    const w = v.w * ratio, h = v.h * ratio;
    state.viewBox = { x: v.x + (v.w - w) / 2, y: v.y + (v.h - h) / 2, w, h };
    state.zoom = next;
    applyViewBox();
  }
  function renderDiagram() {
    const diagram = state.diagrams[state.diagram]; if (!diagram) return;
    $("diagramTitle").textContent = diagram.title;
    $("diagramDescription").textContent = diagram.description || "点击模块进入内部模型，点击信号连线接入示波器。";
    $("sourceLabel").textContent = diagram.source || "数学模型 ↔ 代码";
    const svg = $("diagram"); svg.replaceChildren();
    const defs = svgElement("defs");
    for (const [id, fill] of [["arrow", "#89a1b9"], ["arrowActive", "#1a92a2"]]) {
      const marker = svgElement("marker", { id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
      marker.append(svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", fill })); defs.append(marker);
    }
    svg.append(defs);
    const nodes = new Map((diagram.nodes || []).map((node) => [node.id, { ...node, x: Number(node.x) || 0, y: Number(node.y) || 0, w: node.w || 120, h: node.h || 64 }]));
    const port = (node) => {
      const radius = ["sum", "operator", "product"].includes(node.kind) ? Math.min(node.w, node.h) / 2 - 2 : null;
      return { left: node.x + (radius === null ? 0 : node.w / 2 - radius), right: node.x + (radius === null ? node.w : node.w / 2 + radius), top: node.y + (radius === null ? 0 : node.h / 2 - radius), bottom: node.y + (radius === null ? node.h : node.h / 2 + radius), cx: node.x + node.w / 2, cy: node.y + node.h / 2 };
    };
    (diagram.edges || []).forEach((edge, edgeIndex) => {
      const from = nodes.get(edge.from), to = nodes.get(edge.to); if (!from || !to) return;
      const a = port(from), b = port(to);
      let x1 = a.right, y1 = a.cy, x2 = b.left, y2 = b.cy;
      let path;
      if (Array.isArray(edge.points) && edge.points.length > 1) {
        path = edge.points.map((point, i) => `${i ? "L" : "M"} ${Array.isArray(point) ? point.join(" ") : `${point.x} ${point.y}`}`).join(" ");
      } else if (to.x >= from.x + from.w - 2) {
        const middle = (x1 + x2) / 2;
        path = `M ${x1} ${y1} H ${middle} V ${y2} H ${x2}`;
      } else if (Math.abs(to.y - from.y) < 3 && to.x + to.w < from.x) {
        x1 = a.left; x2 = b.right;
        path = `M ${x1} ${y1} H ${x2}`;
      } else if (Math.abs(to.x - from.x) < from.w / 2 && to.y > from.y + from.h) {
        x1 = a.cx; y1 = a.bottom; x2 = b.cx; y2 = b.top;
        path = `M ${x1} ${y1} V ${(y1 + y2) / 2} H ${x2} V ${y2}`;
      } else {
        x1 = a.cx; y1 = a.bottom; x2 = b.cx; y2 = b.bottom;
        const lane = Math.max(y1, y2) + 22 + (edgeIndex % 3) * 11;
        path = `M ${x1} ${y1} V ${lane} H ${x2} V ${y2}`;
      }
      const group = svgElement("g", { class: `diagram-edge${truthSignal(edge.signal) || /真实|仅评价/.test(edge.label || "") ? " truth" : ""}`, "data-signal": edge.signal || "" });
      const wire = svgElement("path", { class: "wire", d: path, "marker-end": "url(#arrow)" });
      const hit = svgElement("path", { class: "wire-hit", d: path });
      group.append(wire, hit);
      if (edge.label || edge.signal) {
        const text = svgElement("text", { class: "wire-label", x: (x1 + x2) / 2, y: Math.min(y1, y2) - 7, "text-anchor": "middle" });
        text.textContent = edge.label || label(edge.signal); group.append(text);
      }
      const title = svgElement("title"); title.textContent = edge.signal ? `${label(edge.signal)} · 点击监测` : edge.label || "信号连接"; group.append(title);
      if (edge.signal && state.signals[edge.signal]) {
        group.setAttribute("tabindex", "0"); group.setAttribute("role", "button"); group.setAttribute("aria-label", `监测 ${label(edge.signal)}`);
        group.addEventListener("click", () => setProbe(edge.signal, true));
        group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setProbe(edge.signal, true); } });
      }
      svg.append(group);
    });
    for (const node of nodes.values()) {
      const kind = node.kind || "block";
      const group = svgElement("g", { class: `diagram-node kind-${kind}`, transform: `translate(${node.x} ${node.y})`, "data-node": node.id, "data-signal": node.signal || "", tabindex: "0", role: "button", "aria-label": `${node.label}${node.child ? "，打开内部模型" : node.signal ? "，监测信号" : "，查看说明"}` });
      const title = svgElement("title"); title.textContent = `${node.label}${node.child ? " · 点击展开" : node.signal ? ` · ${label(node.signal)}` : ""}`; group.append(title);
      if (kind === "sum" || kind === "operator" || kind === "product") {
        group.append(svgElement("circle", { class: "node-shape", cx: node.w / 2, cy: node.h / 2, r: Math.min(node.w, node.h) / 2 - 2 }));
      } else if (kind === "gain") {
        group.append(svgElement("polygon", { class: "node-shape", points: `2,2 ${node.w - 2},${node.h / 2} 2,${node.h - 2}` }));
      } else {
        group.append(svgElement("rect", { class: "node-shape", width: node.w, height: node.h, rx: kind === "integrator" ? 2 : 5 }));
        if (node.child) group.append(svgElement("rect", { class: "node-band", x: 1, y: 1, width: node.w - 2, height: 5, rx: 3 }));
      }
      const lines = asText(node.label).split("\n");
      const round = ["sum", "operator", "product"].includes(kind);
      const labelY = node.h / 2 - (node.signal ? 6 : 0) - (lines.length - 1) * 7;
      const text = svgElement("text", { class: "node-label", x: kind === "gain" ? node.w * .37 : node.w / 2, y: round ? node.h / 2 + 1 : labelY, "dominant-baseline": "middle" });
      if (round) {
        text.textContent = kind === "sum" ? (/−|-/.test(lines[0]) ? "+ −" : "+") : /÷|\//.test(lines[0]) ? "÷" : "×";
        const caption = svgElement("text", { class: "node-caption", x: node.w / 2, y: -12, "text-anchor": "middle" }); caption.textContent = lines.filter((line) => !/^[+−\-×÷\s]+$/.test(line)).join(" "); group.append(caption);
      } else lines.forEach((line, index) => { const tspan = svgElement("tspan", { x: kind === "gain" ? node.w * .37 : node.w / 2, dy: index ? 19 : 0 }); tspan.textContent = line; text.append(tspan); });
      group.append(text);
      if (node.signal) {
        const value = svgElement("text", { class: "node-value", x: node.w / 2, y: round ? node.h + 16 : node.h - 9, "data-value-signal": node.signal }); value.textContent = "—";
        value.addEventListener("click", (event) => { event.stopPropagation(); setProbe(node.signal, true); }); group.append(value);
      }
      if (node.child) { const child = svgElement("text", { class: "node-child", x: node.w - 7, y: 15 }); child.textContent = "⊞"; group.append(child); }
      const action = () => {
        if (node.signal) setProbe(node.signal, false);
        if (node.child) navigate(node.child);
        else renderInspector(node);
      };
      group.addEventListener("click", action);
      group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); action(); } });
      svg.append(group);
    }
    applyViewBox(); updateDiagramValues();
  }
  function updateDiagramValues() {
    const sample = selectedSample();
    document.querySelectorAll("[data-value-signal]").forEach((element) => {
      const key = element.getAttribute("data-value-signal");
      element.textContent = `${format(sample[key], 2)}${unit(key) ? ` ${unit(key)}` : ""}`;
    });
    document.querySelectorAll(".diagram-node,.diagram-edge").forEach((element) => {
      const active = !!state.probe && element.getAttribute("data-signal") === state.probe;
      element.classList.toggle("selected", active);
      const wire = element.querySelector(".wire"); if (wire) wire.setAttribute("marker-end", active ? "url(#arrowActive)" : "url(#arrow)");
    });
  }

  function renderSignals() {
    const container = $("signalList"); container.replaceChildren();
    const search = $("signalSearch").value.trim().toLowerCase();
    const groups = new Map();
    for (const [key, meta] of Object.entries(state.signals)) {
      if (search && !`${key} ${meta.label} ${meta.category}`.toLowerCase().includes(search)) continue;
      const category = meta.category || "可测信号";
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push([key, meta]);
    }
    for (const [category, signals] of groups) {
      const heading = document.createElement("div"); heading.className = "signal-category"; heading.textContent = categoryLabel(category); container.append(heading);
      for (const [key, meta] of signals) {
        const row = document.createElement("label"); row.className = `signal-row${state.probe === key ? " focused" : ""}`;
        const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.checked = state.selected.has(key); checkbox.setAttribute("aria-label", `示波器监测 ${meta.label}`);
        checkbox.addEventListener("change", () => { checkbox.checked ? state.selected.add(key) : state.selected.delete(key); if (checkbox.checked) state.probe = key; renderSignals(); renderChips(); renderProbe(); updateDiagramValues(); drawScope(); });
        const name = document.createElement("span"); name.className = "signal-name"; name.textContent = meta.label; name.title = `${meta.label} (${key})`;
        const units = document.createElement("span"); units.className = "signal-unit"; units.textContent = meta.unit;
        row.append(checkbox, name, units); container.append(row);
      }
    }
    $("probeCount").textContent = `${state.selected.size} 已选`;
  }
  function renderChips() {
    const container = $("traceChips"); container.replaceChildren();
    for (const key of state.selected) {
      const chip = document.createElement("span"); chip.className = `trace-chip${state.probe === key ? " selected" : ""}`; chip.style.setProperty("--trace-color", color(key));
      const line = document.createElement("i"); const name = document.createElement("span"); name.textContent = label(key);
      chip.setAttribute("tabindex", "0"); chip.setAttribute("role", "button"); chip.setAttribute("aria-label", `查看 ${label(key)}`);
      chip.addEventListener("click", () => setProbe(key));
      chip.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setProbe(key); } });
      const remove = document.createElement("button"); remove.textContent = "×"; remove.setAttribute("aria-label", `移除 ${label(key)} 曲线`);
      remove.addEventListener("click", (event) => { event.stopPropagation(); state.selected.delete(key); renderSignals(); renderChips(); drawScope(); });
      chip.append(line, name, remove); container.append(chip);
    }
  }
  let inspectedNode = null;
  function renderInspector(node = null) {
    inspectedNode = node;
    const diagram = state.diagrams[state.diagram] || {};
    $("inspectorTitle").textContent = node?.label || diagram.title || "系统模型";
    $("inspectorDescription").textContent = node?.description || diagram.description || "";
    $("formula").textContent = asText(node?.formula || diagram.formula || "选择模块查看方程。");
    $("inspectorSource").textContent = asText(node?.source || diagram.source || "—");
    renderModuleValues();
  }
  function renderModuleValues() {
    const container = $("moduleValues"); const parametersOpen = !!container.querySelector(".motor-parameters")?.open; container.replaceChildren();
    const diagram = state.diagrams[state.diagram] || {};
    const keys = inspectedNode?.signal ? [inspectedNode.signal] : [...new Set((diagram.nodes || []).map((node) => node.signal).filter(Boolean))].slice(0, 5);
    const sample = selectedSample();
    for (const key of keys) {
      const row = document.createElement("div"); row.className = "module-value";
      const name = document.createElement("span"); name.textContent = label(key);
      const value = document.createElement("strong"); value.textContent = `${format(sample[key], 3)} ${unit(key)}`;
      row.append(name, value); container.append(row);
    }
    if (["motor", "electrical", "mechanics", "flux_dynamics", "current_dynamics", "torque"].includes(state.diagram) && Object.keys(state.motorParameters).length) {
      const details = document.createElement("details"); details.className = "motor-parameters";
      details.open = parametersOpen;
      const summary = document.createElement("summary"); summary.textContent = "电机参数（SI 单位）"; details.append(summary);
      const metadata = { rs: ["定子电阻 Rs", "Ω"], lm: ["励磁电感 Lm", "H"], ls: ["定子自感 Ls", "H"], lr: ["转子自感 Lr", "H"], poles: ["极对数 p", ""], inertia: ["转动惯量 J", "kg·m²"], friction: ["黏性摩擦 B", "N·m·s/rad"] };
      for (const [key, [name, units]] of Object.entries(metadata)) {
        if (!number(state.motorParameters[key])) continue;
        const row = document.createElement("div"); row.className = "module-value";
        const text = document.createElement("span"); text.textContent = name;
        const value = document.createElement("strong"); value.textContent = `${format(state.motorParameters[key], 4)} ${units}`;
        row.append(text, value); details.append(row);
      }
      container.append(details);
    }
  }
  function renderProbe() {
    const sample = selectedSample();
    const meta = state.signals[state.probe] || {};
    $("probeTitle").textContent = meta.label || "请选择信号";
    $("probeValue").textContent = format(sample[state.probe], 4);
    $("probeUnit").textContent = meta.unit || "";
    $("probeCategory").textContent = categoryLabel(meta.category);
    $("probeTimestamp").textContent = `t = ${format(sample.time || 0, 4)} s`;
    $("probeDescription").textContent = meta.description || (truthSignal(state.probe) ? "评价通道：显示仿真真值或由真值计算的指标，辨识器无法读取这些数据。" : "");
    $("viewMode").textContent = state.live ? "● 最新采样" : "◷ 历史采样";
    $("viewMode").classList.toggle("historical", !state.live);
    $("latestButton").classList.toggle("active", state.live);
    $("cursorTime").textContent = `${state.live ? "最新" : "历史"} t = ${format(sample.time || 0, 4)} s`;
    $("timeCursor").max = Math.max(0, state.history.length - 1);
    $("timeCursor").value = state.cursor;
    $("timeCursor").disabled = state.history.length < 2;
    $("historyCount").textContent = `${Math.max(0, state.history.length - (state.history[0]?.time === 0 ? 1 : 0)).toLocaleString()} 个采样`;
  }
  const metricLabels = {
    rr_rmse: ["电阻 RMSE", "Ω"], rr_rmse_ohm: ["电阻 RMSE", "Ω"], resistance_rmse: ["电阻 RMSE", "Ω"],
    rr_mae: ["电阻平均绝对误差", "Ω"], rr_error_pct: ["当前电阻误差", "%"], final_error_pct: ["末值电阻误差", "%"],
    rr_relative_error_pct: ["当前电阻误差", "%"], mean_relative_error_pct: ["平均电阻相对误差", "%"], rr_mape_pct: ["平均电阻相对误差", "%"],
    tail_rr_error_pct: ["末段电阻误差", "%"], tail_mean_error_pct: ["末段电阻误差", "%"], tail_mean_relative_error_pct: ["末段电阻误差", "%"],
    speed_rmse: ["转速 RMSE", "rpm"], speed_rmse_rpm: ["转速 RMSE", "rpm"], speed_error_rpm: ["当前转速误差", "rpm"],
    flux_angle_rmse_deg: ["磁链定向 RMSE", "°"], samples: ["采样数量", ""], sample_count: ["采样数量", ""],
    elapsed: ["仿真时长", "s"], time: ["仿真时长", "s"], wall_time: ["计算耗时", "s"], convergence_time: ["收敛时间", "s"],
    tail_relative_mae_percent: ["末 0.4 s 电阻平均误差", "%"], tail_aligned_relative_mae_percent: ["时间对齐后的末段误差", "%"],
    full_rmse_ohm: ["全程电阻 RMSE", "Ω"], tail_speed_rmse_rpm: ["末段转速 RMSE", "rpm"],
    tail_flux_angle_rms_deg: ["末段磁链偏角 RMS", "°"], peak_current_a: ["全程电流峰值", "A"],
    voltage_saturation_percent: ["电压限幅占比", "%"], final_rr_est: ["当前估计电阻", "Ω"], final_rr_true: ["当前真实电阻", "Ω"],
    duration: ["已仿真时间", "s"], tail_window_seconds: ["末段评价窗口", "s"],
  };
  function renderMetrics() {
    const container = $("metrics"); container.replaceChildren();
    const preferred = ["tail_relative_mae_percent", "tail_aligned_relative_mae_percent", "full_rmse_ohm", "tail_speed_rmse_rpm", "tail_flux_angle_rms_deg", "peak_current_a", "voltage_saturation_percent", "samples"];
    const entries = preferred.some((key) => key in state.metrics && key !== "samples") ? preferred.filter((key) => key in state.metrics).map((key) => [key, state.metrics[key]]) : Object.entries(state.metrics);
    for (const [key, raw] of entries) {
      if (["notes", "note", "description", "mode"].includes(key)) continue;
      const object = raw !== null && typeof raw === "object";
      const value = object ? raw.value : raw;
      if (!(number(value) || typeof value === "string")) continue;
      const translated = metricLabels[key] || [key, ""];
      const row = document.createElement("div"); row.className = "metric-row";
      const name = document.createElement("span"); name.textContent = object ? raw.label || translated[0] : translated[0];
      const result = document.createElement("strong"); result.textContent = `${number(value) ? format(value, /samples|count/.test(key) ? 0 : 3) : value}${object ? raw.unit ? ` ${raw.unit}` : "" : translated[1] ? ` ${translated[1]}` : ""}`;
      row.append(name, result); container.append(row);
    }
    if (number(state.metrics.tail_window_seconds)) {
      const note = document.createElement("p"); note.className = "explanation"; note.textContent = `末段窗口：最近 ${format(state.metrics.tail_window_seconds, 3)} s。误差由独立真值评价；末段精度不代表全部工况。`; container.append(note);
    }
    if (!container.children.length) { const hint = document.createElement("p"); hint.className = "explanation"; hint.textContent = "运行后显示估计误差和控制指标。"; container.append(hint); }
  }

  const fields = [
    ["duration", "仿真总时长 / s", .01, 30, .1, "总时长使用仿真时间。"],
    ["sample_time", "采样周期 Ts / s", .0001, .001, .0001, "控制器与辨识器按此周期更新。"],
    ["plant_substeps", "每次采样的物理积分步数", 1, 20, 1, "积分 Δt = Ts / 积分步数。"],
    ["target_rpm", "目标转速 / rpm", 0, 1500, 50, "速度外环的给定值。"],
    ["mode", "控制器电阻参数来源"],
    ["rr_final", "变化后转子电阻 / Ω", .2, 2.5, .05, "只配置被测电机；辨识器不读取此值。"],
    ["load_final", "变化后负载转矩 / N·m", 0, 15, .5, "用于测试负载扰动。"],
    ["noise", "测量噪声幅度", 0, 1, .001, "按引擎定义应用于采样链路。"],
    ["current_noise", "电流噪声标准差 / A", 0, 2, .01, "独立高斯噪声。", "采样与传感器"],
    ["voltage_noise", "电压噪声标准差 / V", 0, 10, .01, "", "采样与传感器"],
    ["speed_noise", "转速噪声标准差 / rad·s⁻¹", 0, 5, .01, "机械角速度的测量噪声。", "采样与传感器"],
    ["current_bias", "电流偏置 / A", -2, 2, .01, "", "采样与传感器"],
    ["voltage_bias", "电压偏置 / V", -10, 10, .01, "", "采样与传感器"],
    ["sensor_delay_steps", "传感器延迟 / 采样步", 0, 20, 1, "延迟 = 步数 × Ts。", "采样与传感器"],
    ["adc_bits", "ADC 位数", 0, 24, 1, "0 表示不进行量化。", "采样与传感器"],
    ["current_range", "电流传感器量程 / ±A", 1, 200, 1, "", "采样与传感器"],
    ["voltage_range", "电压传感器量程 / ±V", 10, 1000, 10, "", "采样与传感器"],
    ["speed_kp", "速度 PI · Kp", .001, 2, .01, "", "FOC 与反馈环"],
    ["speed_ki", "速度 PI · Ki", 0, 10, .1, "", "FOC 与反馈环"],
    ["current_bandwidth_hz", "电流环设计带宽 / Hz", 20, 250, 10, "用于计算 d/q 电流 PI 增益。", "FOC 与反馈环"],
    ["id_ref", "励磁电流指令 / A", .5, 8, .1, "须小于电流指令限幅。", "FOC 与反馈环"],
    ["current_limit", "电流指令限幅 / A", 2, 20, .5, "限制电流指令；并非硬件过流保护。", "FOC 与反馈环"],
    ["dc_bus_voltage", "直流母线电压 / V", 100, 800, 10, "", "FOC 与反馈环"],
    ["magnetization_time", "预励磁时间 / s", .15, 5, .05, "", "FOC 与反馈环"],
    ["speed_ramp_time", "转速指令爬升时间 / s", .1, 10, .1, "", "FOC 与反馈环"],
    ["rr_initial", "被测电机初始电阻 / Ω", .2, 2.5, .05, "", "工况与辨识初值"],
    ["initial_estimate", "辨识器初始估计 / Ω", .1, 3, .05, "可故意偏离真实电阻以观察收敛。", "工况与辨识初值"],
    ["nominal_rr", "控制器标称电阻 / Ω", .2, 2.5, .05, "固定参数模式使用此值。", "工况与辨识初值"],
    ["ramp_start", "电阻开始变化 / s", 0, 30, .1, "", "工况与辨识初值"],
    ["ramp_end", "电阻变化结束 / s", .01, 30, .1, "应晚于开始变化时刻。", "工况与辨识初值"],
    ["load_initial", "初始负载 / N·m", 0, 15, .5, "", "工况与辨识初值"],
    ["load_step", "负载突变时刻 / s", 0, 30, .1, "", "工况与辨识初值"],
    ["adaptation_start", "启用参数补偿时刻 / s", 0, 30, .1, "仅在线辨识补偿模式使用。", "工况与辨识初值"],
    ["adaptation_tau", "补偿参数滤波时间常数 / s", .01, 5, .01, "", "工况与辨识初值"],
    ["seed", "测量噪声随机种子", 0, 4294967295, 1, "相同配置与种子便于重复比较。", "工况与辨识初值"],
  ];
  function renderSettings() {
    const container = $("configFields"); container.replaceChildren();
    const sections = new Map();
    for (const [key, name, min, max, step, hint, section] of fields) {
      if (!(key in state.config || key in state.defaults)) continue;
      const current = state.config[key] ?? state.defaults[key];
      const field = document.createElement("label"); field.className = "settings-field";
      const title = document.createElement("span"); title.textContent = name; field.append(title);
      let input;
      if (key === "mode") {
        input = document.createElement("select");
        for (const [value, text] of [["fixed", "固定初始电阻"], ["adaptive", "在线辨识补偿"], ["oracle", "真实值参考（仅评价）"]]) {
          const option = document.createElement("option"); option.value = value; option.textContent = text; input.append(option);
        }
        input.value = current;
      } else if (typeof current === "boolean") {
        input = document.createElement("select");
        for (const [value, text] of [["true", "开启"], ["false", "关闭"]]) { const option = document.createElement("option"); option.value = value; option.textContent = text; input.append(option); }
        input.value = String(current); input.dataset.boolean = "true";
      } else {
        input = document.createElement("input"); input.type = "number"; input.value = current; input.min = min; input.max = max; input.step = ["plant_substeps", "sensor_delay_steps", "adc_bits", "seed"].includes(key) ? "1" : "any"; input.required = true;
      }
      input.name = key; field.append(input);
      if (hint) { const helper = document.createElement("small"); helper.textContent = hint; field.append(helper); }
      if (section) {
        if (!sections.has(section)) { const details = document.createElement("details"); details.className = "config-section"; const summary = document.createElement("summary"); summary.textContent = section; details.append(summary); container.append(details); sections.set(section, details); }
        sections.get(section).append(field);
      } else container.append(field);
    }
  }
  function switchTab(settings) {
    $("modelTab").classList.toggle("active", !settings); $("settingsTab").classList.toggle("active", settings);
    $("modelTab").setAttribute("aria-selected", String(!settings)); $("settingsTab").setAttribute("aria-selected", String(settings));
    $("modelPanel").hidden = settings; $("settingsPanel").hidden = !settings;
  }

  let scopeBounds = null;
  function scopeRange() {
    const end = Number(state.history[state.history.length - 1]?.time || state.snapshot.time || 0);
    const period = $("scopeWindow").value;
    if (period === "all") return { start: 0, end: Math.max(end, 0.01) };
    const width = Number(period);
    const anchor = state.live ? end : Number(selectedSample().time || 0);
    const right = state.live ? Math.max(width, end) : Math.max(width, Math.min(end, anchor + width / 2));
    return { start: Math.max(0, right - width), end: right };
  }
  function drawScope() {
    const canvas = $("scopeCanvas"); const wrap = $("scopeWrap");
    const rect = wrap.getBoundingClientRect(); if (!rect.width || !rect.height) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = rect.width, height = rect.height;
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) { canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr); }
    const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, width, height);
    const groups = new Map();
    for (const key of state.selected) { const units = unit(key) || "无量纲"; if (!groups.has(units)) groups.set(units, []); groups.get(units).push(key); }
    const empty = state.history.length < 2 || !groups.size;
    $("scopeEmpty").hidden = !empty;
    if (empty) { scopeBounds = null; return; }
    const range = scopeRange(); const plotLeft = 51, plotRight = width - 17, top = 8, bottom = height - 24;
    const trackHeight = Math.max(20, (bottom - top) / groups.size);
    let first = state.history.findIndex((s) => s.time >= range.start); if (first < 0) first = state.history.length - 1; first = Math.max(0, first - 1);
    let last = state.history.length - 1;
    for (let i = first; i < state.history.length; i++) if (state.history[i].time > range.end) { last = i; break; }
    const x = (t) => plotLeft + (t - range.start) / (range.end - range.start) * (plotRight - plotLeft);
    scopeBounds = { ...range, left: plotLeft, right: plotRight, width, height };
    ctx.font = '9px "Segoe UI", "Microsoft YaHei", sans-serif'; ctx.textBaseline = "middle";
    let track = 0;
    for (const [units, keys] of groups) {
      const yTop = top + track * trackHeight + 7, yBottom = top + (track + 1) * trackHeight - 12;
      let min = Infinity, max = -Infinity;
      for (let i = first; i <= last; i++) for (const key of keys) if (number(state.history[i][key])) { min = Math.min(min, state.history[i][key]); max = Math.max(max, state.history[i][key]); }
      if (!Number.isFinite(min)) { min = 0; max = 1; }
      const padding = Math.max((max - min) * .13, Math.max(Math.abs(max), Math.abs(min)) * .025, .001);
      min -= padding; max += padding;
      const y = (v) => yBottom - (v - min) / (max - min) * (yBottom - yTop);
      ctx.fillStyle = track % 2 ? "#fafcfe" : "#fff"; ctx.fillRect(plotLeft, yTop - 7, plotRight - plotLeft, trackHeight);
      for (let line = 0; line <= 2; line++) {
        const gy = yTop + (yBottom - yTop) * line / 2;
        ctx.strokeStyle = "#e9eff5"; ctx.lineWidth = 1; ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(plotLeft, gy); ctx.lineTo(plotRight, gy); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "#93a3b4"; ctx.textAlign = "right";
        const value = max - (max - min) * line / 2;
        ctx.fillText(format(value, Math.abs(max) > 100 ? 0 : Math.abs(max) > 10 ? 1 : 2), plotLeft - 7, gy);
      }
      ctx.fillStyle = "#889aab"; ctx.textAlign = "left"; ctx.fillText(units, plotLeft + 5, yTop - 2);
      ctx.save(); ctx.beginPath(); ctx.rect(plotLeft, yTop - 2, plotRight - plotLeft, yBottom - yTop + 4); ctx.clip();
      for (const key of keys) {
        ctx.strokeStyle = color(key); ctx.lineWidth = key === state.probe ? 1.8 : 1.3;
        ctx.setLineDash(/_true$|_ref/.test(key) ? [5, 3] : []); ctx.beginPath();
        let started = false;
        let bucket = null;
        const dense = last - first > (plotRight - plotLeft) * 2;
        const point = (entry) => { if (started) ctx.lineTo(entry.x, entry.y); else { ctx.moveTo(entry.x, entry.y); started = true; } };
        const flush = () => {
          if (!bucket) return;
          const unique = new Map([bucket.first, bucket.min, bucket.max, bucket.last].map((entry) => [entry.index, entry]));
          [...unique.values()].sort((a, b) => a.index - b.index).forEach(point);
          bucket = null;
        };
        for (let i = first; i <= last; i++) {
          const sample = state.history[i]; const value = sample[key];
          if (!number(value)) { flush(); started = false; continue; }
          const px = x(sample.time), py = y(value);
          if (!dense) point({ x: px, y: py });
          else {
            const column = Math.floor(px); const entry = { x: px, y: py, index: i };
            if (bucket && bucket.column !== column) flush();
            if (!bucket) bucket = { column, first: entry, min: entry, max: entry, last: entry };
            else { bucket.last = entry; if (py < bucket.min.y) bucket.min = entry; if (py > bucket.max.y) bucket.max = entry; }
          }
        }
        flush();
        ctx.stroke(); ctx.setLineDash([]);
      }
      ctx.restore(); track += 1;
    }
    for (let tick = 0; tick <= 5; tick++) {
      const tx = plotLeft + (plotRight - plotLeft) * tick / 5;
      ctx.strokeStyle = "#e8eef4"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(tx, top); ctx.lineTo(tx, bottom); ctx.stroke();
      ctx.fillStyle = "#92a2b3"; ctx.textAlign = tick === 0 ? "left" : tick === 5 ? "right" : "center";
      ctx.fillText(`${format(range.start + (range.end - range.start) * tick / 5, 2)} s`, tx, height - 10);
    }
    const cursor = selectedSample();
    if (number(cursor.time) && cursor.time >= range.start && cursor.time <= range.end) {
      const cx = x(cursor.time); ctx.strokeStyle = state.live ? "#5c9bcc" : "#cf984c"; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(cx, top); ctx.lineTo(cx, bottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = state.live ? "#5c9bcc" : "#cf984c"; ctx.beginPath(); ctx.moveTo(cx - 4, top); ctx.lineTo(cx + 4, top); ctx.lineTo(cx, top + 6); ctx.closePath(); ctx.fill();
    }
  }
  function cursorFromPosition(event) {
    if (!scopeBounds || state.history.length < 2) return;
    const rect = $("scopeCanvas").getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (event.clientX - rect.left - scopeBounds.left) / (scopeBounds.right - scopeBounds.left)));
    const time = scopeBounds.start + fraction * (scopeBounds.end - scopeBounds.start);
    let left = 0, right = state.history.length - 1;
    while (left < right) { const middle = Math.floor((left + right) / 2); if (state.history[middle].time < time) left = middle + 1; else right = middle; }
    if (left && Math.abs(state.history[left - 1].time - time) < Math.abs(state.history[left].time - time)) left--;
    state.cursor = left; state.live = false; scheduleRender();
  }
  function scheduleRender() {
    if (state.renderPending) return;
    state.renderPending = true;
    requestAnimationFrame(() => { state.renderPending = false; renderLive(); });
  }
  function renderLive() {
    const config = state.config; const snapshot = state.snapshot;
    const ts = Number(config.sample_time || .0005);
    $("simTime").replaceChildren(document.createTextNode(`${format(snapshot.time || 0, 4)} `)); const seconds = document.createElement("small"); seconds.textContent = "s"; $("simTime").append(seconds);
    $("sampleNumber").textContent = `第 ${Math.round(snapshot.sample_index ?? ((snapshot.time || 0) / ts)).toLocaleString()} 次采样`;
    $("tsValue").textContent = niceTime(ts);
    $("dtValue").textContent = niceTime(Number(snapshot.integration_step || ts / (config.plant_substeps || 1)));
    $("durationValue").textContent = `${format(Number(config.duration || 0), 2)} s`;
    renderProbe(); updateDiagramValues(); renderModuleValues(); renderMetrics(); drawScope();
  }

  $("runButton").addEventListener("click", () => state.running ? pause() : start());
  $("stepButton").addEventListener("click", () => advance(1));
  $("batchButton").addEventListener("click", () => advance(100));
  $("resetButton").addEventListener("click", () => reset({ ...state.config }));
  $("dismissError").addEventListener("click", () => { $("errorBanner").hidden = true; });
  $("modelTab").addEventListener("click", () => switchTab(false));
  $("settingsTab").addEventListener("click", () => switchTab(true));
  $("signalSearch").addEventListener("input", renderSignals);
  $("settingsForm").addEventListener("submit", (event) => {
    event.preventDefault(); const config = { ...state.config };
    for (const input of $("settingsForm").querySelectorAll("input[name],select[name]")) config[input.name] = input.dataset.boolean ? input.value === "true" : input.name === "mode" ? input.value : Number(input.value);
    reset(config);
  });
  $("zoomIn").addEventListener("click", () => zoom(1.25));
  $("zoomOut").addEventListener("click", () => zoom(.8));
  $("fitDiagram").addEventListener("click", () => { state.zoom = 1; state.viewBox = null; applyViewBox(); });
  $("diagram").addEventListener("pointerdown", (event) => {
    if (event.target.closest(".diagram-node,.diagram-edge")) return;
    state.drag = { x: event.clientX, y: event.clientY, ...state.viewBox, px: event.clientX, py: event.clientY };
    $("diagram").setPointerCapture(event.pointerId);
  });
  $("diagram").addEventListener("pointermove", (event) => {
    if (!state.drag) return; const rect = $("diagram").getBoundingClientRect();
    const scale = Math.max(state.drag.w / rect.width, state.drag.h / rect.height);
    state.viewBox.x = state.drag.x - (event.clientX - state.drag.px) * scale;
    state.viewBox.y = state.drag.y - (event.clientY - state.drag.py) * scale;
    applyViewBox();
  });
  $("diagram").addEventListener("pointerup", () => { state.drag = null; });
  $("diagram").addEventListener("pointercancel", () => { state.drag = null; });
  $("diagram").addEventListener("wheel", (event) => { if (event.ctrlKey || event.metaKey) { event.preventDefault(); zoom(event.deltaY < 0 ? 1.1 : 1 / 1.1); } }, { passive: false });
  $("scopeWindow").addEventListener("change", drawScope);
  $("latestButton").addEventListener("click", () => { state.live = true; state.cursor = Math.max(0, state.history.length - 1); scheduleRender(); });
  $("timeCursor").addEventListener("input", () => { state.live = false; state.cursor = Number($("timeCursor").value); scheduleRender(); });
  let scrubbing = false;
  $("scopeCanvas").addEventListener("pointerdown", (event) => { scrubbing = true; $("scopeCanvas").setPointerCapture(event.pointerId); cursorFromPosition(event); });
  $("scopeCanvas").addEventListener("pointermove", (event) => { if (scrubbing) cursorFromPosition(event); });
  $("scopeCanvas").addEventListener("pointerup", () => { scrubbing = false; });
  $("scopeCanvas").addEventListener("pointercancel", () => { scrubbing = false; });
  $("scopeCanvas").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || !state.history.length) return;
    event.preventDefault(); state.live = event.key === "End";
    state.cursor = event.key === "Home" ? 0 : event.key === "End" ? state.history.length - 1 : Math.max(0, Math.min(state.history.length - 1, state.cursor + (event.key === "ArrowRight" ? 1 : -1)));
    scheduleRender();
  });
  new ResizeObserver(() => scheduleRender()).observe($("scopeWrap"));
  window.addEventListener("beforeunload", pause);

  async function init() {
    try {
      const data = await api("/api/config");
      state.defaults = data.defaults || {}; state.config = { ...state.defaults, ...(data.config || {}) };
      state.signals = data.signals || {}; state.diagrams = data.diagrams || {};
      state.selected = new Set(["speed_rpm", "speed_ref_rpm", "rr_est", "rr_true", "iq"].filter((key) => state.signals[key]));
      if (!state.signals[state.probe]) state.probe = Object.keys(state.signals)[0] || "";
      acceptState(data);
      if (Number(data.snapshot?.time || 0) > 0) { state.history = []; acceptState(await api("/api/history")); }
      if (!data.snapshot) acceptState(await api("/api/state"));
      navigate(state.diagrams.system ? "system" : Object.keys(state.diagrams)[0], state.diagrams.system ? ["system"] : [Object.keys(state.diagrams)[0]]);
      renderSignals(); renderChips(); renderSettings(); updateControls(); scheduleRender();
      $("connectionStatus").textContent = "引擎已连接";
    } catch (error) { showError(error); $("statusText").textContent = "连接失败"; $("connectionStatus").textContent = "请检查服务"; }
  }
  init();
})();
