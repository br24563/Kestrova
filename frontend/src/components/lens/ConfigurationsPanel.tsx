/**
 * Configurations (Code V's zoom table): the lens's configurations, the
 * parameters that differ between them with one value per configuration,
 * which configuration the analyses show, and a first-order comparison.
 *
 * The surface table always shows configuration 1, so editing a value of
 * configuration 1 here also edits the table.
 */
import { useState } from "react";
import { lensConfigurations } from "../../api";
import {
  LENGTH_UNIT_LABELS,
  SYSTEM_ZOOM_PARAMETERS,
  fmtLen,
  fromMeters,
  toMeters,
} from "../../types";
import type {
  LengthUnit,
  LensConfigurationSummary,
  LensData,
  LensSurface,
  ZoomRow,
} from "../../types";
import { SURFACE_PARAMETERS } from "./lensEdit";

const LENGTHS = new Set([
  "thickness",
  "radius",
  "radius_x",
  "semi_diameter",
  "focal_length",
  "decenter_x",
  "decenter_y",
  "decenter_z",
  "object_distance",
  "object_height",
  "entrance_pupil_diameter",
]);
const ANGLES = new Set(["tilt_x", "tilt_y", "tilt_z", "field_angle"]);
const BREAK_PARAMETERS = [
  "thickness",
  "decenter_x",
  "decenter_y",
  "decenter_z",
  "tilt_x",
  "tilt_y",
  "tilt_z",
];

const LABELS: Record<string, string> = {
  object_distance: "Object distance",
  object_height: "Object height",
  field_angle: "Field angle",
  entrance_pupil_diameter: "Entrance pupil diam.",
};

/** Parameters a zoom row on this surface (or the system) can vary. */
function parametersOf(surface: LensSurface | null): string[] {
  if (surface === null) return [...SYSTEM_ZOOM_PARAMETERS];
  if (surface.surface_type === "coordinate_break") return BREAK_PARAMETERS;
  return SURFACE_PARAMETERS[surface.surface_type];
}

/** Current value of a parameter on the lens (configuration 1). */
function currentValue(
  lens: LensData,
  surface: number | null,
  parameter: string,
): number | null {
  const source =
    surface === null
      ? (lens as unknown as Record<string, unknown>)
      : (lens.surfaces[surface] as unknown as Record<string, unknown>);
  const v = source[parameter];
  return typeof v === "number" ? v : surface === null ? null : 0;
}

/** The lens with configuration 1's value of a row written to the surface table. */
function withBaseValue(lens: LensData, row: ZoomRow): LensData {
  const v = row.values[0];
  if (row.surface === null) return { ...lens, [row.parameter]: v };
  return {
    ...lens,
    surfaces: lens.surfaces.map((s, i) =>
      i === row.surface ? { ...s, [row.parameter]: v } : s,
    ),
  };
}

