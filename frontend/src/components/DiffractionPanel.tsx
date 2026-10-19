/**
 * Diffraction Analysis Panel Component.
 *
 * Displays diffraction-based performance metrics including:
 * - MTF (Modulation Transfer Function) plot
 * - PSF (Point Spread Function) plot
 * - Encircled energy plot
 * - Airy disk radius
 * - Diffraction-limited assessment
 */

import { useEffect, useState } from "react";
import type { OpticalSystem, DiffractionResult, LengthUnit } from "../types";
import { fromMeters, LENGTH_UNIT_LABELS } from "../types";
import { analyzeDiffraction } from "../api";

interface DiffractionPanelProps {
  system: OpticalSystem;
  displayUnit: LengthUnit;
}

export function DiffractionPanel({
  system,
  displayUnit,
}: DiffractionPanelProps) {
  const unitLabel = LENGTH_UNIT_LABELS[displayUnit];
  const [data, setData] = useState<DiffractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setData(null);
    setError(null);

    analyzeDiffraction(system)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [system]);

  if (loading) {
    return (
      <div className="p-4 border-t border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Diffraction Analysis
        </h2>
        <p className="text-gray-500 text-sm">Analyzing diffraction...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 border-t border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Diffraction Analysis
        </h2>
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 border-t border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Diffraction Analysis
        </h2>
        <p className="text-gray-500 text-sm">No diffraction data available.</p>
      </div>
    );
  }

  const airyRadius = fromMeters(data.airy_disk_radius, displayUnit);
  const rmsSpot = fromMeters(
    data.diffraction_limited.rms_spot_radius,
    displayUnit,
  );
  const isDL = data.diffraction_limited.is_diffraction_limited;
  const strehl = data.diffraction_limited.strehl_ratio;
  const rmsWaves = data.diffraction_limited.rms_wavefront_waves;

  return (
    <div className="p-4 border-t border-gray-200">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Diffraction Analysis
      </h2>
      <div className="space-y-3">
        <div
          className={`p-3 rounded border ${isDL ? "bg-green-50 border-green-200" : "bg-yellow-50 border-yellow-200"}`}
        >
          <div className="text-xs text-gray-500 uppercase">
            Diffraction Limited
          </div>
          <div
            className={`text-lg font-bold ${isDL ? "text-green-700" : "text-yellow-700"}`}
          >
            {isDL ? "Yes" : "No"}
          </div>
          <div className="text-xs text-gray-500">
            Strehl {strehl.toFixed(3)} (RMS wavefront {rmsWaves.toFixed(3)}{" "}
            waves); criterion: {data.diffraction_limited.criterion}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">Airy Disk Radius</div>
            <div className="font-medium">
              {airyRadius.toFixed(4)} {unitLabel}
            </div>
          </div>
          <div className="p-2 bg-gray-50 rounded border">
            <div className="text-xs text-gray-500">
              RMS Spot Radius (geometric)
            </div>
            <div className="font-medium">
              {rmsSpot.toFixed(4)} {unitLabel}
            </div>
          </div>
        </div>
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase mb-2">
            Modulation Transfer Function
          </div>
          <MTFPlot data={data.mtf} />
        </div>
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase mb-2">
            Point Spread Function
          </div>
          <PSFPlot
            data={data.psf}
            displayUnit={displayUnit}
            unitLabel={unitLabel}
          />
        </div>
        <div className="p-3 bg-gray-50 rounded border">
          <div className="text-xs text-gray-500 uppercase mb-2">
            Encircled Energy
          </div>
          <EncircledEnergyPlot
            data={data.encircled_energy}
            displayUnit={displayUnit}
            unitLabel={unitLabel}
          />
        </div>
      </div>
    </div>
  );
}

