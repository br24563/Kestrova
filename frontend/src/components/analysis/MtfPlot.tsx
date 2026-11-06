/**
 * Diffraction MTF (wavelength-weighted) for the field table: tangential and
 * sagittal curves with the diffraction limit, MTF through focus at one
 * frequency, and MTF across the field at chosen frequencies. "Hopkins"
 * integrates the pupil overlap directly with the real wavefront; "FFT"
 * autocorrelates the sampled pupil. The two are independent checks.
 */

import { useState } from "react";
import type { OpticalSystem, LengthUnit } from "../../types";
import {
  analyzeMtf,
  analyzeMtfVsField,
  analyzeThroughFocusMtf,
  type MtfMethod,
} from "../../api";
import { LinePlot, type PlotSeries } from "./LinePlot";
import { ExportButton } from "../ExportButton";
import { useAnalysis } from "./useAnalysis";

interface MtfPlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

const COLORS = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c"];

/** Number of field points the backend analyses (the table, or 0 / 0.7 / 1). */
export function fieldCount(system: OpticalSystem): number {
  if (system.fields && system.fields.length > 0) return system.fields.length;
  return system.object.height ? 3 : 1;
}

/** "10, 30, 50" -> [10, 30, 50]; invalid or non-positive entries dropped. */
export function parseFrequencies(text: string): number[] {
  return text
    .split(/[,\s]+/)
    .map(Number)
    .filter((v) => Number.isFinite(v) && v > 0);
}

