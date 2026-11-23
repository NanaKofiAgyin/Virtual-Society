/** Procedural gene-driven layered animal sprite generator with LRU canvas cache. */
window.WorldSprites = (() => {
  const SIZE = 32, MAX_CACHE = 1200;
  const cache = new Map();

  const BASE_COLORS = {
    deer: [184, 128, 72], antelope: [204, 152, 86], rabbit: [212, 198, 180],
    elephant: [148, 152, 158], whale: [68, 96, 134], turtle: [72, 138, 86],
    beaver: [126, 82, 48], duck: [130, 114, 88], frog: [74, 168, 78],
    bird: [88, 166, 224], seabird: [232, 238, 246], fox: [218, 108, 44],
    lizard: [108, 166, 82], big_fish: [72, 134, 196], salmon: [188, 104, 108],
    seal: [128, 138, 148], dolphin: [108, 154, 192], jellyfish: [218, 156, 232],
    octopus: [186, 88, 118], otter: [118, 84, 58], wolf: [118, 124, 134],
    lion: [212, 166, 88], bear: [108, 74, 48], shark: [112, 132, 152],
    orca: [32, 38, 46], eagle: [116, 78, 44], crocodile: [78, 122, 68],
    vulture: [88, 74, 68], hyena: [176, 142, 94], crab: [212, 78, 56],
    bat: [76, 68, 88],
  };

  function mixRgb(a, b, t) {
    return [
      Math.round(a[0] + (b[0] - a[0]) * t),
      Math.round(a[1] + (b[1] - a[1]) * t),
      Math.round(a[2] + (b[2] - a[2]) * t),
    ];
  }

  function rgbStr(c, delta = 0) {
    const cl = (v) => Math.max(0, Math.min(255, Math.round(v + delta)));
    return `rgb(${cl(c[0])},${cl(c[1])},${cl(c[2])})`;
  }

  function stageScale(stage) {
    if (stage === "baby" || stage === "child") return 0.56;
    if (stage === "juvenile") return 0.78;
    if (stage === "elder") return 0.94;
    return 1.0;
  }

  function archOf(species, bodyType) {
    if (species === "turtle" || species === "crab") return "shelled";
    if (bodyType === "flying" || species === "bird" || species === "eagle" || species === "seabird" || species === "duck" || species === "bat") return "winged";
    if (bodyType === "aquatic" || species === "shark" || species === "whale" || species === "orca" || species === "dolphin" || species === "big_fish" || species === "salmon") return "finned";
    if (species === "crocodile" || species === "lizard" || species === "frog") return "reptile";
    return "quadruped";
  }

  function drawCreature(ctx, spec, biomeRgb) {
    const { species, bodyType, stage, sex, anim, frame, g } = spec;
    const arch = archOf(species, bodyType);
    const base = BASE_COLORS[species] || [165, 152, 130];
    const camo = g.camouflage ?? 0.5;
    const bodyRgb = mixRgb(base, biomeRgb || base, Math.max(0, camo - 0.25) * 0.65);
    const dark = rgbStr(bodyRgb, -42), main = rgbStr(bodyRgb, 0), light = rgbStr(bodyRgb, 36);
    const sc = stageScale(stage) * (0.76 + (g.size ?? 0.5) * 0.48);
    const legLen = 3.5 + (g.speed ?? 0.5) * 4.5;
    const fluffy = (g.cold_tolerance ?? 0.5) > 0.62;
    const stride = anim === "walk" ? Math.sin((frame / 4) * Math.PI * 2) * 2.8 : 0;
    const flap = anim === "fly" ? [5, 1, -5, 1][frame % 4] : 0;
    const wave = anim === "swim" ? Math.sin((frame / 4) * Math.PI * 2) * 2.5 : 0;
    const headDip = anim === "eat" && (frame % 2 === 1) ? 3.2 : 0;

    ctx.save();
    ctx.translate(SIZE / 2, SIZE / 2 + 2);
    if (anim === "die") { ctx.rotate(Math.PI / 2); ctx.globalAlpha = frame % 2 === 0 ? 0.85 : 0.45; }
    ctx.scale(sc, sc);

    // Ground/water shadow
    ctx.fillStyle = "rgba(0,0,0,0.22)";
    ctx.beginPath();
    ctx.ellipse(0, arch === "winged" ? 9 : 6, 8, 2.6, 0, 0, Math.PI * 2);
    ctx.fill();

    if (anim === "sleep") {
      // Curled resting body + sleeping z
      ctx.fillStyle = main; ctx.strokeStyle = dark; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.ellipse(0, 2, 7.5, 5, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = light; ctx.beginPath(); ctx.arc(4, 1, 3.2, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#fef08a"; ctx.font = "bold 7px sans-serif";
      ctx.fillText(frame % 2 === 0 ? "z" : "Z", 5, -5);
      ctx.restore();
      return;
    }

    if (arch === "finned") {
      // Swimming aquatic creature: tail fin, dorsal fin, streamlined body, eye
      ctx.fillStyle = dark;
      ctx.beginPath(); ctx.moveTo(-6, 0); ctx.lineTo(-12, -4 + wave); ctx.lineTo(-12, 4 + wave); ctx.closePath(); ctx.fill();
      if (species === "shark" || species === "orca" || species === "dolphin") {
        ctx.beginPath(); ctx.moveTo(-1, -4); ctx.lineTo(2, -9.5); ctx.lineTo(4, -3.5); ctx.closePath(); ctx.fill();
      }
      ctx.fillStyle = main;
      ctx.beginPath(); ctx.ellipse(1, 0, 8.5, 4.4, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = species === "orca" ? "#f8fafc" : light;
      ctx.beginPath(); ctx.ellipse(2, 1.8, 5.5, 1.8, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#0f172a"; ctx.fillRect(6, -1.8, 1.6, 1.6);
      if (anim === "swim") {
        ctx.strokeStyle = "rgba(255,255,255,0.45)"; ctx.lineWidth = 0.8;
        ctx.beginPath(); ctx.arc(-9, wave * 0.5, 2.5, 0.5, 2.6); ctx.stroke();
      }
    } else if (arch === "winged") {
      // Flying/perching bird or bat: animated wings, body, head, beak, sex crest
      const yOff = anim === "fly" ? -3 : 0;
      ctx.fillStyle = dark;
      ctx.beginPath(); ctx.moveTo(-2, yOff); ctx.quadraticCurveTo(-7, yOff - 5 - flap, -11, yOff - flap); ctx.lineTo(-4, yOff + 2); ctx.fill();
      ctx.beginPath(); ctx.moveTo(2, yOff); ctx.quadraticCurveTo(7, yOff - 5 - flap, 11, yOff - flap); ctx.lineTo(4, yOff + 2); ctx.fill();
      ctx.fillStyle = main;
      ctx.beginPath(); ctx.ellipse(0, yOff + 1, 5.2, 3.6, 0, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.arc(4.8, yOff - 1.5 + headDip * 0.5, 2.8, 0, Math.PI * 2); ctx.fill();
      if (sex === "M" && species !== "bat") {
        ctx.fillStyle = "#f97316"; ctx.fillRect(3.5, yOff - 5.2, 2.8, 1.8);
      }
      ctx.fillStyle = species === "bat" ? dark : "#f59e0b";
      ctx.beginPath(); ctx.moveTo(7.2, yOff - 1.5 + headDip * 0.5); ctx.lineTo(10.5, yOff - 0.5 + headDip * 0.5); ctx.lineTo(7.2, yOff + 0.4 + headDip * 0.5); ctx.fill();
      ctx.fillStyle = "#0f172a"; ctx.fillRect(5.6, yOff - 2.4 + headDip * 0.5, 1.2, 1.2);
    } else if (arch === "shelled") {
      // Turtle or crab with patterned carapace + legs
      ctx.strokeStyle = dark; ctx.lineWidth = 1.6;
      for (const lx of [-5, 0, 5]) {
        ctx.beginPath(); ctx.moveTo(lx, 2); ctx.lineTo(lx + stride * 0.5, 5.5); ctx.stroke();
      }
      ctx.fillStyle = dark; ctx.beginPath(); ctx.ellipse(0, 0, 7.5, 5.2, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = main; ctx.beginPath(); ctx.ellipse(0, -0.5, 5.6, 3.6, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = light; ctx.beginPath(); ctx.arc(7.8, 0.5 + headDip * 0.4, 2.4, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#0f172a"; ctx.fillRect(8.6, -0.4 + headDip * 0.4, 1.1, 1.1);
    } else {
      // Quadruped / Reptile: tail, 4 speed-scaled legs, fur-thick body, head, ears/antlers/mane
      ctx.strokeStyle = dark; ctx.lineWidth = species === "elephant" ? 2.6 : 1.5; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(-7, -1); ctx.quadraticCurveTo(-11, -4 + stride * 0.4, -12, arch === "reptile" ? 2 : -2); ctx.stroke();
      const bodyY = arch === "reptile" ? 2 : 0;
      const legY = bodyY + (arch === "reptile" ? 3.5 : legLen);
      for (const [lx, dir] of [[-5, 1], [-2.5, -1], [3, -1], [5.2, 1]]) {
        ctx.beginPath(); ctx.moveTo(lx, bodyY + 1.5); ctx.lineTo(lx + stride * dir, legY); ctx.stroke();
      }
      if (fluffy) {
        ctx.fillStyle = light;
        ctx.beginPath(); ctx.ellipse(0, bodyY, 8.6, 5.6, 0, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = main;
      ctx.beginPath(); ctx.ellipse(0, bodyY, 7.4, arch === "reptile" ? 3.2 : 4.6, 0, 0, Math.PI * 2); ctx.fill();
      // Head
      const hx = 7.2, hy = bodyY - 2.6 + headDip;
      if (species === "lion" && sex === "M") {
        ctx.fillStyle = "#7c471b"; ctx.beginPath(); ctx.arc(hx - 0.8, hy, 4.6, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = main; ctx.beginPath(); ctx.arc(hx, hy, 3.2, 0, Math.PI * 2); ctx.fill();
      // Ears / Antlers / Trunk
      if (species === "elephant") {
        ctx.strokeStyle = main; ctx.lineWidth = 2.0;
        ctx.beginPath(); ctx.moveTo(hx + 2.2, hy + 1); ctx.quadraticCurveTo(hx + 5, hy + 4, hx + 3.5, hy + 7); ctx.stroke();
      } else if ((species === "deer" || species === "antelope") && sex === "M" && stage === "adult") {
        ctx.strokeStyle = "#78350f"; ctx.lineWidth = 1.1;
        ctx.beginPath(); ctx.moveTo(hx, hy - 2.8); ctx.lineTo(hx - 1.5, hy - 7.5); ctx.moveTo(hx + 1, hy - 2.8); ctx.lineTo(hx + 3, hy - 7.5); ctx.stroke();
      } else if (arch !== "reptile") {
        const earH = species === "rabbit" ? 5.5 : 2.6;
        ctx.fillStyle = dark; ctx.beginPath(); ctx.ellipse(hx - 1, hy - 2.5 - earH * 0.4, 1.2, earH * 0.6, -0.2, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = "#0f172a"; ctx.fillRect(hx + 1.1, hy - 1.1, 1.3, 1.3);
    }
    ctx.restore();
  }

  function getAnimalSprite(animal, biomeRgb, frameIdx) {
    const g = animal.genome || {};
    const anim = !animal.alive ? "die" : (animal.last_action || (animal.body_type === "flying" ? "fly" : animal.body_type === "aquatic" ? "swim" : "walk"));
    const frame = (anim === "eat" || anim === "sleep" || anim === "die") ? (frameIdx % 2) : (frameIdx % 4);
    const q = (v) => Math.round((v ?? 0.5) * 4);
    const bKey = biomeRgb ? `${biomeRgb[0] >> 5},${biomeRgb[1] >> 5},${biomeRgb[2] >> 5}` : "0";
    const key = `${animal.species}|${animal.stage || "adult"}|${animal.sex || "F"}|${anim}|${frame}|${q(g.size)}|${q(g.speed)}|${q(g.cold_tolerance)}|${q(g.camouflage)}|${bKey}`;
    if (cache.has(key)) return cache.get(key);

    const c = document.createElement("canvas");
    c.width = SIZE; c.height = SIZE;
    drawCreature(c.getContext("2d"), {
      species: animal.species, bodyType: animal.body_type || "land",
      stage: animal.stage || "adult", sex: animal.sex || "F", anim, frame, g,
    }, biomeRgb);

    if (cache.size >= MAX_CACHE) cache.delete(cache.keys().next().value);
    cache.set(key, c);
    return c;
  }

  return { getAnimalSprite, SIZE };
})();
