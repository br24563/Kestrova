import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { ConfigurationsPanel } from "./ConfigurationsPanel";
import { ConstraintsEditor } from "./ConstraintsEditor";
import { LensDataEditor } from "./LensDataEditor";
import { newSurface } from "./lensEdit";
import type { LensData, OpticalSystem } from "../../types";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

const base: LensData = {
  name: "Zoom",
  surfaces: [
    {
      ...newSurface(),
      surface_type: "paraxial",
      focal_length: 0.1,
      thickness: 0.03,
      semi_diameter: 0.01,
      is_stop: true,
    },
    {
      ...newSurface(),
      surface_type: "paraxial",
      focal_length: 0.05,
      thickness: 0.05,
    },
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0.0175,
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

const zoomed: LensData = {
  ...base,
  configuration_names: ["Wide", "Tele"],
  zoom: [{ surface: 0, parameter: "thickness", values: [0.03, 0.05] }],
};

function renderPanel(lens: LensData, active = 0) {
  const onChange = vi.fn();
  const onActivate = vi.fn();
  render(
    <ConfigurationsPanel
      lens={lens}
      displayUnit="mm"
      active={active}
      busy={false}
      onChange={onChange}
      onActivate={onActivate}
    />,
  );
  return { onChange, onActivate };
}

function commit(label: string, text: string) {
  const input = screen.getByLabelText(label) as HTMLInputElement;
  fireEvent.change(input, { target: { value: text } });
  fireEvent.blur(input);
}

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("ConfigurationsPanel", () => {
  it("turns a lens into two configurations", () => {
    const { onChange } = renderPanel(base);
    expect(screen.queryByRole("table")).toBeNull();
    fireEvent.click(screen.getByText("Add configuration"));
    expect(onChange.mock.calls[0][0].configuration_names).toEqual(["1", "2"]);
  });

  it("adds a configuration, copying the last values", () => {
    const { onChange } = renderPanel(zoomed);
    fireEvent.click(screen.getByText("Add configuration"));
    const next = onChange.mock.calls[0][0];
    expect(next.configuration_names).toEqual(["Wide", "Tele", "3"]);
    expect(next.zoom[0].values).toEqual([0.03, 0.05, 0.05]);
  });

  it("adds a zoomed parameter filled with its current value", () => {
    const { onChange } = renderPanel({ ...zoomed, zoom: [] });
    fireEvent.click(screen.getByText("Add zoomed parameter"));
    expect(onChange.mock.calls[0][0].zoom).toEqual([
      { surface: 0, parameter: "focal_length", values: [0.1, 0.1] },
    ]);
  });

  it("shows values in lens units and stores metres", () => {
    const { onChange } = renderPanel(zoomed);
    const tele = screen.getByLabelText(
      "Zoom row 1 configuration 2",
    ) as HTMLInputElement;
    expect(tele.value).toBe("50");
    commit("Zoom row 1 configuration 2", "60");
    expect(onChange.mock.calls[0][0].zoom[0].values[1]).toBeCloseTo(0.06);
    // configuration 1 is also written to the surface table
    cleanup();
    const second = renderPanel(zoomed);
    commit("Zoom row 1 configuration 1", "25");
    const next = second.onChange.mock.calls[0][0];
    expect(next.zoom[0].values[0]).toBeCloseTo(0.025);
    expect(next.surfaces[0].thickness).toBeCloseTo(0.025);
  });

  it("zooms system parameters: field angle in degrees, an object at infinity", () => {
    const lens: LensData = {
      ...zoomed,
      zoom: [
        { surface: null, parameter: "field_angle", values: [0.0175, 0.0175] },
        { surface: null, parameter: "object_distance", values: [null, 1] },
      ],
    };
    const { onChange } = renderPanel(lens);
    expect(
      (screen.getByLabelText("Zoom row 2 configuration 1") as HTMLInputElement)
        .value,
    ).toBe("Infinity");
    commit("Zoom row 1 configuration 2", "10");
    expect(onChange.mock.calls[0][0].zoom[0].values[1]).toBeCloseTo(
      (10 * Math.PI) / 180,
    );
    expect(screen.queryByLabelText("Zoom row 1 variable")).toBeNull();
  });

  it("flags a zoom row as variable and removes rows", () => {
    const { onChange } = renderPanel(zoomed);
    fireEvent.click(screen.getByLabelText("Zoom row 1 variable"));
    expect(onChange.mock.calls[0][0].zoom[0].variable).toBe(true);
    fireEvent.click(screen.getByLabelText("Remove zoom row 1"));
    expect(onChange.mock.calls[1][0].zoom).toEqual([]);
  });

  it("removing one of two configurations leaves a single lens", () => {
    const { onChange, onActivate } = renderPanel(zoomed, 1);
    fireEvent.click(screen.getByLabelText("Remove configuration 2"));
    const next = onChange.mock.calls[0][0];
    expect(next.configuration_names).toEqual([]);
    expect(next.zoom).toEqual([]);
    expect(onActivate).toHaveBeenCalledWith(0);
  });

  it("removes a configuration from every row and its constraints", () => {
    const three: LensData = {
      ...zoomed,
      configuration_names: ["A", "B", "C"],
      zoom: [
        { surface: 0, parameter: "thickness", values: [0.03, 0.04, 0.05] },
      ],
      constraints: [
        { kind: "efl", target: 0.04, configuration: 1 },
        { kind: "efl", target: 0.06, configuration: 2 },
      ],
    };
    const { onChange } = renderPanel(three);
    fireEvent.click(screen.getByLabelText("Remove configuration 2"));
    const next = onChange.mock.calls[0][0];
    expect(next.configuration_names).toEqual(["A", "C"]);
    expect(next.zoom[0].values).toEqual([0.03, 0.05]);
    expect(next.constraints).toEqual([
      { kind: "efl", target: 0.06, configuration: 1 },
    ]);
  });

  it("picks the configuration the analyses show and compares them", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        configurations: [
          {
            configuration: 0,
            name: "Wide",
            first_order: { efl: 0.04167, bfl: 0.0292, f_number: 2.08 },
          },
          {
            configuration: 1,
            name: "Tele",
            first_order: { efl: 0.05, bfl: 0.025, f_number: 2.5 },
          },
        ],
      }),
    );
    const { onActivate } = renderPanel(zoomed);
    fireEvent.click(screen.getByLabelText("Show configuration 2"));
    expect(onActivate).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByText("Compare"));
    await waitFor(() => screen.getByTestId("configuration-summary"));
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/lens/configurations",
    );
    const text = screen.getByTestId("configuration-summary").textContent;
    expect(text).toContain("Tele");
    expect(text).toContain("50.000");
  });
});

