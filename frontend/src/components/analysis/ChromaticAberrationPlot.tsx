/**
 * Chromatic Aberration Plot Component.
 *
 * Chromatic focal shift: paraxial image position vs. wavelength relative to
 * the 550 nm image, from each material's dispersion formula. The summary
 * shows axial (longitudinal) and lateral colour between the F (486.1 nm)
 * and C (656.3 nm) lines, as computed by the backend.
 */

import type { OpticalSystem, LengthUnit } from "../../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../../types";
import { analyzeChromatic } from "../../api";
import { LinePlot } from "./LinePlot";
import { ExportButton } from "../ExportButton";
import { useAnalysis } from "./useAnalysis";

interface ChromaticAberrationPlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

// 400-700 nm in 10 nm steps; the middle sample (550 nm) is the reference.
const SWEEP = Array.from({ length: 31 }, (_, i) => (400 + 10 * i) * 1e-9);
const F_D_C = [486.1327e-9, 587.5618e-9, 656.2725e-9];

export function ChromaticAberrationPlot({
  system,
  displayUnit,
}: ChromaticAberrationPlotProps) {
  const { data, error, loading } = useAnalysis(
    () =>
      Promise.all([
        analyzeChromatic(system, SWEEP),
        analyzeChromatic(system, F_D_C),
      ]),
    [system],
  );
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const sweep = data?.[0];
  const fdc = data?.[1];
  const ref = sweep
    ? sweep.image_positions[Math.floor(sweep.image_positions.length / 2)]
    : 0;
  const shift = sweep
    ? sweep.image_positions.map((z) => fromMeters(z - ref, displayUnit))
    : [];

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-2 gap-2">
        <h3 className="text-sm font-semibold text-gray-700">
          Chromatic Focal Shift
        </h3>
        {sweep && (
          <div className="flex gap-2">
            <ExportButton
              svgId="chromatic-plot"
              filename="chromatic-focal-shift"
            />
            <ExportButton
              type="csv"
              filename="chromatic-focal-shift"
              data={sweep.wavelengths.map((w, i) => ({
                wavelength_nm: w * 1e9,
                image_position_m: sweep.image_positions[i],
                focal_shift_m: sweep.image_positions[i] - ref,
                image_height_m: sweep.image_heights[i],
              }))}
            />
          </div>
        )}
      </div>

      {loading && !data && (
        <p className="text-xs text-gray-500">
          Computing chromatic aberration...
        </p>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
      {sweep && fdc && !error && (
        <>
          <div className="flex gap-4 text-xs text-gray-600 mb-2">
            <span>
              Axial colour (F&minus;C):{" "}
              {fromMeters(fdc.lca, displayUnit).toPrecision(4)} {unitLabel}
            </span>
            <span>
              Lateral colour (F&minus;C):{" "}
              {fromMeters(fdc.tca, displayUnit).toPrecision(4)} {unitLabel}
            </span>
          </div>
          <LinePlot
            id="chromatic-plot"
            series={[
              {
                label: "Image position − image at 550 nm",
                color: "#7c3aed",
                x: sweep.wavelengths.map((w) => w * 1e9),
                y: shift,
              },
            ]}
            xLabel="Wavelength (nm)"
            yLabel={`Focal shift (${unitLabel})`}
            xDomain={[400, 700]}
          />
          <div className="mt-2 text-xs text-gray-500">
            Paraxial. Negative axial colour means blue focuses before red
            (under-corrected). Lateral colour is measured in the d-line image
            plane.
          </div>
        </>
      )}
    </div>
  );
}
