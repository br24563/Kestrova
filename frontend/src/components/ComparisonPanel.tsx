/**
 * System Comparison Panel Component.
 *
 * Allows the user to save a snapshot of the current system and compare
 * it side-by-side with the current system. Displays metrics with
 * advantage indicators.
 */

import { useState } from "react";
import type { OpticalSystem, ComparisonResult, LengthUnit } from "../types";
import { compareSystems } from "../api";

interface ComparisonPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

// Spot sizes are shown in micrometres whatever the display unit.
export function ComparisonPanel({ system }: ComparisonPanelProps) {
  const [snapshot, setSnapshot] = useState<OpticalSystem | null>(null);
  const [labelA, setLabelA] = useState("Saved");
  const [labelB, setLabelB] = useState("Current");
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSnapshot = () => {
    setSnapshot(JSON.parse(JSON.stringify(system)));
    setResult(null);
    setError(null);
  };

  const handleCompare = async () => {
    if (!snapshot) {
      setError("Take a snapshot first.");
      return;
    }
    setError(null);
    try {
      const res = await compareSystems({
        system_a: snapshot,
        system_b: system,
        label_a: labelA,
        label_b: labelB,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed");
    }
  };

  return (
    <div className="p-4 border-t border-gray-200">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">System Comparison</h2>

      <div className="space-y-3">
        <button
          onClick={handleSnapshot}
          className="w-full px-3 py-1.5 bg-blue-600 text-white text-xs rounded hover:bg-blue-700"
        >
          {snapshot ? "Update Snapshot" : "Take Snapshot"}
        </button>

        {snapshot && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Label A</label>
                <input
                  type="text"
                  value={labelA}
                  onChange={(e) => setLabelA(e.target.value)}
                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Label B</label>
                <input
                  type="text"
                  value={labelB}
                  onChange={(e) => setLabelB(e.target.value)}
                  className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                />
              </div>
            </div>
            <button
              onClick={handleCompare}
              className="w-full px-3 py-1.5 bg-optical-600 text-white text-xs rounded hover:bg-optical-700"
            >
              Compare Systems
            </button>
          </>
        )}

        {error && <p className="text-xs text-red-500">{error}</p>}

        {result && (
          <div className="p-3 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500 uppercase mb-2">Comparison Results</div>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500">
                  <th className="text-left py-0.5">Metric</th>
                  <th className="text-right py-0.5">{result.summary_a.label}</th>
                  <th className="text-right py-0.5">{result.summary_b.label}</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, i) => (
                  <tr key={i} className="border-t border-gray-200">
                    <td className="py-0.5 text-gray-600">{row.metric}</td>
                    <td className={`py-0.5 text-right ${row.advantage === "a" ? "font-bold text-green-700" : ""}`}>
                      {typeof row.a === "number" ? row.a.toFixed(3) : row.a}
                    </td>
                    <td className={`py-0.5 text-right ${row.advantage === "b" ? "font-bold text-green-700" : ""}`}>
                      {typeof row.b === "number" ? row.b.toFixed(3) : row.b}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
