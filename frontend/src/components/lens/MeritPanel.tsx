/**
 * Merit function (Code V's error function): the image term the optimizer
 * minimises (transverse ray errors or wavefront variance, its pupil
 * sampling and reference) and weighted operands that add
 * weight x (value - target) for any system property. "Evaluate" shows the
 * current merit term by term.
 */
import { useState } from "react";
import { lensMerit } from "../../api";
import { SURFACE_CONSTRAINTS, fmtLen } from "../../types";
import type {
  LengthUnit,
  LensConstraintKind,
  LensData,
  MeritReport,
  MeritSpec,
  Operand,
} from "../../types";
import {
  FIELD_PROPERTIES,
  PROPERTY_LABELS,
  fromDisplayValue,
  showValue,
  unitLabel,
} from "./properties";

export const DEFAULT_MERIT: MeritSpec = {
  kind: "transverse",
  rings: 3,
  reference: "chief",
  image_weight: 1,
  operands: [],
};

export function MeritPanel({
  lens,
  displayUnit,
  busy,
  onChange,
}: {
  lens: LensData;
  displayUnit: LengthUnit;
  busy: boolean;
  onChange: (lens: LensData) => void;
}) {
  const merit = { ...DEFAULT_MERIT, ...(lens.merit ?? {}) };
  const [report, setReport] = useState<MeritReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const configs = lens.configuration_names ?? [];
  const multi = configs.length > 1;
  const fieldCount = lens.fields?.length ?? 3;

  const set = (patch: Partial<MeritSpec>) => {
    setReport(null);
    onChange({ ...lens, merit: { ...merit, ...patch } });
  };
  const setOperand = (k: number, patch: Partial<Operand>) =>
    set({
      operands: merit.operands.map((o, i) =>
        i === k ? { ...o, ...patch } : o,
      ),
    });

  const evaluate = async () => {
    setError(null);
    try {
      setReport(await lensMerit(lens));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not evaluate the merit",
      );
    }
  };

  /** Current values of operand k, one per configuration it applies to. */
  const valuesOf = (k: number) =>
    (report?.configurations ?? []).flatMap((c) =>
      c.operands
        .filter((o) => o.index === k)
        .map((o) => ({ configuration: c.configuration, value: o.value })),
    );

  const imageRms = (c: MeritReport["configurations"][number]) =>
    c.image_rms === null
      ? "—"
      : c.image_kind === "wavefront"
        ? `${c.image_rms.toFixed(4)} waves`
        : `${fmtLen(c.image_rms, "um", 3)} µm`;

  return (
    <div className="mt-3" data-testid="merit-panel">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h4 className="text-xs font-semibold text-gray-700">Merit function</h4>
        <span className="text-[11px] text-gray-400">
          what Optimize minimises
        </span>
        <button
          onClick={evaluate}
          disabled={busy}
          className="ml-auto px-2 py-0.5 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
        >
          Evaluate
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
        <label className="flex items-center gap-1">
          Image term
          <select
            aria-label="Merit kind"
            value={merit.kind}
            onChange={(e) => set({ kind: e.target.value as MeritSpec["kind"] })}
            className="border border-gray-200 rounded text-xs py-0.5"
          >
            <option value="transverse">Transverse ray error</option>
            <option value="wavefront">Wavefront variance</option>
          </select>
        </label>
        {merit.kind === "transverse" && (
          <label className="flex items-center gap-1">
            from
            <select
              aria-label="Merit reference"
              value={merit.reference}
              onChange={(e) =>
                set({ reference: e.target.value as MeritSpec["reference"] })
              }
              className="border border-gray-200 rounded text-xs py-0.5"
            >
              <option value="chief">chief ray</option>
              <option value="centroid">spot centroid</option>
            </select>
          </label>
        )}
        <label
          className="flex items-center gap-1"
          title="Rings of the Gaussian pupil sampling (more rings: higher-order aberrations)"
        >
          Rings
          <input
            aria-label="Merit rings"
            type="number"
            min={1}
            max={12}
            value={merit.rings}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (v >= 1 && v <= 12) set({ rings: v });
            }}
            className="w-12 border border-gray-200 rounded px-1 text-right"
          />
        </label>
        <label
          className="flex items-center gap-1"
          title="Weight of the image term (0: optimize the operands only)"
        >
          Weight
          <input
            key={merit.image_weight}
            aria-label="Image term weight"
            defaultValue={merit.image_weight}
            onBlur={(e) => {
              const v = Number(e.target.value);
              if (Number.isFinite(v) && v >= 0) set({ image_weight: v });
              else e.target.value = String(merit.image_weight);
            }}
            className="w-12 border border-gray-200 rounded px-1 text-right"
          />
        </label>
        <button
          onClick={() =>
            set({
              operands: [
                ...merit.operands,
                { kind: "distortion", target: 0, weight: 1, field: null },
              ],
            })
          }
          className="px-2 py-0.5 text-xs border border-gray-300 rounded hover:bg-gray-50"
        >
          Add operand
        </button>
      </div>

      {merit.operands.length > 0 && (
        <table className="mt-1 text-xs border border-gray-200 rounded">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-1 py-0.5 text-left font-medium">Operand</th>
              <th className="px-1 py-0.5 text-left font-medium">
                Surface / field
              </th>
              {multi && (
                <th className="px-1 py-0.5 text-left font-medium">
                  Configuration
                </th>
              )}
              <th className="px-1 py-0.5 text-right font-medium">Target</th>
              <th className="px-1 py-0.5 text-right font-medium">Weight</th>
              <th className="px-1 py-0.5 text-right font-medium">Current</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {merit.operands.map((o, k) => {
              const ul = unitLabel(o.kind, displayUnit);
              const target = showValue(o.kind, o.target, displayUnit);
              return (
                <tr key={k} className="border-t border-gray-100">
                  <td className="px-1">
                    <select
                      aria-label={`Operand ${k + 1} property`}
                      value={o.kind}
                      onChange={(e) => {
                        const kind = e.target.value as LensConstraintKind;
                        setOperand(k, {
                          kind,
                          surface: SURFACE_CONSTRAINTS.includes(kind)
                            ? (o.surface ?? 0)
                            : null,
                          field: FIELD_PROPERTIES.includes(kind)
                            ? (o.field ?? null)
                            : null,
                          target: 0,
                        });
                      }}
                      className="bg-transparent text-xs py-0.5"
                    >
                      {Object.entries(PROPERTY_LABELS).map(([v, label]) => (
                        <option key={v} value={v}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-1">
                    {SURFACE_CONSTRAINTS.includes(o.kind) ? (
                      <input
                        aria-label={`Operand ${k + 1} surface`}
                        type="number"
                        min={0}
                        value={o.surface ?? 0}
                        onChange={(e) =>
                          setOperand(k, {
                            surface: parseInt(e.target.value, 10),
                          })
                        }
                        className="w-12 border border-gray-200 rounded px-1 text-right"
                      />
                    ) : FIELD_PROPERTIES.includes(o.kind) ? (
                      <select
                        aria-label={`Operand ${k + 1} field`}
                        value={o.field == null ? "last" : String(o.field)}
                        onChange={(e) =>
                          setOperand(k, {
                            field:
                              e.target.value === "last"
                                ? null
                                : parseInt(e.target.value, 10),
                          })
                        }
                        className="bg-transparent text-xs py-0.5"
                      >
                        <option value="last">Last field</option>
                        {Array.from({ length: fieldCount }, (_, i) => (
                          <option key={i} value={i}>
                            Field {i + 1}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  {multi && (
                    <td className="px-1">
                      <select
                        aria-label={`Operand ${k + 1} configuration`}
                        value={
                          o.configuration == null
                            ? "all"
                            : String(o.configuration)
                        }
                        onChange={(e) =>
                          setOperand(k, {
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
                  <td className="px-1 text-right whitespace-nowrap">
                    <input
                      key={`${o.kind}-${target}`}
                      aria-label={`Operand ${k + 1} target`}
                      defaultValue={target}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (e.target.value.trim() !== "" && Number.isFinite(v))
                          setOperand(k, {
                            target: fromDisplayValue(o.kind, v, displayUnit),
                          });
                        else e.target.value = target;
                      }}
                      className="w-20 border border-gray-200 rounded px-1 text-right font-mono"
                    />
                    <span className="text-gray-400"> {ul}</span>
                  </td>
                  <td className="px-1 text-right">
                    <input
                      key={`w-${o.weight}`}
                      aria-label={`Operand ${k + 1} weight`}
                      defaultValue={o.weight}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (Number.isFinite(v) && v >= 0)
                          setOperand(k, { weight: v });
                        else e.target.value = String(o.weight);
                      }}
                      className="w-14 border border-gray-200 rounded px-1 text-right font-mono"
                    />
                  </td>
                  <td
                    className="px-1 text-right font-mono"
                    data-testid={`operand-${k}-value`}
                  >
                    {valuesOf(k).length
                      ? valuesOf(k).map((v) => (
                          <span key={v.configuration} className="block">
                            {multi ? `${configs[v.configuration]}: ` : ""}
                            {showValue(o.kind, v.value, displayUnit)} {ul}
                          </span>
                        ))
                      : "—"}
                  </td>
                  <td className="px-1">
                    <button
                      aria-label={`Remove operand ${k + 1}`}
                      onClick={() =>
                        set({
                          operands: merit.operands.filter((_, i) => i !== k),
                        })
                      }
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

      {error && (
        <p className="text-xs text-red-500 mt-1" role="alert">
          {error}
        </p>
      )}
      {report && (
        <p className="text-xs text-gray-600 mt-1" data-testid="merit-report">
          {report.configurations.map((c) => (
            <span key={c.configuration} className="mr-3">
              {multi ? `${configs[c.configuration]}: ` : ""}
              {merit.kind === "wavefront" ? "RMS wavefront" : "RMS spot"}{" "}
              {imageRms(c)}
            </span>
          ))}
          <span className="text-gray-400">
            merit {report.merit.toPrecision(4)}
          </span>
        </p>
      )}
    </div>
  );
}
