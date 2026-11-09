import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { GlassExpertPanel } from "./GlassExpertPanel";
import { MeritPanel } from "./MeritPanel";
import { newSurface } from "./lensEdit";
import type { LensData } from "../../types";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

const lens: LensData = {
  name: "Achromat",
  surfaces: [
    {
      ...newSurface(),
      radius: 0.0489,
      thickness: 0.001,
      material: "N-BK7",
      semi_diameter: 0.005,
      is_stop: true,
    },
    { ...newSurface(), radius: -0.0489, thickness: 0.0005, material: "N-F2" },
    { ...newSurface(), radius: -0.3076, thickness: 0.098 },
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0,
  entrance_pupil_diameter: null,
  wavelengths: [587.56e-9],
  first_surface_position: 0,
  analysis_settings: {
    num_rays: 11,
    ray_types: ["chief"],
    aperture_fraction: 1,
    wavelength: 587.56e-9,
  },
};

describe("GlassExpertPanel", () => {
  it("runs the substitution and reports the swaps", async () => {
    const swapped = {
      ...lens,
      surfaces: lens.surfaces.map((s, i) =>
        i === 1 ? { ...s, material: "N-SF2" } : s,
      ),
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        lens: swapped,
        system: { components: [] },
        first_order: { efl: 0.1 },
        merit_before: 0.119,
        merit_after: 0.00019,
        substitutions: [
          { surface: 1, from: "N-F2", to: "N-SF2", merit: 0.00019 },
        ],
        evaluations: 13,
      }),
    } as Response);
    const onDone = vi.fn();
    render(
      <GlassExpertPanel
        lens={lens}
        disabled={false}
        maxEvaluations={100}
        onDone={onDone}
      />,
    );
    fireEvent.change(screen.getByLabelText("Glass candidates"), {
      target: { value: "12" },
    });
    fireEvent.click(screen.getByText("Substitute glasses"));
    await waitFor(() => screen.getByTestId("glass-result"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toMatchObject({ candidates: 12, max_evaluations: 100 });
    const text = screen.getByTestId("glass-result").textContent;
    expect(text).toContain("Surface 1: N-F2 → N-SF2");
    expect(text).toContain("Merit 0.1190 → 0.0001900");
    expect(onDone.mock.calls[0][0].lens).toEqual(swapped);
  });
});

describe("desensitizing in the merit panel", () => {
  it("is offered for the wavefront merit and dropped for transverse", () => {
    const onChange = vi.fn();
    const wavefront: LensData = {
      ...lens,
      merit: {
        kind: "wavefront",
        rings: 3,
        reference: "chief",
        image_weight: 1,
        operands: [],
      },
    };
    render(
      <MeritPanel
        lens={wavefront}
        displayUnit="mm"
        busy={false}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByLabelText("Desensitize"));
    expect(onChange.mock.calls[0][0].merit.desensitize).toEqual({
      weight: 1,
      tolerances: [],
      rings: 4,
    });
    fireEvent.change(screen.getByLabelText("Merit kind"), {
      target: { value: "transverse" },
    });
    expect(onChange.mock.calls[1][0].merit).toMatchObject({
      kind: "transverse",
      desensitize: null,
    });
  });

  it("is not offered for the transverse merit", () => {
    render(
      <MeritPanel
        lens={lens}
        displayUnit="mm"
        busy={false}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("Desensitize")).toBeNull();
  });
});