export function ConfigurationsPanel({
  lens,
  displayUnit,
  active,
  busy,
  onChange,
  onActivate,
}: {
  lens: LensData;
  displayUnit: LengthUnit;
  active: number;
  busy: boolean;
  onChange: (lens: LensData) => void;
  onActivate: (k: number) => void;
}) {
  const [summary, setSummary] = useState<LensConfigurationSummary[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const unit = LENGTH_UNIT_LABELS[displayUnit];
  const names = lens.configuration_names ?? [];
  const zoom = lens.zoom ?? [];
  const n = Math.max(1, names.length);

  const show = (parameter: string, v: number | null): string => {
    if (v === null) return "Infinity";
    if (ANGLES.has(parameter))
      return String(Number(((v * 180) / Math.PI).toPrecision(8)));
    if (LENGTHS.has(parameter))
      return String(Number(fromMeters(v, displayUnit).toPrecision(8)));
    return String(Number(v.toPrecision(10)));
  };
  const parse = (
    parameter: string,
    text: string,
  ): number | null | undefined => {
    const t = text.trim();
    if (parameter === "object_distance" && /^inf/i.test(t)) return null;
    const v = Number(t);
    if (t === "" || !Number.isFinite(v)) return undefined;
    if (ANGLES.has(parameter)) return (v * Math.PI) / 180;
    if (LENGTHS.has(parameter)) return toMeters(v, displayUnit);
    return v;
  };
  const unitOf = (parameter: string) =>
    ANGLES.has(parameter) ? "°" : LENGTHS.has(parameter) ? unit : "";

  const commit = (next: LensData) => {
    setSummary(null);
    setError(null);
    onChange(next);
  };

  const setZoom = (rows: ZoomRow[], base: LensData = lens) =>
    commit({ ...base, zoom: rows });

  const addConfiguration = () => {
    const nextNames =
      names.length === 0 ? ["1", "2"] : [...names, String(names.length + 1)];
    const rows = zoom.map((r) => ({
      ...r,
      values: [...r.values, r.values[r.values.length - 1]],
    }));
    commit({ ...lens, configuration_names: nextNames, zoom: rows });
  };

  const removeConfiguration = (k: number) => {
    if (n <= 2) {
      commit({
        ...lens,
        configuration_names: [],
        zoom: [],
        configuration_weights: null,
      });
      onActivate(0);
      return;
    }
    const rows = zoom.map((r) => ({
      ...r,
      values: r.values.filter((_, i) => i !== k),
    }));
    let next: LensData = {
      ...lens,
      configuration_names: names.filter((_, i) => i !== k),
      zoom: rows,
      configuration_weights: null,
      constraints: (lens.constraints ?? [])
        .filter((c) => c.configuration !== k)
        .map((c) =>
          c.configuration != null && c.configuration > k
            ? { ...c, configuration: c.configuration - 1 }
            : c,
        ),
    };
    if (k === 0) for (const r of rows) next = withBaseValue(next, r);
    commit(next);
    if (active >= n - 1) onActivate(n - 2);
  };

  const addRow = () => {
    const used = new Set(zoom.map((r) => `${r.surface}:${r.parameter}`));
    const surface = 0;
    const param =
      parametersOf(lens.surfaces[surface]).find(
        (p) => !used.has(`${surface}:${p}`),
      ) ?? "thickness";
    const v = currentValue(lens, surface, param);
    setZoom([...zoom, { surface, parameter: param, values: Array(n).fill(v) }]);
  };

  const changeTarget = (k: number, surface: number | null) => {
    const params = parametersOf(
      surface === null ? null : lens.surfaces[surface],
    );
    const param = params[0];
    const v = currentValue(lens, surface, param);
    setZoom(
      zoom.map((r, i) =>
        i === k ? { surface, parameter: param, values: Array(n).fill(v) } : r,
      ),
    );
  };

  const changeParameter = (k: number, parameter: string) => {
    const row = zoom[k];
    const v = currentValue(lens, row.surface, parameter);
    setZoom(
      zoom.map((r, i) =>
        i === k ? { ...r, parameter, values: Array(n).fill(v) } : r,
      ),
    );
  };

  const setValue = (k: number, c: number, v: number | null) => {
    const row = {
      ...zoom[k],
      values: zoom[k].values.map((x, i) => (i === c ? v : x)),
    };
    const rows = zoom.map((r, i) => (i === k ? row : r));
    setZoom(rows, c === 0 ? withBaseValue(lens, row) : lens);
  };

  const compare = async () => {
    setError(null);
    try {
      setSummary((await lensConfigurations(lens)).configurations);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not compare them");
    }
  };

  return (
    <div className="mt-3" data-testid="configurations">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-xs font-semibold text-gray-700">Configurations</h4>
        <span className="text-[11px] text-gray-400">
          zoom positions, focus settings or alternate fields
        </span>
        <button
          onClick={addConfiguration}
          disabled={busy}
          className="px-2 py-0.5 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
        >
          Add configuration
        </button>
        {names.length > 1 && (
          <>
            <button
              onClick={addRow}
              disabled={busy}
              className="px-2 py-0.5 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
            >
              Add zoomed parameter
            </button>
            <button
              onClick={compare}
              disabled={busy}
              className="px-2 py-0.5 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
            >
              Compare
            </button>
          </>
        )}
      </div>
      {names.length > 1 && (
        <div className="overflow-x-auto mt-1">
          <table className="text-xs border border-gray-200 rounded">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="px-1 py-0.5 text-left font-medium">Surface</th>
                <th className="px-1 py-0.5 text-left font-medium">Parameter</th>
                {names.map((name, c) => (
                  <th key={c} className="px-1 py-0.5 font-medium">
                    <div className="flex items-center gap-1">
                      <input
                        type="radio"
                        name="active-configuration"
                        aria-label={`Show configuration ${c + 1}`}
                        title="Show this configuration in the analyses"
                        checked={active === c}
                        onChange={() => onActivate(c)}
                      />
                      <input
                        key={name}
                        aria-label={`Configuration ${c + 1} name`}
                        defaultValue={name}
                        onBlur={(e) =>
                          e.target.value !== name &&
                          commit({
                            ...lens,
                            configuration_names: names.map((x, i) =>
                              i === c ? e.target.value : x,
                            ),
                          })
                        }
                        className="w-16 border border-gray-200 rounded px-1"
                      />
                      <button
                        aria-label={`Remove configuration ${c + 1}`}
                        title="Remove this configuration"
                        onClick={() => removeConfiguration(c)}
                        className="text-gray-400 hover:text-red-500"
                      >
                        ×
                      </button>
                    </div>
                  </th>
                ))}
                <th
                  className="px-1 py-0.5 font-medium"
                  title="Vary each configuration's value when optimizing"
                >
                  Var
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {zoom.map((row, k) => (
                <tr key={k} className="border-t border-gray-100">
                  <td className="px-1">
                    <select
                      aria-label={`Zoom row ${k + 1} surface`}
                      value={
                        row.surface === null ? "system" : String(row.surface)
                      }
                      onChange={(e) =>
                        changeTarget(
                          k,
                          e.target.value === "system"
                            ? null
                            : parseInt(e.target.value, 10),
                        )
                      }
                      className="bg-transparent text-xs py-0.5"
                    >
                      <option value="system">System</option>
                      {lens.surfaces.map((s, i) => (
                        <option key={i} value={i}>
                          {s.is_stop ? "STO" : i} {s.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-1">
                    <select
                      aria-label={`Zoom row ${k + 1} parameter`}
                      value={row.parameter}
                      onChange={(e) => changeParameter(k, e.target.value)}
                      className="bg-transparent text-xs py-0.5"
                    >
                      {parametersOf(
                        row.surface === null
                          ? null
                          : lens.surfaces[row.surface],
                      ).map((p) => (
                        <option key={p} value={p}>
                          {LABELS[p] ?? p}
                        </option>
                      ))}
                    </select>
                  </td>
                  {row.values.map((v, c) => {
                    const text = show(row.parameter, v);
                    return (
                      <td key={c} className="px-1">
                        <input
                          key={`${row.surface}-${row.parameter}-${text}`}
                          aria-label={`Zoom row ${k + 1} configuration ${c + 1}`}
                          defaultValue={text}
                          onBlur={(e) => {
                            const typed = e.target.value;
                            if (typed === text) return;
                            const parsed = parse(row.parameter, typed);
                            if (parsed === undefined) {
                              e.target.value = text;
                              setError(`'${typed}' is not a number`);
                              return;
                            }
                            setValue(k, c, parsed);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter")
                              (e.target as HTMLInputElement).blur();
                          }}
                          className="w-20 border border-gray-200 rounded px-1 text-right font-mono"
                        />
                        <span className="text-gray-400 ml-0.5">
                          {unitOf(row.parameter)}
                        </span>
                      </td>
                    );
                  })}
                  <td className="px-1 text-center">
                    {row.surface !== null && (
                      <input
                        type="checkbox"
                        aria-label={`Zoom row ${k + 1} variable`}
                        checked={!!row.variable}
                        onChange={(e) =>
                          setZoom(
                            zoom.map((r, i) =>
                              i === k
                                ? { ...r, variable: e.target.checked }
                                : r,
                            ),
                          )
                        }
                      />
                    )}
                  </td>
                  <td className="px-1">
                    <button
                      aria-label={`Remove zoom row ${k + 1}`}
                      onClick={() => setZoom(zoom.filter((_, i) => i !== k))}
                      className="text-gray-400 hover:text-red-500"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
              {zoom.length === 0 && (
                <tr>
                  <td
                    colSpan={names.length + 4}
                    className="px-1 py-1 text-[11px] text-gray-400"
                  >
                    Add a zoomed parameter (a spacing, a field angle, an object
                    distance…) to give it a value in each configuration.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {error && (
        <p className="text-xs text-red-500 mt-1" role="alert">
          {error}
        </p>
      )}
      {summary && (
        <table
          className="text-xs mt-1 border border-gray-200 rounded"
          data-testid="configuration-summary"
        >
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-1 py-0.5 text-left font-medium">
                Configuration
              </th>
              <th className="px-1 py-0.5 text-right font-medium">
                EFL ({unit})
              </th>
              <th className="px-1 py-0.5 text-right font-medium">
                BFL ({unit})
              </th>
              <th className="px-1 py-0.5 text-right font-medium">F/#</th>
              <th className="px-1 py-0.5 text-right font-medium">
                Image height ({unit})
              </th>
            </tr>
          </thead>
          <tbody>
            {summary.map((s) => (
              <tr key={s.configuration} className="border-t border-gray-100">
                <td className="px-1">{s.name}</td>
                <td className="px-1 text-right font-mono">
                  {fmtLen(s.first_order.efl, displayUnit, 4)}
                </td>
                <td className="px-1 text-right font-mono">
                  {fmtLen(s.first_order.bfl, displayUnit, 4)}
                </td>
                <td className="px-1 text-right font-mono">
                  {s.first_order.f_number === null
                    ? "—"
                    : s.first_order.f_number.toFixed(3)}
                </td>
                <td className="px-1 text-right font-mono">
                  {fmtLen(s.first_order.image_height, displayUnit, 4)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
