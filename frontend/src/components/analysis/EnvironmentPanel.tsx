/**
 * Temperature and pressure analysis of the prescription (glass dn/dT and
 * CTE from the vendors, the air index, optional housing expansion): focus
 * drift from the image plane, EFL and RMS wavefront at each temperature.
 */
import { useState } from "react";
import { lensEnvironment } from "../../api";
import type { EnvironmentRow } from "../../api";
import { fmtLen } from "../../types";
import type { LengthUnit, LensData } from "../../types";

export function parseTemperatures(text: string): number[] | null {
  const values = text
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number);
  return values.length && values.every(Number.isFinite) ? values : null;
}

export function EnvironmentPanel({
  lens,
  displayUnit,
}: {
  lens: LensData | null;
  displayUnit: LengthUnit;
}) {
  const [temps, setTemps] = useState("-20, 0, 20, 40, 60");
  const [pressure, setPressure] = useState("101.325");
  const [housing, setHousing] = useState("");
  const [rows, setRows] = useState<EnvironmentRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  if (!lens)
    return (
      <p className="p-4 text-xs text-gray-500">
        The environment analysis works on the lens data (open or convert a lens
        in the Lens Data Editor).
      </p>
    );

  const run = async () => {
    const temperatures = parseTemperatures(temps);
    const p = Number(pressure);
    const cte = housing.trim() === "" ? null : Number(housing);
    if (
      !temperatures ||
      !Number.isFinite(p) ||
      p < 0 ||
      (cte !== null && !Number.isFinite(cte))
    ) {
      setError("Check the temperatures, pressure and housing CTE");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const out = await lensEnvironment(lens, {
        temperatures,
        pressure: p * 1000,
        mountCte: cte,
      });
      setRows(out.rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setRunning(false);
    }
  };

  const ref = rows?.find((r) => r.temperature === 20) ?? rows?.[0];

  return (
    <div className="p-4 space-y-3 text-xs" data-testid="environment">
      <div className="flex flex-wrap items-center gap-3 text-gray-600">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Temperature and pressure
        </h3>
        <label className="flex items-center gap-1">
          Temperatures (°C)
          <input
            aria-label="Temperatures"
            value={temps}
            onChange={(e) => setTemps(e.target.value)}
            className="w-40 border border-gray-200 rounded px-1 py-0.5"
          />
        </label>
        <label className="flex items-center gap-1">
          Pressure (kPa)
          <input
            aria-label="Pressure"
            value={pressure}
            onChange={(e) => setPressure(e.target.value)}
            className="w-16 border border-gray-200 rounded px-1 py-0.5 text-right"
          />
        </label>
        <label
          className="flex items-center gap-1"
          title="Expansion of the air spaces (e.g. aluminium 23.6); empty = rigid spacings"
        >
          Housing CTE (1e-6/K)
          <input
            aria-label="Housing CTE"
            value={housing}
            placeholder="rigid"
            onChange={(e) => setHousing(e.target.value)}
            className="w-14 border border-gray-200 rounded px-1 py-0.5 text-right"
          />
        </label>
        <button
          onClick={run}
          disabled={running}
          className="px-3 py-1 bg-optical-600 text-white rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {running ? "Analysing..." : "Analyse"}
        </button>
      </div>
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {rows && ref && (
        <table
          className="border border-gray-200 rounded"
          data-testid="environment-table"
        >
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-2 py-0.5 text-right font-medium">T (°C)</th>
              <th className="px-2 py-0.5 text-right font-medium">EFL</th>
              <th className="px-2 py-0.5 text-right font-medium">
                Focus drift (µm)
              </th>
              <th className="px-2 py-0.5 text-right font-medium">
                RMS wavefront (waves)
              </th>
              <th className="px-2 py-0.5 text-right font-medium">
                Depth of focus (µm)
              </th>
              <th className="px-2 py-0.5 text-left font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const drift = r.focus_shift - ref.focus_shift;
              const ok = Math.abs(drift) <= r.depth_of_focus;
              return (
                <tr key={r.temperature} className="border-t border-gray-100">
                  <td className="px-2 text-right">{r.temperature}</td>
                  <td className="px-2 text-right font-mono">
                    {fmtLen(r.efl, displayUnit, 4)}
                  </td>
                  <td className="px-2 text-right font-mono">
                    {(drift * 1e6).toFixed(2)}
                  </td>
                  <td className="px-2 text-right font-mono">
                    {r.rms_wavefront.toFixed(4)}
                  </td>
                  <td className="px-2 text-right font-mono">
                    ±{(r.depth_of_focus * 1e6).toFixed(1)}
                  </td>
                  <td
                    className={`px-2 ${ok ? "text-green-700" : "text-amber-700"}`}
                  >
                    {ok ? "in focus" : "refocus"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {rows && (
        <p className="text-gray-400">
          Focus drift is the paraxial focus moving relative to the image plane,
          measured from {ref?.temperature} °C; depth of focus ±2 λ N² (quarter
          wave). Mirrors keep their shape.
        </p>
      )}
    </div>
  );
}
