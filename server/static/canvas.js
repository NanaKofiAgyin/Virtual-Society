/** Canvas renderer: zoom/pan, 4 map layers, clustered offsets, hover/selected labels, bubbles. */
window.WorldCanvas = (() => {
  const BUBBLE_MS = 4000;
  const FADE_MS = 1500;
  const ANIMALS = { deer: "#d97706", rabbit: "#f8fafc", wolf: "#1f2937", bird: "#38bdf8" };

  function overlaps(a, b) {
    return a && b && a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }

  function tempColor(v) {
    const t = v / 255;
    const r = Math.round(255 * Math.min(1, Math.max(0, (t - 0.35) * 1.8)));
    const g = Math.round(200 * (1 - Math.abs(t - 0.5) * 2));
    const b = Math.round(255 * Math.min(1, Math.max(0, (0.65 - t) * 1.8)));
    return `rgb(${r},${g},${b})`;
  }

  function depthColor(v) {
    if (v <= 0) return "#334155";
    const t = v / 255;
    return `rgb(${Math.round(14 + (1 - t) * 40)},${Math.round(45 + (1 - t) * 140)},${Math.round(110 + (1 - t) * 120)})`;
  }

  function create(canvas) {
    const ctx = canvas.getContext("2d");
    const terrainCanvas = document.createElement("canvas");
    const terrainCtx = terrainCanvas.getContext("2d");
    const bubbles = new Map(), lastSeenSpeech = new Map();
    let humanPoints = [], tileSize = 4, mapCache = null, layerCache = null;
    let activeLayer = "biomes", zoom = 1, panX = 0, panY = 0;

    function rebuildTerrain() {
      if (!mapCache) return;
      tileSize = Math.max(4, Math.min(16, Math.floor(800 / mapCache.width)));
      canvas.width = terrainCanvas.width = mapCache.width * tileSize;
      canvas.height = terrainCanvas.height = mapCache.height * tileSize;
      const palette = mapCache.palette || {}, biomes = mapCache.biomes || [];
      const temps = layerCache?.temperature || [], depths = layerCache?.ocean_depth || [];
      for (let y = 0; y < mapCache.height; y++) {
        for (let x = 0; x < mapCache.width; x++) {
          const i = y * mapCache.width + x;
          terrainCtx.fillStyle =
            activeLayer === "temperature" && temps.length ? tempColor(temps[i])
            : activeLayer === "ocean_depth" && depths.length ? depthColor(depths[i])
            : activeLayer === "species_density" ? "#0f172a"
            : (palette[String(biomes[i])]?.color || "#68a357");
          terrainCtx.fillRect(x * tileSize, y * tileSize, tileSize, tileSize);
        }
      }
    }

    function setMap(mapData, layersData) { mapCache = mapData; if (layersData) layerCache = layersData; rebuildTerrain(); }
    function setLayer(layerName) { activeLayer = layerName; rebuildTerrain(); }
    function panBy(dx, dy) { if (zoom > 1) { panX += dx; panY += dy; } }
    function resetView() { zoom = 1; panX = 0; panY = 0; }

    function setZoom(nextZoom, cx = canvas.width / 2, cy = canvas.height / 2) {
      const clamped = Math.max(1, Math.min(8, nextZoom));
      const scale = clamped / zoom;
      panX = cx - (cx - panX) * scale;
      panY = cy - (cy - panY) * scale;
      zoom = clamped;
      if (zoom === 1) { panX = 0; panY = 0; }
    }

    function syncBubbles(humans, pointsById) {
      const now = performance.now();
      for (const h of humans) {
        if (!h.alive) continue;
        const speech = (h.last_speech || "").trim();
        if (speech && speech !== lastSeenSpeech.get(h.id)) {
          lastSeenSpeech.set(h.id, speech);
          const pt = pointsById.get(h.id);
          if (pt) bubbles.set(h.id, { text: speech, tileKey: `${h.position[0]},${h.position[1]}`, cx: pt.cx, cy: pt.cy, startedAt: now });
        } else if (bubbles.has(h.id) && pointsById.has(h.id)) {
          const b = bubbles.get(h.id);
          const pt = pointsById.get(h.id);
          b.cx = pt.cx; b.cy = pt.cy; b.tileKey = `${h.position[0]},${h.position[1]}`;
        }
      }
      for (const [id, b] of bubbles.entries()) {
        if (now - b.startedAt > BUBBLE_MS) bubbles.delete(id);
      }
    }

    function computeHumanPoints(humans) {
      const groups = new Map();
      for (const h of humans) {
        if (!h.alive) continue;
        const key = `${h.position[0]},${h.position[1]}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(h);
      }
      const points = [];
      const byId = new Map();
      const rOff = Math.max(3.5, tileSize * 0.35);
      for (const group of groups.values()) {
        group.forEach((h, i) => {
          const bx = h.position[0] * tileSize + tileSize / 2;
          const by = h.position[1] * tileSize + tileSize / 2;
          const ang = (Math.PI * 2 * i) / group.length;
          const r = group.length > 1 ? rOff : 0;
          const pt = { id: h.id, human: h, cx: bx + Math.cos(ang) * r, cy: by + Math.sin(ang) * r };
          points.push(pt);
          byId.set(h.id, pt);
        });
      }
      return { points, byId };
    }

    function drawLabel(text, cx, cy, highlight) {
      ctx.font = "bold 10px system-ui, sans-serif";
      const w = ctx.measureText(text).width + 10;
      const h = 15;
      const x = Math.max(2, Math.min(canvas.width - w - 2, cx - w / 2));
      const y = Math.max(2, cy - 23);
      ctx.fillStyle = highlight ? "rgba(250, 204, 21, 0.95)" : "rgba(15, 23, 42, 0.9)";
      ctx.fillRect(x, y, w, h);
      ctx.fillStyle = highlight ? "#0f172a" : "#f8fafc";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, x + w / 2, y + h / 2);
      return { x, y, w, h };
    }

    function draw(mapData, stateData, selectedId, hoveredId) {
      if (!mapData || !stateData) return false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      ctx.translate(panX, panY);
      ctx.scale(zoom, zoom);
      ctx.drawImage(terrainCanvas, 0, 0);

      if (activeLayer === "species_density") {
        ctx.fillStyle = "rgba(250, 204, 21, 0.32)";
        for (const a of stateData.animals) {
          if (!a.alive) continue;
          ctx.beginPath();
          ctx.arc(a.position[0] * tileSize + tileSize / 2, a.position[1] * tileSize + tileSize / 2, 10, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      const animalR = Math.max(2.2, Math.min(3.2, tileSize * 0.45));
      for (const a of stateData.animals) {
        if (!a.alive) continue;
        ctx.beginPath();
        ctx.arc(a.position[0] * tileSize + tileSize / 2, a.position[1] * tileSize + tileSize / 2, animalR, 0, Math.PI * 2);
        ctx.fillStyle = ANIMALS[a.species] || "#e2e8f0";
        ctx.fill();
      }

      const { points, byId } = computeHumanPoints(stateData.humans);
      humanPoints = points;
      syncBubbles(stateData.humans, byId);

      for (const pt of points) {
        const isSel = pt.id === selectedId;
        const isHov = pt.id === hoveredId;
        ctx.beginPath();
        ctx.arc(pt.cx, pt.cy, isSel || isHov ? 6.0 : 5.0, 0, Math.PI * 2);
        ctx.fillStyle = isSel ? "#facc15" : isHov ? "#38bdf8" : "#f43f5e";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = isSel || isHov ? 1.8 : 1.0;
        ctx.stroke();
        ctx.font = "bold 8px system-ui, sans-serif";
        ctx.fillStyle = isSel ? "#0f172a" : "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText((pt.human.name || "?")[0].toUpperCase(), pt.cx, pt.cy + 0.5);
      }

      if (activeLayer === "biomes" && stateData.environment.time_of_day === "night") {
        ctx.fillStyle = "rgba(15, 23, 42, 0.45)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }

      let selectedLabelRect = null;
      if (selectedId && byId.has(selectedId)) {
        const pt = byId.get(selectedId);
        selectedLabelRect = drawLabel(pt.human.name, pt.cx, pt.cy, true);
      }
      if (hoveredId && hoveredId !== selectedId && byId.has(hoveredId)) {
        const pt = byId.get(hoveredId);
        drawLabel(pt.human.name, pt.cx, pt.cy, false);
      }

      const now = performance.now();
      const perTile = new Map();
      for (const b of bubbles.values()) {
        const cur = perTile.get(b.tileKey);
        if (!cur || b.startedAt > cur.startedAt) perTile.set(b.tileKey, b);
      }
      ctx.font = "10px system-ui, sans-serif";
      for (const b of perTile.values()) {
        const rem = BUBBLE_MS - (now - b.startedAt);
        if (rem <= 0) continue;
        const text = b.text.length > 30 ? `${b.text.slice(0, 29)}…` : b.text;
        const w = Math.min(185, ctx.measureText(text).width + 10);
        const rect = { x: Math.max(2, Math.min(canvas.width - w - 2, b.cx - w / 2)), y: Math.max(2, b.cy - 26), w, h: 15 };
        if (overlaps(rect, selectedLabelRect)) rect.y = Math.min(canvas.height - 17, b.cy + 10);
        if (overlaps(rect, selectedLabelRect)) continue;
        ctx.save();
        ctx.globalAlpha = rem < FADE_MS ? rem / FADE_MS : 1;
        ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
        ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
        ctx.fillStyle = "#fef08a";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, rect.x + rect.w / 2, rect.y + rect.h / 2);
        ctx.restore();
      }
      ctx.restore();
      return bubbles.size > 0;
    }

    function hitTest(clientX, clientY) {
      const rect = canvas.getBoundingClientRect();
      const sx = (clientX - rect.left) * (canvas.width / rect.width);
      const sy = (clientY - rect.top) * (canvas.height / rect.height);
      const x = (sx - panX) / zoom;
      const y = (sy - panY) / zoom;
      let best = null;
      let bestDist = 11 / zoom;
      for (const pt of humanPoints) {
        const d = Math.hypot(pt.cx - x, pt.cy - y);
        if (d < bestDist) { bestDist = d; best = pt.id; }
      }
      return best;
    }

    return { setMap, setLayer, setZoom, panBy, resetView, getZoom: () => zoom, draw, hitTest };
  }

  return { create };
})();
