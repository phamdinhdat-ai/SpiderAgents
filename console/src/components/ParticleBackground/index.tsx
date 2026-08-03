import { useEffect, useRef } from "react";
import { useTheme } from "../../contexts/ThemeContext";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  alpha: number;
}

/**
 * Lightweight canvas particle background.
 *
 * Renders slow-drifting, softly glowing dots behind the app layout.
 * The color adapts to the current theme (orange accent on light,
 * cool tint on dark). Respects `prefers-reduced-motion` by rendering
 * a static frame instead of animating.
 */
export default function ParticleBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { isDark } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let width = 0;
    let height = 0;
    let particles: Particle[] = [];

    const reducedMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    const COLOR = isDark ? "255, 160, 90" : "255, 127, 22";

    const init = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * DPR;
      canvas.height = height * DPR;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

      const count = Math.min(70, Math.floor((width * height) / 22000));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.15,
        vy: -0.05 - Math.random() * 0.12,
        r: 1 + Math.random() * 2.2,
        alpha: 0.08 + Math.random() * 0.25,
      }));
    };

    const draw = (animate: boolean) => {
      ctx.clearRect(0, 0, width, height);
      for (const p of particles) {
        if (animate) {
          p.x += p.vx;
          p.y += p.vy;
          // Respawn near the bottom when drifting off the top
          if (p.y < -10) {
            p.y = height + 10;
            p.x = Math.random() * width;
          }
          if (p.x < -10) p.x = width + 10;
          if (p.x > width + 10) p.x = -10;
        }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${COLOR}, ${p.alpha})`;
        ctx.fill();
      }
      if (animate) {
        raf = requestAnimationFrame(() => draw(true));
      }
    };

    init();
    if (reducedMotion) {
      draw(false);
    } else {
      draw(true);
    }

    const onResize = () => {
      init();
      if (reducedMotion) draw(false);
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, [isDark]);

  return <canvas ref={canvasRef} className="particle-bg" aria-hidden="true" />;
}
