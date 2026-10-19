/**
 * Seidel Aberration Panel Component.
 *
 * Displays third-order (Seidel) monochromatic aberration analysis results:
 * - Spherical aberration (longitudinal and transverse)
 * - Coma
 * - Astigmatism
 * - Field curvature
 * - Distortion
 */

import { useEffect, useState } from "react";
import type { OpticalSystem, SeidelResult, LengthUnit } from "../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../types";
import { analyzeSeidel } from "../api";

interface SeidelPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

export function SeidelPanel({ system, displayUnit }: SeidelPanelProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const [data, setData] = useState<SeidelResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setData(null);
    setError(null);

    analyzeSeidel(system)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [system]);

  if (loading) {
    return (
      <div className="p-4 border-t border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Seidel Aberrations
        </h2>
        <p className="text-gray-500 text-sm">Analyzing aberrations...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 border-t border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Seidel Aberrations
        </h2>
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 border-t border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Seidel Aberrations
        </h2>
        <p className="text-gray-500 text-sm">No aberration data available.</p>
      </div>
    );
  }

  const saLong = fromMeters(
    data.spherical_aberration.longitudinal,
    displayUnit,
  );
  const saTrans = fromMeters(data.spherical_aberration.transverse, displayUnit);
  const coma = fromMeters(data.coma, displayUnit);
  const astig = fromMeters(data.astigmatism, displayUnit);
  const fieldCurv = fromMeters(data.field_curvature, displayUnit);
  const distort = data.distortion * 100; // as percentage

  return (
    <div className="p-4 border-t border-gray-200">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Seidel Aberrations
      </h2>
      <div className="space-y-3">
        <div className="text-[10px] text-gray-400">
          Third-order values from the Seidel sums at full aperture and full
          field.
        </div>
        {/* Spherical Aberration */}
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase">
            Spherical Aberration
          </div>
          <div className="grid grid-cols-2 gap-2 mt-1">
            <div>
              <div className="text-xs text-gray-400">Longitudinal</div>
              <div className="font-medium text-sm">
                {saLong.toFixed(4)} {unitLabel}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Transverse</div>
              <div className="font-medium text-sm">
                {saTrans.toFixed(4)} {unitLabel}
              </div>
            </div>
          </div>
        </div>

        {/* Coma */}
        <div className="p-2 bg-gray-50 rounded border">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Coma</span>
            <span className="font-medium">
              {coma.toFixed(4)} {unitLabel}
            </span>
          </div>
        </div>

        {/* Astigmatism */}
        <div className="p-2 bg-gray-50 rounded border">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Astigmatism</span>
            <span className="font-medium">
              {astig.toFixed(4)} {unitLabel}
            </span>
          </div>
        </div>

        {/* Field Curvature */}
        <div className="p-2 bg-gray-50 rounded border">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Field Curvature</span>
            <span className="font-medium">
              {fieldCurv.toFixed(4)} {unitLabel}
            </span>
          </div>
        </div>

        {/* Distortion */}
        <div className="p-2 bg-gray-50 rounded border">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Distortion</span>
            <span className="font-medium">{distort.toFixed(3)}%</span>
          </div>
        </div>

        {/* Focus positions */}
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase mb-1">
            Focus Positions
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <div className="text-gray-400">Paraxial</div>
              <div className="font-medium">
                {fromMeters(data.paraxial_image_position, displayUnit).toFixed(
                  2,
                )}
              </div>
            </div>
            <div>
              <div className="text-gray-400">Tangential (from paraxial)</div>
              <div className="font-medium">
                {fromMeters(data.tangential_focus, displayUnit).toFixed(4)}
              </div>
            </div>
            <div>
              <div className="text-gray-400">Sagittal (from paraxial)</div>
              <div className="font-medium">
                {fromMeters(data.sagittal_focus, displayUnit).toFixed(4)}
              </div>
            </div>
          </div>
          <div className="text-[10px] text-gray-400 mt-1">
            (all in {unitLabel})
          </div>
        </div>
      </div>
    </div>
  );
}
