import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { PsfPlot, psfShade } from "./PsfPlot";
import { FieldPlotsPanel } from "./FieldPlotsPanel";
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

function mockFetch(body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  } as Response);
}

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

describe("psfShade", () => {
  it("maps linear and logarithmic intensities to grey levels", () => {
    expect(psfShade(1, false)).toBe(255);
    expect(psfShade(0.5, false)).toBe(128);
    expect(psfShade(1, true)).toBe(255);
    expect(psfShade(1e-2, true)).toBe(128); // halfway through 4 decades
    expect(psfShade(1e-5, true)).toBe(0);
    expect(psfShade(-1, false)).toBe(0);
  });
});

describe("PsfPlot", () => {
  it("shows the image, statistics and energy curves", async () => {
    const fetchMock = mockFetch({
      field: 0,
      axis_mm: [-0.01, 0, 0.01],
      psf: [
        [0, 0.1, 0],
        [0.1, 1, 0.1],
        [0, 0.1, 0],
      ],
      centroid_mm: [0, 0],
      radius_mm: [0, 0.005, 0.01],
      encircled: [0, 0.7, 0.9],
      ensquared: [0, 0.75, 0.93],
      diffraction_limited_encircled: [0, 0.8, 0.9],
      radius_80_mm: 0.0072,
      airy_radius_mm: 0.0036,
      strehl: [{ wavelength: 550e-9, strehl: 0.91 }],
      energy_total: 1,
    });
    render(<PsfPlot system={system} displayUnit="mm" />);
    await waitFor(() => screen.getByTestId("psf-stats"));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/analyze/psf");
    const stats = screen.getByTestId("psf-stats").textContent;
    expect(stats).toContain("3.60 µm");
    expect(stats).toContain("7.20 µm");
    expect(stats).toContain("0.910");
    expect(screen.getByTestId("psf-image")).toBeTruthy();
    expect(document.getElementById("psf-energy")).toBeTruthy();
    expect(screen.queryByTestId("psf-window-warning")).toBeNull();
  });

  it("warns when the blur exceeds the diffraction window", async () => {
    mockFetch({
      field: 0,
      axis_mm: [-0.1, 0, 0.1],
      psf: [
        [0, 0, 0],
        [0, 1, 0],
        [0, 0, 0],
      ],
      centroid_mm: [0, 0],
      radius_mm: [0, 0.1],
      encircled: [0, 0.5],
      ensquared: [0, 0.55],
      diffraction_limited_encircled: [0, 1],
      radius_80_mm: null,
      airy_radius_mm: 0.005,
      strehl: [{ wavelength: 550e-9, strehl: 0.01 }],
      energy_total: 1,
      window_mm: 0.126,
      exceeds_window: true,
    });
    render(<PsfPlot system={system} displayUnit="mm" />);
    await waitFor(() => screen.getByTestId("psf-window-warning"));
    expect(screen.getByTestId("psf-window-warning").textContent).toContain(
      "126 µm",
    );
  });
});

describe("FieldPlotsPanel", () => {
  it("plots distortion with F-theta, lateral colour and illumination", async () => {
    mockFetch({
      field_fractions: [0, 0.5, 1],
      field_angle_deg: [0, 10, 20],
      distortion: [0, -0.01, -0.03],
      ftheta_distortion: [0, 0.01, 0.04],
      reference_wavelength: 587.56e-9,
      lateral_colour_mm: [
        { wavelength: 486.13e-9, offset_mm: [0, 0.001, 0.003] },
        { wavelength: 587.56e-9, offset_mm: [0, 0, 0] },
      ],
      relative_illumination: [1, 0.9, 0.7],
      cos4: [1, 0.94, 0.78],
    });
    render(<FieldPlotsPanel system={system} displayUnit="mm" />);
    await waitFor(() =>
      expect(document.getElementById("field-distortion")).toBeTruthy(),
    );
    expect(screen.getByText(/dashed: F-θ/)).toBeTruthy();
    expect(screen.getByText(/relative to 587.6 nm/)).toBeTruthy();
    expect(document.getElementById("field-colour")).toBeTruthy();
    expect(document.getElementById("field-illumination")).toBeTruthy();
  });
});
