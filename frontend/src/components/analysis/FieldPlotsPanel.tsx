/**
 * Standard field plots: distortion (and F-theta distortion for an object at
 * infinity), lateral colour at each wavelength relative to the reference,
 * and relative illumination with the cos^4 law, from axis to full field.
 */

import type { OpticalSystem, LengthUnit } from "../../types";
import { analyzeFieldPlots } from "../../api";
import { LinePlot, type PlotSeries } from "./LinePlot";
import { ExportButton } from "../ExportButton";
import { useAnalysis } from "./useAnalysis";

interface FieldPlotsPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

const COLORS = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c"];

export function FieldPlotsPanel({ system }: FieldPlotsPanelProps) {
  const { data, error, loading } = useAnalysis(
    () => analyzeFieldPlots(system, 11),
    [system],
  );
  const x = data
    ? (data.field_angle_deg ?? data.field_fractions.map((f) => f))
    : [];
  const xLabel = data?.field_angle_deg
    ? "Field angle (deg)"
    : "Field (fraction of the object height)";

  const distortion: PlotSeries[] = data
    ? [
        {
          label: "Distortion",
          color: COLORS[0],
          x,
          y: data.distortion.map((d) => d * 100),
        },
        ...(data.ftheta_distortion
          ? [
              {
                label: "F-θ distortion",
                color: COLORS[2],
                x,
                y: data.ftheta_distortion.map((d) => d * 100),
                dashed: true,
              },
            ]
          : []),
      ]
    : [];

  const colour: PlotSeries[] = data
    ? data.lateral_colour_mm.map((row, k) => ({
        label: `${(row.wavelength * 1e9).toFixed(1)} nm`,
        color: COLORS[k % COLORS.length],
        x,
        y: row.offset_mm.map((v) => v * 1e3),
      }))
    : [];

  const illumination: PlotSeries[] = data
    ? [
        {
          label: "Relative illumination",
          color: COLORS[0],
          x,
          y: data.relative_illumination,
        },
        {
          label: "cos⁴",
          color: "#9ca3af",
          x,
          y: data.cos4,
          dashed: true,
        },
      ]
    : [];

  return (
    <div className="p-4 space-y-4 text-xs">
      <h3 className="text-sm font-semibold text-gray-700">
        Distortion, lateral colour and illumination
      </h3>
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {loading && !data && <p className="text-gray-400">Computing...</p>}
      {data && (
        <>
          <section>
            <div className="flex justify-between items-center">
              <h4 className="font-medium text-gray-700">
                Distortion
                {data.ftheta_distortion
                  ? " (solid: paraxial, dashed: F-θ)"
                  : ""}
              </h4>
              <ExportButton svgId="field-distortion" filename="distortion" />
            </div>
            <LinePlot
              id="field-distortion"
              series={distortion}
              xLabel={xLabel}
              yLabel="Distortion (%)"
              symmetricY
            />
          </section>
          <section>
            <div className="flex justify-between items-center">
              <h4 className="font-medium text-gray-700">
                Lateral colour (relative to{" "}
                {(data.reference_wavelength * 1e9).toFixed(1)} nm)
              </h4>
              <ExportButton svgId="field-colour" filename="lateral-colour" />
            </div>
            <LinePlot
              id="field-colour"
              series={colour}
              xLabel={xLabel}
              yLabel="Chief ray offset (µm)"
              symmetricY
            />
          </section>
          <section>
            <div className="flex justify-between items-center">
              <h4 className="font-medium text-gray-700">
                Relative illumination
              </h4>
              <ExportButton
                svgId="field-illumination"
                filename="relative-illumination"
              />
            </div>
            <LinePlot
              id="field-illumination"
              series={illumination}
              xLabel={xLabel}
              yLabel="Relative to the axis"
              yDomain={[0, 1.05]}
            />
          </section>
        </>
      )}
    </div>
  );
}
