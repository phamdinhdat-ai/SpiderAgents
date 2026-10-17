import { useId } from "react";
import "./spider-scene.css";

/** Decorative vector web. Motion is CSS-only and follows the appearance toggle. */
export default function SpiderScene({
  background = false,
}: {
  background?: boolean;
}) {
  const id = useId().replace(/:/g, "");
  const center = { x: 180, y: 137 };
  const point = (radius: number, index: number) => {
    const angle = (index * Math.PI) / 6;
    return `${center.x + Math.cos(angle) * radius},${
      center.y + Math.sin(angle) * radius
    }`;
  };
  return (
    <div
      className={background ? "spider-web-background" : "spider-scene"}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 360 280"
        className="spider-scene-svg"
        fill="none"
        preserveAspectRatio={background ? "xMidYMid slice" : "xMidYMid meet"}
      >
        <defs>
          <radialGradient id={`web-glow-${id}`}>
            <stop stopColor="var(--spider-secondary)" stopOpacity=".15" />
            <stop
              offset="1"
              stopColor="var(--spider-secondary)"
              stopOpacity="0"
            />
          </radialGradient>
        </defs>
        <circle cx="180" cy="137" r="132" fill={`url(#web-glow-${id})`} />
        <g className="spider-web-threads">
          {Array.from({ length: 12 }, (_, index) => (
            <path key={`spoke-${index}`} d={`M180,137 L${point(157, index)}`} />
          ))}
          {[26, 52, 79, 106, 133].map((radius) => (
            <polygon
              key={radius}
              points={Array.from({ length: 12 }, (_, index) =>
                point(radius, index),
              ).join(" ")}
            />
          ))}
        </g>
        <g className="spider-web-signals">
          <path d={`M${point(133, 7)} L180,137 L${point(133, 1)}`} />
          <path d={`M${point(133, 11)} L180,137 L${point(133, 5)}`} />
        </g>
        {[1, 4, 7, 10].map((index, i) => (
          <circle
            key={index}
            className={`spider-web-node spider-node-${i}`}
            cx={center.x + Math.cos((index * Math.PI) / 6) * 106}
            cy={center.y + Math.sin((index * Math.PI) / 6) * 106}
            r="4"
          />
        ))}
        <g className="spider-swing">
          <path className="spider-silk" d="M180,0 V102" />
          <g className="spider-character">
            <path d="M170 123 L151 112 L147 94 M170 133 L146 132 L132 115 M171 143 L150 153 L138 170 M173 151 L162 170 L163 184 M190 123 L209 112 L213 94 M190 133 L214 132 L228 115 M189 143 L210 153 L222 170 M187 151 L198 170 L197 184" />
            <ellipse cx="180" cy="139" rx="14" ry="22" />
            <circle cx="180" cy="114" r="12" />
            <path
              className="spider-eyes"
              d="M172 110 L178 114 L176 119 L172 116 Z M188 110 L182 114 L184 119 L188 116 Z"
            />
            <path
              className="spider-emblem"
              d="M180 130 V148 M175 135 L185 143 M185 135 L175 143"
            />
          </g>
        </g>
        {!background && (
          <text
            x="180"
            y="273"
            textAnchor="middle"
            className="spider-scene-caption"
          >
            EVERY THREAD LEADS TO A DISCOVERY
          </text>
        )}
      </svg>
    </div>
  );
}
