/**
 * Advanced Optimization Panel Component.
 *
 * - Hybrid: global search (differential evolution or particle swarm)
 *   followed by local refinement (damped least squares, L-BFGS-B or
 *   Nelder-Mead), with the constraint operands from the merit editor.
 * - High-yield: minimizes RMS spot while penalizing designs whose
 *   Monte-Carlo yield under the given tolerances falls below the threshold.
 */

import { useState } from "react";
import type { OpticalSystem, LengthUnit } from "../../types";
import { fromMeters, toMeters, LENGTH_UNIT_LABELS } from "../../types";
import {
  hybridOptimize,
  highYieldOptimize,
  type HybridOptimizeRequest,
  type HybridOptimizeResult,
  type HighYieldOptimizeResult,
} from "../../api";
import {
  MeritFunctionEditor,
  operandsToConstraints,
  type MeritOperand,
} from "./MeritFunctionEditor";

interface AdvancedOptimizationPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
  onApplyOptimized: (system: OpticalSystem) => void;
}

interface ParamChoice {
  id: string; // "<component id>.<field>"
  label: string;
  value: number; // current value, meters
}

type Result =
  | { kind: "hybrid"; data: HybridOptimizeResult }
  | { kind: "high-yield"; data: HighYieldOptimizeResult };

/** Default search range: +-50% of a power/curvature value, +-10 % of the track for a position. */
function defaultBounds(p: ParamChoice, track: number): [number, number] {
  if (p.id.endsWith(".position"))
    return [p.value - 0.1 * track, p.value + 0.1 * track];
  const a = p.value * 0.5;
  const b = p.value * 1.5;
  return a < b ? [a, b] : [b, a];
}

