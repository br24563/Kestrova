/**
 * OPD/Wavefront Plot Component.
 *
 * Real-ray optical path difference along the tangential and sagittal pupil
 * axes, relative to the reference sphere centred on the chief ray at the
 * system image plane, in waves. RMS, P-V and Strehl are over the full 2D pupil.
 */

import { useState } from "react";
import type { OpticalSystem, LengthUnit } from "../../types";
import { analyzeOPDFan } from "../../api";
import { LinePlot } from "./LinePlot";
import { ExportButton } from "../ExportButton";
import { useAnalysis, FIELD_FRACTIONS, describeField } from "./useAnalysis";

interface OPDPlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

export function OPDPlot({ system, displayUnit }: OPDPlotProps) {
  const [fieldFraction, setFieldFraction] = useState(1);
  const { data, error, loading } = useAnalysis(
    () => analyzeOPDFan(system, fieldFraction, 41),
    [system, fieldFraction],
  );

  const waves = (vals: (number | null)[]) =>
    vals.map((v) => (v === null || !data ? null : v / data.wavelength));

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-2 gap-2">
        <h3 className="text-sm font-semibold text-gray-700">
          OPD
          {data &&
            ` (field ${describeField(data, fieldFraction, displayUnit)}, λ = ${(data.wavelength * 1e9).toFixed(0)} nm)`}
        </h3>
        <div className="flex items-center gap-2">
          <select
            value={fieldFraction}
            onChange={(e) => setFieldFraction(parseFloat(e.target.value))}
            className="text-xs border border-gray-200 rounded px-2 py-1"
          >
            {FIELD_FRACTIONS.map((f) => (
              <option key={f} value={f}>
                Field {f.toFixed(1)}
              </option>
            ))}
          </select>
          {data && <ExportButton svgId="opd-plot" filename="opd-fan" />}
          {data && (
            <ExportButton
              type="csv"
              filename="opd-fan"
              data={data.pupil.map((p, i) => ({
                pupil: p,
                opd_tangential_m: data.opd_t[i],
                opd_sagittal_m: data.opd_s[i],
              }))}
            />
          )}
        </div>
      </div>

      {loading && !data && (
        <p className="text-xs text-gray-500">Computing wavefront...</p>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
      {data && !error && (
        <>
          <div className="flex gap-4 text-xs text-gray-600 mb-2">
            <span>
              RMS: {(data.opd_rms / data.wavelength).toFixed(3)} {"λ"}
            </span>
            <span>
              P-V: {(data.opd_peak_to_valley / data.wavelength).toFixed(3)}{" "}
              {"λ"}
            </span>
            <span>Strehl: {data.strehl_ratio.toFixed(3)}</span>
          </div>
          <LinePlot
            id="opd-plot"
            series={[
              {
                label: "Tangential (py)",
                color: "#2563eb",
                x: data.pupil,
                y: waves(data.opd_t),
              },
              {
                label: "Sagittal (px)",
                color: "#dc2626",
                x: data.pupil,
                y: waves(data.opd_s),
              },
            ]}
            xLabel="Normalised pupil coordinate"
            yLabel={"OPD (waves)"}
            xDomain={[-1, 1]}
            symmetricY
          />
          <div className="mt-2 text-xs text-gray-500">
            Referenced to the chief ray at the current image plane, so defocus
            from it is included. Diffraction-limited (Mar&eacute;chal): RMS &le;
            0.071 {"λ"}, Strehl &ge; 0.8.
          </div>
        </>
      )}
    </div>
  );
}
