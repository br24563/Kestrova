/**
 * What an optimization run did: success, the RMS spot before and after,
 * each constraint's final value, and the merit per cycle.
 */

import type { LengthUnit, LensOptimizeResult } from "../../types";
import { fmtLen } from "../../types";
import { LinePlot } from "../analysis/LinePlot";
import { CONSTRAINT_LABELS, describeConstraint } from "./ConstraintsEditor";
import { toDisplayValue, unitLabel } from "./properties";

interface Props {
  result: LensOptimizeResult;
  displayUnit: LengthUnit;
}

export function OptimizeReport({ result, displayUnit }: Props) {
  const constraints = result.constraints ?? [];
  const history = result.history ?? [];
  // the default merit is the mean-square transverse ray error (m^2)
  const rmsUm = history.map((h) => Math.sqrt(Math.max(h.merit, 0)) * 1e6);

  return (
    <div
      className="mt-3 p-3 border border-gray-200 rounded text-xs"
      data-testid="optimize-report"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span
          className={`px-1.5 py-0.5 rounded font-medium ${
            result.success
              ? "bg-green-100 text-green-800"
              : "bg-amber-100 text-amber-800"
          }`}
        >
          {result.success ? "Constraints met" : "Constraints not all met"}
        </span>
        {result.rms_spot_before !== null &&
          result.rms_spot_after !== null &&
          (result.image_kind === "wavefront" ? (
            <span className="text-gray-700">
              RMS wavefront {result.rms_spot_before.toFixed(4)} →{" "}
              <strong>{result.rms_spot_after.toFixed(4)}</strong> waves
            </span>
          ) : (
            <span className="text-gray-700">
              RMS spot {fmtLen(result.rms_spot_before, "um", 3)} →{" "}
              <strong>{fmtLen(result.rms_spot_after, "um", 3)}</strong> µm
            </span>
          ))}
        <span className="text-gray-500">
          {result.iterations ?? "?"} cycles, {result.evaluations} evaluations
        </span>
        <span className="text-gray-500">{result.message}</span>
      </div>

      {constraints.length > 0 && (
        <table className="mt-2 text-xs">
          <tbody>
            {constraints.map((c, k) => {
              const value = toDisplayValue(c.kind, c.value, displayUnit);
              const ul = unitLabel(c.kind, displayUnit);
              return (
                <tr key={k}>
                  <td className="pr-3 text-gray-600">
                    {CONSTRAINT_LABELS[c.kind]}
                    {c.surface !== null && c.surface !== undefined
                      ? ` (surface ${c.surface})`
                      : ""}
                  </td>
                  <td className="pr-3 text-gray-500">
                    {describeConstraint(c, displayUnit)}
                    {ul ? ` ${ul}` : ""}
                  </td>
                  <td
                    className={`font-mono ${c.satisfied ? "text-green-700" : "text-red-600"}`}
                  >
                    {Number(value.toPrecision(8))}
                    {ul ? ` ${ul}` : ""} {c.satisfied ? "✓" : "✗"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {history.length > 1 && (
        <div className="mt-2">
          <LinePlot
            id="optimize-history"
            series={[
              {
                label: "RMS transverse error",
                color: "#2563eb",
                x: rmsUm.map((_, i) => i),
                y: rmsUm,
              },
            ]}
            xLabel="Cycle"
            yLabel="RMS (µm)"
            height={160}
          />
        </div>
      )}
    </div>
  );
}