export function AdvancedOptimizationPanel({
  system,
  displayUnit,
  onApplyOptimized,
}: AdvancedOptimizationPanelProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const [mode, setMode] = useState<"hybrid" | "high-yield">("hybrid");
  const [globalAlgo, setGlobalAlgo] = useState<
    NonNullable<HybridOptimizeRequest["global_algorithm"]>
  >("differential_evolution");
  const [localAlgo, setLocalAlgo] = useState<
    NonNullable<HybridOptimizeRequest["local_algorithm"]>
  >("damped_least_squares");
  const [objective, setObjective] = useState<
    "rms_spot" | "efl" | "magnification"
  >("rms_spot");
  const [target, setTarget] = useState("");
  const [maxIter, setMaxIter] = useState(30);
  const [tolerance, setTolerance] = useState("0.05"); // display units, sigma
  const [yieldThreshold, setYieldThreshold] = useState(0.9);
  const [selected, setSelected] = useState<string[]>([]);
  const [bounds, setBounds] = useState<Record<string, [string, string]>>({});
  const [operands, setOperands] = useState<MeritOperand[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const available: ParamChoice[] = system.components.flatMap((c) => {
    const out: ParamChoice[] = [];
    if (c.type === "thin_lens")
      out.push({
        id: `${c.id}.focal_length`,
        label: `${c.id} focal length`,
        value: c.focal_length,
      });
    if (c.type === "thick_lens") {
      out.push({
        id: `${c.id}.radius1`,
        label: `${c.id} R1`,
        value: c.radius1,
      });
      out.push({
        id: `${c.id}.radius2`,
        label: `${c.id} R2`,
        value: c.radius2,
      });
      out.push({
        id: `${c.id}.thickness`,
        label: `${c.id} thickness`,
        value: c.thickness,
      });
    }
    out.push({
      id: `${c.id}.position`,
      label: `${c.id} position`,
      value: c.position,
    });
    return out;
  });
  const positions = [
    system.object.position,
    system.image_plane.position,
    ...system.components.map((c) => c.position),
  ];
  const track = Math.max(...positions) - Math.min(...positions) || 0.1;

  const toggle = (p: ParamChoice) => {
    if (selected.includes(p.id)) {
      setSelected(selected.filter((s) => s !== p.id));
      return;
    }
    const [lo, hi] = defaultBounds(p, track);
    const fmt = (m: number) =>
      parseFloat(fromMeters(m, displayUnit).toPrecision(6)).toString();
    setBounds({ ...bounds, [p.id]: [fmt(lo), fmt(hi)] });
    setSelected([...selected, p.id]);
  };

  const handleRun = async () => {
    setError(null);
    setResult(null);
    const params = selected.map((id) => {
      const dot = id.lastIndexOf(".");
      return { component_id: id.slice(0, dot), field: id.slice(dot + 1) };
    });
    const b: [number, number][] = selected.map((id) => {
      const [lo, hi] = bounds[id].map((s) =>
        toMeters(parseFloat(s), displayUnit),
      );
      return [lo, hi];
    });
    if (b.some(([lo, hi]) => !(lo < hi))) {
      setError("Each parameter needs Min < Max.");
      return;
    }
    setRunning(true);
    try {
      if (mode === "hybrid") {
        let t: number | undefined;
        if (objective !== "rms_spot") {
          const v = parseFloat(target);
          if (Number.isNaN(v))
            throw new Error(
              `Enter a target ${objective === "efl" ? "focal length" : "magnification"}.`,
            );
          t = objective === "efl" ? toMeters(v, displayUnit) : v;
        }
        const data = await hybridOptimize({
          system,
          objective,
          target: t,
          params,
          bounds: b,
          constraints: operandsToConstraints(operands, displayUnit),
          global_algorithm: globalAlgo,
          local_algorithm: localAlgo,
          global_maxiter: maxIter,
          local_maxiter: maxIter,
          seed: 42,
        });
        setResult({ kind: "hybrid", data });
      } else {
        const sigma = toMeters(parseFloat(tolerance), displayUnit);
        if (!(sigma > 0)) throw new Error("Enter a positive tolerance.");
        const data = await highYieldOptimize({
          system,
          objective: "rms_spot",
          params,
          bounds: b,
          tolerances: Object.fromEntries(selected.map((id) => [id, sigma])),
          yield_threshold: yieldThreshold,
          n_monte_carlo: 20,
          seed: 42,
          global_maxiter: maxIter,
          local_maxiter: maxIter,
        });
        setResult({ kind: "high-yield", data });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Optimization failed");
    } finally {
      setRunning(false);
    }
  };

  const selectCls = "w-full px-2 py-1 text-xs border border-gray-200 rounded";

  return (
    <div className="p-4 space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-700">
            Advanced Optimization
          </h3>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Mode</label>
            <select
              value={mode}
              onChange={(e) =>
                setMode(e.target.value as "hybrid" | "high-yield")
              }
              className={selectCls}
            >
              <option value="hybrid">Hybrid (global + local)</option>
              <option value="high-yield">
                High-yield (RMS spot with tolerance yield)
              </option>
            </select>
          </div>

          {mode === "hybrid" ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">
                    Global
                  </label>
                  <select
                    value={globalAlgo}
                    onChange={(e) =>
                      setGlobalAlgo(e.target.value as typeof globalAlgo)
                    }
                    className={selectCls}
                  >
                    <option value="differential_evolution">
                      Differential evolution
                    </option>
                    <option value="particle_swarm">Particle swarm</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">
                    Local
                  </label>
                  <select
                    value={localAlgo}
                    onChange={(e) =>
                      setLocalAlgo(e.target.value as typeof localAlgo)
                    }
                    className={selectCls}
                  >
                    <option value="damped_least_squares">
                      Damped least squares
                    </option>
                    <option value="l_bfgs_b">L-BFGS-B</option>
                    <option value="nelder_mead">None (global only)</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">
                    Objective
                  </label>
                  <select
                    value={objective}
                    onChange={(e) =>
                      setObjective(e.target.value as typeof objective)
                    }
                    className={selectCls}
                  >
                    <option value="rms_spot">Minimize RMS spot</option>
                    <option value="efl">Target EFL</option>
                    <option value="magnification">Target magnification</option>
                  </select>
                </div>
                {objective !== "rms_spot" && (
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">
                      Target {objective === "efl" ? `(${unitLabel})` : "(x)"}
                    </label>
                    <input
                      type="number"
                      step="any"
                      value={target}
                      onChange={(e) => setTarget(e.target.value)}
                      className={selectCls}
                    />
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-gray-600 mb-1">
                  Tolerance &sigma; ({unitLabel}, each parameter)
                </label>
                <input
                  type="number"
                  step="any"
                  value={tolerance}
                  onChange={(e) => setTolerance(e.target.value)}
                  className={selectCls}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">
                  Yield threshold: {(yieldThreshold * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="0.99"
                  step="0.01"
                  value={yieldThreshold}
                  onChange={(e) =>
                    setYieldThreshold(parseFloat(e.target.value))
                  }
                  className="w-full"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-600 mb-1">
              Max iterations (global and local): {maxIter}
            </label>
            <input
              type="range"
              min="10"
              max="200"
              step="10"
              value={maxIter}
              onChange={(e) => setMaxIter(parseInt(e.target.value))}
              className="w-full"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-600 mb-1">
            Variables and search range ({unitLabel})
          </label>
          <div className="max-h-56 overflow-y-auto border border-gray-200 rounded p-2 space-y-1">
            {available.map((p) => (
              <div key={p.id} className="flex items-center gap-2 text-xs">
                <label className="flex items-center gap-2 cursor-pointer flex-1">
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={() => toggle(p)}
                    className="w-3 h-3"
                  />
                  <span className="text-gray-700">{p.label}</span>
                  <span className="text-gray-400">
                    (
                    {parseFloat(
                      fromMeters(p.value, displayUnit).toPrecision(5),
                    )}
                    )
                  </span>
                </label>
                {selected.includes(p.id) &&
                  ([0, 1] as const).map((i) => (
                    <input
                      key={i}
                      type="number"
                      step="any"
                      value={bounds[p.id]?.[i] ?? ""}
                      onChange={(e) => {
                        const next = [...(bounds[p.id] ?? ["", ""])] as [
                          string,
                          string,
                        ];
                        next[i] = e.target.value;
                        setBounds({ ...bounds, [p.id]: next });
                      }}
                      className="w-20 px-1 py-0.5 text-right border border-gray-200 rounded"
                      title={i === 0 ? "Min" : "Max"}
                    />
                  ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {mode === "hybrid" && (
        <MeritFunctionEditor
          system={system}
          displayUnit={displayUnit}
          operands={operands}
          onChange={setOperands}
        />
      )}

      <button
        onClick={handleRun}
        disabled={running || selected.length === 0}
        className="w-full px-3 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {running
          ? "Optimizing..."
          : selected.length === 0
            ? "Select at least one variable"
            : "Run Optimization"}
      </button>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700">
          {error}
        </div>
      )}

      {result && (
        <div
          className={`p-3 border rounded text-xs space-y-1 ${result.data.success ? "bg-green-50 border-green-200" : "bg-yellow-50 border-yellow-200"}`}
        >
          <div className="font-medium">
            {result.data.success
              ? "Optimization converged"
              : "Optimization finished without full convergence"}
          </div>
          <table className="w-full">
            <tbody>
              {selected.map((id, i) => (
                <tr key={id}>
                  <td className="text-gray-600">{id}</td>
                  <td className="text-right font-mono">
                    {result.data.params[i] !== undefined
                      ? `${fromMeters(result.data.params[i], displayUnit).toPrecision(6)} ${unitLabel}`
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.kind === "hybrid" && (
            <>
              <div>
                Merit: {result.data.objective.toPrecision(4)} (after global
                search {result.data.global_objective.toPrecision(4)});{" "}
                {result.data.n_global_iterations} global,{" "}
                {result.data.n_local_iterations} local iterations
              </div>
              {Object.keys(result.data.constraint_violations).length > 0 && (
                <div className="text-orange-700">
                  Violated:{" "}
                  {Object.entries(result.data.constraint_violations)
                    .map(([k, v]) => `${k} by ${v.toPrecision(3)}`)
                    .join(", ")}
                </div>
              )}
            </>
          )}
          {result.kind === "high-yield" && result.data.yield_stats && (
            <div>
              Yield: {((result.data.yield_stats.yield ?? 0) * 100).toFixed(1)}%{" "}
              ({result.data.yield_stats.n_pass}/
              {result.data.yield_stats.n_total} trials within 1.5&times; the
              optimized RMS spot)
            </div>
          )}
          <button
            onClick={() => onApplyOptimized(result.data.system)}
            className="mt-1 px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
          >
            Apply Optimized System
          </button>
        </div>
      )}
    </div>
  );
}
