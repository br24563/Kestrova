import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { LensDataEditor } from "./LensDataEditor";
import { ConstraintsEditor } from "./ConstraintsEditor";
import { OptimizeReport } from "./OptimizeReport";
import {
  LensTolerancePanel,
  limitFromDisplay,
  limitToDisplay,
} from "./LensTolerancePanel";
import {
  hasParameter,
  modelGlassName,
  newSurface,
  parseModelGlass,
  setMaterial,
  setModifier,
} from "./lensEdit";
import type {
  LensData,
  LensOptimizeResult,
  LensToleranceResult,
  OpticalSystem,
} from "../../types";

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

function makeLens(material = "N-BK7"): LensData {
  return {
    name: "",
    surfaces: [
      {
        ...newSurface(),
        label: "STO",
        is_stop: true,
        semi_diameter: 0.005,
        thickness: 0.001,
      },
      {
        ...newSurface(),
        element: "L1",
        radius: 0.05,
        thickness: 0.005,
        material,
      },
      { ...newSurface(), element: "L1", radius: -0.05, thickness: 0.09 },
    ],
    object_distance: null,
    object_height: 0,
    field_angle: 0,
    entrance_pupil_diameter: null,
    wavelengths: [550e-9],
    first_surface_position: 0,
    analysis_settings: system.analysis_settings,
  };
}

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

