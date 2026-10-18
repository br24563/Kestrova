/**
 * Ray Fan Plot Component.
 *
 * Real-ray transverse aberration vs. normalised pupil coordinate at the
 * system image plane, relative to the chief ray: tangential fan (y error
 * vs. py) and sagittal fan (x error vs. px).
 */

import { useState } from 'react';
import type { OpticalSystem, LengthUnit } from '../../types';
import { fromMeters, LENGTH_UNIT_LABELS } from '../../types';
import { analyzeRayFan } from '../../api';
import { LinePlot, formatTick } from './LinePlot';
import { ExportButton } from '../ExportButton';
import { useAnalysis, FIELD_FRACTIONS, describeField } from './useAnalysis';

interface RayFanPlotProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

export function RayFanPlot({ system, displayUnit }: RayFanPlotProps) {
  const [fieldFraction, setFieldFraction] = useState(1);
  const { data, error, loading } = useAnalysis(
    () => analyzeRayFan(system, fieldFraction, 31),
    [system, fieldFraction],
  );
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const conv = (vals: (number | null)[]) => vals.map((v) => (v === null ? null : fromMeters(v, displayUnit)));

  const maxAbs = data
    ? Math.max(0, ...[...data.transverse_t, ...data.transverse_s]
        .filter((v): v is number => v !== null).map(Math.abs))
    : 0;

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-2 gap-2">
        <h3 className="text-sm font-semibold text-gray-700">
          Ray Fan{data && ` (field ${describeField(data, fieldFraction, displayUnit)})`}
        </h3>
        <div className="flex items-center gap-2">
          <select
            value={fieldFraction}
            onChange={(e) => setFieldFraction(parseFloat(e.target.value))}
            className="text-xs border border-gray-200 rounded px-2 py-1"
          >
            {FIELD_FRACTIONS.map((f) => (
              <option key={f} value={f}>Field {f.toFixed(1)}</option>
            ))}
          </select>
          {data && <ExportButton svgId="ray-fan-plot" filename="ray-fan" />}
          {data && (
            <ExportButton
              type="csv"
              filename="ray-fan"
              data={data.pupil_x.map((p, i) => ({
                pupil: p,
                tangential_ey_m: data.transverse_t[i],
                sagittal_ex_m: data.transverse_s[i],
              }))}
            />
          )}
        </div>
      </div>

      {loading && !data && <p className="text-xs text-gray-500">Tracing rays...</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
      {data && !error && (
        <>
          <LinePlot
            id="ray-fan-plot"
            series={[
              { label: 'Tangential (ey vs py)', color: '#2563eb', x: data.pupil_x, y: conv(data.transverse_t) },
              { label: 'Sagittal (ex vs px)', color: '#dc2626', x: data.pupil_x, y: conv(data.transverse_s) },
            ]}
            xLabel="Normalised pupil coordinate"
            yLabel={`Ray error (${unitLabel})`}
            xDomain={[-1, 1]}
            symmetricY
          />
          <div className="mt-2 text-xs text-gray-500">
            Max |error|: {formatTick(fromMeters(maxAbs, displayUnit))} {unitLabel} at the image plane
            {' '}({fromMeters(system.image_plane.position, displayUnit).toFixed(3)} {unitLabel}).
            Gaps mark vignetted rays.
          </div>
        </>
      )}
    </div>
  );
}
