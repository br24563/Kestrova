/**
 * Wavelength-weighted diffraction PSF of a field point (image, linear or
 * logarithmic), with encircled and ensquared energy against the
 * diffraction-limited encircled energy, the 80 % energy radius and the
 * Strehl ratio at each wavelength.
 */

import { useEffect, useRef, useState } from "react";
import type { OpticalSystem, LengthUnit } from "../../types";
import { analyzePsf } from "../../api";
import { LinePlot } from "./LinePlot";
import { ExportButton } from "../ExportButton";
import { useAnalysis } from "./useAnalysis";
import { fieldCount } from "./MtfPlot";

interface PsfPlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

/** Grey level 0..255 of a PSF value (peak 1), linear or over 4 decades. */
export function psfShade(value: number, log: boolean): number {
  const v = Math.max(0, Math.min(1, value));
  if (!log) return Math.round(255 * v);
  if (v <= 1e-4) return 0;
  return Math.round((255 * (Math.log10(v) + 4)) / 4);
}

function PsfImage({ psf, log }: { psf: number[][]; log: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return; // no canvas support (tests)
    const n = psf.length;
    const img = ctx.createImageData(n, n);
    for (let row = 0; row < n; row++) {
      for (let col = 0; col < n; col++) {
        // image y up: the first row of the array is the most negative y
        const g = psfShade(psf[n - 1 - row][col], log);
        const k = 4 * (row * n + col);
        img.data[k] = g;
        img.data[k + 1] = g;
        img.data[k + 2] = g;
        img.data[k + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [psf, log]);
  return (
    <canvas
      ref={ref}
      width={psf.length}
      height={psf.length}
      data-testid="psf-image"
      className="w-64 h-64 border border-gray-200 [image-rendering:pixelated]"
    />
  );
}

export function PsfPlot({ system }: PsfPlotProps) {
  const [field, setField] = useState(0);
  const [log, setLog] = useState(true);
  const nFields = fieldCount(system);
  const f = Math.min(field, nFields - 1);
  const { data, error, loading } = useAnalysis(
    () => analyzePsf(system, f),
    [system, f],
  );
  const um = (mm: number) => mm * 1e3;
  const half = data ? um(data.axis_mm[data.axis_mm.length - 1]) : 0;

  return (
    <div className="p-4 space-y-3 text-xs">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          PSF and encircled energy (wavelength-weighted)
        </h3>
        <label className="flex items-center gap-1 text-gray-600">
          Field
          <select
            aria-label="PSF field"
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
        <label className="flex items-center gap-1 text-gray-600">
          <input
            type="checkbox"
            aria-label="Logarithmic PSF"
            checked={log}
            onChange={(e) => setLog(e.target.checked)}
          />
          Log scale
        </label>
      </div>
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {loading && !data && <p className="text-gray-400">Computing...</p>}
      {data?.exceeds_window && (
        <p className="text-amber-700" data-testid="psf-window-warning">
          This image is aberration-limited: its blur is wider than the
          diffraction calculation's window (±
          {((data.window_mm ?? 0) * 1e3).toFixed(0)} µm), so the PSF and energy
          shown are incomplete. The spot diagram describes it better.
        </p>
      )}
      {data && (
        <div className="flex flex-wrap gap-6">
          <div>
            <PsfImage psf={data.psf} log={log} />
            <p className="text-gray-500 mt-1">
              ±{half.toFixed(1)} µm about the chief ray
              {log ? ", 4 decades" : ""}
            </p>
          </div>
          <table className="self-start" data-testid="psf-stats">
            <tbody>
              <tr>
                <td className="pr-3 text-gray-600">Airy radius</td>
                <td className="font-mono">
                  {um(data.airy_radius_mm).toFixed(2)} µm
                </td>
              </tr>
              <tr>
                <td className="pr-3 text-gray-600">80 % energy radius</td>
                <td className="font-mono">
                  {data.radius_80_mm === null
                    ? "beyond the view"
                    : `${um(data.radius_80_mm).toFixed(2)} µm`}
                </td>
              </tr>
              {data.strehl.map((s) => (
                <tr key={s.wavelength}>
                  <td className="pr-3 text-gray-600">
                    Strehl at {(s.wavelength * 1e9).toFixed(1)} nm
                  </td>
                  <td className="font-mono">{s.strehl.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && (
        <div>
          <div className="flex justify-end">
            <ExportButton svgId="psf-energy" filename="encircled-energy" />
          </div>
          <LinePlot
            id="psf-energy"
            series={[
              {
                label: "Encircled",
                color: "#2563eb",
                x: data.radius_mm.map(um),
                y: data.encircled,
              },
              {
                label: "Ensquared (half-width)",
                color: "#16a34a",
                x: data.radius_mm.map(um),
                y: data.ensquared,
              },
              {
                label: "Diffraction limit",
                color: "#9ca3af",
                x: data.radius_mm.map(um),
                y: data.diffraction_limited_encircled,
                dashed: true,
              },
            ]}
            xLabel="Radius (µm)"
            yLabel="Energy fraction"
            yDomain={[0, 1]}
          />
        </div>
      )}
    </div>
  );
}
