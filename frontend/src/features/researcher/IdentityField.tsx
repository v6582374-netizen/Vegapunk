import { useEffect, useRef } from "react";

type IdentityFieldProps = {
  seed: string;
  className?: string;
};

function seededRandom(seed: string) {
  let state = 2166136261;
  for (const character of seed) {
    state ^= character.charCodeAt(0);
    state = Math.imul(state, 16777619);
  }

  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

export function IdentityField({ seed, className }: IdentityFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const width = Math.max(1, bounds.width);
      const height = Math.max(1, bounds.height);
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      const context = canvas.getContext("2d");
      if (!context) return;

      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      context.setTransform(scale, 0, 0, scale, 0, 0);
      context.clearRect(0, 0, width, height);

      const tokens = getComputedStyle(document.documentElement);
      const deep = tokens.getPropertyValue("--color-identity-deep").trim();
      const mid = tokens.getPropertyValue("--color-identity-mid").trim();
      const light = tokens.getPropertyValue("--color-identity-light").trim();
      const random = seededRandom(seed);
      const count = Math.min(540, Math.max(180, Math.round((width * height) / 750)));

      for (let index = 0; index < count; index += 1) {
        const progress = index / count;
        const spread = (random() - 0.5) * height * 0.72;
        const x = width * (0.06 + progress * 0.88) + (random() - 0.5) * width * 0.08;
        const wave = Math.sin(progress * Math.PI * 4.2 + random() * 1.4) * height * 0.14;
        const y = height * 0.5 + wave + spread * (0.3 + random() * 0.7);
        const centerDistance = Math.abs(y - height * 0.5) / height;
        const radius = centerDistance < 0.19 ? 1 + random() * 2.2 : 0.5 + random() * 1.35;

        context.fillStyle = centerDistance < 0.14 ? deep : random() > 0.58 ? mid : light;
        context.globalAlpha = 0.16 + (1 - Math.min(centerDistance * 1.8, 1)) * 0.7;
        context.beginPath();
        context.arc(x, y, radius, 0, Math.PI * 2);
        context.fill();
      }

      context.globalAlpha = 0.3;
      context.strokeStyle = mid;
      context.lineWidth = 1;
      for (let index = 0; index < 5; index += 1) {
        const offset = random() * height;
        context.beginPath();
        context.moveTo(0, offset);
        context.bezierCurveTo(
          width * 0.28,
          offset - height * 0.16,
          width * 0.72,
          offset + height * 0.16,
          width,
          offset + (random() - 0.5) * height * 0.18,
        );
        context.stroke();
      }
      context.globalAlpha = 1;
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [seed]);

  return (
    <div className={`identity-field ${className ?? ""}`} aria-label="课题身份点云">
      <div className="identity-field-grid" aria-hidden="true" />
      <canvas ref={canvasRef} className="identity-field-canvas" aria-hidden="true" />
      <div className="identity-field-corners" aria-hidden="true">
        <span>RESEARCH FIELD</span>
        <span>VEGAPUNK / 01</span>
      </div>
    </div>
  );
}
