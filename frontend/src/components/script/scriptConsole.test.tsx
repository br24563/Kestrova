import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { ScriptConsole, EXAMPLES } from "./ScriptConsole";
import { DesignReportPanel, fileName } from "../report/DesignReportPanel";
import { DrawingsPanel } from "../report/DrawingsPanel";
import { newSurface } from "../lens/lensEdit";
import type { LensData } from "../../types";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(cleanup);

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
  analysis_settings: {
    num_rays: 11,
    ray_types: ["chief"],
    aperture_fraction: 1,
    wavelength: 588e-9,
  },
};

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("ScriptConsole", () => {
  it("runs the script with the lens and sends the result back", async () => {
    const changed = { ...lens, name: "Changed" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        output: "efl 0.0967\n",
        error: null,
        lens: changed,
        duration: 2.4,
        timed_out: false,
      }),
    );
    const onApply = vi.fn();
    render(<ScriptConsole lens={lens} onApplyLens={onApply} />);
    fireEvent.change(screen.getByLabelText("Script"), {
      target: { value: "print('efl', lens.efl)" },
    });
    fireEvent.click(screen.getByText("Run"));
    await waitFor(() => screen.getByTestId("script-output"));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/script/run");
    const body = JSON.parse(String(init?.body));
    expect(body.code).toBe("print('efl', lens.efl)");
    expect(body.lens.name).toBe("Singlet");
    expect(screen.getByTestId("script-output").textContent).toContain(
      "efl 0.0967",
    );
    fireEvent.click(screen.getByText("Send lens to the editor"));
    expect(onApply).toHaveBeenCalledWith(changed);
    expect(screen.getByText("Sent to the editor")).toBeTruthy();
  });

  it("shows the traceback and runs on Ctrl+Enter", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        output: "",
        error: "ZeroDivisionError: division by zero",
        lens: null,
        duration: 2,
        timed_out: false,
      }),
    );
    render(<ScriptConsole lens={null} onApplyLens={vi.fn()} />);
    expect(screen.getByText(/`lens` is not defined/)).toBeTruthy();
    fireEvent.keyDown(screen.getByLabelText("Script"), {
      key: "Enter",
      ctrlKey: true,
    });
    await waitFor(() => screen.getByText(/ZeroDivisionError/));
    expect(screen.queryByText("Send lens to the editor")).toBeNull();
  });

  it("loads examples and the filtered API reference", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        reference: [
          { name: "lens.efl", signature: "", doc: "Effective focal length" },
          { name: "lens.optimize", signature: "()", doc: "Damped least" },
        ],
      }),
    );
    render(<ScriptConsole lens={lens} onApplyLens={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Example"), {
      target: { value: EXAMPLES[1].label },
    });
    expect((screen.getByLabelText("Script") as HTMLTextAreaElement).value).toBe(
      EXAMPLES[1].code,
    );
    fireEvent.click(screen.getByText("API reference"));
    await waitFor(() => screen.getByText("lens.optimize"));
    fireEvent.change(screen.getByLabelText("Filter reference"), {
      target: { value: "focal" },
    });
    expect(screen.queryByText("lens.optimize")).toBeNull();
    expect(screen.getByText("lens.efl")).toBeTruthy();
  });

  it("indents with Tab", () => {
    render(<ScriptConsole lens={lens} onApplyLens={vi.fn()} />);
    const area = screen.getByLabelText("Script") as HTMLTextAreaElement;
    fireEvent.change(area, { target: { value: "x" } });
    area.selectionStart = area.selectionEnd = 0;
    fireEvent.keyDown(area, { key: "Tab" });
    expect(area.value).toBe("    x");
  });
});

describe("DesignReportPanel", () => {
  it("names the file from the title", () => {
    expect(fileName("Geiser triplet (OPTI 517)")).toBe(
      "Geiser_triplet_OPTI_517",
    );
    expect(fileName("***")).toBe("lens_report");
  });

  it("generates the report with the options and previews it", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(ok({ html: "<!doctype html><h1>Singlet</h1>" }));
    render(<DesignReportPanel lens={lens} />);
    fireEvent.change(screen.getByLabelText("Author"), {
      target: { value: "Me" },
    });
    fireEvent.click(screen.getByLabelText("Tolerances"));
    fireEvent.click(screen.getByText("Generate"));
    await waitFor(() => screen.getByTitle("Report preview"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toMatchObject({
      author: "Me",
      tolerances: false,
      mtf: true,
      drawings: true,
    });
    expect(
      (screen.getByTitle("Report preview") as HTMLIFrameElement).srcdoc,
    ).toContain("Singlet");
  });

  it("saves the PDF through the desktop app", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(ok({ html: "<p>r</p>" }));
    const savePdf = vi.fn().mockResolvedValue("C:/r.pdf");
    (window as unknown as { electronAPI: unknown }).electronAPI = { savePdf };
    try {
      render(<DesignReportPanel lens={lens} />);
      fireEvent.click(screen.getByText("Generate"));
      await waitFor(() => screen.getByText("Save PDF"));
      fireEvent.click(screen.getByText("Save PDF"));
      await waitFor(() => screen.getByText("Saved C:/r.pdf"));
      expect(savePdf).toHaveBeenCalledWith("<p>r</p>", "Singlet.pdf");
    } finally {
      delete (window as unknown as { electronAPI?: unknown }).electronAPI;
    }
  });

  it("asks for a lens", () => {
    render(<DesignReportPanel lens={null} />);
    expect(
      screen.getByText(/design report works on the lens data/),
    ).toBeTruthy();
  });
});

describe("DrawingsPanel", () => {
  it("draws the elements with the notes and margin", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      ok({
        drawings: [
          {
            name: "Element 1",
            surfaces: [0, 1],
            glass: "N-BK7",
            center_thickness: 0.004,
            edge_thickness: 0.0027,
            clear_diameter: 0.02,
            outer_diameter: 0.022,
            left: [["Radius (mm)", "R 100.0000 CX"]],
            material: [["Glass", "N-BK7"]],
            right: [["Radius (mm)", "R 100.0000 CX"]],
            svg: "<svg></svg>",
            html: "",
          },
        ],
      }),
    );
    render(<DrawingsPanel lens={lens} />);
    fireEvent.change(screen.getByLabelText("5/ imperfections"), {
      target: { value: "5/3×0.16" },
    });
    fireEvent.change(screen.getByLabelText("Edge margin"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByText("Draw"));
    await waitFor(() => screen.getByTestId("element-drawing"));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.notes).toEqual({ "5/": "5/3×0.16" });
    expect(body.edge_margin).toBeCloseTo(0.002);
    expect(screen.getByText(/Element 1: S0–S1, N-BK7/)).toBeTruthy();
    expect(screen.getAllByText("R 100.0000 CX")).toHaveLength(2);
  });

  it("checks the margin and reports mirror-only systems", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(ok({ drawings: [] }));
    render(<DrawingsPanel lens={lens} />);
    fireEvent.change(screen.getByLabelText("Edge margin"), {
      target: { value: "-1" },
    });
    fireEvent.click(screen.getByText("Draw"));
    expect(screen.getByRole("alert").textContent).toContain("0 or more");
    fireEvent.change(screen.getByLabelText("Edge margin"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByText("Draw"));
    await waitFor(() => screen.getByText(/mirrors only/));
  });
});
