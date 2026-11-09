/**
 * Global search (in the spirit of Code V's Global Synthesis): local
 * optimizations from many starting points spread over the variables'
 * ranges; lists the distinct designs that meet every constraint, best merit
 * first, and loads the chosen one into the editor.
 */
import { useState } from "react";
import { globalOptimizeLens } from "../../api";
import type { GlobalSearchResult } from "../../api";
import { fmtLen } from "../../types";
import type { LengthUnit, LensData } from "../../types";

export function GlobalSearchPanel({
  lens,
  displayUnit,
  disabled,
  maxEvaluations,
  onUse,
}: {
  lens: LensData;
  displayUnit: LengthUnit;
  disabled: boolean;
  maxEvaluations: number;
  onUse: (lens: LensData) => void;
}) {
  const [starts, setStarts] = useState("16");
  const [workers, setWorkers] = useState("1");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<GlobalSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const n = parseInt(starts, 10);
      const w = parseInt(workers, 10);
      setResult(
        await globalOptimizeLens(lens, {
          starts: Number.isFinite(n) && n > 0 ? Math.min(n, 256) : 16,
          workers: Number.isFinite(w) && w > 0 ? Math.min(w, 64) : 1,
          maxEvaluations,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Global search failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mt-2" data-testid="global-search">
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <button
          onClick={run}
          disabled={disabled || running}
          title="Optimize from many starting points and list the distinct designs found"
          className="px-3 py-1 text-xs border border-optical-600 text-optical-700 rounded hover:bg-optical-50 disabled:opacity-40"
        >
          {running ? "Searching..." : "Global search"}
        </button>
        <label className="flex items-center gap-1">
          Starts
          <input
            aria-label="Global search starts"
            value={starts}
            onChange={(e) => setStarts(e.target.value)}
            className="w-12 px-1 py-0.5 border border-gray-200 rounded text-right"
          />
        </label>
        <label
          className="flex items-center gap-1"
          title="Processes running the starts in parallel"
        >
          Workers
          <input
            aria-label="Global search workers"
            value={workers}
            onChange={(e) => setWorkers(e.target.value)}
            className="w-10 px-1 py-0.5 border border-gray-200 rounded text-right"
          />
        </label>
        {result && (
          <span className="text-gray-500">
            {result.distinct} distinct design
            {result.distinct === 1 ? "" : "s"} from {result.starts} starts (
            {result.feasible} met the constraints, {result.evaluations}{" "}
            evaluations)
          </span>
        )}
      </div>
      {error && (
        <p className="text-xs text-red-500 mt-1" role="alert">
          {error}
        </p>
      )}
      {result && result.solutions.length > 0 && (
        <table
          className="mt-1 text-xs border border-gray-200 rounded"
          data-testid="global-solutions"
        >
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-1 py-0.5 text-left font-medium">#</th>
              <th className="px-1 py-0.5 text-right font-medium">Merit</th>
              <th className="px-1 py-0.5 text-right font-medium">EFL</th>
              <th className="px-1 py-0.5 text-right font-medium">F/#</th>
              <th className="px-1 py-0.5 text-right font-medium">From start</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {result.solutions.map((s, k) => (
              <tr key={k} className="border-t border-gray-100">
                <td className="px-1">{k + 1}</td>
                <td className="px-1 text-right font-mono">
                  {s.merit.toPrecision(4)}
                </td>
                <td className="px-1 text-right font-mono">
                  {fmtLen(s.first_order.efl, displayUnit, 3)}
                </td>
                <td className="px-1 text-right font-mono">
                  {s.first_order.f_number === null
                    ? "—"
                    : s.first_order.f_number.toFixed(2)}
                </td>
                <td className="px-1 text-right">
                  {s.start === 0 ? "as given" : s.start}
                </td>
                <td className="px-1">
                  <button
                    onClick={() => onUse(s.lens)}
                    aria-label={`Use design ${k + 1}`}
                    className="px-2 py-0.5 border border-gray-300 rounded hover:bg-gray-50"
                  >
                    Use
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {result && result.solutions.length === 0 && (
        <p className="text-xs text-amber-700 mt-1">
          No start reached a design that meets every constraint.
        </p>
      )}
    </div>
  );
}
