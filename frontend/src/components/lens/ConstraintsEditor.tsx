/**
 * Constraints the optimizer holds exactly (Code V style): first-order
 * properties and centre / edge thicknesses, each with a target or limits.
 * "Check" shows each constraint's current value.
 */

import type {
  LengthUnit,
  LensConstraint,
  LensConstraintKind,
  LensConstraintStatus,
  LensData,
} from "../../types";
import {
  fromMeters,
  toMeters,
  LENGTH_UNIT_LABELS,
  SURFACE_CONSTRAINTS,
} from "../../types";

export const CONSTRAINT_LABELS: Record<LensConstraintKind, string> = {
  efl: "Effective focal length",
  bfl: "Back focal length",
  working_f_number: "Working F-number",
  magnification: "Magnification",
  total_track: "Total track",
  center_thickness: "Centre thickness",
  edge_thickness: "Edge thickness",
};

/** Constraints whose values are lengths (the others are pure numbers). */
export function isLengthConstraint(kind: LensConstraintKind): boolean {
  return kind !== "working_f_number" && kind !== "magnification";
}

/** "= target", "≥ min", "≤ max" or "min … max" in display units. */
export function describeConstraint(
  c: LensConstraint,
  displayUnit: LengthUnit,
): string {
  const show = (v: number) =>
    String(
      Number(
        (isLengthConstraint(c.kind)
          ? fromMeters(v, displayUnit)
          : v
        ).toPrecision(6),
      ),
    );
  if (c.target !== null && c.target !== undefined) return `= ${show(c.target)}`;
  const lo = c.minimum ?? null;
  const hi = c.maximum ?? null;
  if (lo !== null && hi !== null) return `${show(lo)} … ${show(hi)}`;
  if (lo !== null) return `≥ ${show(lo)}`;
  return hi !== null ? `≤ ${show(hi)}` : "";
}

interface Props {
  lens: LensData;
  displayUnit: LengthUnit;
  statuses: LensConstraintStatus[] | null;
  busy: boolean;
  onChange: (constraints: LensConstraint[]) => void;
  onCheck: () => void;
}

