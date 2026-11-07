import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { MtfPlot, fieldCount, parseFrequencies } from "./MtfPlot";
import type { OpticalSystem } from "../../types";

const system: OpticalSystem = {
  components: [],
  wavelengths: [550e-9],
  object: { position: 0, height: 0.01, orientation: 0 },
  image_plane: { position: 0.1 },
  analysis_settings: {
    num_rays: 11,
    ray_types: ["chief"],
    aperture_fraction: 1,
    wavelength: 550e-9,
  },
};

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

describe("MtfPlot helpers", () => {
  it("counts the field points the backend analyses", () => {
    expect(fieldCount(system)).toBe(3); // default 0, 0.7, 1
    expect(
      fieldCount({ ...system, object: { ...system.object, height: 0 } }),
    ).toBe(1);
    expect(
      fieldCount({
        ...system,
        fields: [
          { x: 0, y: 0, weight: 1, vux: 0, vlx: 0, vuy: 0, vly: 0 },
          { x: 0, y: 1, weight: 1, vux: 0, vlx: 0, vuy: 0, vly: 0 },
        ],
      }),
    ).toBe(2);
  });

  it("parses a frequency list", () => {
    expect(parseFrequencies("10, 30 50")).toEqual([10, 30, 50]);
    expect(parseFrequencies("abc, -5, 0, 20")).toEqual([20]);
  });
});

describe("MtfPlot", () => {
  it("requests the three analyses and shows the plots", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const url = String(input);
        const body = url.includes("through-focus")
          ? {
              field: 0,
              method: "fft",
              frequency_cyc_per_mm: 50,
              defocus_mm: [-0.1, 0, 0.1],
              tangential: [0.2, 0.5, 0.2],
              sagittal: [0.2, 0.5, 0.2],
              best_focus_mm: { tangential: 0, sagittal: 0, mean: 0 },
              half_peak_range_mm: 0.1,
              peak_at_scan_edge: true,
            }
          : url.includes("mtf-vs-field")
            ? {
                method: "fft",
                field_fraction: [0, 1],
                frequencies_cyc_per_mm: [30],
                tangential: [[0.8, 0.4]],
                sagittal: [[0.8, 0.5]],
              }
            : {
                field: 0,
                method: "fft",
                frequency_cyc_per_mm: [0, 100],
                tangential: [1, 0.3],
                sagittal: [1, 0.35],
                diffraction_limit: [1, 0.4],
                cutoff_cyc_per_mm: 250,
              };
        return { ok: true, status: 200, json: async () => body } as Response;
      });
    render(<MtfPlot system={system} displayUnit="mm" />);
    await waitFor(() => {
      expect(document.getElementById("mtf-curves")).toBeTruthy();
      expect(document.getElementById("mtf-focus")).toBeTruthy();
      expect(document.getElementById("mtf-field")).toBeTruthy();
    });
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.endsWith("/analyze/mtf"))).toBe(true);
    expect(urls.some((u) => u.includes("/analyze/through-focus-mtf"))).toBe(
      true,
    );
    expect(urls.some((u) => u.includes("/analyze/mtf-vs-field"))).toBe(true);
    expect(screen.getByText(/cutoff 250 cycles\/mm/)).toBeTruthy();
    expect(screen.getByTestId("best-focus").textContent).toContain(
      "edge of the scan",
    );
  });
});
