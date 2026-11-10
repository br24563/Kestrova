/**
 * Surface details: the terms and clear aperture of the selected row that
 * do not fit the table (aspheric, Q, Zernike, XY polynomial and phase
 * coefficients, normalisation radius, toroid x radius, diffraction order,
 * obscuration and rectangular / elliptical apertures).
 *
 * Values are shown in lens units: a coefficient of r^k as unit^(1-k), Q,
 * Zernike and XY terms as lengths, phase terms of r^k in rad / unit^k.
 */
import { LENGTH_UNIT_FACTORS, LENGTH_UNIT_LABELS } from "../../types";
import type { CoatingSpec, LengthUnit, LensSurface } from "../../types";

/** MgF2 near 550 nm, for the quarter-wave preset (edit the thickness for others). */
const MGF2_INDEX = 1.38;

function quarterWave(wavelengthNm: number): CoatingSpec {
  return {
    name: `QW MgF2 @ ${wavelengthNm} nm`,
    layers: [
      { material: "MgF2", thickness: (wavelengthNm * 1e-9) / (4 * MGF2_INDEX) },
    ],
  };
}

type Patch = Partial<LensSurface>;

const XY_MAX_ORDER = 10;

function show(v: number): string {
  return v === 0 ? "0" : String(Number(v.toPrecision(10)));
}

function parse(text: string): number | null {
  const t = text.trim();
  if (t === "") return 0;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

/** A number input committed on blur or Enter (Escape restores it). */
function NumberField({
  label,
  value,
  onCommit,
  unit,
  title,
}: {
  label: string;
  value: number;
  onCommit: (v: number) => void;
  unit?: string;
  title?: string;
}) {
  const text = show(value);
  return (
    <label
      className="flex items-center gap-1 text-xs text-gray-600"
      title={title}
    >
      <span className="w-16 shrink-0 font-mono">{label}</span>
      <input
        key={text}
        defaultValue={text}
        aria-label={label}
        className="w-28 border border-gray-200 rounded px-1 py-0.5 text-right font-mono"
        onBlur={(e) => {
          const v = parse(e.target.value);
          if (v === null) e.target.value = text;
          else if (e.target.value !== text) onCommit(v);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            (e.target as HTMLInputElement).value = text;
            (e.target as HTMLInputElement).blur();
          }
        }}
      />
      {unit && <span className="text-gray-400">{unit}</span>}
    </label>
  );
}

/** Coefficient list: slot k has a label and a display scale (display = SI * scale). */
function Coefficients({
  title,
  values,
  labels,
  scale,
  unit,
  minShown,
  onChange,
}: {
  title: string;
  values: number[];
  labels: string[];
  scale: (k: number) => number;
  unit?: (k: number) => string;
  minShown: number;
  onChange: (next: number[]) => void;
}) {
  const shown = Math.min(labels.length, Math.max(minShown, values.length + 1));
  const set = (k: number, display: number) => {
    const next = [...values];
    while (next.length <= k) next.push(0);
    next[k] = display / scale(k);
    while (next.length && next[next.length - 1] === 0) next.pop();
    onChange(next);
  };
  return (
    <fieldset className="mt-2">
      <legend className="text-xs font-medium text-gray-700">{title}</legend>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 mt-1">
        {labels.slice(0, shown).map((label, k) => (
          <NumberField
            key={label}
            label={label}
            value={(values[k] ?? 0) * scale(k)}
            unit={unit?.(k)}
            onCommit={(v) => set(k, v)}
          />
        ))}
      </div>
    </fieldset>
  );
}

function xyTermName(i: number, j: number): string {
  return `x${i}y${j}`;
}

/** All XY term names x<i>y<j>, 1 <= i + j <= 10, in increasing order. */
const XY_TERMS: string[] = [];
for (let n = 1; n <= XY_MAX_ORDER; n++)
  for (let i = n; i >= 0; i--) XY_TERMS.push(xyTermName(i, n - i));

