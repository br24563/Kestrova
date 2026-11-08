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
  name: "Geiser triplet",
  surfaces: [
    {
      ...newSurface(),
      radius: 0.023713,
      thickness: 0.004831,
      material: "N-LAK9",
    },
    { ...newSurface(), is_stop: true, semi_diameter: 0.0048, thickness: 0.04 },
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0.349,
  entrance_pupil_diameter: 0.0125,
  wavelengths: [587.5618e-9],
  first_surface_position: 0,
  analysis_settings: system.analysis_settings,
};

const samples = [
  {
    id: "geiser-triplet",
    name: "Geiser triplet, f/4, 50 mm",
    description: "Air-spaced Cooke triplet",
    citation: "Sasian, OPTI 517",
    url: "https://example.org/triplet",
    notes: "",
  },
  {
    id: "hubble-ota",
    name: "Hubble Space Telescope",
    description: "Ritchey-Chretien",
    citation: "STScI",
    url: "https://example.org/hst",
    notes: "",
  },
];

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

describe("sample lenses", () => {
  it("lists the samples only when asked", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(ok(samples));
    renderEditor({});
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Samples"));
    await waitFor(() => screen.getByRole("menu", { name: "Sample lenses" }));
    expect(screen.getAllByRole("menuitem")).toHaveLength(2);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/lens\/samples$/);
    // a second click closes the menu without fetching again
    fireEvent.click(screen.getByText("Samples"));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("opens a sample, resolves it and shows its source", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.endsWith("/lens/samples")) return ok(samples);
        if (url.includes("/lens/samples/")) return ok({ ...samples[0], lens });
        return ok({ lens, system, first_order: { efl: 0.05 } });
      });
    const props = renderEditor({});
    fireEvent.click(screen.getByText("Samples"));
    await waitFor(() => screen.getByRole("menu"));
    fireEvent.click(screen.getByText("Geiser triplet, f/4, 50 mm"));
    await waitFor(() => expect(props.onResolved).toHaveBeenCalledTimes(1));
    expect(props.onImported).toHaveBeenCalledWith(lens);
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      "/lens/samples/geiser-triplet",
    );
    const note = screen.getByTestId("file-note");
    expect(note.textContent).toContain("Opened sample: Geiser triplet");
    const link = screen.getByRole("link", { name: "Sasian, OPTI 517" });
    expect(link.getAttribute("href")).toBe("https://example.org/triplet");
  });

  it("reports a sample list that cannot be fetched", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Server Error",
      json: async () => ({}),
      clone() {
        return this;
      },
    } as unknown as Response);
    renderEditor({});
    fireEvent.click(screen.getByText("Samples"));
    await waitFor(() => screen.getByRole("alert"));
    expect(screen.getByRole("alert").textContent).toContain(
      "Failed to list the sample lenses",
    );
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