describe("model glasses", () => {
  it("parses and writes model glass names", () => {
    expect(parseModelGlass("MODEL:1.62:36.3")).toEqual([1.62, 36.3]);
    expect(parseModelGlass("model:1.5:64")).toEqual([1.5, 64]);
    expect(parseModelGlass("N-BK7")).toBeNull();
    expect(parseModelGlass(null)).toBeNull();
    expect(modelGlassName(1.62, 36.3)).toBe("MODEL:1.62:36.3");
  });

  it("has nd / Vd parameters only on a model glass surface", () => {
    const lens = makeLens("MODEL:1.6:40");
    expect(hasParameter(lens.surfaces[1], "glass_nd")).toBe(true);
    expect(hasParameter(lens.surfaces[0], "glass_nd")).toBe(false);
    expect(hasParameter(makeLens().surfaces[1], "glass_vd")).toBe(false);
  });

  it("drops glass flags when the material stops being a model glass", () => {
    let s = makeLens("MODEL:1.6:40").surfaces[1];
    s = setModifier(s, "glass_nd", { kind: "variable" });
    s = setModifier(s, "radius", { kind: "variable" });
    expect(setMaterial(s, "MODEL:1.7:30").variables).toContain("glass_nd");
    expect(setMaterial(s, "N-SF5").variables).toEqual(["radius"]);
  });

  it("shows nd / Vd flags in the editor for a model glass", () => {
    render(
      <LensDataEditor
        lens={makeLens("MODEL:1.6:40")}
        system={system}
        displayUnit="mm"
        dirty={false}
        onChange={vi.fn()}
        onResolved={vi.fn()}
        onImported={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Glass nd flag, surface 1")).toBeTruthy();
    expect(screen.getByLabelText("Glass Vd flag, surface 1")).toBeTruthy();
    expect(screen.queryByLabelText("Glass nd flag, surface 0")).toBeNull();
    expect(screen.getByText("Snap model glasses to catalog")).toBeTruthy();
  });

  it("snaps model glasses through the backend and lists the substitutions", async () => {
    const snapped = makeLens("N-BAF10");
    const fetchMock = mockFetch({
      lens: snapped,
      substitutions: [{ surface: 1, model: "MODEL:1.6:40", glass: "N-BAF10" }],
    });
    const onChange = vi.fn();
    render(
      <LensDataEditor
        lens={makeLens("MODEL:1.6:40")}
        system={system}
        displayUnit="mm"
        dirty={false}
        onChange={onChange}
        onResolved={vi.fn()}
        onImported={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Snap model glasses to catalog"));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(snapped));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/lens/snap-glasses");
    expect(screen.getByTestId("substitutions").textContent).toContain(
      "N-BAF10",
    );
  });
});

describe("ConstraintsEditor", () => {
  it("adds an EFL target and shows it in display units", () => {
    const onChange = vi.fn();
    const lens = makeLens();
    const { rerender } = render(
      <ConstraintsEditor
        lens={lens}
        displayUnit="mm"
        statuses={null}
        busy={false}
        onChange={onChange}
        onCheck={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Add constraint"));
    const added = onChange.mock.calls[0][0];
    expect(added).toEqual([{ kind: "efl", target: 0.1, surface: null }]);
    rerender(
      <ConstraintsEditor
        lens={{ ...lens, constraints: added }}
        displayUnit="mm"
        statuses={[{ ...added[0], value: 0.1, satisfied: true }]}
        busy={false}
        onChange={onChange}
        onCheck={vi.fn()}
      />,
    );
    expect(
      (screen.getByLabelText("Constraint 1 target") as HTMLInputElement).value,
    ).toBe("100");
    expect(screen.getByTestId("constraint-0-value").textContent).toContain(
      "100 mm ✓",
    );
  });

  it("gives edge thickness a surface and converts limits to meters", () => {
    const onChange = vi.fn();
    const lens: LensData = {
      ...makeLens(),
      constraints: [{ kind: "efl", target: 0.1, surface: null }],
    };
    render(
      <ConstraintsEditor
        lens={lens}
        displayUnit="mm"
        statuses={null}
        busy={false}
        onChange={onChange}
        onCheck={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Constraint 1 property"), {
      target: { value: "edge_thickness" },
    });
    expect(onChange.mock.calls[0][0][0]).toMatchObject({
      kind: "edge_thickness",
      surface: 1, // the first surface with glass after it
    });
    fireEvent.change(screen.getByLabelText("Constraint 1 mode"), {
      target: { value: "limits" },
    });
    const limits = onChange.mock.calls[1][0][0];
    expect(limits.target).toBeNull();
    expect(limits.minimum).toBeCloseTo(0.1);
  });
});

describe("OptimizeReport", () => {
  it("shows success, constraint values and the convergence chart", () => {
    const result: LensOptimizeResult = {
      lens: makeLens(),
      system,
      first_order: {
        efl: 0.1,
        bfl: null,
        f_number: null,
        working_f_number: null,
        image_z: null,
        image_height: null,
        magnification: null,
        entrance_pupil_diameter: 0.01,
        exit_pupil_z: null,
      },
      variables: {},
      merit_before: 1e-8,
      merit_after: 1e-10,
      rms_spot_before: 1e-4,
      rms_spot_after: 1e-5,
      evaluations: 40,
      iterations: 6,
      constraints: [
        {
          kind: "efl",
          target: 0.1,
          surface: null,
          value: 0.1,
          satisfied: true,
        },
      ],
      history: [
        { merit: 1e-8, violation: 1e-3, damping: 1e-3 },
        { merit: 1e-10, violation: 0, damping: 1e-4 },
      ],
      success: true,
      message: "converged",
    };
    render(<OptimizeReport result={result} displayUnit="mm" />);
    const report = screen.getByTestId("optimize-report");
    expect(report.textContent).toContain("Constraints met");
    expect(report.textContent).toContain("6 cycles, 40 evaluations");
    expect(report.textContent).toContain("= 100 mm");
    expect(report.querySelector("svg")).toBeTruthy();
  });
});

describe("LensTolerancePanel", () => {
  it("converts limits between stored and display units", () => {
    expect(limitToDisplay("DLT", 5e-5, "mm")).toBeCloseTo(0.05);
    expect(limitToDisplay("BTX", Math.PI / (180 * 60), "mm")).toBeCloseTo(1);
    expect(limitToDisplay("DLF", 3, "mm")).toBe(3);
    expect(limitFromDisplay("DLX", 0.025, "mm")).toBeCloseTo(2.5e-5);
    expect(limitFromDisplay("TRY", 2, "mm")).toBeCloseTo(
      (2 * Math.PI) / (180 * 60),
    );
  });

  it("runs the analysis and shows the prediction and sensitivities", async () => {
    const result: LensToleranceResult = {
      units: "waves",
      nominal_rms: 0.08,
      nominal_field_rms: [0.07, 0.08, 0.09],
      sensitivities: [
        {
          tolerance: "DLT S1",
          kind: "DLT",
          surface: 1,
          last_surface: null,
          limit: 5e-5,
          rms_plus: 0.081,
          rms_minus: 0.0805,
          change_plus: 0.001,
          change_minus: 0.0005,
        },
        {
          tolerance: "DLN S1",
          kind: "DLN",
          surface: 1,
          last_surface: null,
          limit: 5e-4,
          rms_plus: 0.09,
          rms_minus: 0.085,
          change_plus: 0.01,
          change_minus: 0.005,
        },
      ],
      rss_increase: 0.01,
      predicted: {
        mean: 0.083,
        std: 0.003,
        percentiles: {
          "50.0": 0.082,
          "84.13": 0.087,
          "97.72": 0.093,
          "99.87": 0.098,
        },
        cumulative: { probability: [0, 0.5, 1], rms: [0.079, 0.082, 0.1] },
      },
      predicted_fields: [],
      compensators: [
        { compensator: "back_focus", mean: 0, std: 1e-4, max_abs: 4e-4 },
      ],
      trials: 20000,
    };
    const fetchMock = mockFetch(result);
    render(<LensTolerancePanel lens={makeLens()} displayUnit="mm" />);
    fireEvent.click(screen.getByText("Analyse with default tolerances"));
    await waitFor(() => screen.getByTestId("tolerance-result"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.tolerances).toBeNull(); // the backend's default set
    expect(body.compensators).toEqual([{ kind: "back_focus", limit: null }]);
    expect(screen.getByTestId("pct-84.13").textContent).toBe("0.0870");
    // ranked by impact: the index tolerance first
    const rows = screen
      .getByLabelText("Sensitivities")
      .querySelectorAll("tbody tr");
    expect(rows[0].textContent).toContain("DLN S1");

    mockFetch({
      trials: 50,
      failed_trials: 0,
      rms: [],
      mean: 0.0832,
      std: 0.003,
      percentiles: { "50.0": 0.082, "84.13": 0.0868 },
    });
    fireEvent.click(screen.getByText("Check with Monte Carlo"));
    await waitFor(() => screen.getByTestId("monte-carlo-result"));
    expect(screen.getByTestId("monte-carlo-result").textContent).toContain(
      "0.0832",
    );
  });

  it("loads the default tolerances into an editable table", async () => {
    mockFetch({
      tolerances: [
        { kind: "DLF", surface: 1, limit: 3 },
        { kind: "BTX", surface: 1, last_surface: 2, limit: Math.PI / 10800 },
      ],
    });
    render(<LensTolerancePanel lens={makeLens()} displayUnit="mm" />);
    fireEvent.click(screen.getByText("Load default tolerances"));
    await waitFor(() => screen.getByLabelText("Tolerances"));
    expect(
      (screen.getByLabelText("BTX surface 1 limit") as HTMLInputElement).value,
    ).toBe("1");
    expect(screen.getByText("Analyse (2 tolerances)")).toBeTruthy();
  });
});
