/** Viewport-culled, zoom-LOD layered sprite renderer with minimap and hover/selected labels. */
window.WorldCanvas = (() => {
  const BUBBLE_MS = 4000, FADE_MS = 1500;

  function overlaps(a, b) {
    return a && b && a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }

  function hexToRgb(hex) {
    const h = (hex || "#76c85b").replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function create(canvas, minimap) {
    const ctx = canvas.getContext("2d");
    const miniCtx = minimap ? minimap.getContext("2d") : null;
    const terrainCanvas = document.createElement("canvas");
    const bubbles = new Map(), lastSeenSpeech = new Map();
    let humanPoints = [], tileSize = 4, mapCache = null, layerCache = null, biomeRgbById = {};
    let activeLayer = "biomes", zoom = 1, panX = 0, panY = 0;

    function worldSize() { return mapCache ? { w: mapCache.width * tileSize, h: mapCache.height * tileSize } : { w: 800, h: 800 }; }
    function setLayer(layerName) { activeLayer = layerName; rebuildTerrain(); }
    function panBy(dx, dy) { panX += dx; panY += dy; }
    function resetView() { fitToViewport(); }
    function centerOnWorld(wx, wy) { panX = canvas.width / 2 - wx * zoom; panY = canvas.height / 2 - wy * zoom; }

    function fitToViewport() {
      const wrap = canvas.parentElement;
      if (!wrap) return;
      canvas.width = Math.max(300, wrap.clientWidth); canvas.height = Math.max(300, wrap.clientHeight);
      const ws = worldSize();
      zoom = Math.min(canvas.width / ws.w, canvas.height / ws.h);
      panX = (canvas.width - ws.w * zoom) / 2; panY = (canvas.height - ws.h * zoom) / 2;
    }

    function rebuildTerrain() {
      if (!mapCache) return;
      tileSize = Math.max(4, Math.min(16, Math.floor(800 / mapCache.width)));
      biomeRgbById = {};
      for (const [id, entry] of Object.entries(mapCache.palette || {})) biomeRgbById[Number(id)] = hexToRgb(entry.color);
      window.WorldTerrain.renderTerrain(terrainCanvas, mapCache, layerCache, activeLayer, tileSize);
    }

    function setMap(mapData, layersData, resetCam = false) {
      const first = !mapCache || mapCache.width !== mapData.width;
      mapCache = mapData; if (layersData) layerCache = layersData;
      rebuildTerrain(); if (first || resetCam) fitToViewport();
    }

    function setZoom(nextZoom, cx = canvas.width / 2, cy = canvas.height / 2) {
      const clamped = Math.max(0.4, Math.min(16, nextZoom)), scale = clamped / zoom;
      panX = cx - (cx - panX) * scale; panY = cy - (cy - panY) * scale; zoom = clamped;
    }

    function visibleBounds(W, H) {
      return {
        minX: Math.max(0, Math.floor((-panX / zoom) / tileSize) - 2),
        minY: Math.max(0, Math.floor((-panY / zoom) / tileSize) - 2),
        maxX: Math.min(W - 1, Math.ceil(((canvas.width - panX) / zoom) / tileSize) + 2),
        maxY: Math.min(H - 1, Math.ceil(((canvas.height - panY) / zoom) / tileSize) + 2),
      };
    }

    function syncBubbles(humans, byId) {
      const now = performance.now();
      for (const h of humans) {
        if (!h.alive) continue;
        const speech = (h.last_speech || "").trim();
        if (speech && speech !== lastSeenSpeech.get(h.id)) {
          lastSeenSpeech.set(h.id, speech);
          const pt = byId.get(h.id);
          if (pt) bubbles.set(h.id, { text: speech, tileKey: `${h.position[0]},${h.position[1]}`, cx: pt.cx, cy: pt.cy, startedAt: now });
        } else if (bubbles.has(h.id) && byId.has(h.id)) {
          const b = bubbles.get(h.id), pt = byId.get(h.id);
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
      const points = [], byId = new Map();
      const rOff = Math.max(3.0, tileSize * 0.35);
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

    function drawScreenLabel(text, wx, wy, highlight) {
      const sx = wx * zoom + panX, sy = wy * zoom + panY;
      ctx.font = "bold 11px system-ui, sans-serif";
      const w = ctx.measureText(text).width + 10, h = 16;
      const x = Math.max(4, Math.min(canvas.width - w - 4, sx - w / 2));
      const y = Math.max(4, sy - 24);
      ctx.fillStyle = highlight ? "rgba(250, 204, 21, 0.96)" : "rgba(15, 23, 42, 0.9)";
      ctx.fillRect(x, y, w, h);
      ctx.fillStyle = highlight ? "#0f172a" : "#f8fafc";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(text, x + w / 2, y + h / 2);
      return { x, y, w, h };
    }

    function drawMinimap() {
      if (!miniCtx || !mapCache) return;
      const mw = minimap.width, mh = minimap.height, ws = worldSize();
      miniCtx.clearRect(0, 0, mw, mh);
      miniCtx.drawImage(terrainCanvas, 0, 0, mw, mh);
      miniCtx.strokeStyle = "#facc15"; miniCtx.lineWidth = 1.5;
      miniCtx.strokeRect((-panX / zoom / ws.w) * mw, (-panY / zoom / ws.h) * mh, (canvas.width / zoom / ws.w) * mw, (canvas.height / zoom / ws.h) * mh);
    }

    function draw(mapData, stateData, selectedId, hoveredId) {
      if (!mapData || !stateData) return false;
      const W = mapData.width, H = mapData.height;
      const bounds = visibleBounds(W, H);
      const frameIdx = Math.floor(performance.now() / 220);

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      ctx.translate(panX, panY);
      ctx.scale(zoom, zoom);
      ctx.drawImage(terrainCanvas, 0, 0);

      if (activeLayer === "species_density") {
        ctx.fillStyle = "rgba(250, 204, 21, 0.28)";
        for (const a of stateData.animals) {
          if (!a.alive) continue;
          const [ax, ay] = a.position;
          if (ax < bounds.minX || ax > bounds.maxX || ay < bounds.minY || ay > bounds.maxY) continue;
          ctx.fillRect(ax * tileSize - 6, ay * tileSize - 6, 12 + tileSize, 12 + tileSize);
        }
      }

      // LOD thresholds by zoom: zoomed-out shows terrain+roads+buildings; mid adds trees+sprites; close adds bubbles
      const showProps = activeLayer === "biomes" && (zoom >= 1.2 || W <= 60);
      const showEntities = zoom >= 1.2 || W <= 60;
      const showBubbles = zoom >= 2.6 || W <= 60;

      if (activeLayer === "biomes" && window.WorldStructures) {
        window.WorldStructures.renderVisibleStructures(ctx, mapData, stateData, tileSize, bounds, showProps);
      }

      const { points, byId } = computeHumanPoints(stateData.humans);
      humanPoints = points;
      syncBubbles(stateData.humans, byId);

      if (showEntities) {
        const biomes = mapData.biomes || [];
        const animalDrawSize = Math.max(tileSize * 1.4, 10);
        const halfA = animalDrawSize / 2;
        for (const a of stateData.animals) {
          if (!a.alive) continue;
          const [ax, ay] = a.position;
          if (ax < bounds.minX || ax > bounds.maxX || ay < bounds.minY || ay > bounds.maxY) continue;
          const bRgb = biomeRgbById[biomes[ay * W + ax]] || [118, 200, 91];
          const sprite = window.WorldSprites.getAnimalSprite(a, bRgb, frameIdx);
          ctx.drawImage(sprite, ax * tileSize + tileSize / 2 - halfA, ay * tileSize + tileSize / 2 - halfA, animalDrawSize, animalDrawSize);
        }

        const humanDrawSize = Math.max(tileSize * 1.65, 13);
        const halfH = humanDrawSize / 2;
        for (const pt of points) {
          const [hx, hy] = pt.human.position;
          if (hx < bounds.minX || hx > bounds.maxX || hy < bounds.minY || hy > bounds.maxY) continue;
          const hl = pt.id === selectedId ? "sel" : (pt.id === hoveredId ? "hov" : "");
          const sprite = window.WorldHumanSprites.getHumanSprite(pt.human, frameIdx, hl);
          ctx.drawImage(sprite, pt.cx - halfH, pt.cy - halfH, humanDrawSize, humanDrawSize);
        }
      }

      if (activeLayer === "biomes" && stateData.environment.time_of_day === "night") {
        ctx.fillStyle = "rgba(15, 23, 42, 0.34)";
        ctx.fillRect(0, 0, terrainCanvas.width, terrainCanvas.height);
      }
      ctx.restore();

      let selRect = (selectedId && byId.has(selectedId)) ? drawScreenLabel(byId.get(selectedId).human.name, byId.get(selectedId).cx, byId.get(selectedId).cy, true) : null;
      if (hoveredId && hoveredId !== selectedId && byId.has(hoveredId)) {
        const pt = byId.get(hoveredId);
        drawScreenLabel(pt.human.name, pt.cx, pt.cy, false);
      }

      if (showBubbles) {
        const now = performance.now(), perTile = new Map();
        for (const b of bubbles.values()) {
          const cur = perTile.get(b.tileKey);
          if (!cur || b.startedAt > cur.startedAt) perTile.set(b.tileKey, b);
        }
        ctx.font = "11px system-ui, sans-serif";
        for (const b of perTile.values()) {
          const rem = BUBBLE_MS - (now - b.startedAt);
          if (rem <= 0) continue;
          const text = b.text.length > 32 ? `${b.text.slice(0, 31)}…` : b.text;
          const sx = b.cx * zoom + panX, sy = b.cy * zoom + panY, w = Math.min(200, ctx.measureText(text).width + 12);
          const rect = { x: Math.max(4, Math.min(canvas.width - w - 4, sx - w / 2)), y: Math.max(4, sy - 30), w, h: 17 };
          if (overlaps(rect, selRect)) rect.y = Math.min(canvas.height - 20, sy + 12);
          if (overlaps(rect, selRect)) continue;
          ctx.save(); ctx.globalAlpha = rem < FADE_MS ? rem / FADE_MS : 1;
          ctx.fillStyle = "rgba(15, 23, 42, 0.92)"; ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
          ctx.fillStyle = "#fef08a"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(text, rect.x + w / 2, rect.y + rect.h / 2); ctx.restore();
        }
      }
      drawMinimap();
      return showEntities || bubbles.size > 0;
    }

    function hitTest(clientX, clientY) {
      const r = canvas.getBoundingClientRect();
      const wx = ((clientX - r.left) * (canvas.width / r.width) - panX) / zoom;
      const wy = ((clientY - r.top) * (canvas.height / r.height) - panY) / zoom;
      let best = null, bestDist = 14 / zoom;
      for (const pt of humanPoints) {
        const d = Math.hypot(pt.cx - wx, pt.cy - wy);
        if (d < bestDist) { bestDist = d; best = pt.id; }
      }
      return best;
    }

    function minimapClick(clientX, clientY) {
      if (!minimap || !mapCache) return;
      const r = minimap.getBoundingClientRect(), ws = worldSize();
      centerOnWorld(((clientX - r.left) / r.width) * ws.w, ((clientY - r.top) / r.height) * ws.h);
    }

    return { setMap, setLayer, setZoom, panBy, resetView, resize: fitToViewport, getZoom: () => zoom, draw, hitTest, minimapClick };
  }
  return { create };
})();
