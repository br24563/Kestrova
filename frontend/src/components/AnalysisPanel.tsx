/**
 * Analysis Panel Component.
 *
 * Displays the optical analysis results in a clear, readable format.
 * Shows effective focal length, magnification, image/object distances,
 * F-number, numerical aperture, and RMS spot radius.
 */

import type { AnalysisResult, OpticalSystem } from "../types";
import { toMM } from "../types";

interface AnalysisPanelProps {
  analysis: AnalysisResult | null;
  system: OpticalSystem;
}

export function AnalysisPanel({ analysis, system }: AnalysisPanelProps) {
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
          <div className="text-xs text-gray-500 uppercase">Effective Focal Length</div>
          <div className="text-xl font-bold text-optical-700">{toMM(analysis.effective_focal_length).toFixed(2)} mm</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase">Magnification</div>
          <div className="text-xl font-bold text-optical-700">
            {analysis.magnification.toFixed(3)}
            {analysis.is_image_inverted && " (inverted)"}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Object Distance</div>
            <div className="font-medium">{toMM(analysis.object_distance).toFixed(2)} mm</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Image Distance</div>
            <div className="font-medium">{toMM(analysis.image_distance).toFixed(2)} mm</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">F-number</div>
            <div className="font-medium">f/{analysis.f_number.toFixed(2)}</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Numerical Aperture</div>
            <div className="font-medium">{analysis.numerical_aperture.toFixed(4)}</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Aperture Diameter</div>
            <div className="font-medium">{toMM(analysis.aperture_diameter).toFixed(2)} mm</div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Working Distance</div>
            <div className="font-medium">{toMM(analysis.working_distance).toFixed(2)} mm</div>
          </div>
        </div>
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase">RMS Spot Radius</div>
          <div className="text-lg font-bold text-optical-700">{toMM(analysis.rms_spot_radius).toFixed(4)} mm</div>
        </div>
        <div className="flex gap-4 text-sm">
          <span className={`px-2 py-1 rounded ${analysis.is_image_real ? "bg-green-100 text-green-800" : "bg-yellow-100 text-yellow-800"}`}>
            {analysis.is_image_real ? "Real Image" : "Virtual Image"}
          </span>
          <span className={`px-2 py-1 rounded ${analysis.is_image_inverted ? "bg-blue-100 text-blue-800" : "bg-purple-100 text-purple-800"}`}>
            {analysis.is_image_inverted ? "Inverted" : "Upright"}
          </span>
        </div>
      </div>
    </div>
  );
}
