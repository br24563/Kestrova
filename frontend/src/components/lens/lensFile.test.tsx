import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { LensDataEditor } from "./LensDataEditor";
import { newSurface } from "./lensEdit";
import type { LensData, OpticalSystem } from "../../types";

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
  name: "Doublet",
  surfaces: [
    { ...newSurface(), label: "STO", is_stop: true, semi_diameter: 0.005 },
    { ...newSurface(), radius: 0.05, thickness: 0.005, material: "N-BK7" },
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

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function renderEditor(props: Partial<Parameters<typeof LensDataEditor>[0]>) {
  const all = {
    lens,
    system,
    displayUnit: "mm" as const,
    dirty: false,
    onChange: vi.fn(),
    onResolved: vi.fn(),
    onImported: vi.fn(),
    ...props,
  };
  render(<LensDataEditor {...all} />);
  return all;
}

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

describe("lens files", () => {
  it("opens a file, resolves it and lists the warnings", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) =>
        String(input).includes("/lens/import")
          ? ok({ lens, warnings: ["Code V command POL not interpreted (1x)"] })
          : ok({ lens, system, first_order: { efl: 0.1 } }),
      );
    const props = renderEditor({ lens: null });
    const input = screen.getByLabelText("Lens file") as HTMLInputElement;
    const file = new File(["SO 0 1e20\n"], "design.seq", {
      type: "text/plain",
    });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(props.onResolved).toHaveBeenCalledTimes(1));
    expect(props.onImported).toHaveBeenCalledWith(lens);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/lens/import");
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("shows the file's warnings after opening", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("/lens/import")
        ? ok({ lens, warnings: ["Zemax keyword TOL not interpreted (2x)"] })
        : ok({ lens, system, first_order: { efl: 0.1 } }),
    );
    renderEditor({});
    const input = screen.getByLabelText("Lens file") as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["x"], "lens.zmx")] },
    });
    await waitFor(() => screen.getByTestId("file-note"));
    const note = screen.getByTestId("file-note").textContent;
    expect(note).toContain("Opened lens.zmx");
    expect(note).toContain("TOL not interpreted");
  });

  it("saves through the backend and downloads the file", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        filename: "Doublet.zmx",
        content: "VERS 0\n",
        warnings: ["Surface 1: variable radius written as a fixed value"],
      }),
    );
    const createUrl = vi.fn(() => "blob:lens");
    const revokeUrl = vi.fn();
    Object.assign(URL, {
      createObjectURL: createUrl,
      revokeObjectURL: revokeUrl,
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    renderEditor({});
    fireEvent.click(screen.getByText("Save .zmx"));
    await waitFor(() => screen.getByTestId("file-note"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.format).toBe("zmx");
    expect(body.lens.name).toBe("Doublet");
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("file-note").textContent).toContain(
      "Saved Doublet.zmx",
    );
  });

  it("reports a file the backend cannot read", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: async () => ({
        detail:
          "Could not read the file: Sequence file has no object surface (SO)",
      }),
      clone() {
        return this;
      },
    } as unknown as Response);
    renderEditor({});
    fireEvent.change(screen.getByLabelText("Lens file"), {
      target: { files: [new File(["S 1 2"], "bad.seq")] },
    });
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toContain("object surface");
  });
});
