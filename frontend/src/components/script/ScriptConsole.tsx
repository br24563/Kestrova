/**
 * Script console: Python with the kestrova scripting API, run by the
 * engine in its own process. `lens` is the lens in the editor (a
 * kestrova.Lens); a changed lens can be sent back to the editor.
 */
import { useEffect, useMemo, useState } from "react";
import type { LensData } from "../../types";
import { runScript, scriptReference } from "../../api";
import type { ScriptReferenceEntry, ScriptResult } from "../../api";

export const EXAMPLES: { label: string; code: string }[] = [
  {
    label: "First order",
    code: `fo = lens.first_order()
for key in ("efl", "bfl", "f_number", "image_height"):
    print(f"{key:14s} {fo[key]:.6g}")`,
  },
  {
    label: "Thickness sweep",
    code: `# RMS spot against the thickness of surface 1
for t in np.linspace(0.8, 1.2, 5) * lens.get(1, "thickness"):
    trial = lens.copy().set(1, "thickness", t)
    print(f"t = {t * 1e3:.3f} mm   spot = {trial.spot_rms() * 1e6:.2f} um")`,
  },
  {
    label: "Optimize radii",
    code: `# Vary every radius and optimize; the result can go back to the editor
for i, s in enumerate(lens.surfaces):
    if s.radius:
        lens.vary(i, "radius")
before = lens.wavefront_rms()
lens.optimize()
print(f"RMS wavefront {before:.4f} -> {lens.wavefront_rms():.4f} waves")`,
  },
  {
    label: "Temperature",
    code: `for row in lens.environment([-20, 0, 20, 40, 60]):
    print(f"{row['temperature']:5.0f} C  EFL {row['efl'] * 1e3:.4f} mm  "
          f"focus {row['focus_shift'] * 1e6:+.2f} um")`,
  },
  {
    label: "Tolerances",
    code: `result = lens.tolerance(trials=2000)
print("nominal", round(result["nominal_rms"], 4), "waves")
worst = sorted(result["sensitivities"], key=lambda d: -abs(d["change_plus"]))
for d in worst[:5]:
    print(f"{d['tolerance']:10s} {d['change_plus']:+.4f} waves")`,
  },
];

export function ScriptConsole({
  lens,
  onApplyLens,
}: {
  lens: LensData | null;
  onApplyLens: (lens: LensData) => void;
}) {
  const [code, setCode] = useState(EXAMPLES[0].code);
  const [result, setResult] = useState<ScriptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [applied, setApplied] = useState(false);
  const [reference, setReference] = useState<ScriptReferenceEntry[] | null>(
    null,
  );
  const [showHelp, setShowHelp] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!showHelp || reference) return;
    scriptReference()
      .then((r) => setReference(r.reference))
      .catch((err) => setError(err.message));
  }, [showHelp, reference]);

  const run = async () => {
    setRunning(true);
    setError(null);
    setApplied(false);
    try {
      setResult(await runScript(code, lens));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The script failed");
    } finally {
      setRunning(false);
    }
  };

  const shown = useMemo(
    () =>
      (reference ?? []).filter((r) =>
        `${r.name} ${r.doc}`.toLowerCase().includes(filter.toLowerCase()),
      ),
    [reference, filter],
  );

  return (
    <div className="p-4 space-y-2 text-xs" data-testid="script-console">
      <div className="flex flex-wrap items-center gap-2 text-gray-600">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Script console (Python)
        </h3>
        <label className="flex items-center gap-1">
          Example
          <select
            aria-label="Example"
            value=""
            onChange={(e) => {
              const ex = EXAMPLES.find((x) => x.label === e.target.value);
              if (ex) setCode(ex.code);
            }}
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            <option value="">Choose...</option>
            {EXAMPLES.map((x) => (
              <option key={x.label} value={x.label}>
                {x.label}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={() => setShowHelp((v) => !v)}
          className="px-2 py-1 border border-gray-200 rounded hover:bg-gray-50"
        >
          {showHelp ? "Hide reference" : "API reference"}
        </button>
        <button
          onClick={run}
          disabled={running || !code.trim()}
          title="Ctrl+Enter"
          className="px-3 py-1 bg-optical-600 text-white rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {running ? "Running..." : "Run"}
        </button>
      </div>
      {!lens && (
        <p className="text-amber-700">
          No lens in the editor: `lens` is not defined (use ks.sample(...) or
          ks.open_lens(...)).
        </p>
      )}
      <textarea
        aria-label="Script"
        value={code}
        spellCheck={false}
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            if (!running) run();
          } else if (e.key === "Tab") {
            e.preventDefault();
            const el = e.currentTarget;
            const { selectionStart: a, selectionEnd: b } = el;
            const next = `${code.slice(0, a)}    ${code.slice(b)}`;
            setCode(next);
            requestAnimationFrame(() => {
              el.selectionStart = el.selectionEnd = a + 4;
            });
          }
        }}
        rows={12}
        className="w-full font-mono text-xs border border-gray-200 rounded p-2 bg-gray-50"
      />
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="space-y-1">
          <pre
            data-testid="script-output"
            className="font-mono bg-gray-900 text-gray-100 rounded p-2 max-h-72 overflow-auto whitespace-pre-wrap"
          >
            {result.output}
            {result.error && (
              <span className="text-red-300">{result.error}</span>
            )}
            {!result.output && !result.error && (
              <span className="text-gray-400">(no output)</span>
            )}
          </pre>
          <div className="flex items-center gap-3 text-gray-500">
            <span>{result.duration.toFixed(1)} s</span>
            {result.lens && lens && (
              <button
                onClick={() => {
                  if (result.lens) onApplyLens(result.lens);
                  setApplied(true);
                }}
                disabled={applied}
                className="px-2 py-0.5 border border-optical-600 text-optical-700 rounded hover:bg-optical-50 disabled:opacity-50"
              >
                {applied ? "Sent to the editor" : "Send lens to the editor"}
              </button>
            )}
          </div>
        </div>
      )}
      {showHelp && (
        <div className="border border-gray-200 rounded p-2 space-y-1">
          <input
            aria-label="Filter reference"
            placeholder="Filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="border border-gray-200 rounded px-1 py-0.5 w-48"
          />
          {!reference && <p className="text-gray-400">Loading...</p>}
          <dl data-testid="script-reference" className="max-h-72 overflow-auto">
            {shown.map((r) => (
              <div key={r.name} className="py-0.5">
                <dt className="font-mono text-gray-800">
                  {r.name}
                  <span className="text-gray-500">{r.signature}</span>
                </dt>
                <dd className="pl-4 text-gray-600">{r.doc}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      <p className="text-gray-400">
        Each run starts fresh with <code>ks</code> (the kestrova module),{" "}
        <code>np</code> and <code>lens</code>; units are SI (m, rad). Scripts
        run on this computer with your permissions, stopped after 2 minutes.
      </p>
    </div>
  );
}
