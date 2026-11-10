/**
 * Layout of the prescription with real rays: a 2D meridional section (the
 * true surface shapes, the meridional ray fan per field) or a 3D view of
 * the elements and the marginal ray ring, turned by dragging.
 */
import { useMemo, useRef, useState } from "react";
import type { LengthUnit, LensData } from "../../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../../types";
import { lensLayout } from "../../api";
import type { LensLayout } from "../../api";
import { useAnalysis } from "./useAnalysis";

const FIELD_COLORS = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c"];
const W = 760;
const H = 360;
const PAD = 24;

type P3 = [number, number, number];

/** Screen point of a 3D point: turned by yaw about y, then pitch. */
export function project(p: P3, yaw: number, pitch: number): [number, number] {
  const [x, y, z] = p;
  const z1 = z * Math.cos(yaw) - x * Math.sin(yaw);
  const x1 = z * Math.sin(yaw) + x * Math.cos(yaw);
  const y2 = y * Math.cos(pitch) - x1 * Math.sin(pitch);
  return [z1, y2];
}

/** Scale and offset mapping (u, v) bounds into the drawing (equal axes). */
function fit(us: number[], vs: number[]) {
  const u0 = Math.min(...us);
  const u1 = Math.max(...us);
  const v0 = Math.min(...vs);
  const v1 = Math.max(...vs);
  const s = Math.min(
    (W - 2 * PAD) / Math.max(u1 - u0, 1e-12),
    (H - 2 * PAD) / Math.max(v1 - v0, 1e-12),
  );
  const ox = W / 2 - ((u0 + u1) / 2) * s;
  const oy = H / 2 + ((v0 + v1) / 2) * s;
  return (u: number, v: number) =>
    `${(ox + u * s).toFixed(1)},${(oy - v * s).toFixed(1)}`;
}

/** 3D wireframe of an element outline: meridians and rings. */
function wireframe(outline: [number, number][]): P3[][] {
  const lines: P3[][] = [];
  for (let k = 0; k < 8; k++) {
    const a = (k * Math.PI) / 4;
    lines.push(
      outline.map(([z, r]) => [r * Math.sin(a), r * Math.cos(a), z] as P3),
    );
  }
  const ringAt = (z: number, r: number) =>
    Array.from({ length: 49 }, (_, k) => {
      const a = (k * 2 * Math.PI) / 48;
      return [r * Math.sin(a), r * Math.cos(a), z] as P3;
    });
  outline.forEach(([z, r], i) => {
    const prev = outline[i - 1];
    const next = outline[i + 1];
    // rings where the outline turns a corner (rims and edges)
    const corner =
      r > 0 &&
      prev &&
      next &&
      Math.abs(
        Math.atan2(r - prev[1], z - prev[0]) -
          Math.atan2(next[1] - r, next[0] - z),
      ) > 0.3;
    if (corner) lines.push(ringAt(z, r));
  });
  return lines;
}