export function SurfaceDetails({
  surface,
  row,
  displayUnit,
  onChange,
}: {
  surface: LensSurface;
  row: number;
  displayUnit: LengthUnit;
  onChange: (patch: Patch) => void;
}) {
  const s = LENGTH_UNIT_FACTORS[displayUnit]; // metres per display unit
  const unit = LENGTH_UNIT_LABELS[displayUnit];
  const len = (m: number | null | undefined) => (m ?? 0) / s;
  const toM = (v: number) => v * s;
  const type = surface.surface_type;
  const hasAperture = !["coordinate_break", "component"].includes(type);
  if (
    !hasAperture &&
    !["even_asphere", "odd_asphere", "q_asphere", "toroid"].includes(type)
  )
    return null;

  // coefficient of r^k: display = SI * s^(k-1)
  const powerScale = (order: (k: number) => number) => (k: number) =>
    Math.pow(s, order(k) - 1);
  const powerUnit = (order: (k: number) => number) => (k: number) =>
    order(k) === 1 ? "" : `${unit}^${1 - order(k)}`;
  const evenOrder = (k: number) => 2 * k + 4;
  const oddOrder = (k: number) => 2 * k + 3;
  const phaseOrder = (k: number) => 2 * k + 2;

  const xy = surface.xy_coefficients ?? {};

  return (
    <div
      className="mt-2 border border-gray-200 rounded p-2 bg-gray-50"
      data-testid="surface-details"
    >
      <h4 className="text-xs font-semibold text-gray-700">
        Surface {row} details
      </h4>

      {(type === "q_asphere" ||
        type === "zernike" ||
        type === "xy_polynomial") && (
        <div className="mt-1">
          <NumberField
            label="Norm. R"
            title="Normalisation radius of the polynomial terms"
            value={len(surface.norm_radius)}
            unit={unit}
            onCommit={(v) => onChange({ norm_radius: v > 0 ? toM(v) : null })}
          />
        </div>
      )}

      {(type === "even_asphere" || type === "odd_asphere") && (
        <Coefficients
          title="Even terms"
          values={surface.aspheric_coefficients ?? []}
          labels={Array.from({ length: 9 }, (_, k) => `A${evenOrder(k)}`)}
          scale={powerScale(evenOrder)}
          unit={powerUnit(evenOrder)}
          minShown={3}
          onChange={(next) => onChange({ aspheric_coefficients: next })}
        />
      )}
      {type === "odd_asphere" && (
        <Coefficients
          title="Odd terms"
          values={surface.odd_coefficients ?? []}
          labels={Array.from({ length: 9 }, (_, k) => `A${oddOrder(k)}`)}
          scale={powerScale(oddOrder)}
          unit={powerUnit(oddOrder)}
          minShown={3}
          onChange={(next) => onChange({ odd_coefficients: next })}
        />
      )}

      {type === "q_asphere" && (
        <>
          <label className="flex items-center gap-1 text-xs text-gray-600 mt-1">
            <span className="w-16 shrink-0">Q type</span>
            <select
              aria-label="Q type"
              value={surface.q_type ?? "qbfs"}
              onChange={(e) =>
                onChange({ q_type: e.target.value as "qbfs" | "qcon" })
              }
              className="border border-gray-200 rounded text-xs py-0.5"
            >
              <option value="qbfs">Qbfs (best-fit sphere)</option>
              <option value="qcon">Qcon (conic)</option>
            </select>
          </label>
          <Coefficients
            title="Q terms"
            values={surface.q_coefficients ?? []}
            labels={Array.from({ length: 13 }, (_, k) => `q${k}`)}
            scale={() => 1 / s}
            unit={() => unit}
            minShown={4}
            onChange={(next) => onChange({ q_coefficients: next })}
          />
        </>
      )}

      {type === "toroid" && (
        <div className="mt-1">
          <NumberField
            label="Radius x"
            title="Radius in the x-z plane (0 = flat: a cylinder)"
            value={len(surface.radius_x)}
            unit={unit}
            onCommit={(v) => onChange({ radius_x: toM(v) })}
          />
        </div>
      )}

      {type === "zernike" && (
        <Coefficients
          title="Zernike terms (Noll)"
          values={surface.zernike_coefficients ?? []}
          labels={Array.from({ length: 37 }, (_, k) => `Z${k + 1}`)}
          scale={() => 1 / s}
          unit={() => unit}
          minShown={11}
          onChange={(next) => onChange({ zernike_coefficients: next })}
        />
      )}

      {type === "xy_polynomial" && (
        <fieldset className="mt-2">
          <legend className="text-xs font-medium text-gray-700">
            XY terms C<sub>ij</sub> (x/R)<sup>i</sup> (y/R)<sup>j</sup>
          </legend>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 mt-1">
            {Object.entries(xy).map(([name, value]) => (
              <div key={name} className="flex items-center gap-1">
                <NumberField
                  label={name}
                  value={value / s}
                  unit={unit}
                  onCommit={(v) => {
                    const next = { ...xy };
                    if (v === 0) delete next[name];
                    else next[name] = toM(v);
                    onChange({ xy_coefficients: next });
                  }}
                />
              </div>
            ))}
          </div>
          <label className="flex items-center gap-1 text-xs text-gray-600 mt-1">
            <span className="w-16 shrink-0">Add term</span>
            <select
              aria-label="Add XY term"
              value=""
              onChange={(e) => {
                if (e.target.value)
                  onChange({
                    xy_coefficients: { ...xy, [e.target.value]: 0 },
                  });
              }}
              className="border border-gray-200 rounded text-xs py-0.5"
            >
              <option value="">choose…</option>
              {XY_TERMS.filter((t) => !(t in xy)).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        </fieldset>
      )}

      {type === "diffractive" && (
        <>
          <div className="mt-1">
            <NumberField
              label="Order"
              title="Diffraction order"
              value={surface.diffraction_order ?? 1}
              onCommit={(v) =>
                onChange({ diffraction_order: Math.round(v) || 1 })
              }
            />
          </div>
          <Coefficients
            title="Phase terms (radians)"
            values={surface.phase_coefficients ?? []}
            labels={Array.from({ length: 10 }, (_, k) => `r^${phaseOrder(k)}`)}
            scale={(k) => Math.pow(s, phaseOrder(k))}
            unit={(k) => `rad/${unit}^${phaseOrder(k)}`}
            minShown={3}
            onChange={(next) => onChange({ phase_coefficients: next })}
          />
        </>
      )}

      {hasAperture && type !== "paraxial" && (
        <fieldset className="mt-2" data-testid="coating-editor">
          <legend className="text-xs font-medium text-gray-700">
            Coating{" "}
            <span className="font-normal text-gray-400">
              (layers in the order light meets them; none = bare surface)
            </span>
          </legend>
          <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-gray-600">
            <select
              aria-label="Coating"
              value={
                !surface.coating
                  ? "none"
                  : surface.coating.name?.startsWith("QW MgF2")
                    ? "qw"
                    : "custom"
              }
              onChange={(e) => {
                const v = e.target.value;
                if (v === "none") onChange({ coating: null });
                else if (v === "qw") onChange({ coating: quarterWave(550) });
                else
                  onChange({
                    coating: {
                      name: "Custom",
                      layers: surface.coating?.layers.length
                        ? surface.coating.layers
                        : [{ material: "MgF2", thickness: 1e-7 }],
                    },
                  });
              }}
              className="border border-gray-200 rounded text-xs py-0.5"
            >
              <option value="none">None (bare)</option>
              <option value="qw">Quarter-wave MgF2 @ 550 nm</option>
              <option value="custom">Custom layers</option>
            </select>
            {surface.coating && (
              <button
                onClick={() =>
                  onChange({
                    coating: {
                      name: "Custom",
                      layers: [
                        ...(surface.coating?.layers ?? []),
                        { material: "SiO2", thickness: 1e-7 },
                      ],
                    },
                  })
                }
                className="px-2 py-0.5 border border-gray-300 rounded hover:bg-gray-50"
              >
                Add layer
              </button>
            )}
          </div>
          {surface.coating?.layers.map((layer, k) => (
            <div key={k} className="flex items-center gap-2 mt-1 text-xs">
              <span className="text-gray-500 w-12">Layer {k + 1}</span>
              <input
                key={`m-${layer.material}`}
                aria-label={`Coating layer ${k + 1} material`}
                defaultValue={layer.material ?? ""}
                onBlur={(e) => {
                  const material = e.target.value.trim();
                  if (!material || material === layer.material) return;
                  onChange({
                    coating: {
                      name: "Custom",
                      layers: surface.coating!.layers.map((x, i) =>
                        i === k ? { ...x, material, n: null } : x,
                      ),
                    },
                  });
                }}
                className="w-20 border border-gray-200 rounded px-1"
              />
              <NumberField
                label={`L${k + 1} nm`}
                value={layer.thickness * 1e9}
                unit="nm"
                onCommit={(v) =>
                  v > 0 &&
                  onChange({
                    coating: {
                      name: "Custom",
                      layers: surface.coating!.layers.map((x, i) =>
                        i === k ? { ...x, thickness: v * 1e-9 } : x,
                      ),
                    },
                  })
                }
              />
              <button
                aria-label={`Remove coating layer ${k + 1}`}
                onClick={() => {
                  const layers = surface.coating!.layers.filter(
                    (_, i) => i !== k,
                  );
                  onChange({
                    coating: layers.length ? { name: "Custom", layers } : null,
                  });
                }}
                className="text-gray-400 hover:text-red-500"
              >
                ×
              </button>
            </div>
          ))}
        </fieldset>
      )}

      {hasAperture && (
        <fieldset className="mt-2">
          <legend className="text-xs font-medium text-gray-700">
            Clear aperture
          </legend>
          <div className="flex flex-wrap items-center gap-3 mt-1">
            <label className="flex items-center gap-1 text-xs text-gray-600">
              Shape
              <select
                aria-label="Aperture shape"
                value={surface.aperture_shape ?? "circular"}
                disabled={surface.is_stop}
                title={
                  surface.is_stop ? "The aperture stop is circular" : undefined
                }
                onChange={(e) => {
                  const shape = e.target.value as LensSurface["aperture_shape"];
                  const semi = surface.semi_diameter ?? 0.01;
                  onChange({
                    aperture_shape: shape,
                    aperture_half_x:
                      shape === "circular"
                        ? null
                        : (surface.aperture_half_x ?? semi),
                    aperture_half_y:
                      shape === "circular"
                        ? null
                        : (surface.aperture_half_y ?? semi),
                  });
                }}
                className="border border-gray-200 rounded text-xs py-0.5"
              >
                <option value="circular">Circular</option>
                <option value="rectangular">Rectangular</option>
                <option value="elliptical">Elliptical</option>
              </select>
            </label>
            <NumberField
              label="Obscur."
              title="Radius of a central circular obscuration (0 = none)"
              value={len(surface.obscuration_semi)}
              unit={unit}
              onCommit={(v) =>
                onChange({ obscuration_semi: v > 0 ? toM(v) : null })
              }
            />
          </div>
          {surface.aperture_shape && surface.aperture_shape !== "circular" && (
            <div className="flex flex-wrap gap-3 mt-1">
              <NumberField
                label="Half x"
                value={len(surface.aperture_half_x)}
                unit={unit}
                onCommit={(v) => onChange({ aperture_half_x: toM(v) })}
              />
              <NumberField
                label="Half y"
                value={len(surface.aperture_half_y)}
                unit={unit}
                onCommit={(v) => onChange({ aperture_half_y: toM(v) })}
              />
            </div>
          )}
        </fieldset>
      )}
    </div>
  );
}
