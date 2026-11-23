/** CC0 SVG sprite sheet renderer for biome trees, era buildings, walls, docks, markets & roads. */
window.WorldStructures = (() => {
  const propsImg = new Image();
  const bldgImg = new Image();
  let propsReady = false, bldgReady = false;
  propsImg.onload = () => { propsReady = true; };
  bldgImg.onload = () => { bldgReady = true; };
  propsImg.src = "/assets/sprites/terrain_props.svg";
  bldgImg.src = "/assets/sprites/buildings.svg";

  function eraLevel(eraName) {
    const e = (eraName || "Stone Age").toLowerCase();
    if (e.includes("iron") || e.includes("classical") || e.includes("medieval")) return 2;
    if (e.includes("bronze") || e.includes("agricultural") || e.includes("neolithic")) return 1;
    return 0;
  }

  function hash2(x, y) {
    return ((x * 73856093) ^ (y * 19349663)) >>> 0;
  }

  function drawSheetTile(ctx, img, ready, idx, wx, wy, size, fallbackColor) {
    if (ready) {
      ctx.drawImage(img, idx * 32, 0, 32, 32, wx, wy, size, size);
    } else {
      ctx.fillStyle = fallbackColor;
      ctx.fillRect(wx + size * 0.15, wy + size * 0.15, size * 0.7, size * 0.7);
    }
  }

  function buildNameMap(palette) {
    const out = {};
    for (const [id, entry] of Object.entries(palette || {})) {
      out[Number(id)] = entry.name || "";
    }
    return out;
  }

  function drawRoads(ctx, settlements, houses, farms, tileSize, eraLvl) {
    const hubs = settlements.length
      ? settlements.map((s) => s.center)
      : (houses.length ? [houses[0]] : []);
    if (!hubs.length) return;

    ctx.save();
    ctx.strokeStyle = eraLvl >= 2 ? "#94a3b8" : (eraLvl === 1 ? "#c29b61" : "#a67c52");
    ctx.lineWidth = Math.max(1.2, tileSize * (eraLvl >= 2 ? 0.32 : 0.24));
    ctx.lineCap = "round";

    // Connect nearby settlements with inter-settlement trade roads
    for (let i = 0; i < hubs.length; i++) {
      for (let j = i + 1; j < hubs.length; j++) {
        const d = Math.hypot(hubs[i][0] - hubs[j][0], hubs[i][1] - hubs[j][1]);
        if (d <= 45) {
          ctx.beginPath();
          ctx.moveTo(hubs[i][0] * tileSize + tileSize / 2, hubs[i][1] * tileSize + tileSize / 2);
          ctx.lineTo(hubs[j][0] * tileSize + tileSize / 2, hubs[j][1] * tileSize + tileSize / 2);
          ctx.stroke();
        }
      }
    }

    // Connect houses & farms to their nearest settlement hub
    const stops = [...houses.slice(0, 60), ...farms.slice(0, 60)];
    ctx.lineWidth = Math.max(0.9, tileSize * 0.18);
    for (const pt of stops) {
      let best = hubs[0], bestD = Infinity;
      for (const h of hubs) {
        const d = Math.hypot(pt[0] - h[0], pt[1] - h[1]);
        if (d < bestD) { bestD = d; best = h; }
      }
      if (bestD > 0.5 && bestD <= 18) {
        ctx.beginPath();
        ctx.moveTo(pt[0] * tileSize + tileSize / 2, pt[1] * tileSize + tileSize / 2);
        ctx.lineTo(best[0] * tileSize + tileSize / 2, best[1] * tileSize + tileSize / 2);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function renderVisibleStructures(ctx, mapData, stateData, tileSize, bounds, showProps) {
    const W = mapData.width, H = mapData.height;
    const biomes = mapData.biomes || [];
    const names = buildNameMap(mapData.palette);
    const eraLvl = eraLevel(stateData.society?.era);
    const settlements = stateData.society?.settlements || [];
    const { minX, maxX, minY, maxY } = bounds;

    const houses = [], farms = [];
    for (let y = minY; y <= maxY; y++) {
      for (let x = minX; x <= maxX; x++) {
        const bName = names[biomes[y * W + x]] || "";
        if (bName === "house") houses.push([x, y]);
        else if (bName === "farm") farms.push([x, y]);
      }
    }

    // 1) Emergent roads connecting frequently visited settlement stops
    drawRoads(ctx, settlements, houses, farms, tileSize, eraLvl);

    // 2) Viewport-culled trees & terrain props (mid/close zoom)
    if (showProps) {
      for (let y = minY; y <= maxY; y++) {
        for (let x = minX; x <= maxX; x++) {
          const bName = names[biomes[y * W + x]] || "";
          const h = hash2(x, y) % 100;
          let propIdx = -1;
          if (bName === "temperate_forest" && h < 42) propIdx = 0;
          else if (bName === "taiga" && h < 42) propIdx = 1;
          else if ((bName === "jungle" && h < 46) || (bName === "beach" && h < 8)) propIdx = 2;
          else if (bName === "savanna" && h < 14) propIdx = 0;
          else if (bName === "desert" && h < 9) propIdx = 3;
          if (propIdx >= 0) {
            drawSheetTile(ctx, propsImg, propsReady, propIdx, x * tileSize - tileSize * 0.15, y * tileSize - tileSize * 0.35, tileSize * 1.3, "#2d6a36");
          }
        }
      }
    }

    // 3) Farms and era-styled houses (hut -> timber house -> stone manor)
    const bSize = Math.max(tileSize * 1.25, 6);
    const bOff = (bSize - tileSize) / 2;
    for (const [x, y] of farms) {
      drawSheetTile(ctx, bldgImg, bldgReady, 3, x * tileSize, y * tileSize, tileSize, "#eab308");
    }
    for (const [x, y] of houses) {
      const idx = eraLvl === 0 ? 0 : (eraLvl === 1 ? 1 : 2);
      drawSheetTile(ctx, bldgImg, bldgReady, idx, x * tileSize - bOff, y * tileSize - bOff * 1.3, bSize, "#d4b483");
    }

    // 4) Settlement walls, central markets, and waterfront docks
    const waterNames = new Set(["shallow_sea", "deep_ocean", "river", "lake"]);
    for (const s of settlements) {
      const [cx, cy] = s.center;
      if (cx < minX - 6 || cx > maxX + 6 || cy < minY - 6 || cy > maxY + 6) continue;
      const sx = cx * tileSize, sy = cy * tileSize;

      // Perimeter wall for growing settlements (wooden palisade -> stone rampart)
      if ((s.population || 0) >= 6) {
        const rad = Math.max(tileSize * 2.4, Math.min(tileSize * 4.5, tileSize * (1.8 + (s.population || 6) * 0.08)));
        ctx.save();
        ctx.strokeStyle = eraLvl >= 2 ? "#64748b" : "#78350f";
        ctx.lineWidth = Math.max(1.4, tileSize * 0.25);
        ctx.setLineDash(eraLvl >= 2 ? [] : [tileSize * 0.5, tileSize * 0.22]);
        ctx.beginPath();
        ctx.arc(sx + tileSize / 2, sy + tileSize / 2, rad, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }

      // Market stall at settlement center
      drawSheetTile(ctx, bldgImg, bldgReady, 4, sx - bOff, sy - bOff, bSize * 1.1, "#ef4444");

      // Dock if settlement borders water within 3 tiles
      let dockPlaced = false;
      for (let dy = -3; dy <= 3 && !dockPlaced; dy++) {
        for (let dx = -3; dx <= 3 && !dockPlaced; dx++) {
          const wx = cx + dx, wy = cy + dy;
          if (wx >= 0 && wx < W && wy >= 0 && wy < H && waterNames.has(names[biomes[wy * W + wx]])) {
            drawSheetTile(ctx, bldgImg, bldgReady, 5, wx * tileSize, wy * tileSize, bSize, "#9a6b3e");
            dockPlaced = true;
          }
        }
      }
    }
  }

  return { renderVisibleStructures };
})();
