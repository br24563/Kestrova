import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { PolarizationPanel, mapRange, rampColor } from "./PolarizationPanel";
import { SurfaceDetails } from "../lens/SurfaceDetails";
import { newSurface } from "../lens/lensEdit";
import type { OpticalSystem } from "../../types";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

const system: OpticalSystem = {
  components: [],
  wavelengths: [486e-9, 588e-9],
  object: { position: 0, height: 0, orientation: 0 },
  image_plane: { position: 0.1 },
  analysis_settings: {
    num_rays: 11,
    ray_types: ["chief"],
    aperture_fraction: 1,
    wavelength: 588e-9,
  },
};

describe("PolarizationPanel", () => {
  it("shows the pupil maps' ranges and the transmittance per wavelength", async () => {
    const map = [
      [null, 0.9, null],
      [0.91, 0.92, 0.9],
      [null, 0.9, null],
    ];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        pupil: [-1, 0, 1],
        field: 0,
        wavelength: 588e-9,
        transmittance: map,
        diattenuation: [
          [null, 0.01, null],
          [0.0, 0.0, 0.02],
          [null, 0.01, null],
        ],
        retardance: [
          [null, 0, null],
          [0, 0, Math.PI / 180],
          [null, 0, null],
        ],
        summary: {
          field: 0,
          wavelengths: [486e-9, 588e-9],
          per_wavelength: [0.905, 0.91],
          transmittance: 0.9075,
        },
      }),
    } as Response);
    render(<PolarizationPanel system={system} />);
    await waitFor(() => screen.getByTestId("pol-summary"));
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/analyze/polarization",
    );
    expect(screen.getByTestId("pol-transmittance").textContent).toContain(
      "90.00 % … 92.00 %",
    );
    expect(screen.getByTestId("pol-retardance").textContent).toContain(
      "0.000° … 1.000°",
    );
    const summary = screen.getByTestId("pol-summary").textContent;
    expect(summary).toContain("486.0 nm");
    expect(summary).toContain("90.75 %");
  });

  it("helpers: colour ramp ends and map range skip empty cells", () => {
    expect(rampColor(0)).toEqual([68, 1, 84]);
    expect(rampColor(1)).toEqual([253, 231, 37]);
    expect(
      mapRange([
        [null, 2],
        [1, null],
      ]),
    ).toEqual([1, 2]);
    expect(mapRange([[null]])).toEqual([0, 0]);
  });
});

describe("coating editor", () => {
  function renderSurface(surface = {}) {
    const onChange = vi.fn();
    render(
      <SurfaceDetails
        surface={{ ...newSurface(), material: "N-BK7", ...surface }}
        row={0}
        displayUnit="mm"
        onChange={onChange}
      />,
    );
    return onChange;
  }

  it("applies the quarter-wave preset and clears it", () => {
    const onChange = renderSurface();
    fireEvent.change(screen.getByLabelText("Coating"), {
      target: { value: "qw" },
    });
    const coating = onChange.mock.calls[0][0].coating;
    expect(coating.layers[0].material).toBe("MgF2");
    expect(coating.layers[0].thickness).toBeCloseTo(550e-9 / (4 * 1.38));
    fireEvent.change(screen.getByLabelText("Coating"), {
      target: { value: "none" },
    });
    expect(onChange.mock.calls[1][0]).toEqual({ coating: null });
  });

  it("edits, adds and removes layers", () => {
    const onChange = renderSurface({
      coating: {
        name: "Custom",
        layers: [{ material: "TiO2", thickness: 7e-8 }],
      },
    });
    fireEvent.click(screen.getByText("Add layer"));
    expect(onChange.mock.calls[0][0].coating.layers).toHaveLength(2);
    const nm = screen.getByLabelText("L1 nm") as HTMLInputElement;
    expect(nm.value).toBe("70");
    fireEvent.change(nm, { target: { value: "65" } });
    fireEvent.blur(nm);
    expect(onChange.mock.calls[1][0].coating.layers[0].thickness).toBeCloseTo(
      6.5e-8,
    );
    const mat = screen.getByLabelText(
      "Coating layer 1 material",
    ) as HTMLInputElement;
    fireEvent.change(mat, { target: { value: "Al2O3" } });
    fireEvent.blur(mat);
    expect(onChange.mock.calls[2][0].coating.layers[0].material).toBe("Al2O3");
    fireEvent.click(screen.getByLabelText("Remove coating layer 1"));
    expect(onChange.mock.calls[3][0]).toEqual({ coating: null });
  });
});
