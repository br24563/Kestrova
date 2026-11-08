import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { SurfaceDetails } from "./SurfaceDetails";
import { LensDataEditor } from "./LensDataEditor";
import { newSurface } from "./lensEdit";
import type { LensData, LensSurface, OpticalSystem } from "../../types";

afterEach(cleanup);

function renderDetails(surface: Partial<LensSurface>, unit: "mm" | "m" = "mm") {
  const onChange = vi.fn();
  render(
    <SurfaceDetails
      surface={{ ...newSurface(), ...surface }}
      row={1}
      displayUnit={unit}
      onChange={onChange}
    />,
  );
  return onChange;
}

function commit(label: string, text: string) {
  const input = screen.getByLabelText(label) as HTMLInputElement;
  fireEvent.change(input, { target: { value: text } });
  fireEvent.blur(input);
}

describe("SurfaceDetails", () => {
  it("shows aspheric terms in lens units and stores them in SI", () => {
    // A4 = 100 m^-3 is 1e-7 mm^-3
    const onChange = renderDetails({
      surface_type: "even_asphere",
      aspheric_coefficients: [100],
    });
    expect((screen.getByLabelText("A4") as HTMLInputElement).value).toBe(
      "1e-7",
    );
    commit("A6", "3e-10"); // mm^-5 -> m^-5: * 1e15
    const next = onChange.mock.calls[0][0].aspheric_coefficients;
    expect(next[0]).toBeCloseTo(100);
    expect(next[1]).toBeCloseTo(3e5);
  });

  it("edits odd asphere terms separately", () => {
    const onChange = renderDetails({ surface_type: "odd_asphere" });
    commit("A3", "0.01"); // mm^-2 -> m^-2: * 1e6
    expect(onChange).toHaveBeenCalledWith({ odd_coefficients: [1e4] });
  });

  it("edits Zernike terms and the normalisation radius as lengths", () => {
    const onChange = renderDetails({
      surface_type: "zernike",
      norm_radius: 0.01,
    });
    expect((screen.getByLabelText("Norm. R") as HTMLInputElement).value).toBe(
      "10",
    );
    commit("Z4", "0.002");
    expect(onChange.mock.calls[0][0].zernike_coefficients[3]).toBeCloseTo(2e-6);
    commit("Norm. R", "12.5");
    expect(onChange.mock.calls[1][0].norm_radius).toBeCloseTo(0.0125);
  });

  it("adds and removes XY polynomial terms", () => {
    const onChange = renderDetails({
      surface_type: "xy_polynomial",
      norm_radius: 0.01,
      xy_coefficients: { x2y0: 1e-6 },
    });
    expect((screen.getByLabelText("x2y0") as HTMLInputElement).value).toBe(
      "0.001",
    );
    fireEvent.change(screen.getByLabelText("Add XY term"), {
      target: { value: "x1y2" },
    });
    expect(onChange).toHaveBeenLastCalledWith({
      xy_coefficients: { x2y0: 1e-6, x1y2: 0 },
    });
    commit("x2y0", "0");
    expect(onChange).toHaveBeenLastCalledWith({ xy_coefficients: {} });
  });

  it("shows phase terms in rad per lens unit", () => {
    // -2e5 rad/m^2 = -0.2 rad/mm^2
    const onChange = renderDetails({
      surface_type: "diffractive",
      phase_coefficients: [-2e5],
      diffraction_order: 1,
    });
    expect((screen.getByLabelText("r^2") as HTMLInputElement).value).toBe(
      "-0.2",
    );
    commit("Order", "2");
    expect(onChange).toHaveBeenCalledWith({ diffraction_order: 2 });
  });

  it("sets a toroid's x radius and a Q type", () => {
    const onChange = renderDetails({ surface_type: "toroid", radius: 0.05 });
    commit("Radius x", "80");
    expect(onChange.mock.calls[0][0].radius_x).toBeCloseTo(0.08);
    cleanup();
    const onQ = renderDetails({ surface_type: "q_asphere", norm_radius: 0.01 });
    fireEvent.change(screen.getByLabelText("Q type"), {
      target: { value: "qcon" },
    });
    expect(onQ).toHaveBeenCalledWith({ q_type: "qcon" });
  });

  it("sets non-circular apertures and obscurations", () => {
    const onChange = renderDetails({ semi_diameter: 0.01 });
    fireEvent.change(screen.getByLabelText("Aperture shape"), {
      target: { value: "rectangular" },
    });
    expect(onChange).toHaveBeenLastCalledWith({
      aperture_shape: "rectangular",
      aperture_half_x: 0.01,
      aperture_half_y: 0.01,
    });
    commit("Obscur.", "3");
    expect(onChange.mock.calls[1][0].obscuration_semi).toBeCloseTo(0.003);
    cleanup();
    const onClear = renderDetails({ obscuration_semi: 0.003 });
    commit("Obscur.", "0");
    expect(onClear).toHaveBeenLastCalledWith({ obscuration_semi: null });
  });

  it("keeps the stop circular and ignores text that is not a number", () => {
    const onChange = renderDetails({ is_stop: true, surface_type: "toroid" });
    expect(
      (screen.getByLabelText("Aperture shape") as HTMLSelectElement).disabled,
    ).toBe(true);
    commit("Radius x", "abc");
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("surface types in the editor", () => {
  const system: OpticalSystem = {
    components: [],
    wavelengths: [550e-9],
    object: { position: 0, height: 0, orientation: 0 },
    image_plane: { position: 0.1 },
    analysis_settings: {
      num_rays: 11,
      ray_types: ["chief"],
      aperture_fraction: 1,
      wavelength: 550e-9,
    },
  };
  const lens: LensData = {
    name: "Singlet",
    surfaces: [
      {
        ...newSurface(),
        is_stop: true,
        radius: 0.05,
        semi_diameter: 0.006,
        thickness: 0.005,
        material: "N-BK7",
      },
      { ...newSurface(), radius: -0.05, thickness: 0.09 },
    ],
    object_distance: null,
    object_height: 0,
    field_angle: 0,
    entrance_pupil_diameter: null,
    wavelengths: [550e-9],
    first_surface_position: 0,
    analysis_settings: system.analysis_settings,
  };

  it("gives a new Zernike surface a normalisation radius and shows its details", () => {
    const onChange = vi.fn();
    render(
      <LensDataEditor
        lens={lens}
        system={system}
        displayUnit="mm"
        dirty={false}
        onChange={onChange}
        onResolved={vi.fn()}
        onImported={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Type, surface 0"), {
      target: { value: "zernike" },
    });
    const row = onChange.mock.calls[0][0].surfaces[0];
    expect(row.surface_type).toBe("zernike");
    expect(row.norm_radius).toBe(0.006);
    expect(screen.queryByTestId("surface-details")).toBeNull();
    fireEvent.click(screen.getAllByText("STO")[0]);
    expect(screen.getByTestId("surface-details").textContent).toContain(
      "Surface 0 details",
    );
  });
});
