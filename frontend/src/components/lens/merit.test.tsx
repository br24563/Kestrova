import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { MeritPanel } from "./MeritPanel";
import { ConstraintsEditor } from "./ConstraintsEditor";
import { OptimizeReport } from "./OptimizeReport";
import { newSurface } from "./lensEdit";
import type { LensData, LensOptimizeResult, MeritSpec } from "../../types";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

const lens: LensData = {
  name: "Singlet",
  surfaces: [
    {
      ...newSurface(),
      radius: 0.05,
      thickness: 0.004,
      material: "N-BK7",
      semi_diameter: 0.006,
      is_stop: true,
    },
    { ...newSurface(), radius: -0.05, thickness: 0.09 },
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0.1,
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

const withOperands = (operands: MeritSpec["operands"]): LensData => ({
  ...lens,
  merit: {
    kind: "transverse",
    rings: 3,
    reference: "chief",
    image_weight: 1,
    operands,
  },
});

function renderPanel(l: LensData) {
  const onChange = vi.fn();
  render(
    <MeritPanel lens={l} displayUnit="mm" busy={false} onChange={onChange} />,
  );
  return onChange;
}

function commit(label: string, text: string) {
  const input = screen.getByLabelText(label) as HTMLInputElement;
  fireEvent.change(input, { target: { value: text } });
  fireEvent.blur(input);
}

describe("MeritPanel", () => {
  it("starts from the default merit and changes its image term", () => {
    const onChange = renderPanel(lens);
    expect(
      (screen.getByLabelText("Merit kind") as HTMLSelectElement).value,
    ).toBe("transverse");
    fireEvent.change(screen.getByLabelText("Merit kind"), {
      target: { value: "wavefront" },
    });
    expect(onChange.mock.calls[0][0].merit).toMatchObject({
      kind: "wavefront",
      rings: 3,
      operands: [],
    });
    fireEvent.change(screen.getByLabelText("Merit reference"), {
      target: { value: "centroid" },
    });
    expect(onChange.mock.calls[1][0].merit.reference).toBe("centroid");
    fireEvent.change(screen.getByLabelText("Merit rings"), {
      target: { value: "6" },
    });
    expect(onChange.mock.calls[2][0].merit.rings).toBe(6);
  });

  it("adds operands with targets in display units", () => {
    const onChange = renderPanel(lens);
    fireEvent.click(screen.getByText("Add operand"));
    expect(onChange.mock.calls[0][0].merit.operands).toEqual([
      { kind: "distortion", target: 0, weight: 1, field: null },
    ]);
    cleanup();
    const second = renderPanel(
      withOperands([{ kind: "distortion", target: 0, weight: 1, field: null }]),
    );
    commit("Operand 1 target", "-2"); // percent
    expect(second.mock.calls[0][0].merit.operands[0].target).toBeCloseTo(-0.02);
    fireEvent.change(screen.getByLabelText("Operand 1 field"), {
      target: { value: "0" },
    });
    expect(second.mock.calls[1][0].merit.operands[0].field).toBe(0);
    fireEvent.change(screen.getByLabelText("Operand 1 property"), {
      target: { value: "edge_thickness" },
    });
    expect(second.mock.calls[2][0].merit.operands[0]).toMatchObject({
      kind: "edge_thickness",
      surface: 0,
      field: null,
    });
  });

  it("converts angles and lengths, and weights", () => {
    const onChange = renderPanel(
      withOperands([
        { kind: "chief_ray_angle", target: 0, weight: 1 },
        { kind: "efl", target: 0.1, weight: 1 },
      ]),
    );
    commit("Operand 1 target", "3");
    expect(onChange.mock.calls[0][0].merit.operands[0].target).toBeCloseTo(
      (3 * Math.PI) / 180,
    );
    expect(
      (screen.getByLabelText("Operand 2 target") as HTMLInputElement).value,
    ).toBe("100");
    commit("Operand 2 weight", "5");
    expect(onChange.mock.calls[1][0].merit.operands[1].weight).toBe(5);
  });

  it("evaluates the merit and shows each operand's value", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        merit: 1.2e-10,
        configurations: [
          {
            configuration: 0,
            image_kind: "transverse",
            image_rms: 1.1e-5,
            image_contribution: 1.21e-10,
            merit: 1.2e-10,
            operands: [
              {
                kind: "efl",
                target: 0.1,
                weight: 1,
                value: 0.1012,
                contribution: 1.4e-6,
                index: 0,
              },
            ],
          },
        ],
      }),
    } as Response);
    renderPanel(withOperands([{ kind: "efl", target: 0.1, weight: 1 }]));
    fireEvent.click(screen.getByText("Evaluate"));
    await waitFor(() => screen.getByTestId("merit-report"));
    expect(String(fetchMock.mock.calls[0][0])).toContain("/lens/merit");
    expect(screen.getByTestId("merit-report").textContent).toContain(
      "RMS spot 11.000 µm",
    );
    expect(screen.getByTestId("operand-0-value").textContent).toContain(
      "101.2 mm",
    );
  });
});

describe("new properties elsewhere", () => {
  it("constraints take a field for field properties", () => {
    const onChange = vi.fn();
    render(
      <ConstraintsEditor
        lens={{
          ...lens,
          constraints: [{ kind: "chief_ray_angle", target: 0, field: null }],
        }}
        displayUnit="mm"
        statuses={null}
        busy={false}
        onChange={onChange}
        onCheck={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Constraint 1 field"), {
      target: { value: "2" },
    });
    expect(onChange.mock.calls[0][0][0].field).toBe(2);
  });

  it("the optimize report shows a wavefront merit in waves", () => {
    const result = {
      lens,
      system: {} as LensOptimizeResult["system"],
      first_order: {} as LensOptimizeResult["first_order"],
      variables: {},
      merit_before: 0.04,
      merit_after: 0.01,
      rms_spot_before: 0.2,
      rms_spot_after: 0.1,
      image_kind: "wavefront",
      evaluations: 10,
      success: true,
      message: "converged",
    } as LensOptimizeResult;
    render(<OptimizeReport result={result} displayUnit="mm" />);
    expect(screen.getByTestId("optimize-report").textContent).toContain(
      "RMS wavefront 0.2000 → 0.1000 waves",
    );
  });
});
