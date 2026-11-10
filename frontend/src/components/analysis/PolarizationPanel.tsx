/**
 * Polarization ray trace of one field: pupil maps of the polarization-
 * averaged transmittance, the diattenuation and the retardance, and the
 * pupil-averaged transmittance at each wavelength (Fresnel losses at bare
 * surfaces, thin-film coatings where a surface has one).
 */
import { useEffect, useRef, useState } from "react";
import type { OpticalSystem } from "../../types";
import { analyzePolarization } from "../../api";
import { useAnalysis } from "./useAnalysis";
import { fieldCount } from "./MtfPlot";

/** RGB of a value 0..1 on a perceptual blue-green-yellow ramp. */
export function rampColor(t: number): [number, number, number] {
  const stops: [number, number, number][] = [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37],
  ];
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  const f = x - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [0, 1, 2].map((k) => Math.round(a[k] + f * (b[k] - a[k]))) as [
    number,
    number,
    number,
  ];
}

/** Range of the non-null values of a map. */
export function mapRange(map: (number | null)[][]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const row of map)
    for (const v of row)
      if (v !== null) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
  return Number.isFinite(lo) ? [lo, hi] : [0, 0];
}

function PupilMap({
  title,
  map,
  format,
  testId,
}: {
  title: string;
  map: (number | null)[][];
  format: (v: number) => string;
  testId: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [lo, hi] = mapRange(map);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return; // no canvas support (tests)
    const n = map.length;
    const img = ctx.createImageData(n, n);
    for (let row = 0; row < n; row++) {
      for (let col = 0; col < n; col++) {
        // pupil y up: the first row of the array is the most negative y
        const v = map[n - 1 - row][col];
        const k = 4 * (row * n + col);
        if (v === null) {
          img.data[k + 3] = 0;
          continue;
        }
        const [r, g, b] = rampColor(hi > lo ? (v - lo) / (hi - lo) : 0.5);
        img.data[k] = r;
        img.data[k + 1] = g;
        img.data[k + 2] = b;
        img.data[k + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [map, lo, hi]);
  return (
    <figure className="text-center" data-testid={testId}>
      <figcaption className="text-gray-700 font-medium mb-1">
        {title}
      </figcaption>
      <canvas
        ref={ref}
        width={map.length}
        height={map.length}
        className="w-40 h-40 border border-gray-200 [image-rendering:pixelated]"
      />
      <p className="text-gray-500 mt-1 font-mono">
        {format(lo)} … {format(hi)}
      </p>
    </figure>
  );
}

export function PolarizationPanel({ system }: { system: OpticalSystem }) {
  const [field, setField] = useState(0);
  const nFields = fieldCount(system);
  const f = Math.min(field, nFields - 1);
  const { data, error, loading } = useAnalysis(
    () => analyzePolarization(system, f),
    [system, f],
  );

  return (
    <div className="p-4 space-y-3 text-xs">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Polarization: Fresnel losses and coatings
        </h3>
        <label className="flex items-center gap-1 text-gray-600">
          Field
          <select
            aria-label="Polarization field"
            value={f}
            onChange={(e) => setField(parseInt(e.target.value, 10))}
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            {Array.from({ length: nFields }, (_, k) => (
              <option key={k} value={k}>
                {k + 1}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {loading && !data && <p className="text-gray-400">Computing...</p>}
      {data && (
        <>
          <div className="flex flex-wrap gap-6">
            <PupilMap
              title="Transmittance"
              map={data.transmittance}
              format={(v) => `${(100 * v).toFixed(2)} %`}
              testId="pol-transmittance"
            />
            <PupilMap
              title="Diattenuation"
              map={data.diattenuation}
              format={(v) => v.toFixed(4)}
              testId="pol-diattenuation"
            />
            <PupilMap
              title="Retardance"
              map={data.retardance}
              format={(v) => `${((v * 180) / Math.PI).toFixed(3)}°`}
              testId="pol-retardance"
            />
          </div>
          <table data-testid="pol-summary">
            <tbody>
              {data.summary.wavelengths.map((wl, k) => (
                <tr key={k}>
                  <td className="pr-3 text-gray-600">
                    {(wl * 1e9).toFixed(1)} nm
                  </td>
                  <td className="font-mono">
                    {(100 * data.summary.per_wavelength[k]).toFixed(2)} %
                  </td>
                </tr>
              ))}
              <tr>
                <td className="pr-3 text-gray-700 font-medium">
                  Transmittance (weighted)
                </td>
                <td className="font-mono font-medium">
                  {(100 * data.summary.transmittance).toFixed(2)} %
                </td>
              </tr>
            </tbody>
          </table>
          <p className="text-gray-400">
            Pupil maps at {(data.wavelength * 1e9).toFixed(1)} nm, unpolarized
            light; transmittance averaged over the pupil (blocked rays count as
            zero). Mirrors are ideal reflectors.
          </p>
        </>
      )}
    </div>
  );
}
