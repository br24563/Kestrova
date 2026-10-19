/**
 * Lens Data Editor.
 *
 * A Code V / Zemax style surface table: one row per surface with radius,
 * thickness to the next surface, material after it, semi-diameter, conic
 * and the aperture stop. Each numeric cell carries a flag button that makes
 * the parameter fixed, a variable for the optimizer, a paraxial solve or a
 * pickup from another surface. Resolve applies solves and pickups on the
 * backend and hands the resulting component system to the rest of the app;
 * Optimize runs damped least squares over the variables.
 */

import { useState } from "react";
import type {
  LensData,
  LensSurface,
  LengthUnit,
  LensFirstOrder,
  LensResolveResult,
  OpticalSystem,
  SolveKind,
  SurfaceType,
} from "../../types";
import {
  fmtLen,
  fmtNum,
  fromMeters,
  toMeters,
  LENGTH_UNIT_LABELS,
  RADIUS_SOLVES,
  THICKNESS_SOLVES,
} from "../../types";
import { lensFromSystem, optimizeLens, resolveLens } from "../../api";
import {
  countVariables,
  deleteSurface,
  getModifier,
  hasParameter,
  insertSurface,
  setModifier,
  setStop,
  SURFACE_PARAMETERS,
  type Modifier,
} from "./lensEdit";

interface LensDataEditorProps {
  lens: LensData | null;
  system: OpticalSystem;
  displayUnit: LengthUnit;
  /** The lens was edited in the table (not yet resolved). */
  dirty: boolean;
  onChange: (lens: LensData) => void;
  /** A resolved or optimized lens and its component system. */
  onResolved: (result: LensResolveResult) => void;
  /** A lens converted from the component system (no analysis change). */
  onImported: (lens: LensData) => void;
}

const LENGTH_PARAMS = new Set([
  "radius",
  "thickness",
  "semi_diameter",
  "focal_length",
]);

const PARAM_LABELS: Record<string, string> = {
  radius: "Radius",
  thickness: "Thickness",
  conic: "Conic",
  semi_diameter: "Semi-diameter",
  focal_length: "Focal length",
};

const SOLVE_LABELS: Record<SolveKind, string> = {
  marginal_height: "Marginal ray height",
  chief_height: "Chief ray height",
  marginal_angle: "Marginal ray angle",
  chief_angle: "Chief ray angle",
  f_number: "F-number",
};

const EDITABLE_TYPES: SurfaceType[] = ["standard", "even_asphere", "paraxial"];

/** Parse a cell; "" and "inf"/"infinity" give null (flat radius, automatic aperture, ...). */
function parseNumber(text: string): number | null | undefined {
  const t = text.trim().toLowerCase();
  if (t === "" || t === "inf" || t === "infinity" || t === "∞" || t === "auto")
    return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : undefined;
}

/** A text input that commits on blur or Enter and resets when its value changes. */
function Cell({
  value,
  onCommit,
  className = "",
  title,
  align = "right",
  ariaLabel,
}: {
  value: string;
  onCommit: (text: string) => void;
  className?: string;
  title?: string;
  align?: "left" | "right";
  ariaLabel: string;
}) {
  return (
    <input
      key={value}
      defaultValue={value}
      title={title}
      aria-label={ariaLabel}
      onBlur={(e) => {
        if (e.target.value !== value) onCommit(e.target.value);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          (e.target as HTMLInputElement).value = value;
          (e.target as HTMLInputElement).blur();
        }
      }}
      className={`w-full min-w-0 bg-transparent px-1 py-0.5 text-xs font-mono focus:bg-white focus:outline focus:outline-1 focus:outline-optical-500 ${
        align === "right" ? "text-right" : "text-left"
      } ${className}`}
    />
  );
}

const BADGE: Record<
  Modifier["kind"],
  { text: string; cls: string; title: string }
