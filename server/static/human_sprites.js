/** Gene- and tech-driven layered human sprite generator with LRU canvas cache. */
window.WorldHumanSprites = (() => {
  const SIZE = 32, MAX_CACHE = 800;
  const cache = new Map();

  const SKIN_STOPS = [
    [244, 212, 188], [224, 178, 142], [192, 138, 98], [148, 96, 62], [96, 58, 36],
  ];
  const HAIR_STOPS = [
    [226, 192, 108], [166, 92, 46], [94, 58, 34], [38, 30, 26], [18, 16, 20],
  ];
  const JOB_TUNIC = {
    farmer: "#3b82f6", woodcutter: "#15803d", hunter: "#b45309", builder: "#9333ea",
    healer: "#0d9488", teacher: "#2563eb", trader: "#d97706", storyteller: "#be185d",
  };

  function pickStop(stops, t) {
    const clamped = Math.max(0, Math.min(1, t ?? 0.5));
    const idx = Math.min(stops.length - 1, Math.round(clamped * (stops.length - 1)));
    const c = stops[idx];
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  function techTier(knownTechs) {
    const s = new Set(knownTechs || []);
    if (s.has("iron")) return "iron";
    if (s.has("bronze")) return "bronze";
    if (s.has("weaving") || s.has("pottery")) return "woven";
    return "hide";
  }

  function carriedKind(inv) {
    if (!inv) return "none";
    if ((inv.wood || 0) >= 1) return "wood";
    if ((inv.stone || 0) >= 1) return "stone";
    if ((inv.food || 0) >= 1) return "food";
    return "none";
  }

  function mapAnim(human) {
    if (!human.alive) return "die";
    const a = (human.last_action || "walk").toLowerCase();
    if (a.includes("sleep") || a.includes("rest")) return "sleep";
    if (a.includes("eat")) return "eat";
    if (a.includes("gather") || a.includes("build") || a.includes("work") || a.includes("farm")) return "work";
    return "walk";
  }

  function drawHuman(ctx, spec) {
    const { stage, sex, anim, frame, g, tier, job, carry, highlight } = spec;
    const sc = stage === "child" ? 0.68 : (stage === "elder" ? 0.94 : 1.0);
    const hScale = sc * (0.88 + (g.size ?? 0.5) * 0.26);
    const wScale = sc * (0.86 + (g.endurance ?? 0.5) * 0.28);
    const skin = pickStop(SKIN_STOPS, g.skin_tone ?? 0.5);
    const hair = stage === "elder" ? "#e2e8f0" : pickStop(HAIR_STOPS, g.hair_tone ?? 0.6);
    const tunic = tier === "hide" ? "#9a6b3e" : (JOB_TUNIC[job] || "#3b82f6");
    const stride = anim === "walk" ? Math.sin((frame / 4) * Math.PI * 2) * 2.5 : 0;
    const armSwing = anim === "work" ? (frame % 2 === 0 ? -4 : 3) : (anim === "eat" ? -3 : stride * 0.7);

    ctx.save();
    ctx.translate(SIZE / 2, SIZE / 2 + 2);
    if (anim === "die") { ctx.rotate(Math.PI / 2); ctx.globalAlpha = frame % 2 === 0 ? 0.85 : 0.45; }

    // Selection / hover halo
    if (highlight) {
      ctx.strokeStyle = highlight === "sel" ? "#facc15" : "#38bdf8";
      ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.ellipse(0, 7, 7.5, 3.2, 0, 0, Math.PI * 2); ctx.stroke();
    }

    // Shadow
    ctx.fillStyle = "rgba(0,0,0,0.24)";
    ctx.beginPath(); ctx.ellipse(0, 8, 6 * wScale, 2.2, 0, 0, Math.PI * 2); ctx.fill();

    if (anim === "sleep") {
      ctx.fillStyle = tunic;
      ctx.fillRect(-6, 1, 10, 4.5);
      ctx.fillStyle = skin;
      ctx.beginPath(); ctx.arc(5.5, 3, 2.8, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#fef08a"; ctx.font = "bold 7px sans-serif";
      ctx.fillText(frame % 2 === 0 ? "z" : "Z", 5, -3);
      ctx.restore();
      return;
    }

    ctx.scale(wScale, hScale);

    // Legs
    ctx.strokeStyle = tier === "hide" ? "#6b4423" : "#334155";
    ctx.lineWidth = 2.0; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(-2, 2); ctx.lineTo(-2 - stride, 8); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(2, 2); ctx.lineTo(2 + stride, 8); ctx.stroke();

    // Torso / Clothing (hides, woven tunic, or metal-trimmed armor)
    ctx.fillStyle = tunic;
    ctx.beginPath();
    if (sex === "F" && tier !== "hide") {
      ctx.moveTo(-3.6, -4.5); ctx.lineTo(3.6, -4.5); ctx.lineTo(4.8, 3.2); ctx.lineTo(-4.8, 3.2);
    } else {
      ctx.roundRect ? ctx.roundRect(-3.8, -4.5, 7.6, 7.2, 1.5) : ctx.rect(-3.8, -4.5, 7.6, 7.2);
    }
    ctx.fill();

    if (tier === "hide") {
      // Diagonal fur-hide strap
      ctx.strokeStyle = "#5c3a21"; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(-3.5, -4); ctx.lineTo(3.5, 2.5); ctx.stroke();
    } else if (tier === "bronze" || tier === "iron") {
      const metal = tier === "iron" ? "#cbd5e1" : "#d97706";
      ctx.fillStyle = metal;
      ctx.fillRect(-4.0, -4.6, 8.0, 1.8);
      ctx.fillRect(-3.8, 0.8, 7.6, 1.2);
    }

    // Arms
    ctx.strokeStyle = skin; ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.moveTo(-4, -3.5); ctx.lineTo(-6.2, 0.5 - armSwing * 0.5); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(4, -3.5); ctx.lineTo(6.2, 0.5 + armSwing * 0.6); ctx.stroke();

    // Tool in right hand based on tech level
    const toolColor = tier === "iron" ? "#e2e8f0" : (tier === "bronze" ? "#f59e0b" : "#94a3b8");
    ctx.strokeStyle = "#78350f"; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(6.2, 3.5 + armSwing * 0.4); ctx.lineTo(6.8, -5.5 + armSwing * 0.4); ctx.stroke();
    ctx.fillStyle = toolColor;
    ctx.beginPath(); ctx.moveTo(6.8, -7.8 + armSwing * 0.4); ctx.lineTo(8.5, -4.8 + armSwing * 0.4); ctx.lineTo(5.2, -4.8 + armSwing * 0.4); ctx.closePath(); ctx.fill();

    // Carried item in left hand
    if (carry !== "none") {
      ctx.fillStyle = carry === "wood" ? "#7c471b" : (carry === "stone" ? "#94a3b8" : "#eab308");
      ctx.beginPath(); ctx.arc(-6.8, 0.2, 2.2, 0, Math.PI * 2); ctx.fill();
    }

    // Head + Hair + Eyes
    const headY = stage === "elder" ? -7.2 : -8.0;
    ctx.fillStyle = skin;
    ctx.beginPath(); ctx.arc(0, headY, 3.5, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = hair;
    ctx.beginPath(); ctx.arc(0, headY - 0.8, 3.6, Math.PI, Math.PI * 2); ctx.fill();
    if (sex === "F") {
      ctx.fillRect(-3.6, headY - 1, 1.3, 4.2);
      ctx.fillRect(2.3, headY - 1, 1.3, 4.2);
    }
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(-1.5, headY - 0.3, 1.0, 1.0);
    ctx.fillRect(0.8, headY - 0.3, 1.0, 1.0);
    ctx.restore();
  }

  function getHumanSprite(human, frameIdx, highlight = "") {
    const g = human.genome || {};
    const anim = mapAnim(human);
    const frame = (anim === "walk") ? (frameIdx % 4) : (frameIdx % 2);
    const tier = techTier(human.culture?.known_techs);
    const carry = carriedKind(human.inventory);
    const job = human.persona?.job || "farmer";
    const q = (v) => Math.round((v ?? 0.5) * 4);
    const key = `${human.stage || "adult"}|${human.sex || "F"}|${anim}|${frame}|${tier}|${job}|${carry}|${q(g.size)}|${q(g.skin_tone)}|${q(g.hair_tone)}|${highlight}`;
    if (cache.has(key)) return cache.get(key);

    const c = document.createElement("canvas");
    c.width = SIZE; c.height = SIZE;
    drawHuman(c.getContext("2d"), {
      stage: human.stage || "adult", sex: human.sex || "F", anim, frame, g, tier, job, carry, highlight,
    });

    if (cache.size >= MAX_CACHE) cache.delete(cache.keys().next().value);
    cache.set(key, c);
    return c;
  }

  return { getHumanSprite, SIZE };
})();
