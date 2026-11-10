import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { EnvironmentPanel, parseTemperatures } from "./EnvironmentPanel";
import { GhostTracePanel } from "./GhostTracePanel";
import { BeamPanel } from "./BeamPanel";
import { ImageSimulationPanel } from "./ImageSimulationPanel";
import { newSurface } from "../lens/lensEdit";
import type { LensData, OpticalSystem } from "../../types";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

const settings = {
  num_rays: 11,
  ray_types: ["chief"],
  aperture_fraction: 1,
  wavelength: 588e-9,
};
const system: OpticalSystem = {
  components: [],
  wavelengths: [588e-9],
  object: { position: 0, height: 0, orientation: 0 },
  image_plane: { position: 0.1 },
  analysis_settings: settings,
};
const lens: LensData = {
  name: "Singlet",
  surfaces: [
    {
      ...newSurface(),
      radius: 0.1,
      thickness: 0.001,
      material: "N-BK7",
      semi_diameter: 0.0025,
      is_stop: true,
    },
    { ...newSurface(), radius: -0.1, thickness: 0.097 },
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0,
  entrance_pupil_diameter: null,
  wavelengths: [588e-9],
  first_surface_position: 0,
  analysis_settings: settings,
};

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("EnvironmentPanel", () => {
  it("parses temperatures", () => {
    expect(parseTemperatures("-20, 0 20")).toEqual([-20, 0, 20]);
    expect(parseTemperatures("a, 1")).toBeNull();
    expect(parseTemperatures("")).toBeNull();
  });

  it("runs the analysis and shows the drift from 20 C", async () => {
    const row = (t: number, shift: number) => ({
      temperature: t,
      pressure: 101325,
      efl: 0.0967,
      bfl: 0.0963,
      focus_shift: shift,
      rms_wavefront: 0.05,
      depth_of_focus: 3e-5,
    });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        ok({ rows: [row(0, -0.002), row(20, -0.002005), row(60, -0.00201)] }),
      );
    render(<EnvironmentPanel lens={lens} displayUnit="mm" />);
    fireEvent.change(screen.getByLabelText("Temperatures"), {
      target: { value: "0, 20, 60" },
    });
    fireEvent.change(screen.getByLabelText("Housing CTE"), {
      target: { value: "23.6" },
    });
    fireEvent.click(screen.getByText("Analyse"));
    await waitFor(() => screen.getByTestId("environment-table"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toMatchObject({
      temperatures: [0, 20, 60],
      pressure: 101325,
      mount_cte: 23.6,
    });
    const text = screen.getByTestId("environment-table").textContent;
    expect(text).toContain("-5.00"); // 60 C: 5 um from 20 C
    expect(text).toContain("in focus");
  });

  it("asks for a lens", () => {
    render(<EnvironmentPanel lens={null} displayUnit="mm" />);
    expect(screen.getByText(/works on the lens data/)).toBeTruthy();
  });
});

describe("GhostTracePanel", () => {
  it("lists the ghosts", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        field: 0,
        wavelength: 588e-9,
        image_rms_radius: 2e-6,
        ghosts: [
          {
            surfaces: [3, 2],
            labels: ["", ""],
            fraction: 1,
            power: 1.8e-3,
            rms_radius: 1.7e-4,
            centroid: [0, 0],
            focus_shift: -0.00667,
            relative_irradiance: 2.5e-7,
          },
        ],
      }),
    );
    render(<GhostTracePanel system={system} />);
    await waitFor(() => screen.getByTestId("ghost-table"));
    const text = screen.getByTestId("ghost-table").textContent;
    expect(text).toContain("S3 then S2");
    expect(text).toContain("1.80e-3");
    expect(text).toContain("-6.670");
  });
});

describe("BeamPanel", () => {
  it("propagates the beam with the inputs in mm", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        wavelength: 1064e-9,
        m2: 1,
        matrix: [1, 0, -10, 1],
        waist_radius: 3.4e-5,
        waist_position: -0.05,
        rayleigh_range: 0.0034,
        divergence: 0.01,
        beam_radius_at_image: 0.001,
        wavefront_radius_at_image: 0.05,
        z: [-0.06, -0.05, -0.04],
        beam_radius: [4e-5, 3.4e-5, 4e-5],
      }),
    );
    render(<BeamPanel system={system} />);
    await waitFor(() => screen.getByTestId("beam-results"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toMatchObject({
      waist_radius: 1e-3,
      waist_distance: 0,
      m2: 1,
    });
    expect(screen.getByTestId("beam-results").textContent).toContain(
      "34.00 µm",
    );
  });
});

describe("ImageSimulationPanel", () => {
  it("simulates and shows the image", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        ok({ metadata: {}, quality: {}, png_base64: "iVBORw0KGgo=" }),
      );
    render(<ImageSimulationPanel system={system} />);
    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "grid" },
    });
    fireEvent.click(screen.getByLabelText("Whole field"));
    fireEvent.click(screen.getByText("Simulate"));
    await waitFor(() => screen.getByAltText("Simulated image"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toMatchObject({
      target_kind: "grid",
      full_field: true,
      polychromatic: true,
      include_image: true,
    });
  });
});