> = {
  fixed: {
    text: "",
    cls: "text-gray-300 hover:text-gray-500",
    title: "Fixed — click to make variable, solve or pickup",
  },
  variable: {
    text: "V",
    cls: "bg-green-100 text-green-700",
    title: "Variable",
  },
  solve: { text: "S", cls: "bg-blue-100 text-blue-700", title: "Solve" },
  pickup: { text: "P", cls: "bg-purple-100 text-purple-700", title: "Pickup" },
};

export function LensDataEditor({
  lens,
  system,
  displayUnit,
  dirty,
  onChange,
  onResolved,
  onImported,
}: LensDataEditorProps) {
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [flagCell, setFlagCell] = useState<{
    row: number;
    param: string;
  } | null>(null);
  const [busy, setBusy] = useState<"resolve" | "optimize" | "import" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [firstOrder, setFirstOrder] = useState<LensFirstOrder | null>(null);
  const [rms, setRms] = useState<{
    before: number;
    after: number;
    evaluations: number;
  } | null>(null);
  const [maxEvaluations, setMaxEvaluations] = useState("300");

  const unit = LENGTH_UNIT_LABELS[displayUnit];

  const importFromSystem = async () => {
    setBusy("import");
    setError(null);
    try {
      const { lens: imported } = await lensFromSystem(system);
      onImported(imported);
      setFirstOrder(null);
      setRms(null);
      setFlagCell(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to convert the system",
      );
    } finally {
      setBusy(null);
    }
  };

  if (!lens) {
    return (
      <div className="p-4 text-sm text-gray-500">
        No lens data.{" "}
        <button
          onClick={importFromSystem}
          className="text-optical-600 hover:underline"
          disabled={busy !== null}
        >
          Convert the current system
        </button>
        {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      </div>
    );
  }

  const update = (next: LensData) => {
    setError(null);
    onChange(next);
  };

  const updateSurface = (row: number, patch: Partial<LensSurface>) => {
    update({
      ...lens,
      surfaces: lens.surfaces.map((s, k) =>
        k === row ? { ...s, ...patch } : s,
      ),
    });
  };

  const commitLength = (
    row: number,
    param: "radius" | "thickness" | "focal_length",
    text: string,
  ) => {
    const v = parseNumber(text);
    if (v === undefined) return setError(`'${text}' is not a number`);
    if (v === null && param !== "radius")
      return setError(`${PARAM_LABELS[param]} needs a value`);
    if (param === "focal_length" && v === 0)
      return setError("A paraxial surface needs a non-zero focal length");
    updateSurface(row, { [param]: v === null ? 0 : toMeters(v, displayUnit) });
  };

  const commitSemi = (row: number, text: string) => {
    const v = parseNumber(text);
    if (v === undefined) return setError(`'${text}' is not a number`);
    if (v !== null && v <= 0)
      return setError("A semi-diameter must be positive");
    updateSurface(row, {
      semi_diameter: v === null ? null : toMeters(v, displayUnit),
      semi_diameter_auto: false,
    });
  };

  const commitConic = (row: number, text: string) => {
    const v = parseNumber(text);
    if (v === undefined || v === null)
      return setError(`'${text}' is not a number`);
    updateSurface(row, { conic: v });
  };

  const changeType = (row: number, type: SurfaceType) => {
    const s = lens.surfaces[row];
    let next: LensSurface = { ...s, surface_type: type };
    if (type === "paraxial" && !next.focal_length) next.focal_length = 0.1;
    // drop flags on parameters the new type does not have
    for (const p of new Set([
      ...s.variables,
      ...Object.keys(s.solves),
      ...Object.keys(s.pickups),
    ])) {
      if (!SURFACE_PARAMETERS[type].includes(p))
        next = setModifier(next, p, { kind: "fixed" });
    }
    update({
      ...lens,
      surfaces: lens.surfaces.map((x, k) => (k === row ? next : x)),
    });
  };

  const insertRow = (where: "before" | "after") => {
    const at =
      selectedRow === null
        ? lens.surfaces.length - 1
        : selectedRow + (where === "after" ? 1 : 0);
    const index = Math.max(0, Math.min(at, lens.surfaces.length));
    update(insertSurface(lens, index));
    setSelectedRow(index);
    setFlagCell(null);
  };

  const deleteRow = () => {
    if (selectedRow === null) return;
    try {
      update(deleteSurface(lens, selectedRow));
      setSelectedRow(Math.min(selectedRow, lens.surfaces.length - 2));
      setFlagCell(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const resolve = async () => {
    setBusy("resolve");
    setError(null);
    try {
      const result = await resolveLens(lens);
      setFirstOrder(result.first_order);
      onResolved(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resolve failed");
    } finally {
      setBusy(null);
    }
  };

  const optimize = async () => {
    setBusy("optimize");
    setError(null);
    try {
      const n = parseInt(maxEvaluations, 10);
      const result = await optimizeLens(
        lens,
        {},
        Number.isFinite(n) && n > 0 ? n : 300,
      );
      setRms({
        before: result.rms_spot_before,
        after: result.rms_spot_after,
        evaluations: result.evaluations,
      });
      setFirstOrder(result.first_order);
      onResolved(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Optimization failed");
    } finally {
      setBusy(null);
    }
  };

  const nVariables = countVariables(lens);

  const flagButton = (row: number, param: string) => {
    const s = lens.surfaces[row];
    if (!hasParameter(s, param)) return null;
    const m = getModifier(s, param);
    const active = flagCell?.row === row && flagCell.param === param;
    const b = BADGE[m.kind];
    return (
      <button
        onClick={() => setFlagCell(active ? null : { row, param })}
        title={b.title}
        aria-label={`${PARAM_LABELS[param]} flag, surface ${row}`}
        className={`shrink-0 w-4 h-4 leading-4 text-[10px] font-bold rounded text-center ${b.cls} ${
          active ? "ring-1 ring-optical-500" : ""
        }`}
      >
        {b.text || "·"}
      </button>
    );
  };

  const cellClass = (s: LensSurface, param: string) => {
    const m = getModifier(s, param).kind;
    return m === "solve" || m === "pickup" ? "text-blue-700 italic" : "";
  };

  const lengthText = (v: number | null | undefined, flatIsInfinity = false) => {
    if (v === null || v === undefined) return "";
    if (flatIsInfinity && v === 0) return "Infinity";
    return String(Number(fromMeters(v, displayUnit).toPrecision(8)));
  };

  // Lens-level settings
  const commitObjectDistance = (text: string) => {
    const v = parseNumber(text);
    if (v === undefined) return setError(`'${text}' is not a number`);
    update({
      ...lens,
      object_distance: v === null ? null : toMeters(v, displayUnit),
    });
  };
  const commitField = (text: string) => {
    const v = parseNumber(text);
    if (v === undefined || v === null)
      return setError(`'${text}' is not a number`);
    update(
      lens.object_distance === null
        ? { ...lens, field_angle: (v * Math.PI) / 180 }
        : { ...lens, object_height: toMeters(v, displayUnit) },
    );
  };
  const commitEpd = (text: string) => {
    const v = parseNumber(text);
    if (v === undefined) return setError(`'${text}' is not a number`);
    if (v !== null && v <= 0)
      return setError("The entrance pupil diameter must be positive");
    update({
      ...lens,
      entrance_pupil_diameter: v === null ? null : toMeters(v, displayUnit),
    });
  };

  return (
    <div className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <h3 className="text-sm font-semibold text-gray-700">
          Lens Data{lens.name ? ` — ${lens.name}` : ""}
          {dirty && (
            <span className="ml-2 text-xs font-normal text-amber-600">
              edited, not resolved
            </span>
          )}
        </h3>
        <div className="flex flex-wrap items-center gap-1">
          <button
            onClick={() => insertRow("before")}
            className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
          >
            Insert before
          </button>
          <button
            onClick={() => insertRow("after")}
            className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
          >
            Insert after
          </button>
          <button
            onClick={deleteRow}
            disabled={selectedRow === null}
            className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
          >
            Delete
          </button>
          <button
            onClick={importFromSystem}
            disabled={busy !== null}
            title="Replace the table with the prescription of the component system (after editing components)"
            className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
          >
            {busy === "import" ? "Converting..." : "From components"}
          </button>
          <button
            onClick={resolve}
            disabled={busy !== null}
            className="px-3 py-1 text-xs bg-optical-600 text-white rounded hover:bg-optical-700 disabled:opacity-50"
          >
            {busy === "resolve" ? "Resolving..." : "Resolve"}
          </button>
        </div>
      </div>

      {/* Object and aperture */}
      <div className="flex flex-wrap gap-3 mb-2 text-xs text-gray-600">
        <label className="flex items-center gap-1">
          Object distance ({unit})
          <span className="w-24 border border-gray-200 rounded">
            <Cell
              ariaLabel="Object distance"
              value={
                lens.object_distance === null
                  ? "Infinity"
                  : lengthText(lens.object_distance)
              }
              onCommit={commitObjectDistance}
            />
          </span>
        </label>
        <label className="flex items-center gap-1">
          {lens.object_distance === null
            ? "Field angle (deg)"
            : `Object height (${unit})`}
          <span className="w-20 border border-gray-200 rounded">
            <Cell
              ariaLabel="Field"
              value={
                lens.object_distance === null
                  ? String(
                      Number(
                        ((lens.field_angle * 180) / Math.PI).toPrecision(8),
                      ),
                    )
                  : lengthText(lens.object_height)
              }
              onCommit={commitField}
            />
          </span>
        </label>
        <label className="flex items-center gap-1">
          Entrance pupil diameter ({unit})
          <span className="w-20 border border-gray-200 rounded">
            <Cell
              ariaLabel="Entrance pupil diameter"
              value={
                lens.entrance_pupil_diameter === null
                  ? ""
                  : lengthText(lens.entrance_pupil_diameter)
              }
              title="Blank: the stop's semi-diameter sets the aperture"
              onCommit={commitEpd}
            />
          </span>
        </label>
      </div>

      <div className="overflow-x-auto border border-gray-200 rounded">
        <table
          className="w-full min-w-[760px] text-xs border-collapse"
          aria-label="Lens data"
        >
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-1 py-1 text-left font-medium w-8">Surf</th>
              <th className="px-1 py-1 text-left font-medium">Label</th>
              <th className="px-1 py-1 text-left font-medium">Type</th>
              <th className="px-1 py-1 text-right font-medium">
                Radius ({unit})
              </th>
              <th className="px-1 py-1 text-right font-medium">
                Thickness ({unit})
              </th>
              <th className="px-1 py-1 text-left font-medium">Material</th>
              <th className="px-1 py-1 text-right font-medium">
                Semi-diam. ({unit})
              </th>
              <th className="px-1 py-1 text-right font-medium">Conic</th>
              <th className="px-1 py-1 text-center font-medium">Stop</th>
            </tr>
          </thead>
          <tbody>
            {lens.surfaces.map((s, row) => {
              const editable = EDITABLE_TYPES.includes(s.surface_type);
              const paraxial = s.surface_type === "paraxial";
              return (
                <tr
                  key={row}
                  className={`border-t border-gray-100 ${selectedRow === row ? "bg-optical-50" : "hover:bg-gray-50"}`}
                >
                  <td className="px-1">
                    <button
                      onClick={() =>
                        setSelectedRow(selectedRow === row ? null : row)
                      }
                      className="w-full text-left font-mono text-gray-500 hover:text-optical-700"
                      title="Select row"
                    >
                      {s.is_stop ? "STO" : row}
                    </button>
                  </td>
                  <td className="px-1 w-24">
                    <Cell
                      ariaLabel={`Label, surface ${row}`}
                      align="left"
                      value={s.label}
                      onCommit={(t) => updateSurface(row, { label: t.trim() })}
                    />
                  </td>
                  <td className="px-1">
                    {editable ? (
                      <select
                        aria-label={`Type, surface ${row}`}
                        value={s.surface_type}
                        onChange={(e) =>
                          changeType(row, e.target.value as SurfaceType)
                        }
                        className="bg-transparent text-xs py-0.5"
                      >
                        <option value="standard">Standard</option>
                        <option value="even_asphere">Even asphere</option>
                        <option value="paraxial">Paraxial</option>
                      </select>
                    ) : (
                      <span
                        className="text-gray-500"
                        title={
                          s.component
                            ? String(s.component.type ?? "")
                            : undefined
                        }
                      >
                        {s.surface_type === "coordinate_break"
                          ? "Coord. break"
                          : `Component${s.component?.type ? ` (${String(s.component.type)})` : ""}`}
                      </span>
                    )}
                  </td>
                  <td className="px-1 w-28">
                    {paraxial ? (
                      <div className="flex items-center gap-0.5">
                        <span className="text-gray-400">f</span>
                        <Cell
                          ariaLabel={`Focal length, surface ${row}`}
                          className={cellClass(s, "focal_length")}
                          value={lengthText(s.focal_length)}
                          onCommit={(t) => commitLength(row, "focal_length", t)}
                        />
                        {flagButton(row, "focal_length")}
                      </div>
                    ) : hasParameter(s, "radius") ? (
                      <div className="flex items-center gap-0.5">
                        <Cell
                          ariaLabel={`Radius, surface ${row}`}
                          className={cellClass(s, "radius")}
                          value={lengthText(s.radius, true)}
                          onCommit={(t) => commitLength(row, "radius", t)}
                        />
                        {flagButton(row, "radius")}
                      </div>
                    ) : (
                      <span className="block text-right text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-1 w-28">
                    <div className="flex items-center gap-0.5">
                      <Cell
                        ariaLabel={`Thickness, surface ${row}`}
                        className={cellClass(s, "thickness")}
                        value={lengthText(s.thickness)}
                        onCommit={(t) => commitLength(row, "thickness", t)}
                      />
                      {flagButton(row, "thickness")}
                    </div>
                  </td>
                  <td className="px-1 w-24">
                    {editable && !paraxial ? (
                      <Cell
                        ariaLabel={`Material, surface ${row}`}
                        align="left"
                        value={s.material ?? ""}
                        title='Medium after the surface: a glass name, "MIRROR", or blank for air'
                        onCommit={(t) => {
                          const m = t.trim();
                          updateSurface(row, {
                            material:
                              m === "" || m.toLowerCase() === "air"
                                ? null
                                : m.toLowerCase() === "mirror"
                                  ? "MIRROR"
                                  : m,
                          });
                        }}
                      />
                    ) : (
                      <span className="text-gray-400 px-1">
                        {paraxial ? (s.ideal_lens_glass ?? "") : ""}
                      </span>
                    )}
                  </td>
                  <td className="px-1 w-28">
                    {hasParameter(s, "semi_diameter") ? (
                      <div className="flex items-center gap-0.5">
                        <Cell
                          ariaLabel={`Semi-diameter, surface ${row}`}
                          className={
                            s.semi_diameter_auto
                              ? "text-gray-400"
                              : cellClass(s, "semi_diameter")
                          }
                          value={
                            s.semi_diameter === null || s.semi_diameter_auto
                              ? ""
                              : lengthText(s.semi_diameter)
                          }
                          title={
                            s.semi_diameter_auto && s.semi_diameter !== null
                              ? `Automatic: ${fmtLen(s.semi_diameter, displayUnit, 4)} ${unit}. Type a value to fix it.`
                              : "Blank: automatic from real rays"
                          }
                          onCommit={(t) => commitSemi(row, t)}
                        />
                        {(s.semi_diameter === null || s.semi_diameter_auto) && (
                          <span
                            className="text-[10px] text-gray-400 shrink-0"
                            title="Automatic semi-diameter"
                          >
                            {s.semi_diameter_auto && s.semi_diameter !== null
                              ? `${fmtLen(s.semi_diameter, displayUnit, 3)} auto`
                              : "auto"}
                          </span>
                        )}
                        {flagButton(row, "semi_diameter")}
                      </div>
                    ) : (
                      <span className="block text-right text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-1 w-20">
                    {hasParameter(s, "conic") ? (
                      <div className="flex items-center gap-0.5">
                        <Cell
                          ariaLabel={`Conic, surface ${row}`}
                          className={cellClass(s, "conic")}
                          value={String(s.conic)}
                          onCommit={(t) => commitConic(row, t)}
                        />
                        {flagButton(row, "conic")}
                      </div>
                    ) : (
                      <span className="block text-right text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-1 text-center">
                    <input
                      type="radio"
                      name="lens-stop"
                      aria-label={`Stop, surface ${row}`}
                      checked={s.is_stop}
                      onChange={() => update(setStop(lens, row))}
                    />
                  </td>
                </tr>
              );
            })}
            <tr className="border-t border-gray-200 bg-gray-50 text-gray-500">
              <td className="px-1 font-mono">IMG</td>
              <td colSpan={8} className="px-1 py-0.5">
                Image plane at{" "}
                {fmtLen(system.image_plane.position, displayUnit, 3)} {unit}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {flagCell &&
        flagCell.row < lens.surfaces.length &&
        hasParameter(lens.surfaces[flagCell.row], flagCell.param) && (
          <ModifierEditor
            lens={lens}
            row={flagCell.row}
            param={flagCell.param}
            displayUnit={displayUnit}
            onChange={(m) =>
              update({
                ...lens,
                surfaces: lens.surfaces.map((s, k) =>
                  k === flagCell.row ? setModifier(s, flagCell.param, m) : s,
                ),
              })
            }
            onClose={() => setFlagCell(null)}
          />
        )}

      {error && (
        <p className="text-xs text-red-500 mt-2" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 mt-3">
        <button
          onClick={optimize}
          disabled={busy !== null || nVariables === 0}
          title={
            nVariables === 0
              ? "Flag at least one parameter as a variable (V)"
              : undefined
          }
          className="px-3 py-1 text-xs bg-optical-600 text-white rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {busy === "optimize"
            ? "Optimizing..."
            : `Optimize (${nVariables} variable${nVariables === 1 ? "" : "s"})`}
        </button>
        <label className="flex items-center gap-1 text-xs text-gray-600">
          Max evaluations
          <input
            value={maxEvaluations}
            onChange={(e) => setMaxEvaluations(e.target.value)}
            className="w-16 px-1 py-0.5 border border-gray-200 rounded text-right"
          />
        </label>
        {rms && (
          <span
            className="text-xs text-gray-700"
            data-testid="lens-rms"
            title="Optimizer merit: RMS transverse ray error over fields 0, 0.7 and 1 and all wavelengths"
          >
            RMS spot: {fmtLen(rms.before, "um", 3)} →{" "}
            <strong>{fmtLen(rms.after, "um", 3)}</strong> µm
            <span className="text-gray-400">
              {" "}
              ({rms.evaluations} evaluations)
            </span>
          </span>
        )}
      </div>

      {firstOrder && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-gray-600">
          <span>
            EFL {fmtLen(firstOrder.efl, displayUnit, 3)} {unit}
          </span>
          <span>
            BFL {fmtLen(firstOrder.bfl, displayUnit, 3)} {unit}
          </span>
          <span>F/# {fmtNum(firstOrder.f_number, 2)}</span>
          <span>Working F/# {fmtNum(firstOrder.working_f_number, 2)}</span>
          <span>
            EPD {fmtLen(firstOrder.entrance_pupil_diameter, displayUnit, 3)}{" "}
            {unit}
          </span>
          <span>
            Image z {fmtLen(firstOrder.image_z, displayUnit, 3)} {unit}
          </span>
        </div>
      )}
    </div>
  );
}

/** Edits whether one parameter is fixed, variable, solved or picked up. */
function ModifierEditor({
  lens,
  row,
  param,
  displayUnit,
  onChange,
  onClose,
}: {
  lens: LensData;
  row: number;
  param: string;
  displayUnit: LengthUnit;
  onChange: (m: Modifier) => void;
  onClose: () => void;
}) {
  const surface = lens.surfaces[row];
  const m = getModifier(surface, param);
  const unit = LENGTH_UNIT_LABELS[displayUnit];
  const isLength = LENGTH_PARAMS.has(param);
  const solveKinds: SolveKind[] =
    param === "thickness"
      ? THICKNESS_SOLVES
      : param === "radius"
        ? RADIUS_SOLVES
        : [];
  const others = lens.surfaces
    .map((s, k) => ({ s, k }))
    .filter(
      ({ s, k }) => k !== row && SURFACE_PARAMETERS[s.surface_type].length > 0,
    );

  const defaultSolve = (kind: SolveKind) => ({
    kind,
    target: kind === "f_number" ? 4 : 0,
  });
  const defaultPickup = () => {
    const src =
      others.find(({ s }) =>
        SURFACE_PARAMETERS[s.surface_type].includes(param),
      ) ?? others[0];
    const srcParams = src ? SURFACE_PARAMETERS[src.s.surface_type] : [];
    return {
      source: src?.k ?? 0,
      parameter: srcParams.includes(param) ? null : (srcParams[0] ?? null),
      scale: 1,
      offset: 0,
    };
  };

  const solveTargetIsLength = (kind: SolveKind) =>
    kind === "marginal_height" || kind === "chief_height";
  const num = (text: string, fallback: number) => {
    const v = Number(text);
    return Number.isFinite(v) ? v : fallback;
  };

  return (
    <div
      className="mt-2 p-3 border border-optical-200 bg-optical-50/40 rounded text-xs"
      role="dialog"
      aria-label="Parameter flag"
    >
      <div className="flex justify-between items-center mb-2">
        <span className="font-semibold text-gray-700">
          Surface {row}
          {surface.label ? ` (${surface.label})` : ""} —{" "}
          {PARAM_LABELS[param] ?? param}
        </span>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600"
          aria-label="Close"
        >
          ✕
        </button>
      </div>
      <div className="flex flex-wrap gap-3 mb-2">
        {(["fixed", "variable", "solve", "pickup"] as const).map((kind) => {
          const disabled =
            (kind === "solve" && solveKinds.length === 0) ||
            (kind === "pickup" && others.length === 0);
          return (
            <label
              key={kind}
              className={`flex items-center gap-1 ${disabled ? "opacity-40" : ""}`}
            >
              <input
                type="radio"
                name="lens-modifier"
                aria-label={
                  kind === "fixed"
                    ? "Fixed"
                    : kind === "variable"
                      ? "Variable"
                      : kind === "solve"
                        ? "Solve"
                        : "Pickup"
                }
                checked={m.kind === kind}
                disabled={disabled}
                onChange={() =>
                  onChange(
                    kind === "solve"
                      ? { kind, solve: defaultSolve(solveKinds[0]) }
                      : kind === "pickup"
                        ? { kind, pickup: defaultPickup() }
                        : { kind },
                  )
                }
              />
              {kind === "fixed"
                ? "Fixed"
                : kind === "variable"
                  ? "Variable"
                  : kind === "solve"
                    ? "Solve"
                    : "Pickup"}
            </label>
          );
        })}
      </div>

      {m.kind === "solve" && (
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Solve kind"
            value={m.solve.kind}
            onChange={(e) =>
              onChange({
                kind: "solve",
                solve: defaultSolve(e.target.value as SolveKind),
              })
            }
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            {solveKinds.map((k) => (
              <option key={k} value={k}>
                {SOLVE_LABELS[k]}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1">
            {m.solve.kind === "f_number"
              ? "F-number"
              : solveTargetIsLength(m.solve.kind)
                ? `Height at next surface (${unit})`
                : "Slope after surface"}
            <input
              key={`${m.solve.kind}-${m.solve.target}`}
              aria-label="Solve target"
              defaultValue={String(
                solveTargetIsLength(m.solve.kind)
                  ? fromMeters(m.solve.target, displayUnit)
                  : m.solve.target,
              )}
              onBlur={(e) => {
                const v = num(e.target.value, NaN);
                if (!Number.isFinite(v)) return;
                const target = solveTargetIsLength(m.solve.kind)
                  ? toMeters(v, displayUnit)
                  : v;
                if (target !== m.solve.target)
                  onChange({ kind: "solve", solve: { ...m.solve, target } });
              }}
              onKeyDown={(e) =>
                e.key === "Enter" && (e.target as HTMLInputElement).blur()
              }
              className="w-20 border border-gray-200 rounded px-1 py-0.5 text-right"
            />
          </label>
          {m.solve.kind === "marginal_height" &&
            m.solve.target === 0 &&
            param === "thickness" && (
              <span className="text-gray-500">
                (paraxial image when on the last surface)
              </span>
            )}
        </div>
      )}

      {m.kind === "pickup" && (
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1">
            From surface
            <select
              aria-label="Pickup source"
              value={m.pickup.source}
              onChange={(e) => {
                const source = parseInt(e.target.value, 10);
                const params =
                  SURFACE_PARAMETERS[lens.surfaces[source].surface_type];
                onChange({
                  kind: "pickup",
                  pickup: {
                    ...m.pickup,
                    source,
                    parameter: params.includes(param)
                      ? null
                      : (params[0] ?? null),
                  },
                });
              }}
              className="border border-gray-200 rounded px-1 py-0.5"
            >
              {others.map(({ s, k }) => (
                <option key={k} value={k}>
                  {k}
                  {s.label ? ` (${s.label})` : ""}
                </option>
              ))}
            </select>
          </label>
          <select
            aria-label="Pickup parameter"
            value={m.pickup.parameter ?? param}
            onChange={(e) =>
              onChange({
                kind: "pickup",
                pickup: {
                  ...m.pickup,
                  parameter: e.target.value === param ? null : e.target.value,
                },
              })
            }
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            {SURFACE_PARAMETERS[
              lens.surfaces[m.pickup.source]?.surface_type ?? "standard"
            ].map((p) => (
              <option key={p} value={p}>
                {PARAM_LABELS[p] ?? p}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1">
            × scale
            <input
              key={`scale-${m.pickup.scale}`}
              aria-label="Pickup scale"
              defaultValue={String(m.pickup.scale)}
              onBlur={(e) => {
                const scale = num(e.target.value, m.pickup.scale);
                if (scale !== m.pickup.scale)
                  onChange({ kind: "pickup", pickup: { ...m.pickup, scale } });
              }}
              className="w-14 border border-gray-200 rounded px-1 py-0.5 text-right"
            />
          </label>
          <label className="flex items-center gap-1">
            + offset{isLength ? ` (${unit})` : ""}
            <input
              key={`offset-${m.pickup.offset}`}
              aria-label="Pickup offset"
              defaultValue={String(
                isLength
                  ? fromMeters(m.pickup.offset, displayUnit)
                  : m.pickup.offset,
              )}
              onBlur={(e) => {
                const v = num(e.target.value, NaN);
                if (!Number.isFinite(v)) return;
                const offset = isLength ? toMeters(v, displayUnit) : v;
                if (offset !== m.pickup.offset)
                  onChange({ kind: "pickup", pickup: { ...m.pickup, offset } });
              }}
              className="w-16 border border-gray-200 rounded px-1 py-0.5 text-right"
            />
          </label>
        </div>
      )}

      {m.kind === "variable" && (
        <p className="text-gray-500">
          The optimizer may change this parameter.
        </p>
      )}
    </div>
  );
}
