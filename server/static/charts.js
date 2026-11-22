/** Charts, interactive Tree of Life, Human Family Tree, and Milestone Chronicle. */
window.WorldCharts = (() => {
  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function renderLineChart(container, seriesList, width = 290, height = 110) {
    if (!seriesList.length || !seriesList[0].values.length) {
      container.textContent = "Run simulation to collect yearly data.";
      return;
    }
    const maxVal = Math.max(1, ...seriesList.flatMap((s) => s.values));
    const pad = 12;
    const polylines = seriesList.map((s) => {
      const n = s.values.length;
      const pts = s.values.map((v, i) => {
        const x = pad + (n > 1 ? (i / (n - 1)) * (width - 2 * pad) : (width - 2 * pad) / 2);
        const y = height - pad - (v / maxVal) * (height - 2 * pad);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      return `<polyline fill="none" stroke="${esc(s.color)}" stroke-width="2" points="${pts}" />`;
    }).join("");

    const legend = seriesList.map((s) =>
      `<span style="color:${esc(s.color)};margin-right:8px;font-size:11px">● ${esc(s.label)}</span>`
    ).join("");
    container.innerHTML =
      `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" style="background:#0f172a;border-radius:4px">`
      + `${polylines}</svg><div>${legend}</div>`;
  }

  function renderPopulationChart(container, historyData) {
    const popSeries = historyData?.metrics?.population_over_time || [];
    const humans = popSeries.map((p) => p.counts.human || 0);
    const deer = popSeries.map((p) => p.counts.deer || 0);
    const rabbits = popSeries.map((p) => p.counts.rabbit || 0);
    const wolves = popSeries.map((p) => p.counts.wolf || 0);
    renderLineChart(container, [
      { label: "Humans", color: "#f43f5e", values: humans },
      { label: "Deer", color: "#d97706", values: deer },
      { label: "Rabbits", color: "#e2e8f0", values: rabbits },
      { label: "Wolves", color: "#38bdf8", values: wolves },
    ]);
  }

  function renderGeneChart(container, historyData) {
    const gSeries = historyData?.metrics?.gene_averages_over_time || [];
    renderLineChart(container, [
      { label: "Intel", color: "#a78bfa", values: gSeries.map((g) => g.intelligence || 0) },
      { label: "ColdTol", color: "#38bdf8", values: gSeries.map((g) => g.cold_tolerance || 0) },
      { label: "Speed", color: "#34d399", values: gSeries.map((g) => g.speed || 0) },
    ]);
  }

  function renderPhyloTree(container, detailEl, historyData, selectedSpecies, onSelect) {
    const nodes = historyData?.phylo_tree || [];
    if (!nodes.length) { container.textContent = "No species recorded yet."; return; }
    container.innerHTML = `<ul class="people-list">${nodes.slice(0, 40).map((n) => {
      const status = n.extinct_tick ? `extinct t${n.extinct_tick}` : `peak ${n.peak_population}`;
      const cls = n.species_id === selectedSpecies ? "person-btn selected" : "person-btn";
      const prefix = n.parent_species ? "↳ " : "";
      return `<li><button type="button" class="${cls}" data-species-id="${esc(n.species_id)}">`
        + `<span>${prefix}${esc(n.species_id)}</span><span class="person-meta">${esc(status)}</span></button></li>`;
    }).join("")}</ul>`;

    const sel = nodes.find((n) => n.species_id === selectedSpecies) || nodes[0];
    if (sel) {
      const genes = Object.entries(sel.key_gene_averages || {})
        .map(([k, v]) => `${esc(k)}:${Number(v).toFixed(2)}`).join(", ");
      detailEl.innerHTML = `<strong>${esc(sel.species_id)}</strong> (${esc(sel.habitat)}) · `
        + `Parent: ${esc(sel.parent_species || "Founder")} · Born: t${esc(sel.born_tick)} · `
        + `Genes: ${genes}`;
    }
    container.onclick = (e) => {
      const btn = e.target.closest("button[data-species-id]");
      if (btn) onSelect(btn.dataset.speciesId);
    };
  }

  function renderFamilyTreeHtml(human, allHumans) {
    const byId = Object.fromEntries(allHumans.map((x) => [x.id, x.name]));
    const fam = human.family || {};
    const mkBtn = (id) =>
      `<button type="button" class="mini-btn" data-jump-id="${esc(id)}">${esc(byId[id] || id)}</button>`;
    const parents = (fam.parents || []).length ? fam.parents.map(mkBtn).join(" + ") : "Founders";
    const partner = fam.partner ? mkBtn(fam.partner) : "None";
    const kids = (fam.children || []).length ? fam.children.map(mkBtn).join(" ") : "None";
    return `<div class="kv"><strong>Family (${esc(fam.surname || "—")}):</strong><br/>`
      + `Parents: ${parents}<br/>Partner: ${partner}<br/>Children: ${kids}</div>`;
  }

  function renderTimeline(container, warnBox, historyData) {
    const warns = historyData?.warnings || [];
    warnBox.innerHTML = warns.length
      ? warns.slice(-2).map((w) =>
          `<div class="warn-box"><strong>Stagnation (Y${esc(w.year)}):</strong> ${esc(w.cause)} <em>${esc(w.suggestion)}</em></div>`
        ).join("")
      : "";

    const chronicle = historyData?.chronicle || {};
    const eras = Object.keys(chronicle);
    if (!eras.length) { container.textContent = "No milestones recorded yet."; return; }
    container.innerHTML = eras.map((era) => {
      const items = chronicle[era].slice(-12).reverse()
        .map((m) => `<li><strong>Y${esc(m.year)}</strong> ${esc(m.title)}: ${esc(m.detail)}</li>`).join("");
      return `<div class="kv"><strong>${esc(era)}</strong><ul class="event-feed">${items}</ul></div>`;
    }).join("");
  }

  return { renderPopulationChart, renderGeneChart, renderPhyloTree, renderFamilyTreeHtml, renderTimeline };
})();
