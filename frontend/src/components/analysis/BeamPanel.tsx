/**
 * Paraxial Gaussian beam through the prescription (its exact ray-transfer
 * matrix): output waist and its position, the beam radius at the image
 * plane, and the beam radius along the axis around the waist.
 */
import { useState } from "react";
import type { OpticalSystem } from "../../types";
import { gaussianBeam } from "../../api";
import { useAnalysis } from "./useAnalysis";
import { LinePlot } from "./LinePlot";

export function BeamPanel({ system }: { system: OpticalSystem }) {
  const [waist, setWaist] = useState("1");
  const [distance, setDistance] = useState("0");
  const [m2, setM2] = useState("1");
  const w = Number(waist);
  const d = Number(distance);
  const q = Number(m2);
  const valid = w > 0 && Number.isFinite(d) && q >= 1;
  const { data, error, loading } = useAnalysis(
    () =>
      valid
        ? gaussianBeam(system, w * 1e-3, d * 1e-3, q)
        : Promise.reject(new Error("Waist > 0 and M² ≥ 1 needed")),
    [system, w, d, q],
  );
  return (
    <div className="p-4 space-y-3 text-xs" data-testid="beam">
      <div className="flex flex-wrap items-center gap-3 text-gray-600">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Gaussian beam (paraxial)
        </h3>
        <label className="flex items-center gap-1">
          Input waist radius (mm)
          <input
            aria-label="Waist radius"
            value={waist}
            onChange={(e) => setWaist(e.target.value)}
            className="w-14 border border-gray-200 rounded px-1 py-0.5 text-right"
          />
        </label>
        <label
          className="flex items-center gap-1"
          title="In front of the first surface"
        >
          at (mm)
          <input
            aria-label="Waist distance"
            value={distance}
            onChange={(e) => setDistance(e.target.value)}
            className="w-14 border border-gray-200 rounded px-1 py-0.5 text-right"
          />
        </label>
        <label className="flex items-center gap-1">
          M²
          <input
            aria-label="M squared"
            value={m2}
            onChange={(e) => setM2(e.target.value)}
            className="w-10 border border-gray-200 rounded px-1 py-0.5 text-right"
          />
        </label>
      </div>
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {loading && !data && <p className="text-gray-400">Computing...</p>}
      {data && (
        <>
          <table data-testid="beam-results">
            <tbody>
              <tr>
                <td className="pr-3 text-gray-600">Output waist radius</td>
                <td className="font-mono">
                  {(data.waist_radius * 1e6).toFixed(2)} µm
                </td>
              </tr>
              <tr>
                <td className="pr-3 text-gray-600">
                  Waist from the image plane
                </td>
                <td className="font-mono">
                  {(data.waist_position * 1e3).toFixed(4)} mm
                </td>
              </tr>
              <tr>
                <td className="pr-3 text-gray-600">
                  Beam radius at the image plane
                </td>
                <td className="font-mono">
                  {(data.beam_radius_at_image * 1e6).toFixed(2)} µm
                </td>
              </tr>
              <tr>
                <td className="pr-3 text-gray-600">Rayleigh range</td>
                <td className="font-mono">
                  {(data.rayleigh_range * 1e3).toFixed(4)} mm
                </td>
              </tr>
              <tr>
                <td className="pr-3 text-gray-600">Divergence (half angle)</td>
                <td className="font-mono">
                  {(data.divergence * 1e3).toFixed(3)} mrad
                </td>
              </tr>
            </tbody>
          </table>
          <LinePlot
            id="beam-radius"
            series={[
              {
                label: "Beam radius",
                color: "#2563eb",
                x: data.z.map((z) => z * 1e3),
                y: data.beam_radius.map((r) => r * 1e6),
              },
            ]}
            xLabel="Distance from the image plane (mm)"
            yLabel="1/e² radius (µm)"
          />
          <p className="text-gray-400">
            Paraxial (ABCD) propagation: aberrations and aperture clipping are
            not included.
          </p>
        </>
      )}
    </div>
  );
}
