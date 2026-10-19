/**
 * Field Curvature / Distortion Plot Component.
 *
 * Real-ray tangential and sagittal focus positions vs. field (relative to
 * the paraxial image, positive in the direction of travel) with the
 * third-order Petzval surface, and real chief-ray distortion vs. field.
 */

import type { OpticalSystem, LengthUnit } from "../../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../../types";
import { analyzeFieldCurves } from "../../api";
import { LinePlot } from "./LinePlot";
import { ExportButton } from "../ExportButton";
import { useAnalysis } from "./useAnalysis";

interface FieldCurvaturePlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

export function FieldCurvaturePlot({
  system,
  displayUnit,
}: FieldCurvaturePlotProps) {
  const { data, error, loading } = useAnalysis(
    () => analyzeFieldCurves(system, 11),
    [system],
  );
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const conv = (vals: (number | null)[]) =>
    vals.map((v) => (v === null ? null : fromMeters(v, displayUnit)));

  const fieldAxis = data
    ? data.field_fractions.map((f) =>
        data.field_unit === "deg"
          ? f * data.field_max
          : fromMeters(f * data.field_max, displayUnit),
      )
    : [];
  const fieldLabel =
    data?.field_unit === "deg"
      ? "Field angle (deg)"
      : `Object height (${unitLabel})`;
  const maxDist = data ? Math.max(...data.distortion.map(Math.abs)) * 100 : 0;
  const maxAstig = data ? Math.max(...data.astigmatism.map(Math.abs)) : 0;

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-2 gap-2">
        <h3 className="text-sm font-semibold text-gray-700">
          Field Curvature &amp; Distortion
        </h3>
        {data && (
          <div className="flex gap-2">
            <ExportButton
              svgId="field-curvature-plot"
              filename="field-curvature"
            />
            <ExportButton svgId="distortion-plot" filename="distortion" />
            <ExportButton
              type="csv"
              filename="field-curves"
              data={data.field_fractions.map((f, i) => ({
                field_fraction: f,
                tangential_focus_m: data.tangential_focus[i],
                sagittal_focus_m: data.sagittal_focus[i],
                petzval_m: data.petzval[i],
                distortion_fraction: data.distortion[i],
              }))}
            />
          </div>
        )}
      </div>

      {loading && !data && (
        <p className="text-xs text-gray-500">Tracing field rays...</p>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
      {data && !error && (
        <>
          <div className="flex gap-4 text-xs text-gray-600 mb-2">
            <span>
              Max astigmatism:{" "}
              {fromMeters(maxAstig, displayUnit).toPrecision(3)} {unitLabel}
            </span>
            <span>Max distortion: {maxDist.toFixed(3)}%</span>
          </div>
          <div className="flex flex-wrap gap-4 justify-center">
            <LinePlot
              id="field-curvature-plot"
              series={[
                {
                  label: "Tangential",
                  color: "#2563eb",
                  x: conv(data.tangential_focus),
                  y: fieldAxis,
                },
                {
                  label: "Sagittal",
                  color: "#dc2626",
                  x: conv(data.sagittal_focus),
                  y: fieldAxis,
                },
                {
                  label: "Petzval (3rd order)",
                  color: "#6b7280",
                  x: conv(data.petzval),
                  y: fieldAxis,
                  dashed: true,
                },
              ]}
              xLabel={`Focus from paraxial image (${unitLabel})`}
              yLabel={fieldLabel}
              symmetricX
              width={320}
              height={240}
            />
            <LinePlot
              id="distortion-plot"
              series={[
                {
                  label: "Distortion",
                  color: "#16a34a",
                  x: data.distortion.map((d) => d * 100),
                  y: fieldAxis,
                },
              ]}
              xLabel="Distortion (%)"
              yLabel={fieldLabel}
              symmetricX
              width={320}
              height={240}
            />
          </div>
          <div className="mt-2 text-xs text-gray-500">
            Positive distortion = pincushion, negative = barrel.
          </div>
        </>
      )}
    </div>
  );
}
