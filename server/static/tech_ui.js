/** Viewer Tech Tree panel: per-culture techs, lost techs (Tasmania effect), and first-appearance origins. */
window.WorldTechUI = (() => {
  const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  function renderTechTree(container, techTree) {
    if (!container) return;
    if (!techTree) {
      container.innerHTML = `<div class="person-meta">No tech tree data yet.</div>`;
      return;
    }
    const cultures = techTree.cultures || [];
    const origins = techTree.origins || {};
    const specs = techTree.tech_specs || {};

    const cultHtml = cultures.map((c) => {
      const known = (c.known_techs || []).map((t) => `<span class="badge" style="margin:2px;display:inline-block">${esc(t)}</span>`).join("") || `<span class="person-meta">None</span>`;
      const lost = (c.lost_techs || []).map((t) => `<span class="badge" style="margin:2px;display:inline-block;background:#7f1d1d;color:#fecaca">${esc(t)} (lost)</span>`).join("") || `<span class="person-meta">None</span>`;
      const dom = (c.domestication || []).map((d) => `${esc(d.species)} (${Math.round(d.docility * 100)}%${d.domesticated ? " ✓" : ""})`).join(", ") || "None";
      const soc = c.social_structure?.tier || "band";
      return `<div class="kv" style="border-bottom:1px solid #1e293b;padding-bottom:6px;margin-bottom:6px">`
        + `<div><strong>${esc(c.id)}</strong> · <span class="badge">${esc(c.era)}</span></div>`
        + `<div class="person-meta">${esc(soc)} (pop ${esc(c.population)}) · ${esc(c.place)}</div>`
        + `<div><strong>Known:</strong> ${known}</div>`
        + `<div><strong>Lost:</strong> ${lost}</div>`
        + `<div class="person-meta"><strong>Domestication:</strong> ${dom}</div></div>`;
    }).join("") || `<div class="person-meta">No cultures recorded yet.</div>`;

    const originRows = Object.entries(specs).map(([name, sp]) => {
      const orig = origins[name];
      const whenWhere = orig
        ? `Y${esc(orig.year)} · ${esc(orig.place)} (${esc(orig.culture_id)})`
        : `<span class="person-meta">Undiscovered (min ${esc(sp.min_learners)} learners)</span>`;
      const pre = (sp.prereqs || []).length ? ` ← ${sp.prereqs.map(esc).join(", ")}` : "";
      return `<li><strong>${esc(name)}</strong>${pre}: ${whenWhere}</li>`;
    }).join("");

    container.innerHTML =
      `<div class="kv"><strong>Cultures &amp; Eras</strong></div>${cultHtml}`
      + `<div class="kv"><strong>Tech Tree &amp; First Appearances</strong><ul class="event-feed" style="max-height:180px">${originRows}</ul></div>`;
  }

  return { renderTechTree };
})();
