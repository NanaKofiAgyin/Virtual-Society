/** Viewer UI for filterable multi-turn conversation logs, culture glossaries, and person minds. */
window.WorldDialogueUI = (() => {
  const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  function syncSelectOptions(selectEl, values, placeholder) {
    if (!selectEl) return;
    const prev = selectEl.value;
    const opts = [`<option value="">${esc(placeholder)}</option>`]
      .concat([...values].sort().map((v) => `<option value="${esc(v)}">${esc(v)}</option>`));
    selectEl.innerHTML = opts.join("");
    if (values.has(prev)) selectEl.value = prev;
  }

  function renderConversationLog(container, filterEls, conversations) {
    if (!container) return;
    const list = conversations || [];
    const people = new Set(), topics = new Set(), places = new Set();
    for (const c of list) {
      for (const n of (c.participant_names || [])) people.add(n);
      if (c.purpose) topics.add(c.purpose);
      if (c.place) places.add(c.place);
    }
    syncSelectOptions(filterEls.person, people, "All people");
    syncSelectOptions(filterEls.topic, topics, "All topics");
    syncSelectOptions(filterEls.place, places, "All places");

    const fPerson = filterEls.person?.value || "";
    const fTopic = filterEls.topic?.value || "";
    const fPlace = filterEls.place?.value || "";

    const filtered = list.filter((c) => {
      if (fPerson && !(c.participant_names || []).includes(fPerson)) return false;
      if (fTopic && c.purpose !== fTopic) return false;
      if (fPlace && c.place !== fPlace) return false;
      return true;
    }).slice(-18).reverse();

    if (!filtered.length) {
      container.innerHTML = `<div class="person-meta">No conversations match these filters yet.</div>`;
      return;
    }

    container.innerHTML = filtered.map((c) => {
      const turns = (c.turns || []).map((t) =>
        `<li><strong>${esc(t.speaker_name)}:</strong> ${esc(t.line)}</li>`
      ).join("");
      const cons = (c.consequences || []).map(esc).join(" · ");
      const badge = c.used_llm ? " [Ollama]" : "";
      return `<div class="kv" style="border-bottom:1px solid #1e293b;padding-bottom:6px;margin-bottom:6px">`
        + `<div><strong>${esc((c.participant_names || []).join(" & "))}</strong> `
        + `<span class="person-meta">[${esc(c.purpose)} · ${esc(c.place)} · d${esc(c.day)}${badge}]</span></div>`
        + `<ul class="event-feed" style="max-height:110px">${turns}</ul>`
        + `<div class="person-meta"><em>Outcome:</em> ${cons}</div></div>`;
    }).join("");
  }

  function renderGlossaries(container, glossaries) {
    if (!container) return;
    const entries = Object.entries(glossaries || {});
    if (!entries.length) {
      container.innerHTML = `<div class="person-meta">No cultural glossaries yet.</div>`;
      return;
    }
    container.innerHTML = entries.map(([groupId, words]) => {
      const pairs = Object.entries(words || {})
        .map(([meaning, word]) => `<span class="badge" style="margin:2px;display:inline-block">${esc(meaning)}: <strong>${esc(word)}</strong></span>`)
        .join(" ");
      return `<div class="kv"><strong>${esc(groupId)}</strong><div>${pairs}</div></div>`;
    }).join("");
  }

  function renderPersonMindHtml(mind) {
    if (!mind) return "";
    const ops = (mind.opinions || []).slice(0, 6).map((o) => {
      const cls = o.score >= 2 ? "#4ade80" : (o.score <= -1 ? "#f87171" : "#94a3b8");
      return `<span style="color:${cls};margin-right:6px">${esc(o.name)} (${o.score >= 0 ? "+" : ""}${esc(o.score)})</span>`;
    }).join("") || `<span class="person-meta">No opinions yet</span>`;

    const beliefs = (mind.beliefs || []).map((b) => {
      const tag = b.distortions > 0 ? `rumor ×${b.distortions}` : "direct";
      const acc = b.is_accurate ? "" : " (false)";
      return `<li>${esc(b.claim)} <span class="person-meta">[${esc(tag)}${esc(acc)}, ${Math.round((b.confidence || 0) * 100)}%]</span></li>`;
    }).join("") || "<li>None</li>";

    const fears = (mind.fears || []).map(esc).join(", ") || "None";
    return `<div class="kv"><strong>Style:</strong> ${esc(mind.speech_style)} · <strong>Fears:</strong> ${fears}</div>`
      + `<div class="kv"><strong>Relationships:</strong> ${ops}</div>`
      + `<div class="kv"><strong>Beliefs:</strong><ul class="event-feed">${beliefs}</ul></div>`;
  }

  return { renderConversationLog, renderGlossaries, renderPersonMindHtml };
})();