export function MtfPlot({ system }: MtfPlotProps) {
  const [field, setField] = useState(0);
  const [method, setMethod] = useState<MtfMethod>("fft");
  const [focusFreq, setFocusFreq] = useState("50");
  const [fieldFreqs, setFieldFreqs] = useState("10, 30, 50");
  const nFields = fieldCount(system);
  const f = Math.min(field, nFields - 1);
  const focusNu = Number(focusFreq) > 0 ? Number(focusFreq) : 50;
  const freqs = parseFrequencies(fieldFreqs);

  const curves = useAnalysis(
    () => analyzeMtf(system, f, method),
    [system, f, method],
  );
  const focus = useAnalysis(
    () => analyzeThroughFocusMtf(system, focusNu, f, method),
    [system, f, method, focusNu],
  );
  const across = useAnalysis(
    () => analyzeMtfVsField(system, freqs.length ? freqs : [30], method),
    [system, method, freqs.join(",")],
  );

  const curveSeries: PlotSeries[] = curves.data
    ? [
        {
          label: "Tangential",
          color: COLORS[0],
          x: curves.data.frequency_cyc_per_mm,
          y: curves.data.tangential,
        },
        {
          label: "Sagittal",
          color: COLORS[0],
          x: curves.data.frequency_cyc_per_mm,
          y: curves.data.sagittal,
          dashed: true,
        },
        {
          label: "Diffraction limit",
          color: "#9ca3af",
          x: curves.data.frequency_cyc_per_mm,
          y: curves.data.diffraction_limit,
          dashed: true,
        },
      ]
    : [];

  const focusSeries: PlotSeries[] = focus.data
    ? [
        {
          label: "Tangential",
          color: COLORS[0],
          x: focus.data.defocus_mm,
          y: focus.data.tangential,
        },
        {
          label: "Sagittal",
          color: COLORS[0],
          x: focus.data.defocus_mm,
          y: focus.data.sagittal,
          dashed: true,
        },
      ]
    : [];

  const fieldSeries: PlotSeries[] = across.data
    ? across.data.frequencies_cyc_per_mm.flatMap((nu, k) => [
        {
          label: `${nu} c/mm T`,
          color: COLORS[k % COLORS.length],
          x: across.data!.field_fraction,
          y: across.data!.tangential[k],
        },
        {
          label: `${nu} c/mm S`,
          color: COLORS[k % COLORS.length],
          x: across.data!.field_fraction,
          y: across.data!.sagittal[k],
          dashed: true,
        },
      ])
    : [];

  const status = (q: { loading: boolean; error: string | null }) =>
    q.error ? (
      <p className="text-xs text-red-500" role="alert">
        {q.error}
      </p>
    ) : q.loading ? (
      <p className="text-xs text-gray-400">Computing...</p>
    ) : null;

  return (
    <div className="p-4 space-y-4 text-xs">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          MTF (wavelength-weighted)
        </h3>
        <label className="flex items-center gap-1 text-gray-600">
          Field
          <select
            aria-label="MTF field"
            value={f}
            onChange={(e) => setField(parseInt(e.target.value, 10))}
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            {Array.from({ length: nFields }, (_, k) => (
              <option key={k} value={k}>
                {k + 1}
              </option>
            ))}
          </select>
        </label>
        <label
          className="flex items-center gap-1 text-gray-600"
          title="FFT: autocorrelation of the sampled pupil. Hopkins: direct integration over the pupil overlap with the real wavefront at each point (slower, more precise)."
        >
          Method
          <select
            aria-label="MTF method"
            value={method}
            onChange={(e) => setMethod(e.target.value as MtfMethod)}
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            <option value="fft">FFT</option>
            <option value="hopkins">Hopkins</option>
          </select>
        </label>
      </div>

      <section>
        <div className="flex items-center justify-between mb-1">
          <h4 className="font-medium text-gray-700">
            MTF, field {f + 1}
            {curves.data &&
              ` — cutoff ${curves.data.cutoff_cyc_per_mm.toFixed(0)} cycles/mm`}
          </h4>
          {curves.data && (
            <ExportButton svgId="mtf-curves" filename="mtf-curves" />
          )}
        </div>
        {status(curves)}
        {curves.data && (
          <LinePlot
            id="mtf-curves"
            series={curveSeries}
            xLabel="Spatial frequency (cycles/mm)"
            yLabel="MTF"
            yDomain={[0, 1]}
          />
        )}
      </section>

      <section>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h4 className="font-medium text-gray-700">Through focus</h4>
          <label className="flex items-center gap-1 text-gray-600">
            at
            <input
              aria-label="Through-focus frequency"
              value={focusFreq}
              onChange={(e) => setFocusFreq(e.target.value)}
              className="w-14 px-1 py-0.5 border border-gray-200 rounded text-right"
            />
            cycles/mm
          </label>
          {focus.data && (
            <span className="text-gray-500" data-testid="best-focus">
              best focus {focus.data.best_focus_mm.mean.toFixed(4)} mm (T{" "}
              {focus.data.best_focus_mm.tangential.toFixed(4)}, S{" "}
              {focus.data.best_focus_mm.sagittal.toFixed(4)})
              {focus.data.peak_at_scan_edge && (
                <span className="text-amber-600">
                  {" "}
                  — at the edge of the scan; the peak may lie beyond
                </span>
              )}
            </span>
          )}
          {focus.data && (
            <span className="ml-auto">
              <ExportButton svgId="mtf-focus" filename="mtf-through-focus" />
            </span>
          )}
        </div>
        {status(focus)}
        {focus.data && (
          <LinePlot
            id="mtf-focus"
            series={focusSeries}
            xLabel="Image plane shift (mm)"
            yLabel="MTF"
            yDomain={[0, 1]}
            symmetricX
          />
        )}
      </section>

      <section>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h4 className="font-medium text-gray-700">Across the field</h4>
          <label className="flex items-center gap-1 text-gray-600">
            at
            <input
              aria-label="Across-field frequencies"
              value={fieldFreqs}
              onChange={(e) => setFieldFreqs(e.target.value)}
              className="w-28 px-1 py-0.5 border border-gray-200 rounded"
            />
            cycles/mm
          </label>
          {across.data && (
            <span className="ml-auto">
              <ExportButton svgId="mtf-field" filename="mtf-vs-field" />
            </span>
          )}
        </div>
        {status(across)}
        {across.data && (
          <LinePlot
            id="mtf-field"
            series={fieldSeries}
            xLabel="Field (fraction of the largest)"
            yLabel="MTF"
            yDomain={[0, 1]}
          />
        )}
        <p className="text-gray-400 mt-1">
          Solid: tangential. Dashed: sagittal.
        </p>
      </section>
    </div>
  );
}
