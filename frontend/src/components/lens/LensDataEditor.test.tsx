import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { LensDataEditor } from "./LensDataEditor";
import { newSurface } from "./lensEdit";
import type { LensData, OpticalSystem } from "../../types";

const system: OpticalSystem = {
  components: [],
  wavelengths: [550e-9],
  object: { position: 0, height: 0, orientation: 0 },
  image_plane: { position: 0.1 },
  analysis_settings: { num_rays: 11, ray_types: ["chief"], aperture_fraction: 1, wavelength: 550e-9 },
};

const lens: LensData = {
  name: "",
  surfaces: [
    { ...newSurface(), label: "STO", is_stop: true, semi_diameter: 0.005, thickness: 0.001 },
    { ...newSurface(), element: "L1", radius: 0.05, thickness: 0.005, material: "N-BK7" },
    { ...newSurface(), element: "L1", radius: -0.05, thickness: 0.09, semi_diameter: 0.006, semi_diameter_auto: true },
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0,
  entrance_pupil_diameter: null,
  wavelengths: [550e-9],
  first_surface_position: 0,
  analysis_settings: system.analysis_settings,
};

function setup() {
  const props = {
    lens,
    system,
    displayUnit: "mm" as const,
    dirty: false,
    onChange: vi.fn(),
    onResolved: vi.fn(),
    onImported: vi.fn(),
  };
  render(<LensDataEditor {...props} />);
  return props;
}

describe("LensDataEditor", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(cleanup);

  it("shows one row per surface in display units, flat as Infinity, auto apertures", () => {
    setup();
    expect((screen.getByLabelText("Radius, surface 0") as HTMLInputElement).value).toBe("Infinity");
    expect((screen.getByLabelText("Radius, surface 1") as HTMLInputElement).value).toBe("50");
    expect((screen.getByLabelText("Thickness, surface 2") as HTMLInputElement).value).toBe("90");
    expect(screen.getByText("6.000 auto")).toBeTruthy();
  });

  it("commits an edited thickness in meters", () => {
    const { onChange } = setup();
    const cell = screen.getByLabelText("Thickness, surface 1");
    fireEvent.change(cell, { target: { value: "7" } });
    fireEvent.blur(cell);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].surfaces[1].thickness).toBeCloseTo(0.007);
  });

  it("attaches a marginal height solve to a thickness", () => {
    const { onChange } = setup();
    fireEvent.click(screen.getByLabelText("Thickness flag, surface 2"));
    fireEvent.click(screen.getByLabelText("Solve"));
    const next: LensData = onChange.mock.calls[0][0];
    expect(next.surfaces[2].solves.thickness).toEqual({ kind: "marginal_height", target: 0 });
  });

  it("resolves through the backend and hands back the system", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ lens, system, first_order: { efl: 0.05, image_z: 0.096, entrance_pupil_diameter: 0.01 } }),
    } as Response);
    const { onResolved } = setup();
    fireEvent.click(screen.getByText("Resolve"));
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
    expect(onResolved.mock.calls[0][0].system).toEqual(system);
    expect(screen.getByText(/EFL 50.000 mm/)).toBeTruthy();
  });

  it("disables Optimize without variables", () => {
    setup();
    expect((screen.getByText(/Optimize \(0 variables\)/) as HTMLButtonElement).disabled).toBe(true);
  });
});
