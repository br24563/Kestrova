/**
 * Tolerance Analysis Panel Component.
 *
 * Allows the user to run Monte-Carlo tolerance analysis on the optical
 * system and displays the results: mean, std, min, max, 95th percentile
 * of the RMS spot radius under manufacturing variations.
 */

import { useState } from "react";
import type { OpticalSystem, ToleranceResult, LengthUnit, ThinLens, ThickLens } from "../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../types";
import { runToleranceAnalysis } from "../api";

interface TolerancePanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

export function TolerancePanel({ system, displayUnit }: TolerancePanelProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const [trials, setTrials] = useState<string>("100");
  const [tolerance, setTolerance] = useState<string>("0.1");
  const [result, setResult] = useState<ToleranceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lenses = system.components.filter(
    (c): c is ThinLens | ThickLens => c.type === "thin_lens" || c.type === "thick_lens",
  );

  const handleRun = async () => {
    setBusy(true);
    setError(null);
    setResult(null);

    const trialsNum = Math.max(10, Math.min(1000, parseInt(trials) || 100));
    const tolMm = parseFloat(tolerance) || 0.1;
    const tolM = tolMm * 1e-3;

    const tolerances: Record<string, number> = {};
    for (const lens of lenses) {
      tolerances[`${lens.id}.position`] = tolM;
    }

    try {
      const res = await runToleranceAnalysis({
        system,
        tolerances,
        trials: trialsNum,
        seed: 42,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tolerance analysis failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Tolerance Analysis</h2>

      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-xs text-gray-600 mb-1">Trials</label>
            <input
              type="number" min="10" max="1000"
              value={trials}
              onChange={(e) => setTrials(e.target.value)}
              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Position tol. (mm)</label>
            <input
              type="number" step="0.01" min="0.01"
              value={tolerance}
              onChange={(e) => setTolerance(e.target.value)}
              className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
            />
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={busy || lenses.length === 0}
          className="w-full px-3 py-1.5 bg-optical-600 text-white text-xs rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {busy ? "Running..." : "Run Tolerance Analysis"}
        </button>

        {error && <p className="text-xs text-red-500">{error}</p>}

        {result && (
          <div className="p-3 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500 uppercase mb-2">RMS Spot Radius Statistics</div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div className="text-xs text-gray-400">Mean</div>
                <div className="font-medium">{(result.mean * 1e6).toFixed(3)} um</div>
              </div>
              <div>
                <div className="text-xs text-gray-400">Std Dev</div>
                <div className="font-medium">{(result.std * 1e6).toFixed(3)} um</div>
              </div>
              <div>
                <div className="text-xs text-gray-400">Min</div>
                <div className="font-medium">{(result.min * 1e6).toFixed(3)} um</div>
              </div>
              <div>
                <div className="text-xs text-gray-400">Max</div>
                <div className="font-medium">{(result.max * 1e6).toFixed(3)} um</div>
              </div>
              <div>
                <div className="text-xs text-gray-400">95th Percentile</div>
                <div className="font-medium">{(result.p95 * 1e6).toFixed(3)} um</div>
              </div>
              <div>
                <div className="text-xs text-gray-400">Trials</div>
                <div className="font-medium">{result.trials}</div>
              </div>
            </div>
            {/* Trend mini-plot */}
            {result.trend.length > 0 && (
              <div className="mt-2">
                <div className="text-xs text-gray-400 mb-1">Distribution</div>
                <TrendPlot data={result.trend} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TrendPlot({ data }: { data: number[] }) {
  const width = 260;
  const height = 60;
  const pad = 5;
  const plotW = width - 2 * pad;
  const plotH = height - 2 * pad;

  const maxVal = Math.max(...data, 1e-9);
  const minVal = Math.min(...data, 0);
  const range = maxVal - minVal || 1;

  const points = data.map((v, i) => {
    const x = pad + (i / Math.max(1, data.length - 1)) * plotW;
    const y = pad + plotH - ((v - minVal) / range) * plotH;
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg width={width} height={height} className="bg-white rounded border">
      <polyline points={points} fill="none" stroke="#6366f1" strokeWidth={1.5} />
    </svg>
  );
}
