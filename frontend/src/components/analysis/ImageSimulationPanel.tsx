/**
 * Image simulation: a test target through the real system (diffraction
 * PSF from the real wavefront, optionally wavelength-weighted and varying
 * over the field, relative illumination, distortion, sensor noise).
 */
import { useState } from "react";
import type { OpticalSystem } from "../../types";
import { simulateImage } from "../../api";
import type { ImageSimulationResult } from "../../api";

const TARGETS = ["bars", "siemens", "grid", "checkerboard", "edge", "point"];

export function ImageSimulationPanel({ system }: { system: OpticalSystem }) {
  const [target, setTarget] = useState("siemens");
  const [fullField, setFullField] = useState(false);
  const [poly, setPoly] = useState(true);
  const [noise, setNoise] = useState(false);
  const [result, setResult] = useState<ImageSimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(
        await simulateImage(system, {
          targetKind: target,
          fullField,
          polychromatic: poly,
          noise,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="p-4 space-y-3 text-xs" data-testid="image-simulation">
      <div className="flex flex-wrap items-center gap-3 text-gray-600">
        <h3 className="text-sm font-semibold text-gray-700 mr-auto">
          Image simulation
        </h3>
        <label className="flex items-center gap-1">
          Target
          <select
            aria-label="Target"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="border border-gray-200 rounded px-1 py-0.5"
          >
            {TARGETS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            aria-label="Whole field"
            checked={fullField}
            onChange={(e) => setFullField(e.target.checked)}
          />
          Whole field
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            aria-label="All wavelengths"
            checked={poly}
            onChange={(e) => setPoly(e.target.checked)}
          />
          All wavelengths
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            aria-label="Sensor noise"
            checked={noise}
            onChange={(e) => setNoise(e.target.checked)}
          />
          Sensor noise
        </label>
        <button
          onClick={run}
          disabled={running}
          className="px-3 py-1 bg-optical-600 text-white rounded hover:bg-optical-700 disabled:opacity-50"
        >
          {running ? "Simulating..." : "Simulate"}
        </button>
      </div>
      {error && (
        <p className="text-red-500" role="alert">
          {error}
        </p>
      )}
      {result?.png_base64 && (
        <img
          src={`data:image/png;base64,${result.png_base64}`}
          alt="Simulated image"
          className="w-80 h-80 border border-gray-200 [image-rendering:pixelated]"
        />
      )}
      <p className="text-gray-400">
        128 × 128 pixels of 5 µm. &quot;Whole field&quot; blends the axis and
        edge PSFs and applies the relative illumination and distortion.
      </p>
    </div>
  );
}
