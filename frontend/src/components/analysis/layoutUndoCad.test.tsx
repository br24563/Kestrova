import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
  renderHook,
  act,
} from "@testing-library/react";
import { LensLayoutPanel, project } from "./LensLayoutPanel";
import { LensDataEditor } from "../lens/LensDataEditor";
import { newSurface } from "../lens/lensEdit";
import { useHistory } from "../../hooks/useHistory";
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
      thickness: 0.004,
      material: "N-BK7",
      semi_diameter: 0.01,
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

const layout = {
  elements: [
    {
      name: "Element 1",
      outline: [
        [0, 0],
        [-0.0005, 0.01],
        [-0.0005, 0.0105],
        [0.0045, 0.0105],
        [0.0045, 0.01],
        [0.004, 0],
      ],
    },
  ],
  rays: [
    {
      field: 0,
      pupil: [0, 1],
      points: [
        [0, 0.01, -0.01],
        [0, 0.01, 0],
        [0, 0, 0.1],
      ],
    },
    {
      field: 1,
      pupil: [0, -1],
      points: [
        [0, -0.01, -0.01],
        [0, -0.01, 0],
        [0, 0.002, 0.1],
      ],
    },
  ],
  fields: 2,
  stop: { z: 0, semi_diameter: 0.01 },
  image: { z: 0.1, half_height: 0.002 },
  warnings: [],
};

describe("LensLayoutPanel", () => {
  it("projects: no turn is the side view, a quarter turn looks down the axis", () => {
    expect(project([0, 2, 5], 0, 0)).toEqual([5, 2]);
    const [u, v] = project([1, 2, 5], Math.PI / 2, 0);
    expect(u).toBeCloseTo(-1);
    expect(v).toBeCloseTo(2);
    const [, v2] = project([0, 2, 0], 0, Math.PI / 2);
    expect(v2).toBeCloseTo(0);
  });

  it("draws the section, then asks for the ring in 3D", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(ok(layout));
    render(<LensLayoutPanel lens={lens} displayUnit="mm" />);
    await waitFor(() => screen.getByTestId("layout-svg"));
    const svg = screen.getByTestId("layout-svg");
    expect(svg.querySelectorAll("polygon")).toHaveLength(1);
    // two rays, two stop bars, the image plane
    expect(svg.querySelectorAll("polyline")).toHaveLength(5);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).pupil).toBe(
      "fan",
    );
    expect(screen.getByText(/1 elements, 2 rays over 2 fields/)).toBeTruthy();
    fireEvent.click(screen.getByText("3D"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).pupil).toBe(
      "ring",
    );
    await waitFor(() => screen.getByText(/Drag to turn/));
    // 8 meridians + corner rings + 2 rays
    expect(
      screen.getByTestId("layout-svg").querySelectorAll("polyline").length,
    ).toBeGreaterThan(10);
  });

  it("asks for a lens", () => {
    render(<LensLayoutPanel lens={null} displayUnit="mm" />);
    expect(screen.getByText(/layout works on the lens data/)).toBeTruthy();
  });
});

describe("useHistory", () => {
  it("returns the state undo and redo move to", () => {
    const { result } = renderHook(() => useHistory(1));
    act(() => result.current.set(2));
    act(() => result.current.set(3));
    let back = 0;
    act(() => {
      back = result.current.undo();
    });
    expect(back).toBe(2);
    expect(result.current.state).toBe(2);
    let fwd = 0;
    act(() => {
      fwd = result.current.redo();
    });
    expect(fwd).toBe(3);
    act(() => result.current.set((v) => v)); // unchanged: no entry
    act(() => {
      result.current.undo();
      result.current.undo();
    });
    expect(result.current.state).toBe(1);
    expect(result.current.canUndo).toBe(false);
    act(() => result.current.reset(9));
    expect(result.current.canRedo).toBe(false);
  });
});

describe("LensDataEditor undo and CAD", () => {
  function renderEditor(over: Partial<Parameters<typeof LensDataEditor>[0]>) {
    const props = {
      lens,
      system,
      displayUnit: "mm" as const,
      dirty: false,
      onChange: vi.fn(),
      onResolved: vi.fn(),
      onImported: vi.fn(),
      ...over,
    };
    render(<LensDataEditor {...props} />);
    return props;
  }

  it("steps through the lens history", () => {
    const onUndo = vi.fn();
    const onRedo = vi.fn();
    renderEditor({ onUndo, onRedo, canUndo: true, canRedo: false });
    fireEvent.click(screen.getByText("Undo"));
    expect(onUndo).toHaveBeenCalled();
    expect((screen.getByText("Redo") as HTMLButtonElement).disabled).toBe(true);
  });

  it("exports STEP and IGES", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        filename: "Singlet.step",
        content: "ISO-10303-21;",
        warnings: [],
      }),
    );
    const createURL = vi.fn(() => "blob:x");
    Object.assign(URL, {
      createObjectURL: createURL,
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderEditor({});
    fireEvent.click(screen.getByText("STEP"));
    await waitFor(() => screen.getByText(/Saved Singlet.step/));
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).format).toBe(
      "step",
    );
    fireEvent.click(screen.getByText("IGES"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).format).toBe(
      "igs",
    );
  });
});
