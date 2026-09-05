const PHASES = [
  { label: "事实梳理", x: 0.73, y: 0.22, copper: [180, 125, 36] },
  { label: "证据核对", x: 0.82, y: 0.41, copper: [164, 113, 31] },
  { label: "法源分析", x: 0.68, y: 0.64, copper: [138, 101, 42] },
  { label: "行动方案", x: 0.84, y: 0.78, copper: [113, 92, 51] },
];

const sceneMemory = new WeakMap();
const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
const mix = (from, to, amount) => from + (to - from) * amount;
const easeOut = (value) => 1 - Math.pow(1 - clamp(value, 0, 1), 4);

export function particleBudget(viewportWidth, logicalCores = 8, reducedMotion = false) {
  if (reducedMotion) return 24;
  const base = viewportWidth <= 420 ? 28 : viewportWidth <= 1024 ? 52 : 84;
  return logicalCores > 0 && logicalCores <= 4 ? Math.floor(base * 0.76) : base;
}

export function animationShouldRun(reducedMotion, visible) {
  return !reducedMotion && visible;
}

export function cycleState(elapsed) {
  const safeElapsed = Math.max(0, elapsed);
  const cycleIndex = Math.floor(safeElapsed / 12000);
  const position = safeElapsed % 12000;

  if (position < 3000) {
    return { stage: "gather", blend: easeOut(position / 3000), cycleIndex };
  }
  if (position < 5000) {
    return { stage: "hold", blend: 1, cycleIndex };
  }
  if (position < 9000) {
    return {
      stage: "release",
      blend: 1 - easeOut((position - 5000) / 4000),
      cycleIndex,
    };
  }
  return { stage: "drift", blend: 0, cycleIndex };
}

export function phaseSignal(label) {
  const index = PHASES.findIndex((phase) => phase.label === label);
  return { ...PHASES[index < 0 ? 0 : index], index: index < 0 ? 0 : index };
}

export function particleAnchor(index, width, height) {
  const phase = PHASES[Math.abs(index) % PHASES.length];
  return { x: width * phase.x, y: height * phase.y };
}

export function sceneDimensions(width, height) {
  return {
    width: Math.max(1, Math.round(width)),
    height: height > 1 ? Math.round(height) : 300,
  };
}

export function localPointer(clientX, clientY, rect) {
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  return {
    x: clamp(clientX - rect.left, 0, width),
    y: clamp(clientY - rect.top, 0, height),
    active: clientX >= rect.left
      && clientX <= rect.left + width
      && clientY >= rect.top
      && clientY <= rect.top + height,
  };
}

function pointsOnLine(points, count, startX, startY, endX, endY) {
  for (let index = 0; index < count; index += 1) {
    const amount = count === 1 ? 0.5 : index / (count - 1);
    points.push({ x: mix(startX, endX, amount), y: mix(startY, endY, amount) });
  }
}

function pointsOnPan(points, count, centerX, centerY, radiusX, radiusY) {
  for (let index = 0; index < count; index += 1) {
    const amount = count === 1 ? 0.5 : index / (count - 1);
    const angle = Math.PI * amount;
    points.push({
      x: centerX - radiusX * Math.cos(angle),
      y: centerY + radiusY * Math.sin(angle),
    });
  }
}

