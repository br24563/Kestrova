/**
 * Minimal SVG line plot shared by the analysis plots.
 *
 * Draws one or more series with linear axes, tick labels and a zero line.
 * Null points (e.g. vignetted rays) break the line instead of being drawn.
 */

export interface PlotSeries {
  label: string;
  color: string;
  x: (number | null)[];
  y: (number | null)[];
  dashed?: boolean;
}

interface LinePlotProps {
  id: string;
  series: PlotSeries[];
  xLabel: string;
  yLabel: string;
  xDomain?: [number, number];
  yDomain?: [number, number];
  /** Center the y axis on zero (ray fans, OPD). */
  symmetricY?: boolean;
  /** Center the x axis on zero (focus shifts). */
  symmetricX?: boolean;
  width?: number;
  height?: number;
}

const PAD = { left: 52, right: 12, top: 10, bottom: 34 };

function finite(values: (number | null)[]): number[] {
  return values.filter((v): v is number => v !== null && Number.isFinite(v));
}

function domainOf(values: number[], symmetric: boolean): [number, number] {
  if (values.length === 0) return [-1, 1];
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (symmetric) {
    const m = Math.max(Math.abs(lo), Math.abs(hi));
    lo = -m;
    hi = m;
  }
  if (hi - lo < 1e-15 * Math.max(1, Math.abs(hi))) {
    // flat data: give it a visible band around the value
    const pad = Math.abs(hi) > 0 ? Math.abs(hi) * 0.1 : 1e-9;
    return [lo - pad, hi + pad];
  }
  const pad = symmetric ? (hi - lo) * 0.05 : 0;
  return [lo - pad, hi + pad];
}

export function formatTick(v: number): string {
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1e4 || a < 1e-3) return v.toExponential(1);
  return parseFloat(v.toPrecision(3)).toString();
}

export function LinePlot({
  id,
  series,
  xLabel,
  yLabel,
  xDomain,
  yDomain,
  symmetricY = false,
  symmetricX = false,
  width = 360,
  height = 220,
}: LinePlotProps) {
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const [x0, x1] =
    xDomain ??
    domainOf(
      series.flatMap((s) => finite(s.x)),
      symmetricX,
    );
  const [y0, y1] =
    yDomain ??
    domainOf(
      series.flatMap((s) => finite(s.y)),
      symmetricY,
    );

  const sx = (v: number) => PAD.left + ((v - x0) / (x1 - x0)) * plotW;
  const sy = (v: number) => PAD.top + plotH - ((v - y0) / (y1 - y0)) * plotH;

  const path = (s: PlotSeries) => {
    let d = "";
    let pen = false;
    s.x.forEach((xv, i) => {
      const yv = s.y[i];
      if (
        xv === null ||
        yv === null ||
        !Number.isFinite(xv) ||
        !Number.isFinite(yv)
      ) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${sx(xv).toFixed(1)},${sy(yv).toFixed(1)} `;
      pen = true;
    });
    return d;
  };

  const ticks = (lo: number, hi: number) =>
    [0, 0.25, 0.5, 0.75, 1].map((t) => lo + t * (hi - lo));

  return (
    <div>
      <svg
        id={id}
        width={width}
        height={height}
        className="mx-auto block"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect
          x={PAD.left}
          y={PAD.top}
          width={plotW}
          height={plotH}
          fill="#fafafa"
          stroke="#d1d5db"
        />
        {ticks(x0, x1).map((t, i) => (
          <g key={`x${i}`}>
            <line
              x1={sx(t)}
              y1={PAD.top}
              x2={sx(t)}
              y2={PAD.top + plotH}
              stroke="#e5e7eb"
              strokeWidth={0.5}
            />
            <text
              x={sx(t)}
              y={PAD.top + plotH + 12}
              fontSize={9}
              fill="#6b7280"
              textAnchor="middle"
            >
              {formatTick(t)}
            </text>
          </g>
        ))}
        {ticks(y0, y1).map((t, i) => (
          <g key={`y${i}`}>
            <line
              x1={PAD.left}
              y1={sy(t)}
              x2={PAD.left + plotW}
              y2={sy(t)}
              stroke="#e5e7eb"
              strokeWidth={0.5}
            />
            <text
              x={PAD.left - 4}
              y={sy(t) + 3}
              fontSize={9}
              fill="#6b7280"
              textAnchor="end"
            >
              {formatTick(t)}
            </text>
          </g>
        ))}
        {y0 < 0 && y1 > 0 && (
          <line
            x1={PAD.left}
            y1={sy(0)}
            x2={PAD.left + plotW}
            y2={sy(0)}
            stroke="#9ca3af"
            strokeWidth={1}
          />
        )}
        {x0 < 0 && x1 > 0 && (
          <line
            x1={sx(0)}
            y1={PAD.top}
            x2={sx(0)}
            y2={PAD.top + plotH}
            stroke="#9ca3af"
            strokeWidth={1}
          />
        )}
        {series.map((s) => (
          <path
            key={s.label}
            d={path(s)}
            fill="none"
            stroke={s.color}
            strokeWidth={1.5}
            strokeDasharray={s.dashed ? "4,3" : undefined}
          />
        ))}
        <text
          x={PAD.left + plotW / 2}
          y={height - 4}
          fontSize={10}
          fill="#374151"
          textAnchor="middle"
        >
          {xLabel}
        </text>
        <text
          x={12}
          y={PAD.top + plotH / 2}
          fontSize={10}
          fill="#374151"
          textAnchor="middle"
          transform={`rotate(-90, 12, ${PAD.top + plotH / 2})`}
        >
          {yLabel}
        </text>
      </svg>
      <div className="flex flex-wrap gap-3 mt-1 text-xs justify-center">
        {series.map((s) => (
          <span key={s.label} className="flex items-center gap-1">
            <span
              className="inline-block w-4"
              style={{
                borderTop: `2px ${s.dashed ? "dashed" : "solid"} ${s.color}`,
              }}
            />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
