/**
 * Optimization Panel Component.
 *
 * Allows the user to optimize a single component parameter to minimize
 * a chosen objective (RMS spot, magnification, or EFL) using the
 * backend's SciPy-based optimizer.
 */

import { useState } from "react";
import type {
  OpticalSystem,
  OptimizeObjective,
  OptimizeResult,
  ThinLens,
  ThickLens,
  SphericalSurface,
  LengthUnit,
} from "../types";
import { fromMeters } from "../types";
import { optimizeSystem } from "../api";

interface OptimizationPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
  onApplyOptimized: (system: OpticalSystem) => void;
}

type EditableComponent = ThinLens | ThickLens | SphericalSurface;

// Fields available per component type.
const FIELDS_BY_TYPE: Record<string, string[]> = {
  thin_lens: ["position", "focal_length"],
  thick_lens: ["position", "radius1", "radius2", "thickness"],
  spherical_surface: ["position", "radius", "thickness"],
};

export function OptimizationPanel({ system, displayUnit, onApplyOptimized }: OptimizationPanelProps) {
  const [componentId, setComponentId] = useState<string>(system.components[0]?.id ?? "");
  const [field, setField] = useState<string>("position");
  const [objective, setObjective] = useState<OptimizeObjective>("rms_spot");
  const [target, setTarget] = useState<string>("");
  const [minVal, setMinVal] = useState<string>("");
  const [maxVal, setMaxVal] = useState<string>("");
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const comps = system.components.filter(
    (c): c is EditableComponent =>
      c.type === "thin_lens" || c.type === "thick_lens" || c.type === "spherical_surface",
  );

  const selectedComp = comps.find((c) => c.id === componentId);
  const fields = selectedComp ? FIELDS_BY_TYPE[selectedComp.type] ?? ["position"] : ["position"];

  const handleComponentChange = (id: string) => {
    setComponentId(id);
    const comp = comps.find((c) => c.id === id);
    if (comp) {
      const f = FIELDS_BY_TYPE[comp.type]?.[0] ?? "position";
      setField(f);
    }
  };

  const handleRun = async () => {
    // Default bounds if not provided
    let lo = parseFloat(minVal);
    let hi = parseFloat(maxVal);
    const current = selectedComp ? Number(selectedComp[field as keyof EditableComponent]) : 0.01;
    if (isNaN(lo)) lo = current * 0.01;
    if (isNaN(hi)) hi = current * 2;

    setBusy(true);
    setError(null);
    setResult(null);

    try {
      const res = await optimizeSystem({
        system,
        objective,
        target: objective !== "rms_spot" && target !== "" ? parseFloat(target) : undefined,
        params: [{ component_id: componentId, field }],
        bounds: [[lo, hi]],
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Optimization failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <h3 className="text-sm font-medium text-gray-700 mb-2">Optimizer</h3>

      {comps.length === 0 ? (
        <p className="text-xs text-gray-500">Add a lens to optimize.</p>
      ) : (
        <>
          {/* Component + Field */}
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Component</label>
              <select
                value={componentId}
                onChange={(e) => handleComponentChange(e.target.value)}
                className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
              >
                {comps.map((c) => (
                  <option key={c.id} value={c.id}>{c.id}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Field</label>
              <select
                value={field}
                onChange={(e) => setField(e.target.value)}
                className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
              >
                {fields.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Objective */}
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Objective</label>
              <select
                value={objective}
                onChange={(e) => setObjective(e.target.value as OptimizeObjective)}
                className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
              >
                <option value="rms_spot">Minimize RMS spot</option>
                <option value="magnification">Target magnification</option>
                <option value="efl">Target EFL</option>
              </select>
            </div>
            {objective !== "rms_spot" && (
              <div>
                <label className="block text-xs text-gray-600 mb-1">Target</label>
                <input
                  type="number" step="any"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder={objective === "efl" ? `${displayUnit}` : "mag"}
                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                />
              </div>
            )}
          </div>

          {/* Bounds */}
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Min ({displayUnit})</label>
              <input
                type="number" step="any"
                value={minVal}
                onChange={(e) => setMinVal(e.target.value)}
                placeholder="auto"
                className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Max ({displayUnit})</label>
              <input
                type="number" step="any"
                value={maxVal}
                onChange={(e) => setMaxVal(e.target.value)}
                placeholder="auto"
                className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
              />
            </div>
          </div>

          <button
            onClick={handleRun}
            disabled={busy}
            className="w-full px-3 py-1.5 bg-optical-600 text-white text-xs rounded hover:bg-optical-700 disabled:opacity-50"
          >
            {busy ? "Optimizing..." : "Run Optimization"}
          </button>

          {error && <p className="text-xs text-red-500 mt-2">{error}</p>}

          {result && (
            <div className="mt-3 p-2 bg-gray-50 rounded border text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-gray-600">Optimal value</span>
                <span className="font-medium">{fromMeters(result.params[0] ?? 0, displayUnit).toFixed(3)} {displayUnit}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Objective</span>
                <span className="font-medium">{result.objective.toExponential(3)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Converged</span>
                <span className={result.success ? "text-green-600" : "text-yellow-600"}>{result.success ? "Yes" : "No"}</span>
              </div>
              <button
                onClick={() => onApplyOptimized(result.system)}
                className="w-full mt-1 px-2 py-1 bg-optical-100 text-optical-700 text-xs rounded hover:bg-optical-200"
              >
                Apply Optimized System
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}