export function balanceTargets(count, width, height) {
  const centerX = width * (width <= 640 ? 0.72 : 0.68);
  const centerY = height * (width <= 640 ? 0.3 : 0.31);
  const scale = clamp(
    Math.min(width, height) * (width <= 640 ? 0.24 : 0.28),
    82,
    250,
  );
  const points = [];
  const shaftCount = Math.round(count * 0.15);
  const beamCount = Math.round(count * 0.15);
  const baseCount = Math.round(count * 0.11);
  const chainCount = Math.round(count * 0.05);
  const panCount = Math.round(count * 0.14);

  pointsOnLine(points, shaftCount, centerX, centerY - scale * 0.48, centerX, centerY + scale * 0.5);
  pointsOnLine(points, beamCount, centerX - scale * 0.7, centerY - scale * 0.24, centerX + scale * 0.7, centerY - scale * 0.24);
  pointsOnLine(points, baseCount, centerX - scale * 0.34, centerY + scale * 0.52, centerX + scale * 0.34, centerY + scale * 0.52);
  pointsOnLine(points, chainCount, centerX - scale * 0.5, centerY - scale * 0.22, centerX - scale * 0.66, centerY + scale * 0.12);
  pointsOnLine(points, chainCount, centerX - scale * 0.5, centerY - scale * 0.22, centerX - scale * 0.34, centerY + scale * 0.12);
  pointsOnLine(points, chainCount, centerX + scale * 0.5, centerY - scale * 0.22, centerX + scale * 0.34, centerY + scale * 0.12);
  pointsOnLine(points, chainCount, centerX + scale * 0.5, centerY - scale * 0.22, centerX + scale * 0.66, centerY + scale * 0.12);
  pointsOnPan(points, panCount, centerX - scale * 0.5, centerY + scale * 0.12, scale * 0.18, scale * 0.12);
  pointsOnPan(points, panCount, centerX + scale * 0.5, centerY + scale * 0.12, scale * 0.18, scale * 0.12);

  const finialCount = Math.max(0, count - points.length);
  for (let index = 0; index < finialCount; index += 1) {
    const angle = (index / Math.max(finialCount, 1)) * Math.PI * 2;
    points.push({
      x: centerX + Math.cos(angle) * scale * 0.065,
      y: centerY - scale * 0.47 + Math.sin(angle) * scale * 0.065,
    });
  }

  return points.slice(0, count).map((point) => ({
    x: clamp(point.x, 0, width),
    y: clamp(point.y, 0, height),
  }));
}

function makeParticles(count, width, height) {
  return Array.from({ length: count }, (_, index) => {
    const anchorIndex = index % PHASES.length;
    const anchor = particleAnchor(anchorIndex, width, height);
    const ambient = index % 9 === 0;
    return {
      x: ambient
        ? Math.random() * width
        : clamp(anchor.x + (Math.random() - 0.5) * width * 0.24, 0, width),
      y: ambient
        ? height * (0.08 + Math.random() * 0.84)
        : clamp(anchor.y + (Math.random() - 0.5) * height * 0.24, 0, height),
      vx: (Math.random() - 0.5) * 0.16,
      vy: (Math.random() - 0.5) * 0.14,
      radius: index % 13 === 0 ? 2.25 : 0.7 + Math.random() * 1.15,
      alpha: 0.24 + Math.random() * 0.5,
      warmth: Math.random(),
      anchorIndex,
      ambient,
    };
  });
}

function resizeScene(scene, canvas, context, width, height, reducedMotion) {
  const density = Math.min(window.devicePixelRatio || 1, 1.5);
  canvas.width = Math.round(width * density);
  canvas.height = Math.round(height * density);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  context.setTransform(density, 0, 0, density, 0, 0);

  const budget = particleBudget(width, navigator.hardwareConcurrency || 8, reducedMotion);
  if (!scene.particles || scene.particles.length !== budget) {
    scene.particles = makeParticles(budget, width, height);
  } else if (scene.width && scene.height) {
    for (const particle of scene.particles) {
      particle.x = (particle.x / scene.width) * width;
      particle.y = (particle.y / scene.height) * height;
    }
  }
  scene.width = width;
  scene.height = height;
  scene.targets = balanceTargets(budget, width, height);
}

