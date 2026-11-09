/**
 * Fast tolerancing of the lens prescription (Code V TOR style).
 *
 * Load the starting tolerance set (or edit it), run the analysis, and read
 * the sensitivity of the RMS wavefront error to each tolerance at its
 * limits (with refocus) and the predicted distribution over random builds.
 * "Check with Monte Carlo" traces and refocuses real random builds to
 * confirm the prediction; a budget gives the limit each tolerance may have.
 */

import { useState } from "react";
import type {
  LengthUnit,
  LensCompensator,
  LensData,
  LensMonteCarloResult,
  LensTolerance,
  LensToleranceResult,
  ToleranceDistribution,
  ToleranceKind,
} from "../../types";
import {
  fromMeters,
  toMeters,
  ELEMENT_TOLERANCES,
  LENGTH_UNIT_LABELS,
} from "../../types";
import {
  lensToleranceDefaults,
  monteCarloLens,
  toleranceLens,
} from "../../api";
import { LinePlot } from "../analysis/LinePlot";

export const TOLERANCE_LABELS: Record<ToleranceKind, string> = {
  DLF: "Radius (fringes)",
  DLR: "Radius",
  DLT: "Thickness",
  DLN: "Index",
  DLV: "Abbe number",
  DSX: "Surface decenter x",
  DSY: "Surface decenter y",
  TRX: "Surface tilt x",
  TRY: "Surface tilt y",
  DLX: "Element decenter x",
  DLY: "Element decenter y",
  BTX: "Element tilt x",
  BTY: "Element tilt y",
};

const LENGTH_KINDS: ToleranceKind[] = [
  "DLR",
  "DLT",
  "DSX",
  "DSY",
  "DLX",
  "DLY",
];
const TILT_KINDS: ToleranceKind[] = ["TRX", "TRY", "BTX", "BTY"];
const ARCMIN = Math.PI / (180 * 60);

/** A tolerance limit in display units (fringes, length unit, arcmin, ...). */
export function limitToDisplay(
  kind: ToleranceKind,
  limit: number,
  unit: LengthUnit,
): number {
  if (LENGTH_KINDS.includes(kind)) return fromMeters(limit, unit);
  if (TILT_KINDS.includes(kind)) return limit / ARCMIN;
  return limit;
}

export function limitFromDisplay(
  kind: ToleranceKind,
  value: number,
  unit: LengthUnit,
): number {
  if (LENGTH_KINDS.includes(kind)) return toMeters(value, unit);
  if (TILT_KINDS.includes(kind)) return value * ARCMIN;
  return value;
}

export function limitUnit(kind: ToleranceKind, unit: LengthUnit): string {
  if (kind === "DLF") return "fringes";
  if (LENGTH_KINDS.includes(kind)) return LENGTH_UNIT_LABELS[unit];
  if (TILT_KINDS.includes(kind)) return "arcmin";
  return "";
}

const PCT_LABELS: [string, string][] = [
  ["50.0", "50 %"],
  ["84.13", "84 %"],
  ["97.72", "97.7 %"],
  ["99.87", "99.9 %"],
];

const w = (v: number | undefined) =>
  v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(4);

interface Props {
  lens: LensData;
  displayUnit: LengthUnit;
  /** Configuration toleranced (0-based) for a multi-configuration lens. */
  configuration?: number;
}

