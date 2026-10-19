/**
 * Ghost Analysis Panel Component.
 *
 * Real-ray double-reflection ghosts on axis: each path reflects off one
 * surface back toward the object and off an earlier surface forward to
 * the image. Intensity is relative to the primary image (Fresnel
 * reflectance of uncoated surfaces unless a coating reflectance is given).
 */

import { useState } from "react";
import type { OpticalSystem, LengthUnit } from "../../types";
import { fmtLen, LENGTH_UNIT_LABELS } from "../../types";
import { analyzeGhosts } from "../../api";
import { useAnalysis } from "./useAnalysis";

interface GhostAnalysisPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

const THRESHOLDS = [1e-4, 1e-5, 1e-6];

function formatIntensity(intensity: number): string {
  return intensity >= 1e-3
    ? `${(intensity * 100).toFixed(3)}%`
    : intensity.toExponential(2);
}

export function GhostAnalysisPanel({
  system,
  displayUnit,
}: GhostAnalysisPanelProps) {
  const [threshold, setThreshold] = useState(1e-6);
  const { data, error, loading } = useAnalysis(
    () => analyzeGhosts(system, 2, threshold),
    [system, threshold],
  );
  const ghosts = data?.ghosts ?? [];
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-semibold text-gray-700">
          Ghost Reflections (double, on axis)
        </h3>
        <label className="text-xs text-gray-600 flex items-center gap-1">
          Min. intensity
          <select
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="text-xs border border-gray-200 rounded px-2 py-1"
          >
            {THRESHOLDS.map((t) => (
              <option key={t} value={t}>
                {t.toExponential(0)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && !data && (
        <p className="text-xs text-gray-500">Tracing ghost paths...</p>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}

      {data && !error && ghosts.length === 0 && (
        <p className="text-xs text-gray-500">
          No ghost paths above {threshold.toExponential(0)} reach the image.
        </p>
      )}

      {data && !error && ghosts.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-gray-600">
            {ghosts.length} ghost path(s), brightest first. Focus offset is from
            the image plane.
          </div>
          <table className="w-full text-xs border border-gray-200">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-2 py-1 text-left">Path</th>
                <th className="px-2 py-1 text-right">Rel. intensity</th>
                <th className="px-2 py-1 text-right">
                  Focus offset ({unitLabel})
                </th>
                <th className="px-2 py-1 text-center">In field</th>
              </tr>
            </thead>
            <tbody>
              {ghosts.map((ghost, i) => (
                <tr
                  key={i}
                  className={`border-t border-gray-100 ${ghost.is_in_field ? "bg-red-50" : ""}`}
                >
                  <td className="px-2 py-1 text-gray-700">
                    {ghost.description}
                  </td>
                  <td className="px-2 py-1 text-right font-mono">
                    {formatIntensity(ghost.relative_intensity)}
                  </td>
                  <td className="px-2 py-1 text-right font-mono">
                    {fmtLen(ghost.image_position_offset, displayUnit, 3)}
                  </td>
                  <td className="px-2 py-1 text-center">
                    {ghost.is_in_field ? "yes" : "no"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