export function ConstraintsEditor({
  lens,
  displayUnit,
  statuses,
  busy,
  onChange,
  onCheck,
}: Props) {
  const constraints = lens.constraints ?? [];
  const unit = LENGTH_UNIT_LABELS[displayUnit];
  const configs = lens.configuration_names ?? [];
  const multi = configs.length > 1;
  /** Reported values of constraint k (one per configuration it applies to). */
  const statusesOf = (k: number): LensConstraintStatus[] => {
    if (!statuses) return [];
    if (statuses.some((s) => s.index !== undefined))
      return statuses.filter((s) => s.index === k);
    return statuses[k] ? [statuses[k]] : [];
  };

  const set = (k: number, c: LensConstraint) =>
    onChange(constraints.map((x, i) => (i === k ? c : x)));
  const remove = (k: number) => onChange(constraints.filter((_, i) => i !== k));
  const add = () =>
    onChange([...constraints, { kind: "efl", target: 0.1, surface: null }]);

  const toDisplay = (c: LensConstraint, v: number | null | undefined) =>
    v === null || v === undefined
      ? ""
      : String(
          Number(
            (isLengthConstraint(c.kind)
              ? fromMeters(v, displayUnit)
              : v
            ).toPrecision(8),
          ),
        );
  const fromText = (c: LensConstraint, text: string): number | null => {
    const t = text.trim();
    if (t === "") return null;
    const v = Number(t);
    if (!Number.isFinite(v)) return null;
    return isLengthConstraint(c.kind) ? toMeters(v, displayUnit) : v;
  };

  const changeKind = (k: number, kind: LensConstraintKind) => {
    const c = constraints[k];
    const needsSurface = SURFACE_CONSTRAINTS.includes(kind);
    // default: the first surface with glass after it (an element's front)
    const firstGlass = lens.surfaces.findIndex(
      (s) => s.material !== null && s.material !== "MIRROR",
    );
    set(k, {
      ...c,
      kind,
      surface: needsSurface ? (c.surface ?? Math.max(firstGlass, 0)) : null,
    });
  };

  const changeMode = (k: number, mode: "target" | "limits") => {
    const c = constraints[k];
    if (mode === "target")
      set(k, {
        ...c,
        target: c.minimum ?? c.maximum ?? 0,
        minimum: null,
        maximum: null,
      });
    else set(k, { ...c, target: null, minimum: c.target ?? 0, maximum: null });
  };

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2 mb-1">
        <h4 className="text-xs font-semibold text-gray-700">Constraints</h4>
        <span className="text-[11px] text-gray-400">
          held exactly while optimizing
        </span>
        <button
          onClick={add}
          className="ml-auto px-2 py-0.5 text-xs border border-gray-300 rounded hover:bg-gray-50"
        >
          Add constraint
        </button>
        <button
          onClick={onCheck}
          disabled={busy || constraints.length === 0}
          className="px-2 py-0.5 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
          title="Show each constraint's current value"
        >
          Check
        </button>
      </div>
      {constraints.length === 0 ? (
        <p className="text-[11px] text-gray-400">
          None. Add one to hold, for example, the focal length while the
          optimizer improves the image.
        </p>
      ) : (
        <table className="w-full text-xs border border-gray-200 rounded">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-1 py-0.5 text-left font-medium">Property</th>
              <th className="px-1 py-0.5 text-left font-medium">Surface</th>
              {multi && (
                <th className="px-1 py-0.5 text-left font-medium">
                  Configuration
                </th>
              )}
              <th className="px-1 py-0.5 text-left font-medium">Mode</th>
              <th className="px-1 py-0.5 text-right font-medium">
                Target / min
              </th>
              <th className="px-1 py-0.5 text-right font-medium">Max</th>
              <th className="px-1 py-0.5 text-right font-medium">Current</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {constraints.map((c, k) => {
              const mode =
                c.target !== null && c.target !== undefined
                  ? "target"
                  : "limits";
              const reported = statusesOf(k);
              const u = isLengthConstraint(c.kind) ? ` ${unit}` : "";
              return (
                <tr key={k} className="border-t border-gray-100">
                  <td className="px-1">
                    <select
                      aria-label={`Constraint ${k + 1} property`}
                      value={c.kind}
                      onChange={(e) =>
                        changeKind(k, e.target.value as LensConstraintKind)
                      }
                      className="bg-transparent text-xs py-0.5"
                    >
                      {Object.entries(CONSTRAINT_LABELS).map(([v, label]) => (
                        <option key={v} value={v}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-1 w-14">
                    {SURFACE_CONSTRAINTS.includes(c.kind) ? (
                      <input
                        aria-label={`Constraint ${k + 1} surface`}
                        type="number"
                        min={0}
                        value={c.surface ?? 0}
                        onChange={(e) =>
                          set(k, {
                            ...c,
                            surface: parseInt(e.target.value, 10),
                          })
                        }
                        className="w-12 border border-gray-200 rounded px-1 text-right"
                      />
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  {multi && (
                    <td className="px-1">
                      <select
                        aria-label={`Constraint ${k + 1} configuration`}
                        value={
                          c.configuration == null
                            ? "all"
                            : String(c.configuration)
                        }
                        onChange={(e) =>
                          set(k, {
                            ...c,
                            configuration:
                              e.target.value === "all"
                                ? null
                                : parseInt(e.target.value, 10),
                          })
                        }
                        className="bg-transparent text-xs py-0.5"
                      >
                        <option value="all">All</option>
                        {configs.map((name, i) => (
                          <option key={i} value={i}>
                            {name}
                          </option>
                        ))}
                      </select>
                    </td>
                  )}
                  <td className="px-1">
                    <select
                      aria-label={`Constraint ${k + 1} mode`}
                      value={mode}
                      onChange={(e) =>
                        changeMode(k, e.target.value as "target" | "limits")
                      }
                      className="bg-transparent text-xs py-0.5"
                    >
                      <option value="target">equal to</option>
                      <option value="limits">within limits</option>
                    </select>
                  </td>
                  <td className="px-1 w-24">
                    <input
                      key={`${k}-${mode}-${c.target}-${c.minimum}`}
                      aria-label={`Constraint ${k + 1} ${mode === "target" ? "target" : "minimum"}`}
                      defaultValue={toDisplay(
                        c,
                        mode === "target" ? c.target : c.minimum,
                      )}
                      placeholder={mode === "target" ? "" : "none"}
                      onBlur={(e) => {
                        const v = fromText(c, e.target.value);
                        set(
                          k,
                          mode === "target"
                            ? { ...c, target: v ?? 0 }
                            : { ...c, minimum: v },
                        );
                      }}
                      className="w-20 border border-gray-200 rounded px-1 text-right font-mono"
                    />
                    <span className="text-gray-400">{u}</span>
                  </td>
                  <td className="px-1 w-24">
                    {mode === "limits" && (
                      <>
                        <input
                          key={`${k}-max-${c.maximum}`}
                          aria-label={`Constraint ${k + 1} maximum`}
                          defaultValue={toDisplay(c, c.maximum)}
                          placeholder="none"
                          onBlur={(e) =>
                            set(k, {
                              ...c,
                              maximum: fromText(c, e.target.value),
                            })
                          }
                          className="w-20 border border-gray-200 rounded px-1 text-right font-mono"
                        />
                        <span className="text-gray-400">{u}</span>
                      </>
                    )}
                  </td>
                  <td
                    className="px-1 text-right font-mono"
                    data-testid={`constraint-${k}-value`}
                  >
                    {reported.length ? (
                      reported.map((status, j) => (
                        <span
                          key={j}
                          className={`block ${
                            status.satisfied ? "text-green-700" : "text-red-600"
                          }`}
                          title={
                            (status.satisfied ? "Met" : "Not met") +
                            (multi && status.configuration != null
                              ? ` in ${configs[status.configuration]}`
                              : "")
                          }
                        >
                          {multi && status.configuration != null
                            ? `${configs[status.configuration]}: `
                            : ""}
                          {toDisplay(c, status.value)}
                          {u} {status.satisfied ? "✓" : "✗"}
                        </span>
                      ))
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-1 text-right">
                    <button
                      onClick={() => remove(k)}
                      aria-label={`Remove constraint ${k + 1}`}
                      className="text-gray-400 hover:text-red-600"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
