import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { GlobalSearchPanel } from "./GlobalSearchPanel";
import { newSurface } from "./lensEdit";
import type { LensData } from "../../types";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

const lens: LensData = {
  name: "Doublet",
  surfaces: [
    {
      ...newSurface(),
      radius: 0.09,
      thickness: 0.004,
      material: "N-BK7",
      semi_diameter: 0.005,
      is_stop: true,
      variables: ["radius"],
    },
    { ...newSurface(), radius: -0.05, thickness: 0.09 },
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0,
  entrance_pupil_diameter: null,
  wavelengths: [550e-9],
  first_surface_position: 0,
  analysis_settings: {
    num_rays: 11,
    ray_types: ["chief"],
    aperture_fraction: 1,
    wavelength: 550e-9,
  },
};

const design = (r: number): LensData => ({
  ...lens,
  surfaces: [{ ...lens.surfaces[0], radius: r }, lens.surfaces[1]],
});

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("GlobalSearchPanel", () => {
  it("runs the search and loads the chosen design", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        starts: 9,
        feasible: 6,
        distinct: 2,
        evaluations: 1200,
        solutions: [
          {
            lens: design(0.0446),
            merit: 1e-12,
            variables: { "0.radius": 0.0446 },
            start: 4,
            first_order: { efl: 0.1, f_number: 10 },
          },
          {
            lens: design(0.0962),
            merit: 3e-12,
            variables: { "0.radius": 0.0962 },
            start: 0,
            first_order: { efl: 0.1, f_number: 10 },
          },
        ],
      }),
    );
    const onUse = vi.fn();
    render(
      <GlobalSearchPanel
        lens={lens}
        displayUnit="mm"
        disabled={false}
        maxEvaluations={150}
        onUse={onUse}
      />,
    );
    fireEvent.change(screen.getByLabelText("Global search starts"), {
      target: { value: "8" },
    });
    fireEvent.change(screen.getByLabelText("Global search workers"), {
      target: { value: "4" },
    });
    fireEvent.click(screen.getByText("Global search"));
    await waitFor(() => screen.getByTestId("global-solutions"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/lens/global-optimize",
    );
    expect(body).toMatchObject({ starts: 8, workers: 4, max_evaluations: 150 });
    const text = screen.getByTestId("global-search").textContent;
    expect(text).toContain("2 distinct designs from 9 starts");
    expect(text).toContain("as given");
    fireEvent.click(screen.getByLabelText("Use design 2"));
    expect(onUse).toHaveBeenCalledWith(design(0.0962));
  });

  it("says when no design meets the constraints", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        starts: 3,
        feasible: 0,
        distinct: 0,
        evaluations: 90,
        solutions: [],
      }),
    );
    render(
      <GlobalSearchPanel
        lens={lens}
        displayUnit="mm"
        disabled={false}
        maxEvaluations={100}
        onUse={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Global search"));
    await waitFor(() =>
      screen.getByText(
        "No start reached a design that meets every constraint.",
      ),
    );
  });

  it("is disabled without variables", () => {
    render(
      <GlobalSearchPanel
        lens={lens}
        displayUnit="mm"
        disabled={true}
        maxEvaluations={100}
        onUse={vi.fn()}
      />,
    );
    expect(
      (screen.getByText("Global search") as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