export function LensLayoutPanel({
  lens,
  displayUnit,
}: {
  lens: LensData | null;
  displayUnit: LengthUnit;
}) {
  const [mode, setMode] = useState<"2d" | "3d">("2d");
  const [rays, setRays] = useState(7);
  const [yaw, setYaw] = useState(0.6);
  const [pitch, setPitch] = useState(0.35);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const { data, error, loading } = useAnalysis<LensLayout>(
    () =>
      lens
        ? lensLayout(lens, { pupil: mode === "3d" ? "ring" : "fan", rays })
        : Promise.reject(new Error("No lens")),
    [lens, mode, rays],
  );

  const drawing = useMemo(() => {
    if (!data) return null;
    if (mode === "2d") {
      const us: number[] = [data.image.z];
      const vs: number[] = [data.image.half_height, -data.image.half_height];
      data.elements.forEach((e) =>
        e.outline.forEach(([z, r]) => {
          us.push(z);
          vs.push(r, -r);
        }),
      );
      data.rays.forEach((r) =>
        r.points.forEach((p) => {
          us.push(p[2]);
          vs.push(p[1]);
        }),
      );
      const xy = fit(us, vs);
      return (
        <>
          {data.elements.map((e) => {
            const pts = [
              ...e.outline.map(([z, r]) => xy(z, r)),
              ...[...e.outline].reverse().map(([z, r]) => xy(z, -r)),
            ];
            return (
              <polygon
                key={e.name}
                points={pts.join(" ")}
                fill="#dbeafe"
                fillOpacity={0.6}
                stroke="#1e3a8a"
                strokeWidth={1}
              >
                <title>{e.name}</title>
              </polygon>
            );
          })}
          {data.rays.map((r, k) => (
            <polyline
              key={k}
              points={r.points.map((p) => xy(p[2], p[1])).join(" ")}
              fill="none"
              stroke={FIELD_COLORS[r.field % FIELD_COLORS.length]}
              strokeWidth={0.8}
            />
          ))}
          {[1, -1].map((s) => (
            <polyline
              key={s}
              points={[
                xy(data.stop.z, s * data.stop.semi_diameter),
                xy(data.stop.z, s * data.stop.semi_diameter * 1.25),
              ].join(" ")}
              stroke="#111"
              strokeWidth={2}
            />
          ))}
          <polyline
            points={[
              xy(data.image.z, -data.image.half_height),
              xy(data.image.z, data.image.half_height),
            ].join(" ")}
            stroke="#111"
            strokeWidth={1.5}
          />
        </>
      );
    }
    const wires = data.elements.flatMap((e) => wireframe(e.outline));
    const paths = data.rays.map((r) => r.points as P3[]);
    const flat = [...wires.flat(), ...paths.flat()].map((p) =>
      project(p, yaw, pitch),
    );
    const xy = fit(
      flat.map((p) => p[0]),
      flat.map((p) => p[1]),
    );
    const line = (pts: P3[]) =>
      pts
        .map((p) => {
          const [u, v] = project(p, yaw, pitch);
          return xy(u, v);
        })
        .join(" ");
    return (
      <>
        {wires.map((w, k) => (
          <polyline
            key={`w${k}`}
            points={line(w)}
            fill="none"
            stroke="#1e3a8a"
            strokeOpacity={0.45}
            strokeWidth={0.7}
          />
        ))}
        {data.rays.map((r, k) => (
          <polyline
            key={`r${k}`}
            points={line(r.points as P3[])}
            fill="none"
            stroke={FIELD_COLORS[r.field % FIELD_COLORS.length]}
            strokeWidth={0.7}
          />
        ))}
      </>
    );
  }, [data, mode, yaw, pitch]);

  if (!lens)
    return (
      <p className="p-4 text-xs text-gray-500">
        The layout works on the lens data (open or convert a lens in the Lens
        Data Editor).
      </p>
    );

  const unit = LENGTH_UNIT_LABELS[displayUnit];
  const length = data
    ? fromMeters(
        Math.max(...data.rays.flatMap((r) => r.points.map((p) => p[2]))) -
          Math.min(...data.elements.flatMap((e) => e.outline.map((p) => p[0]))),
        displayUnit,
      )
    : null;

  return (
    <div className="p-4 space-y-2 text-xs" data-testid="lens-layout">
      <div className="flex flex-wrap items-center gap-3 text-gray-600">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Lens layout
        </h3>
        <div className="flex border border-gray-200 rounded overflow-hidden">
          {(["2d", "3d"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              className={`px-2 py-0.5 ${
                mode === m ? "bg-optical-600 text-white" : "hover:bg-gray-50"
              }`}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1">
          Rays
          <select
            aria-label="Rays per field"
            value={rays}
            onChange={(e) => setRays(parseInt(e.target.value, 10))}
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            {[3, 5, 7, 11, 15].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && error !== "No lens" && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {loading && !data && <p className="text-gray-400">Tracing...</p>}
      {data && (
        <svg
          data-testid="layout-svg"
          viewBox={`0 0 ${W} ${H}`}
          className={`w-full border border-gray-200 rounded bg-white ${
            mode === "3d" ? "cursor-grab" : ""
          }`}
          onPointerDown={(e) => {
            if (mode !== "3d") return;
            drag.current = { x: e.clientX, y: e.clientY };
            (e.target as Element).setPointerCapture?.(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            setYaw((v) => v + (e.clientX - drag.current!.x) * 0.01);
            setPitch((v) =>
              Math.max(
                -1.5,
                Math.min(1.5, v + (e.clientY - drag.current!.y) * 0.01),
              ),
            );
            drag.current = { x: e.clientX, y: e.clientY };
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
        >
          {drawing}
        </svg>
      )}
      {data && (
        <p className="text-gray-400">
          {data.elements.length} elements, {data.rays.length} rays over{" "}
          {data.fields} fields (colour per field)
          {length !== null && `, ${length.toFixed(2)} ${unit} long`}.{" "}
          {mode === "3d"
            ? "Drag to turn the view."
            : "True surface shapes; the bars mark the stop."}
          {data.warnings.length > 0 &&
            ` Not drawn: ${data.warnings.join("; ")}`}
        </p>
      )}
    </div>
  );
}
