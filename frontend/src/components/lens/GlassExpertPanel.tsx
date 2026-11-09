/**
 * Glass substitution (in the spirit of Code V's glass expert): tries the
 * catalogue glasses nearest each glass of the lens, re-optimizing with the
 * lens's variables, and keeps each substitution that lowers the merit
 * (model glasses are always replaced). The result replaces the lens.
 */
import { useState } from "react";
import { substituteLensGlasses } from "../../api";
import type { GlassSubstitutionResult } from "../../api";
import type { LensData } from "../../types";

export function GlassExpertPanel({
  lens,
  disabled,
  maxEvaluations,
  onDone,
}: {
  lens: LensData;
  disabled: boolean;
  maxEvaluations: number;
  onDone: (result: GlassSubstitutionResult) => void;
}) {
  const [candidates, setCandidates] = useState("8");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<GlassSubstitutionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const n = parseInt(candidates, 10);
      const out = await substituteLensGlasses(lens, {
        candidates: Number.isFinite(n) && n > 0 ? Math.min(n, 60) : 8,
        maxEvaluations,
      });
      setResult(out);
      onDone(out);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Glass substitution failed",
      );
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mt-2" data-testid="glass-expert">
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <button
          onClick={run}
          disabled={disabled || running}
          title="Try the nearest catalogue glasses on each glass, re-optimizing, and keep those that lower the merit"
          className="px-3 py-1 text-xs border border-gray-400 rounded hover:bg-gray-50 disabled:opacity-40"
        >
          {running ? "Substituting..." : "Substitute glasses"}
        </button>
        <label className="flex items-center gap-1">
          Candidates per glass
          <input
            aria-label="Glass candidates"
            value={candidates}
            onChange={(e) => setCandidates(e.target.value)}
            className="w-10 px-1 py-0.5 border border-gray-200 rounded text-right"
          />
        </label>
      </div>
      {error && (
        <p className="text-xs text-red-500 mt-1" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="text-xs text-gray-700 mt-1" data-testid="glass-result">
          {result.substitutions.length === 0 ? (
            <p>No substitution lowered the merit; the glasses are unchanged.</p>
          ) : (
            <ul className="list-disc ml-5">
              {result.substitutions.map((s, k) => (
                <li key={k}>
                  Surface {s.surface}: {s.from} → <strong>{s.to}</strong>{" "}
                  <span className="text-gray-500">
                    (merit {s.merit.toPrecision(4)})
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="text-gray-500">
            Merit {result.merit_before.toPrecision(4)} →{" "}
            {result.merit_after.toPrecision(4)} ({result.evaluations}{" "}
            evaluations)
          </p>
        </div>
      )}
    </div>
  );
}
