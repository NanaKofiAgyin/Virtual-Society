/** Virtual Society Viewer controller: zoom/pan, minimap, legend, layers, charts, timeline. */
(() => {
  const $ = (id) => document.getElementById(id);
  const canvas = $("world-canvas");
  const minimap = $("minimap");
  const renderer = window.WorldCanvas.create(canvas, minimap);
  const el = {
    brain: $("brain-badge"), era: $("era-badge"), clock: $("clock-status"), pop: $("pop-bar"),
    layer: $("layer-select"), zoomIn: $("btn-zoom-in"), zoomOut: $("btn-zoom-out"), zoomReset: $("btn-zoom-reset"),
    legend: $("legend"),
    play: $("btn-play"), step: $("btn-step"), ff: $("btn-ff"), speed: $("speed-slider"), speedVal: $("speed-val"),
    save: $("btn-save"), load: $("btn-load"), reset: $("btn-reset"), toast: $("toast"),
    people: $("people-list"), inspector: $("inspector"), events: $("event-feed"),
    chartPop: $("chart-pop"), chartGenes: $("chart-genes"),
    phylo: $("phylo-tree"), phyloDetail: $("phylo-detail"),
    stagnation: $("stagnation-box"), timeline: $("timeline-box"),
    dlgLog: $("dialogue-log"), glossaries: $("culture-glossaries"), techTreeBox: $("tech-tree-box"),
    dlgPerson: $("dlg-filter-person"), dlgTopic: $("dlg-filter-topic"), dlgPlace: $("dlg-filter-place"),
  };

  const LEGEND_ITEMS = [
    ["Deep Ocean", "#134074"], ["Shallow Sea", "#2ec4b6"], ["River", "#3a86ff"],
    ["Beach", "#f4e2b8"], ["Desert", "#e2c07d"], ["Savanna", "#c5d86d"],
    ["Grassland", "#76c85b"], ["Forest", "#2d6a4f"], ["Jungle", "#15803d"],
    ["Taiga", "#3b7a6b"], ["Tundra", "#9db4ab"], ["Mountain", "#8d99ae"],
    ["Snow", "#f8fafc"], ["Settlement", "#facc15"],
  ];

  let mapData = null, layersData = null, stateData = null, historyData = null;
  let selectedId = null, hoveredId = null, selectedSpecies = null;
  let tickCounter = 0, rafId = null, dragging = false, movedDrag = false, lastDrag = null;

  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function showToast(msg) {
    el.toast.textContent = msg;
    setTimeout(() => { if (el.toast.textContent === msg) el.toast.textContent = ""; }, 2500);
  }

  async function api(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  const postJson = (url, body) => api(url, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });

  function renderLegend() {
    el.legend.innerHTML = LEGEND_ITEMS.map(([name, color]) =>
      `<span class="legend-item"><span class="swatch" style="background:${esc(color)}"></span>${esc(name)}</span>`
    ).join("");
  }

  async function fetchMapAndLayers(resetCam = false) {
    [mapData, layersData] = await Promise.all([api("/api/map"), api("/api/layers")]);
    renderer.setMap(mapData, layersData, resetCam);
  }

  function redraw() {
    if (renderer.draw(mapData, stateData, selectedId, hoveredId) && rafId === null) {
      rafId = requestAnimationFrame(() => { rafId = null; redraw(); });
    }
  }

  function renderHeader() {
    const env = stateData.environment;
    const live = stateData.llm_mode && stateData.llm_mode !== "mock";
    el.brain.textContent = live ? "Brain: Local model (Ollama)" : "Brain: Rule-based (mock)";
    el.era.textContent = stateData.society?.era || "Stone Age";
    el.clock.textContent =
      `Y${env.year} · ${env.season} D${env.day} · ${String(env.hour).padStart(2, "0")}:00 · ${env.weather}`
      + (env.active_event ? ` · [${env.active_event}]` : "");
    el.play.textContent = stateData.running ? "Pause" : "Play";
    el.play.classList.toggle("active", stateData.running);
    el.speed.value = String(stateData.speed);
    el.speedVal.textContent = Number(stateData.speed).toFixed(1);
    el.pop.innerHTML = Object.entries(stateData.counts)
      .filter(([, v]) => v > 0).slice(0, 8)
      .map(([k, v]) => `<span><strong>${esc(k)}</strong>: ${esc(v)}</span>`).join("");
  }

  function renderPeople() {
    const focused = document.activeElement?.dataset?.personId;
    el.people.innerHTML = stateData.humans.map((h) => {
      const cls = h.id === selectedId ? "person-btn selected" : "person-btn";
      const status = h.alive ? h.last_action : "dead";
      return `<li><button type="button" class="${cls}" data-person-id="${esc(h.id)}">`
        + `<span>${esc(h.name)} <span class="person-meta">(${esc(h.persona?.job)})</span></span>`
        + `<span class="person-meta">${esc(status)}</span></button></li>`;
    }).join("");
    if (focused) el.people.querySelector(`[data-person-id="${CSS.escape(focused)}"]`)?.focus();
  }

  function renderInspector() {
    const h = stateData.humans.find((x) => x.id === selectedId);
    if (!h) { el.inspector.textContent = "Select a villager to inspect."; return; }
    const bars = [
      ["Hunger", h.needs.hunger], ["Energy", h.needs.energy],
      ["Social", h.needs.social], ["Health", h.health],
    ].map(([label, val]) => {
      const pct = Math.max(0, Math.min(100, (Number(val) / 10) * 100));
      return `<div class="need-row"><span>${esc(label)}</span>`
        + `<div class="bar-bg"><div class="bar-fill${val < 3.5 ? " low" : ""}" style="width:${pct}%"></div></div>`
        + `<span>${Number(val).toFixed(1)}</span></div>`;
    }).join("");
    const techs = (h.culture?.known_techs || []).map(esc).join(", ") || "None";
    const mems = (h.memories || []).slice(-4).reverse()
      .map((m) => `<li>[t${esc(m.tick)}] ${esc(m.text)}</li>`).join("") || "<li>None</li>";
    const famHtml = window.WorldCharts.renderFamilyTreeHtml(h, stateData.humans);
    const mindHtml = window.WorldDialogueUI ? window.WorldDialogueUI.renderPersonMindHtml(stateData.minds?.[h.id]) : "";

    el.inspector.innerHTML =
      `<div class="kv"><strong>${esc(h.name)}</strong> · ${esc(h.persona?.job)} (${esc(h.stage)}, ${esc(h.age_years)}y)</div>`
      + bars + famHtml + mindHtml
      + `<div class="kv"><strong>Techs:</strong> ${techs}</div>`
      + `<div class="kv"><strong>Plan:</strong> ${esc(h.daily_plan || "None yet")}</div>`
      + `<div class="kv"><strong>Thought:</strong> ${esc(h.last_reflection || h.last_speech || h.last_action)}</div>`
      + `<div class="kv"><strong>Memories:</strong><ul class="event-feed">${mems}</ul></div>`;
  }

  function renderDialogue() {
    if (!stateData || !window.WorldDialogueUI) return;
    window.WorldDialogueUI.renderConversationLog(
      el.dlgLog, { person: el.dlgPerson, topic: el.dlgTopic, place: el.dlgPlace }, stateData.conversations,
    );
    window.WorldDialogueUI.renderGlossaries(el.glossaries, stateData.glossaries);
    if (window.WorldTechUI) window.WorldTechUI.renderTechTree(el.techTreeBox, stateData.tech_tree);
  }

  function renderAnalytics() {
    if (!historyData) return;
    window.WorldCharts.renderPopulationChart(el.chartPop, historyData);
    window.WorldCharts.renderGeneChart(el.chartGenes, historyData);
    window.WorldCharts.renderPhyloTree(el.phylo, el.phyloDetail, historyData, selectedSpecies, (sp) => {
      selectedSpecies = sp;
      renderAnalytics();
    });
    window.WorldCharts.renderTimeline(el.timeline, el.stagnation, historyData);
  }

  async function poll() {
    try {
      const reqs = [api("/api/state"), api("/api/events")];
      const fetchHist = tickCounter % 4 === 0 || !historyData;
      if (fetchHist) reqs.push(api("/api/history"));
      const [st, ev, hist] = await Promise.all(reqs);
      stateData = st;
      if (hist) historyData = hist;
      if (!selectedId && st.humans.length) selectedId = st.humans[0].id;
      if (++tickCounter % 12 === 0 || !mapData) await fetchMapAndLayers(false);
      renderHeader();
      renderPeople();
      renderInspector();
      renderDialogue();
      el.events.innerHTML = (ev.events || []).slice(-25).reverse()
        .map((e) => `<li>[t${esc(e.tick)}] ${esc(e.message)}</li>`).join("");
      if (fetchHist) renderAnalytics();
      redraw();
    } catch { /* retry next 500ms */ }
  }

  document.querySelectorAll(".tab").forEach((btn) => btn.addEventListener("click", () => {
    document.querySelectorAll(".tab, .tab-panel").forEach((n) => n.classList.remove("active"));
    btn.classList.add("active");
    $(`tab-${btn.dataset.tab}`)?.classList.add("active");
    renderAnalytics();
  }));

  el.people.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-person-id]");
    if (b) { selectedId = b.dataset.personId; renderPeople(); renderInspector(); redraw(); }
  });
  el.inspector.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-jump-id]");
    if (b) { selectedId = b.dataset.jumpId; renderPeople(); renderInspector(); redraw(); }
  });
  el.layer.addEventListener("change", () => { renderer.setLayer(el.layer.value); redraw(); });
  [el.dlgPerson, el.dlgTopic, el.dlgPlace].forEach((s) => s?.addEventListener("change", renderDialogue));
  el.zoomIn.addEventListener("click", () => { renderer.setZoom(renderer.getZoom() * 1.4); redraw(); });
  el.zoomOut.addEventListener("click", () => { renderer.setZoom(renderer.getZoom() / 1.4); redraw(); });
  el.zoomReset.addEventListener("click", () => { renderer.resetView(); redraw(); });
  minimap.addEventListener("click", (e) => { renderer.minimapClick(e.clientX, e.clientY); redraw(); });
  window.addEventListener("resize", () => { renderer.resize(); redraw(); });

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    renderer.setZoom(renderer.getZoom() * (e.deltaY < 0 ? 1.25 : 0.8), e.clientX - r.left, e.clientY - r.top);
    redraw();
  }, { passive: false });
  canvas.addEventListener("mousedown", (e) => { dragging = true; movedDrag = false; lastDrag = [e.clientX, e.clientY]; });
  window.addEventListener("mouseup", () => { dragging = false; });
  canvas.addEventListener("mousemove", (e) => {
    if (dragging && lastDrag) {
      const dx = e.clientX - lastDrag[0], dy = e.clientY - lastDrag[1];
      if (Math.hypot(dx, dy) > 2) movedDrag = true;
      renderer.panBy(dx, dy);
      lastDrag = [e.clientX, e.clientY];
      redraw();
      return;
    }
    const hit = renderer.hitTest(e.clientX, e.clientY);
    if (hit !== hoveredId) { hoveredId = hit; redraw(); }
  });
  canvas.addEventListener("mouseleave", () => { if (hoveredId) { hoveredId = null; redraw(); } });
  canvas.addEventListener("click", (e) => {
    if (movedDrag) return;
    const hit = renderer.hitTest(e.clientX, e.clientY);
    if (hit) { selectedId = hit; renderPeople(); renderInspector(); redraw(); }
  });

  el.play.addEventListener("click", async () => { await postJson("/api/control", { running: !stateData?.running }); poll(); });
  el.step.addEventListener("click", async () => { await api("/api/step", { method: "POST" }); poll(); });
  el.ff.addEventListener("click", async () => { const r = await postJson("/api/fast_forward", { days: 7 }); showToast(`Fast-forwarded to Y${r.year}`); poll(); });
  el.speed.addEventListener("change", () => postJson("/api/control", { speed: Number(el.speed.value) }));
  el.save.addEventListener("click", async () => { const r = await api("/api/save", { method: "POST" }); showToast(`Saved tick ${r.tick}`); });
  el.load.addEventListener("click", async () => {
    try { const r = await api("/api/load", { method: "POST" }); await fetchMapAndLayers(false); showToast(`Loaded tick ${r.tick}`); poll(); }
    catch { showToast("No saved snapshot"); }
  });
  el.reset.addEventListener("click", async () => {
    const seed = Math.floor(Math.random() * 100000);
    await postJson("/api/reset", { seed });
    await fetchMapAndLayers(true);
    showToast(`New world (seed ${seed})`);
    poll();
  });

  renderLegend();
  fetchMapAndLayers(true).then(poll);
  setInterval(poll, 500);
})();