export function LensTolerancePanel({
  lens,
  displayUnit,
  configuration = 0,
}: Props) {
  const [tolerances, setTolerances] = useState<LensTolerance[] | null>(null);
  const [compLimit, setCompLimit] = useState("");
  const [trials, setTrials] = useState("20000");
  const [budget, setBudget] = useState("");
  const [mcTrials, setMcTrials] = useState("50");
  const [result, setResult] = useState<LensToleranceResult | null>(null);
  const [mc, setMc] = useState<LensMonteCarloResult | null>(null);
  const [busy, setBusy] = useState<"defaults" | "run" | "mc" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const unit = LENGTH_UNIT_LABELS[displayUnit];

  const compensators = (): LensCompensator[] => {
    const v = Number(compLimit);
    return [
      {
        kind: "back_focus",
        limit:
          compLimit.trim() !== "" && Number.isFinite(v) && v > 0
            ? toMeters(v, displayUnit)
            : null,
      },
    ];
  };

  const run = async <T,>(
    kind: "defaults" | "run" | "mc",
    fn: () => Promise<T>,
  ): Promise<T | null> => {
    setBusy(kind);
    setError(null);
    try {
      return await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setBusy(null);
    }
  };

  const loadDefaults = async () => {
    const out = await run("defaults", () =>
      lensToleranceDefaults(lens, configuration),
    );
    if (out) {
      setTolerances(out.tolerances);
      setResult(null);
      setMc(null);
    }
  };

  const analyse = async () => {
    const n = parseInt(trials, 10);
    const b = Number(budget);
    const out = await run("run", () =>
      toleranceLens(lens, tolerances, compensators(), {
        trials: Number.isFinite(n) && n >= 100 ? n : 20000,
        rssBudget:
          budget.trim() !== "" && Number.isFinite(b) && b > 0 ? b : null,
        configuration,
      }),
    );
    if (out) {
      setResult(out);
      setMc(null);
    }
  };

  const monteCarlo = async () => {
    const n = parseInt(mcTrials, 10);
    const out = await run("mc", () =>
      monteCarloLens(
        lens,
        tolerances,
        compensators(),
        Number.isFinite(n) && n > 0 ? Math.min(n, 500) : 50,
        configuration,
      ),
    );
    if (out) setMc(out);
  };

  const setTol = (k: number, patch: Partial<LensTolerance>) =>
    setTolerances(
      (tolerances ?? []).map((t, i) => (i === k ? { ...t, ...patch } : t)),
    );

  const ranked = result
    ? [...result.sensitivities].sort(
        (a, b) =>
          Math.max(Math.abs(b.change_plus), Math.abs(b.change_minus)) -
          Math.max(Math.abs(a.change_plus), Math.abs(a.change_minus)),
      )
    : [];
  const maxChange = ranked.length
    ? Math.max(
        ...ranked.map((r) =>
          Math.max(Math.abs(r.change_plus), Math.abs(r.change_minus)),
        ),
        1e-12,
      )
    : 1;

  return (
    <div className="mt-4 pt-3 border-t border-gray-200 text-xs">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <h4 className="font-semibold text-gray-700">Tolerancing</h4>
        <span className="text-[11px] text-gray-400">
          RMS wavefront error (waves), refocused; solves and pickups frozen
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={loadDefaults}
          disabled={busy !== null}
          className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
          title="A starting set for every element; edit the limits to your fabricator's"
        >
          {busy === "defaults" ? "Loading..." : "Load default tolerances"}
        </button>
        <label className="flex items-center gap-1 text-gray-600">
          Refocus limit ({unit})
          <input
            value={compLimit}
            onChange={(e) => setCompLimit(e.target.value)}
            placeholder="free"
            className="w-16 px-1 py-0.5 border border-gray-200 rounded text-right"
          />
        </label>
        <label className="flex items-center gap-1 text-gray-600">
          Builds
          <input
            value={trials}
            onChange={(e) => setTrials(e.target.value)}
            className="w-16 px-1 py-0.5 border border-gray-200 rounded text-right"
          />
        </label>
        <label
          className="flex items-center gap-1 text-gray-600"
          title="Optional: total allowed increase in RMS wavefront error, shared equally (RSS) to suggest each tolerance's limit"
        >
          Budget (waves)
          <input
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            placeholder="none"
            className="w-14 px-1 py-0.5 border border-gray-200 rounded text-right"
          />
        </label>
        <button
          onClick={analyse}
          disabled={busy !== null}
          className="px-3 py-1 bg-optical-600 text-white rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {busy === "run"
            ? "Analysing..."
            : tolerances
              ? `Analyse (${tolerances.length} tolerances)`
              : "Analyse with default tolerances"}
        </button>
      </div>

      {tolerances && tolerances.length > 0 && (
        <div className="mt-2 max-h-56 overflow-y-auto border border-gray-200 rounded">
          <table className="w-full" aria-label="Tolerances">
            <thead className="bg-gray-50 text-gray-600 sticky top-0">
              <tr>
                <th className="px-1 py-0.5 text-left font-medium">Tolerance</th>
                <th className="px-1 py-0.5 text-left font-medium">Surfaces</th>
                <th className="px-1 py-0.5 text-right font-medium">± Limit</th>
                <th className="px-1 py-0.5 text-left font-medium">
                  Distribution
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tolerances.map((t, k) => (
                <tr key={k} className="border-t border-gray-100">
                  <td className="px-1" title={t.kind}>
                    <span className="font-mono text-gray-400 mr-1">
                      {t.kind}
                    </span>
                    {TOLERANCE_LABELS[t.kind]}
                  </td>
                  <td className="px-1 font-mono">
                    {ELEMENT_TOLERANCES.includes(t.kind)
                      ? `${t.surface}–${t.last_surface ?? t.surface + 1}`
                      : t.surface}
                  </td>
                  <td className="px-1 text-right">
                    <input
                      key={`${k}-${t.limit}`}
                      aria-label={`${t.kind} surface ${t.surface} limit`}
                      defaultValue={String(
                        Number(
                          limitToDisplay(
                            t.kind,
                            t.limit,
                            displayUnit,
                          ).toPrecision(6),
                        ),
                      )}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (Number.isFinite(v) && v > 0)
                          setTol(k, {
                            limit: limitFromDisplay(t.kind, v, displayUnit),
                          });
                      }}
                      className="w-20 px-1 border border-gray-200 rounded text-right font-mono"
                    />{" "}
                    <span className="text-gray-400">
                      {limitUnit(t.kind, displayUnit)}
                    </span>
                  </td>
                  <td className="px-1">
                    <select
                      aria-label={`${t.kind} surface ${t.surface} distribution`}
                      value={t.distribution ?? "uniform"}
                      onChange={(e) =>
                        setTol(k, {
                          distribution: e.target.value as ToleranceDistribution,
                        })
                      }
                      className="bg-transparent py-0.5"
                    >
                      <option value="uniform">uniform</option>
                      <option value="gaussian">gaussian (2σ)</option>
                      <option value="end_point">end point</option>
                    </select>
                  </td>
                  <td className="px-1 text-right">
                    <button
                      onClick={() =>
                        setTolerances(tolerances.filter((_, i) => i !== k))
                      }
                      aria-label={`Remove ${t.kind} surface ${t.surface}`}
                      className="text-gray-400 hover:text-red-600"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && (
        <p className="mt-2 text-red-500" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-3 space-y-3" data-testid="tolerance-result">
          <div className="flex flex-wrap gap-6">
            <table>
              <tbody>
                <tr>
                  <td className="pr-3 text-gray-600">Nominal</td>
                  <td className="font-mono">{w(result.nominal_rms)}</td>
                </tr>
                {PCT_LABELS.map(([key, label]) => (
                  <tr key={key}>
                    <td className="pr-3 text-gray-600">{label} of builds ≤</td>
                    <td className="font-mono" data-testid={`pct-${key}`}>
                      {w(result.predicted.percentiles[key])}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td className="pr-3 text-gray-600">Mean ± std</td>
                  <td className="font-mono">
                    {w(result.predicted.mean)} ± {w(result.predicted.std)}
                  </td>
                </tr>
                <tr>
                  <td className="pr-3 text-gray-600">RSS of changes</td>
                  <td className="font-mono">{w(result.rss_increase)}</td>
                </tr>
              </tbody>
            </table>
            {result.compensators.map((c) => (
              <div
                key={c.compensator}
                className="text-gray-600"
                data-testid="refocus"
              >
                <div className="font-medium">Refocus ({c.compensator})</div>
                {c.nominal !== undefined && (
                  <div title="Best focus of the nominal lens relative to the image plane">
                    nominal {fromMeters(c.nominal, displayUnit).toPrecision(3)}{" "}
                    {unit}
                  </div>
                )}
                <div>
                  per build ±{fromMeters(c.std, displayUnit).toPrecision(3)}{" "}
                  {unit} (1σ)
                  {c.max_change !== undefined &&
                    `, up to ${fromMeters(c.max_change, displayUnit).toPrecision(3)} ${unit}`}
                </div>
              </div>
            ))}
            {mc && (
              <table data-testid="monte-carlo-result">
                <thead>
                  <tr className="text-gray-600">
                    <th className="pr-3 text-left font-medium">
                      Check ({mc.trials} traced builds)
                    </th>
                    <th className="pr-3 text-right font-medium">Predicted</th>
                    <th className="text-right font-medium">Traced</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="pr-3 text-gray-600">Mean</td>
                    <td className="pr-3 text-right font-mono">
                      {w(result.predicted.mean)}
                    </td>
                    <td className="text-right font-mono">{w(mc.mean)}</td>
                  </tr>
                  {PCT_LABELS.slice(0, 2).map(([key, label]) => (
                    <tr key={key}>
                      <td className="pr-3 text-gray-600">{label}</td>
                      <td className="pr-3 text-right font-mono">
                        {w(result.predicted.percentiles[key])}
                      </td>
                      <td className="text-right font-mono">
                        {w(mc.percentiles[key])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={monteCarlo}
              disabled={busy !== null}
              className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
              title="Trace and refocus real random builds to confirm the prediction (slower)"
            >
              {busy === "mc" ? "Tracing builds..." : "Check with Monte Carlo"}
            </button>
            <label className="flex items-center gap-1 text-gray-600">
              builds
              <input
                value={mcTrials}
                onChange={(e) => setMcTrials(e.target.value)}
                className="w-12 px-1 py-0.5 border border-gray-200 rounded text-right"
              />
            </label>
          </div>

          <LinePlot
            id="tolerance-cumulative"
            series={[
              {
                label: "Predicted",
                color: "#2563eb",
                x: result.predicted.cumulative.rms,
                y: result.predicted.cumulative.probability.map((p) => p * 100),
              },
            ]}
            xLabel="RMS wavefront error (waves)"
            yLabel="Builds (%)"
            yDomain={[0, 100]}
            height={180}
          />

          {ranked.length === 0 && (
            <p className="text-gray-500">
              No tolerances were analysed: the default set covers glass
              elements, and ideal (paraxial) lenses have none.
            </p>
          )}
          <table className="w-full" aria-label="Sensitivities">
            <thead className="text-gray-600">
              <tr>
                <th className="text-left font-medium">Tolerance</th>
                <th className="text-right font-medium">± Limit</th>
                <th className="text-right font-medium">Change at +</th>
                <th className="text-right font-medium">Change at −</th>
                <th className="w-1/3" />
              </tr>
            </thead>
            <tbody>
              {ranked.map((r) => {
                const big = Math.max(
                  Math.abs(r.change_plus),
                  Math.abs(r.change_minus),
                );
                const inverse = result.inverse_limits?.find(
                  (x) => x.tolerance === r.tolerance,
                );
                return (
                  <tr key={r.tolerance} className="border-t border-gray-100">
                    <td className="py-0.5">
                      <span className="font-mono text-gray-400 mr-1">
                        {r.tolerance}
                      </span>
                    </td>
                    <td className="text-right font-mono">
                      {Number(
                        limitToDisplay(
                          r.kind,
                          r.limit,
                          displayUnit,
                        ).toPrecision(3),
                      )}{" "}
                      <span className="text-gray-400">
                        {limitUnit(r.kind, displayUnit)}
                      </span>
                      {inverse && Number.isFinite(inverse.limit) && (
                        <div
                          className={
                            inverse.extrapolated
                              ? "text-amber-600"
                              : "text-gray-500"
                          }
                          title={
                            inverse.extrapolated
                              ? "Suggested limit from the budget (extrapolated beyond the analysed limit)"
                              : "Suggested limit from the budget"
                          }
                        >
                          →{" "}
                          {Number(
                            limitToDisplay(
                              r.kind,
                              inverse.limit,
                              displayUnit,
                            ).toPrecision(3),
                          )}
                        </div>
                      )}
                    </td>
                    <td className="text-right font-mono">
                      {r.change_plus >= 0 ? "+" : ""}
                      {r.change_plus.toFixed(4)}
                    </td>
                    <td className="text-right font-mono">
                      {r.change_minus >= 0 ? "+" : ""}
                      {r.change_minus.toFixed(4)}
                    </td>
                    <td className="pl-2">
                      <div className="h-2 bg-gray-100 rounded">
                        <div
                          className="h-2 bg-amber-400 rounded"
                          style={{ width: `${(100 * big) / maxChange}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
