/**
 * Double-reflection ghosts of the prescription, traced exactly with each
 * surface's coating (or Fresnel) reflectance; brightest first.
 */
import { useState } from "react";
import type { OpticalSystem } from "../../types";
import { ghostTrace } from "../../api";
import { useAnalysis } from "./useAnalysis";
import { fieldCount } from "./MtfPlot";

export function GhostTracePanel({ system }: { system: OpticalSystem }) {
  const [field, setField] = useState(0);
  const nFields = fieldCount(system);
  const f = Math.min(field, nFields - 1);
  const { data, error, loading } = useAnalysis(
    () => ghostTrace(system, f),
    [system, f],
  );
  return (
    <div className="p-4 space-y-2 text-xs" data-testid="ghost-trace">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Ghosts of the prescription (double reflections)
        </h3>
        <label className="flex items-center gap-1 text-gray-600">
          Field
          <select
            aria-label="Ghost field"
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
        <p className="text-amber-700" role="alert">
          {error}
        </p>
      )}
      {loading && !data && <p className="text-gray-400">Tracing...</p>}
      {data && (
        <table
          className="border border-gray-200 rounded"
          data-testid="ghost-table"
        >
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-2 py-0.5 text-left font-medium">Reflects at</th>
              <th className="px-2 py-0.5 text-right font-medium">Power</th>
              <th className="px-2 py-0.5 text-right font-medium">
                Spot RMS (µm)
              </th>
              <th className="px-2 py-0.5 text-right font-medium">
                Focus from image (mm)
              </th>
              <th className="px-2 py-0.5 text-right font-medium">
                Rel. irradiance
              </th>
            </tr>
          </thead>
          <tbody>
            {data.ghosts.map((g) => (
              <tr
                key={g.surfaces.join("-")}
                className="border-t border-gray-100"
              >
                <td className="px-2">
                  S{g.surfaces[0]} then S{g.surfaces[1]}
                </td>
                <td className="px-2 text-right font-mono">
                  {g.power.toExponential(2)}
                </td>
                <td className="px-2 text-right font-mono">
                  {g.rms_radius === null
                    ? "—"
                    : (g.rms_radius * 1e6).toFixed(1)}
                </td>
                <td className="px-2 text-right font-mono">
                  {g.focus_shift === null
                    ? "—"
                    : (g.focus_shift * 1e3).toFixed(3)}
                </td>
                <td className="px-2 text-right font-mono">
                  {g.relative_irradiance.toExponential(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-gray-400">
        Power: the fraction of the beam in the ghost (the two reflectances,
        Fresnel or the surface&apos;s coating). Relative irradiance compares the
        ghost spot with the image spot.
      </p>
    </div>
  );
}