describe("constraints with configurations", () => {
  it("sets a constraint's configuration and lists its value in each", () => {
    const lens: LensData = {
      ...zoomed,
      constraints: [{ kind: "efl", target: 0.05, configuration: null }],
    };
    const onChange = vi.fn();
    render(
      <ConstraintsEditor
        lens={lens}
        displayUnit="mm"
        statuses={[
          {
            kind: "efl",
            target: 0.05,
            configuration: 0,
            value: 0.04,
            satisfied: false,
            index: 0,
          },
          {
            kind: "efl",
            target: 0.05,
            configuration: 1,
            value: 0.05,
            satisfied: true,
            index: 0,
          },
        ]}
        busy={false}
        onChange={onChange}
        onCheck={vi.fn()}
      />,
    );
    const value = screen.getByTestId("constraint-0-value").textContent ?? "";
    expect(value).toContain("Wide: 40");
    expect(value).toContain("Tele: 50");
    fireEvent.change(screen.getByLabelText("Constraint 1 configuration"), {
      target: { value: "1" },
    });
    expect(onChange.mock.calls[0][0][0].configuration).toBe(1);
  });
});

describe("the editor shows the chosen configuration", () => {
  it("resolves the configuration picked in the panel", async () => {
    const system: OpticalSystem = {
      components: [],
      wavelengths: [550e-9],
      object: { position: 0, height: 0, orientation: 0 },
      image_plane: { position: 0.1 },
      analysis_settings: base.analysis_settings,
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        ok({ lens: zoomed, system, first_order: { efl: 0.05 } }),
      );
    const onResolved = vi.fn();
    render(
      <LensDataEditor
        lens={zoomed}
        system={system}
        displayUnit="mm"
        dirty={false}
        onChange={vi.fn()}
        onResolved={onResolved}
        onImported={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText("Show configuration 2"));
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.configuration).toBe(1);
    fireEvent.click(screen.getByText("Resolve"));
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(2));
    expect(
      JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).configuration,
    ).toBe(1);
  });
});
