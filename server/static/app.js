/** Virtual Society Canvas Viewer (16px tiles, 500ms polling, XSS-safe rendering). */
(() => {
  const TILE = 16;
  const TERRAIN_COLORS = {
    water: "#2b6cb0", grass: "#68a357", forest: "#2f6f4e",
    mountain: "#64748b", farm: "#d69e2e", house: "#b45309",
  };
  const ANIMAL_COLORS = { deer: "#d97706", rabbit: "#f8fafc", wolf: "#1f2937", bird: "#38bdf8" };
  const $ = (id) => document.getElementById(id);

  const canvas = $("world-canvas");
  const ctx = canvas.getContext("2d");
  const el = {
    brain: $("brain-badge"), clock: $("clock-status"), pop: $("pop-bar"),
    play: $("btn-play"), step: $("btn-step"), speed: $("speed-slider"),
    speedVal: $("speed-val"), save: $("btn-save"), load: $("btn-load"),
    reset: $("btn-reset"), toast: $("toast"), people: $("people-list"),
    inspector: $("inspector"), events: $("event-feed"),
  };

  let mapData = null;
  let stateData = null;
  let selectedId = null;
  let tickCounter = 0;

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
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

  async function fetchMap() {
    mapData = await api("/api/map");
    canvas.width = mapData.width * TILE;
    canvas.height = mapData.height * TILE;
  }

  function draw() {
    if (!mapData || !stateData) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const row of mapData.tiles) {
      for (const t of row) {
        ctx.fillStyle = TERRAIN_COLORS[t.terrain] || "#68a357";
        ctx.fillRect(t.x * TILE, t.y * TILE, TILE, TILE);
        if (t.terrain === "house") {
          ctx.fillStyle = "#7c2d12";
          ctx.fillRect(t.x * TILE + 2, t.y * TILE + 2, TILE - 4, 5);
        }
      }
    }

    for (const a of stateData.animals) {
      if (!a.alive) continue;
      const [x, y] = a.position;
      ctx.beginPath();
      ctx.arc(x * TILE + TILE / 2, y * TILE + TILE / 2, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = ANIMAL_COLORS[a.species] || "#e2e8f0";
      ctx.fill();
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "center";
    for (const h of stateData.humans) {
      if (!h.alive) continue;
      const cx = h.position[0] * TILE + TILE / 2;
      const cy = h.position[1] * TILE + TILE / 2;
      ctx.beginPath();
      ctx.arc(cx, cy, 5.5, 0, Math.PI * 2);
      ctx.fillStyle = h.id === selectedId ? "#facc15" : "#f43f5e";
      ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = h.id === selectedId ? 2 : 1.2;
      ctx.stroke();

      ctx.fillStyle = "#ffffff";
      ctx.fillText(h.name, cx, cy - 8);

      if (h.last_speech && h.last_action === "talk") {
        const text = h.last_speech.slice(0, 28) + (h.last_speech.length > 28 ? "…" : "");
        const w = Math.min(180, ctx.measureText(text).width + 10);
        const bx = Math.max(2, Math.min(canvas.width - w - 2, cx - w / 2));
        const by = Math.max(2, cy - 30);
        ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
        ctx.fillRect(bx, by, w, 15);
        ctx.fillStyle = "#fef08a";
        ctx.fillText(text, bx + w / 2, by + 11);
      }
    }

    const env = stateData.environment;
    if (env.time_of_day === "night") {
      ctx.fillStyle = "rgba(15, 23, 42, 0.45)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    } else if (env.time_of_day === "dawn" || env.time_of_day === "dusk") {
      ctx.fillStyle = "rgba(124, 45, 18, 0.16)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
  }

  function renderHeader() {
    const env = stateData.environment;
    const live = stateData.llm_mode && stateData.llm_mode !== "mock";
    el.brain.textContent = live ? "Brain: Local model (Ollama)" : "Brain: Rule-based (mock)";
    el.clock.textContent =
      `Year ${env.year} · ${env.season} Day ${env.day} · ${String(env.hour).padStart(2, "0")}:00 (${env.time_of_day}) · ${env.weather}`;
    el.play.textContent = stateData.running ? "Pause" : "Play";
    el.play.classList.toggle("active", stateData.running);
    el.speed.value = String(stateData.speed);
    el.speedVal.textContent = Number(stateData.speed).toFixed(1);
    el.pop.innerHTML = Object.entries(stateData.counts)
      .map(([k, v]) => `<span><strong>${esc(k)}</strong>: ${esc(v)}</span>`)
      .join("");
  }

  function renderPeople() {
    const focusedId = document.activeElement?.dataset?.personId;
    el.people.innerHTML = stateData.humans
      .map((h) => {
        const cls = h.id === selectedId ? "person-btn selected" : "person-btn";
        const job = h.persona?.job || "";
        const status = h.alive ? h.last_action : "dead";
        return `<li><button type="button" class="${cls}" data-person-id="${esc(h.id)}">`
          + `<span>${esc(h.name)} <span class="person-meta">(${esc(job)})</span></span>`
          + `<span class="person-meta">${esc(status)}</span></button></li>`;
      })
      .join("");
    if (focusedId) {
      el.people.querySelector(`[data-person-id="${CSS.escape(focusedId)}"]`)?.focus();
    }
  }

  function renderInspector() {
    const h = stateData.humans.find((x) => x.id === selectedId);
    if (!h) {
      el.inspector.textContent = "Select a villager to inspect.";
      return;
    }
    const nameMap = Object.fromEntries(stateData.humans.map((x) => [x.id, x.name]));
    const bars = [
      ["Hunger", h.needs.hunger],
      ["Energy", h.needs.energy],
      ["Social", h.needs.social],
      ["Health", h.health],
    ].map(([label, val]) => {
      const pct = Math.max(0, Math.min(100, (Number(val) / 10) * 100));
      const low = val < 3.5 ? " low" : "";
      return `<div class="need-row"><span>${esc(label)}</span>`
        + `<div class="bar-bg"><div class="bar-fill${low}" style="width:${pct}%"></div></div>`
        + `<span>${Number(val).toFixed(1)}</span></div>`;
    }).join("");

    const rels = Object.entries(h.relationships || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([id, score]) => `${esc(nameMap[id] || id)} (${Number(score).toFixed(1)})`)
      .join(", ") || "None yet";

    const mems = (h.memories || []).slice(-5).reverse()
      .map((m) => `<li>[t${esc(m.tick)}] ${esc(m.text)}</li>`).join("") || "<li>None</li>";

    el.inspector.innerHTML =
      `<div class="kv"><strong>${esc(h.name)}</strong> · ${esc(h.persona?.job)} (age ${esc(h.persona?.age)})</div>`
      + bars
      + `<div class="kv"><strong>Plan:</strong> ${esc(h.daily_plan || "None yet")}</div>`
      + `<div class="kv"><strong>Thought:</strong> ${esc(h.last_reflection || h.last_speech || h.last_action)}</div>`
      + `<div class="kv"><strong>Relationships:</strong> ${rels}</div>`
      + `<div class="kv"><strong>Recent Memories:</strong><ul class="event-feed">${mems}</ul></div>`;
  }

  function renderEvents(events) {
    el.events.innerHTML = (events || []).slice(-25).reverse()
      .map((e) => `<li>[t${esc(e.tick)}] ${esc(e.message)}</li>`).join("");
  }

  async function poll() {
    try {
      const [st, ev] = await Promise.all([api("/api/state"), api("/api/events")]);
      stateData = st;
      if (!selectedId && st.humans.length) selectedId = st.humans[0].id;
      if (++tickCounter % 10 === 0 || !mapData) await fetchMap();
      renderHeader();
      renderPeople();
      renderInspector();
      renderEvents(ev.events);
      draw();
    } catch { /* retry on next 500ms poll */ }
  }

  el.people.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-person-id]");
    if (btn) { selectedId = btn.dataset.personId; renderPeople(); renderInspector(); draw(); }
  });
  canvas.addEventListener("click", (e) => {
    if (!stateData) return;
    const rect = canvas.getBoundingClientRect();
    const gx = ((e.clientX - rect.left) * (canvas.width / rect.width)) / TILE;
    const gy = ((e.clientY - rect.top) * (canvas.height / rect.height)) / TILE;
    const hit = stateData.humans.find((h) => Math.hypot(h.position[0] + 0.5 - gx, h.position[1] + 0.5 - gy) < 1.5);
    if (hit) { selectedId = hit.id; renderPeople(); renderInspector(); draw(); }
  });
  function postJson(url, body) {
    return api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  el.play.addEventListener("click", async () => {
    await postJson("/api/control", { running: !stateData?.running });
    poll();
  });
  el.step.addEventListener("click", async () => { await api("/api/step", { method: "POST" }); poll(); });
  el.speed.addEventListener("change", () => postJson("/api/control", { speed: Number(el.speed.value) }));
  el.save.addEventListener("click", async () => {
    const r = await api("/api/save", { method: "POST" });
    showToast(`Saved tick ${r.tick}`);
  });
  el.load.addEventListener("click", async () => {
    try { const r = await api("/api/load", { method: "POST" }); await fetchMap(); showToast(`Loaded tick ${r.tick}`); poll(); }
    catch { showToast("No saved snapshot"); }
  });
  el.reset.addEventListener("click", async () => {
    const seed = Math.floor(Math.random() * 100000);
    await postJson("/api/reset", { seed });
    await fetchMap();
    showToast(`New world (seed ${seed})`);
    poll();
  });

  fetchMap().then(poll);
  setInterval(poll, 500);
})();
