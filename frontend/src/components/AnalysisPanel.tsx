/**
 * Analysis Panel Component.
 *
 * Displays the optical analysis results in a clear, readable format.
 * Shows effective focal length, magnification, image/object distances,
 * F-number, numerical aperture, RMS spot radius, and chromatic aberration.
 */

import { useEffect, useState } from "react";
import type { AnalysisResult, OpticalSystem, LengthUnit, ChromaticAberrationResult } from "../types";
import { fmtLen, fmtNum, fromMeters, LENGTH_UNIT_LABELS } from "../types";
import { analyzeAberration } from "../api";
import { HelpTooltip, opticalParameterHelp as help } from "./HelpTooltip";

interface AnalysisPanelProps {
  analysis: AnalysisResult | null;
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

export function AnalysisPanel({ analysis, system, displayUnit }: AnalysisPanelProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const [aberration, setAberration] = useState<ChromaticAberrationResult | null>(null);
  const [aberrationError, setAberrationError] = useState<string | null>(null);

  // Fetch chromatic aberration when the system changes
  useEffect(() => {
    let cancelled = false;
    setAberration(null);
    setAberrationError(null);

    analyzeAberration(system)
      .then((result) => {
        if (!cancelled) setAberration(result);
      })
      .catch((err) => {
        if (!cancelled) setAberrationError(err instanceof Error ? err.message : "Failed to analyze aberration");
      });

    return () => {
      cancelled = true;
    };
  }, [system]);
  if (!analysis) {
    return (
      <div className="p-4">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Analysis Panel</h2>
        <p className="text-gray-500">No analysis available.</p>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Analysis Panel</h2>
      <div className="space-y-3">
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase">Effective Focal Length<HelpTooltip content={help.effective_focal_length} /></div>
          <div className="text-xl font-bold text-optical-700">{fmtLen(analysis.effective_focal_length, displayUnit, 2)} {unitLabel}</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase">Magnification<HelpTooltip content={help.magnification} /></div>
          <div className="text-xl font-bold text-optical-700">
            {fmtNum(analysis.magnification, 3)}
            {analysis.is_image_inverted && " (inverted)"}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Object Distance<HelpTooltip content={help.object_distance} /></div>
            <div className="font-medium">{fmtLen(analysis.object_distance, displayUnit, 2)} {unitLabel}</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Image Distance<HelpTooltip content={help.image_distance} position="bottom-end" /></div>
            <div className="font-medium">{fmtLen(analysis.image_distance, displayUnit, 2)} {unitLabel}</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">F-number<HelpTooltip content={help.f_number} /></div>
            <div className="font-medium">f/{fmtNum(analysis.f_number, 2)}</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Numerical Aperture<HelpTooltip content={help.numerical_aperture} position="bottom-end" /></div>
            <div className="font-medium">{analysis.numerical_aperture.toFixed(4)}</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Aperture Diameter<HelpTooltip content={help.aperture_diameter} /></div>
            <div className="font-medium">{fromMeters(analysis.aperture_diameter, displayUnit).toFixed(2)} {unitLabel}</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Working Distance<HelpTooltip content={help.working_distance} position="bottom-end" /></div>
            <div className="font-medium">{fmtLen(analysis.working_distance, displayUnit, 2)} {unitLabel}</div>
          </div>
        </div>
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase">RMS Spot Radius<HelpTooltip content={help.rms_spot} /></div>
          <div className="text-lg font-bold text-optical-700">{fromMeters(analysis.rms_spot_radius, displayUnit).toFixed(4)} {unitLabel}</div>
        </div>
        <div className="flex gap-4 text-sm">
          <span className={`px-2 py-1 rounded ${analysis.is_image_real ? "bg-green-100 text-green-800" : "bg-yellow-100 text-yellow-800"}`}>
            {analysis.is_image_real ? "Real Image" : "Virtual Image"}
          </span>
          <span className={`px-2 py-1 rounded ${analysis.is_image_inverted ? "bg-blue-100 text-blue-800" : "bg-purple-100 text-purple-800"}`}>
            {analysis.is_image_inverted ? "Inverted" : "Upright"}
          </span>
        </div>

        {/* Chromatic Aberration */}
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase mb-2">Chromatic Aberration<HelpTooltip content={help.chromatic} /></div>
          {aberrationError ? (
            <p className="text-xs text-red-500">{aberrationError}</p>
          ) : aberration ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Longitudinal (LCA)</span>
                <span className="font-medium">{fromMeters(aberration.lca, displayUnit).toFixed(3)} {unitLabel}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Lateral (TCA)</span>
                <span className="font-medium">{fromMeters(aberration.tca, displayUnit).toFixed(3)} {unitLabel}</span>
              </div>
              <div className="text-[10px] text-gray-400">
                Computed across {aberration.wavelengths.length} wavelengths
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-400">Analyzing...</p>
          )}
        </div>
      </div>
    </div>
  );
}