function drawBackgroundEnergy(context, scene, signal, time) {
  const anchorX = scene.width * signal.x;
  const anchorY = scene.height * signal.y;
  const breathing = 0.5 + Math.sin(time * 0.00045) * 0.05;
  const gradient = context.createRadialGradient(anchorX, anchorY, 8, anchorX, anchorY, scene.width * 0.29);
  gradient.addColorStop(0, `rgba(${signal.copper.join(",")},${0.075 * breathing})`);
  gradient.addColorStop(0.46, "rgba(196,139,44,0.025)");
  gradient.addColorStop(1, "rgba(196,139,44,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, scene.width, scene.height);
}

function releaseBalance(scene, cycle) {
  if (cycle.stage !== "release" || scene.releasedCycle === cycle.cycleIndex) return;
  const originX = scene.width * (scene.width <= 640 ? 0.72 : 0.68);
  const originY = scene.height * 0.31;
  scene.particles.forEach((particle, index) => {
    const target = scene.targets[index];
    const dx = target.x - originX;
    const dy = target.y - originY;
    const distance = Math.hypot(dx, dy) || 1;
    particle.vx += (dx / distance) * (0.16 + Math.random() * 0.12);
    particle.vy += (dy / distance) * (0.16 + Math.random() * 0.12);
  });
  scene.releasedCycle = cycle.cycleIndex;
}

function advanceParticles(scene, pointer) {
  const interactionRadius = scene.width <= 640 ? 105 : 155;
  for (const particle of scene.particles) {
    if (!particle.ambient) {
      const anchor = particleAnchor(particle.anchorIndex, scene.width, scene.height);
      particle.vx += (anchor.x - particle.x) * 0.000009;
      particle.vy += (anchor.y - particle.y) * 0.000009;
    }
    if (pointer.active) {
      const dx = pointer.x - particle.x;
      const dy = pointer.y - particle.y;
      const distance = Math.hypot(dx, dy) || 1;
      if (distance < interactionRadius) {
        const pull = (1 - distance / interactionRadius) * 0.011;
        particle.vx += (dx / distance) * pull;
        particle.vy += (dy / distance) * pull;
      }
    }
    particle.vx *= 0.993;
    particle.vy *= 0.993;
    particle.vx += (Math.random() - 0.5) * 0.0026;
    particle.vy += (Math.random() - 0.5) * 0.0022;
    particle.x += particle.vx;
    particle.y += particle.vy;

    const margin = 24;
    if (particle.x < -margin) particle.x = scene.width + margin;
    if (particle.x > scene.width + margin) particle.x = -margin;
    if (particle.y < -margin) particle.y = scene.height + margin;
    if (particle.y > scene.height + margin) particle.y = -margin;
  }
}

function renderedPoints(scene, blend) {
  return scene.particles.map((particle, index) => ({
    ...particle,
    drawX: mix(particle.x, scene.targets[index].x, blend),
    drawY: mix(particle.y, scene.targets[index].y, blend),
  }));
}

function drawConnections(context, points, width, blend) {
  const threshold = width <= 640 ? 72 : 118;
  context.lineWidth = 0.65;
  for (let first = 0; first < points.length; first += 1) {
    for (let second = first + 1; second < points.length; second += 1) {
      const dx = points[first].drawX - points[second].drawX;
      const dy = points[first].drawY - points[second].drawY;
      const distance = Math.hypot(dx, dy);
      if (distance >= threshold) continue;
      const strength = (1 - distance / threshold) * (0.09 + blend * 0.24);
      context.strokeStyle = `rgba(105,82,45,${strength})`;
      context.beginPath();
      context.moveTo(points[first].drawX, points[first].drawY);
      context.lineTo(points[second].drawX, points[second].drawY);
      context.stroke();
    }
  }
}

function drawParticles(context, points, blend, holdPulse = 0) {
  for (const particle of points) {
    const copper = particle.warmth > 0.28 ? "185,127,35" : "31,82,72";
    context.fillStyle = `rgba(${copper},${Math.min(0.84, particle.alpha + blend * 0.2)})`;
    context.beginPath();
    context.arc(
      particle.drawX,
      particle.drawY,
      particle.radius + blend * 0.38 + holdPulse * 0.42,
      0,
      Math.PI * 2,
    );
    context.fill();
  }
}

function drawBalanceAura(context, scene, blend, holdPulse, timestamp) {
  if (blend < 0.02) return;
  const centerX = scene.width * (scene.width <= 640 ? 0.72 : 0.68);
  const centerY = scene.height * (scene.width <= 640 ? 0.3 : 0.31);
  const scale = clamp(
    Math.min(scene.width, scene.height) * (scene.width <= 640 ? 0.24 : 0.28),
    82,
    250,
  );

  context.save();
  context.lineWidth = 0.75;
  context.strokeStyle = `rgba(177,123,34,${0.07 * blend + holdPulse * 0.035})`;
  context.setLineDash([3, 10]);
  context.lineDashOffset = -timestamp * 0.006;
  context.beginPath();
  context.ellipse(centerX, centerY, scale * 1.16, scale * 0.78, -0.1, 0, Math.PI * 2);
  context.stroke();

  context.strokeStyle = `rgba(31,82,72,${0.045 * blend})`;
  context.setLineDash([1, 14]);
  context.lineDashOffset = timestamp * 0.004;
  context.beginPath();
  context.ellipse(centerX, centerY, scale * 1.34, scale * 0.92, 0.12, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}

function drawPhasePulse(context, scene, signal, elapsed) {
  if (elapsed < 0 || elapsed > 980) return;
  const progress = easeOut(elapsed / 980);
  const alpha = (1 - progress) * 0.28;
  const radius = 18 + progress * (scene.width <= 640 ? 74 : 138);
  context.strokeStyle = `rgba(${signal.copper.join(",")},${alpha})`;
  context.lineWidth = 1;
  context.beginPath();
  context.arc(scene.width * signal.x, scene.height * signal.y, radius, 0, Math.PI * 2);
  context.stroke();
}

function drawStaticConstellation(context, scene, signal) {
  context.clearRect(0, 0, scene.width, scene.height);
  drawBackgroundEnergy(context, scene, signal, 0);
  const points = scene.particles.map((particle, index) => ({
    ...particle,
    drawX: scene.targets[index].x,
    drawY: scene.targets[index].y,
  }));
  drawBalanceAura(context, scene, 1, 0, 0);
  drawConnections(context, points, scene.width, 0.72);
  drawParticles(context, points, 0.38);
}

export default function renderEvidenceConstellation(component) {
  const { data = {}, parentElement } = component;
  const container = parentElement.querySelector(".evidence-constellation");
  const canvas = parentElement.querySelector(".evidence-constellation__canvas");
  if (!container || !canvas) return undefined;
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) return undefined;

  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const signal = phaseSignal(data.phase);
  const previous = sceneMemory.get(parentElement);
  const scene = previous || { particles: null, targets: [], phase: signal.label };
  const now = performance.now();
  const phaseChanged = previous && scene.phase !== signal.label;
  scene.phase = signal.label;
  scene.startedAt = scene.startedAt || now;
  scene.phaseStartedAt = phaseChanged ? now : Number.NEGATIVE_INFINITY;
  sceneMemory.set(parentElement, scene);

  const pointer = {
    x: 0,
    y: 0,
    active: false,
  };
  let animationFrame = 0;
  let stopped = false;

  const resize = () => {
    const rect = container.getBoundingClientRect();
    const dimensions = sceneDimensions(rect.width, rect.height);
    if (rect.height <= 1) container.style.height = `${dimensions.height}px`;
    resizeScene(
      scene,
      canvas,
      context,
      dimensions.width,
      dimensions.height,
      motionQuery.matches,
    );
    if (motionQuery.matches) drawStaticConstellation(context, scene, signal);
  };

  const frame = (timestamp) => {
    if (
      stopped
      || !animationShouldRun(motionQuery.matches, !document.hidden)
    ) {
      animationFrame = 0;
      return;
    }
    const elapsed = timestamp - scene.startedAt;
    const cycle = cycleState(elapsed);
    const holdPulse = cycle.stage === "hold"
      ? (Math.sin((elapsed - 3000) * 0.006) + 1) * 0.5
      : 0;
    releaseBalance(scene, cycle);
    advanceParticles(scene, pointer);
    const points = renderedPoints(scene, cycle.blend);

    context.clearRect(0, 0, scene.width, scene.height);
    drawBackgroundEnergy(context, scene, signal, timestamp);
    drawBalanceAura(context, scene, cycle.blend, holdPulse, timestamp);
    drawConnections(context, points, scene.width, cycle.blend);
    drawParticles(context, points, cycle.blend, holdPulse);
    drawPhasePulse(context, scene, signal, timestamp - scene.phaseStartedAt);
    animationFrame = requestAnimationFrame(frame);
  };

  const start = () => {
    cancelAnimationFrame(animationFrame);
    animationFrame = 0;
    if (animationShouldRun(motionQuery.matches, !document.hidden)) {
      animationFrame = requestAnimationFrame(frame);
    } else if (motionQuery.matches) {
      drawStaticConstellation(context, scene, signal);
    }
  };

  const onPointerMove = (event) => {
    const nextPointer = localPointer(
      event.clientX,
      event.clientY,
      container.getBoundingClientRect(),
    );
    pointer.x = nextPointer.x;
    pointer.y = nextPointer.y;
    pointer.active = nextPointer.active;
    if (!animationFrame) start();
  };
  const onPointerLeave = () => { pointer.active = false; };
  const onVisibility = () => start();
  const onMotionChange = () => {
    resize();
    start();
  };

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);
  window.addEventListener("pointermove", onPointerMove, { passive: true });
  document.addEventListener("pointerleave", onPointerLeave, { passive: true });
  document.addEventListener("visibilitychange", onVisibility);
  motionQuery.addEventListener("change", onMotionChange);
  resize();
  start();

  return () => {
    stopped = true;
    cancelAnimationFrame(animationFrame);
    resizeObserver.disconnect();
    window.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerleave", onPointerLeave);
    document.removeEventListener("visibilitychange", onVisibility);
    motionQuery.removeEventListener("change", onMotionChange);
  };
}
