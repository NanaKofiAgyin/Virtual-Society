/** Offscreen terrain renderer: bright palette, NW hillshading, ocean depth, and rivers. */
window.WorldTerrain = (() => {
  function hexToRgb(hex) {
    const h = (hex || "#76c85b").replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function tempRgb(v) {
    const t = v / 255;
    return [
      Math.round(255 * Math.min(1, Math.max(0, (t - 0.30) * 1.6))),
      Math.round(210 * (1 - Math.abs(t - 0.5) * 1.9)),
      Math.round(255 * Math.min(1, Math.max(0, (0.70 - t) * 1.6))),
    ];
  }

  function depthRgb(v) {
    if (v <= 0) return [71, 85, 105];
    const t = v / 255;
    return [
      Math.round(16 + (1 - t) * 42),
      Math.round(62 + (1 - t) * 145),
      Math.round(122 + (1 - t) * 110),
    ];
  }

  function renderTerrain(offscreen, mapData, layersData, activeLayer, tileSize) {
    const W = mapData.width;
    const H = mapData.height;
    const cw = W * tileSize;
    const ch = H * tileSize;
    offscreen.width = cw;
    offscreen.height = ch;
    const ctx = offscreen.getContext("2d");

    // Render 1px-per-tile shaded raster into a temp canvas, then scale crisply
    const small = document.createElement("canvas");
    small.width = W;
    small.height = H;
    const sctx = small.getContext("2d");
    const img = sctx.createImageData(W, H);
    const data = img.data;

    const palette = mapData.palette || {};
    const rgbById = {};
    for (const [id, entry] of Object.entries(palette)) {
      rgbById[id] = hexToRgb(entry.color);
    }

    const biomes = mapData.biomes || [];
    const elev = layersData?.elevation || [];
    const temps = layersData?.temperature || [];
    const depths = layersData?.ocean_depth || [];

    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const i = y * W + x;
        let r, g, b;
        if (activeLayer === "temperature" && temps.length) {
          [r, g, b] = tempRgb(temps[i]);
        } else if (activeLayer === "ocean_depth" && depths.length) {
          [r, g, b] = depthRgb(depths[i]);
        } else if (activeLayer === "species_density") {
          [r, g, b] = [15, 23, 42];
        } else {
          [r, g, b] = rgbById[String(biomes[i])] || [118, 200, 91];
          const depth = depths[i] || 0;
          if (depth > 0) {
            // Subtle ocean depth shading
            const oceanShade = 1.04 - 0.42 * (depth / 255);
            r *= oceanShade; g *= oceanShade; b *= oceanShade;
          } else if (elev.length) {
            // Northwest hillshading (light from top-left: -dx - dy)
            const eL = elev[y * W + Math.max(0, x - 1)];
            const eR = elev[y * W + Math.min(W - 1, x + 1)];
            const eU = elev[Math.max(0, y - 1) * W + x];
            const eD = elev[Math.min(H - 1, y + 1) * W + x];
            const slope = ((eL - eR) + (eU - eD)) * 0.011;
            const shade = Math.max(0.62, Math.min(1.32, 1.0 + slope));
            r *= shade; g *= shade; b *= shade;
          }
        }
        const p = i * 4;
        data[p] = Math.max(0, Math.min(255, r));
        data[p + 1] = Math.max(0, Math.min(255, g));
        data[p + 2] = Math.max(0, Math.min(255, b));
        data[p + 3] = 255;
      }
    }
    sctx.putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(small, 0, 0, cw, ch);

    // Draw rivers as blue lines growing wider downstream
    if (activeLayer === "biomes" && Array.isArray(mapData.rivers)) {
      ctx.strokeStyle = "#3a86ff";
      ctx.lineCap = "round";
      for (const path of mapData.rivers) {
        if (!path || path.length < 2) continue;
        const n = path.length - 1;
        for (let k = 0; k < n; k++) {
          const [x1, y1] = path[k];
          const [x2, y2] = path[k + 1];
          ctx.lineWidth = Math.max(0.8, tileSize * (0.18 + 0.55 * (k / n)));
          ctx.beginPath();
          ctx.moveTo(x1 * tileSize + tileSize / 2, y1 * tileSize + tileSize / 2);
          ctx.lineTo(x2 * tileSize + tileSize / 2, y2 * tileSize + tileSize / 2);
          ctx.stroke();
        }
      }
    }
  }

  return { renderTerrain };
})();