function MTFPlot({
  data,
}: {
  data: { frequency: number[]; mtf: number[]; diffraction_limit?: number[] };
}) {
  const width = 280;
  const height = 120;
  const pad = 30;
  const plotW = width - 2 * pad;
  const plotH = height - 2 * pad;
  const maxFreq = data.frequency[data.frequency.length - 1] || 1;
  const points = data.frequency
    .map((f, i) => {
      const x = pad + (f / maxFreq) * plotW;
      const y = pad + plotH - data.mtf[i] * plotH;
      return `${x},${y}`;
    })
    .join(" ");
  const limitPoints = data.diffraction_limit
    ? data.frequency
        .map(
          (f, i) =>
            `${pad + (f / maxFreq) * plotW},${pad + plotH - data.diffraction_limit![i] * plotH}`,
        )
        .join(" ")
    : null;
  return (
    <svg width={width} height={height} className="bg-white rounded border">
      <line
        x1={pad}
        y1={pad + plotH}
        x2={pad + plotW}
        y2={pad + plotH}
        stroke="#9ca3af"
      />
      <line x1={pad} y1={pad} x2={pad} y2={pad + plotH} stroke="#9ca3af" />
      {limitPoints && (
        <polyline
          points={limitPoints}
          fill="none"
          stroke="#9ca3af"
          strokeWidth={1}
          strokeDasharray="4,3"
        />
      )}
      <polyline points={points} fill="none" stroke="#3b82f6" strokeWidth={2} />
      <text
        x={pad + plotW / 2}
        y={height - 2}
        textAnchor="middle"
        fontSize={9}
        fill="#6b7280"
      >
        frequency (0 to cutoff); dashed = diffraction limit
      </text>
      <text
        x={8}
        y={pad + plotH / 2}
        textAnchor="middle"
        fontSize={9}
        fill="#6b7280"
        transform={`rotate(-90, 8, ${pad + plotH / 2})`}
      >
        MTF
      </text>
    </svg>
  );
}

function PSFPlot({
  data,
  displayUnit,
  unitLabel,
}: {
  data: { r: number[]; intensity: number[] };
  displayUnit: LengthUnit;
  unitLabel: string;
}) {
  const width = 280;
  const height = 120;
  const pad = 30;
  const plotW = width - 2 * pad;
  const plotH = height - 2 * pad;
  const maxR = data.r[data.r.length - 1] || 1;
  const maxI = Math.max(...data.intensity, 0.01);
  const points = data.r
    .map((r, i) => {
      const x =
        pad +
        (fromMeters(r, displayUnit) / fromMeters(maxR, displayUnit)) * plotW;
      const y = pad + plotH - (data.intensity[i] / maxI) * plotH;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="bg-white rounded border">
      <line
        x1={pad}
        y1={pad + plotH}
        x2={pad + plotW}
        y2={pad + plotH}
        stroke="#9ca3af"
      />
      <line x1={pad} y1={pad} x2={pad} y2={pad + plotH} stroke="#9ca3af" />
      <polyline points={points} fill="none" stroke="#ef4444" strokeWidth={2} />
      <text
        x={pad + plotW / 2}
        y={height - 2}
        textAnchor="middle"
        fontSize={9}
        fill="#6b7280"
      >
        r ({unitLabel})
      </text>
      <text
        x={8}
        y={pad + plotH / 2}
        textAnchor="middle"
        fontSize={9}
        fill="#6b7280"
        transform={`rotate(-90, 8, ${pad + plotH / 2})`}
      >
        I
      </text>
    </svg>
  );
}

function EncircledEnergyPlot({
  data,
  displayUnit,
  unitLabel,
}: {
  data: { r: number[]; energy: number[] };
  displayUnit: LengthUnit;
  unitLabel: string;
}) {
  const width = 280;
  const height = 120;
  const pad = 30;
  const plotW = width - 2 * pad;
  const plotH = height - 2 * pad;
  const maxR = data.r[data.r.length - 1] || 1;
  const points = data.r
    .map((r, i) => {
      const x =
        pad +
        (fromMeters(r, displayUnit) / fromMeters(maxR, displayUnit)) * plotW;
      const y = pad + plotH - data.energy[i] * plotH;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="bg-white rounded border">
      <line
        x1={pad}
        y1={pad + plotH}
        x2={pad + plotW}
        y2={pad + plotH}
        stroke="#9ca3af"
      />
      <line x1={pad} y1={pad} x2={pad} y2={pad + plotH} stroke="#9ca3af" />
      <polyline points={points} fill="none" stroke="#22c55e" strokeWidth={2} />
      <text
        x={pad + plotW / 2}
        y={height - 2}
        textAnchor="middle"
        fontSize={9}
        fill="#6b7280"
      >
        r ({unitLabel})
      </text>
      <text
        x={8}
        y={pad + plotH / 2}
        textAnchor="middle"
        fontSize={9}
        fill="#6b7280"
        transform={`rotate(-90, 8, ${pad + plotH / 2})`}
      >
        EE
      </text>
    </svg>
  );
}
