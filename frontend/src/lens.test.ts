import { describe, it, expect, vi, beforeEach } from "vitest";
import { lensFromSystem, resolveLens, optimizeLens } from "./api";
import {
  insertSurface,
  deleteSurface,
  setStop,
  getModifier,
  setModifier,
  countVariables,
  newSurface,
} from "./components/lens/lensEdit";
import type { LensData, LensSurface, OpticalSystem } from "./types";

const system: OpticalSystem = {
  components: [],
  wavelengths: [550e-9],
  object: { position: 0, height: 0.01, orientation: 0 },
  image_plane: { position: 0.2 },
  analysis_settings: {
    num_rays: 11,
    ray_types: ["chief"],
    aperture_fraction: 1,
    wavelength: 550e-9,
  },
};

function surface(patch: Partial<LensSurface>): LensSurface {
  return { ...newSurface(), ...patch };
}

const lens: LensData = {
  name: "",
  surfaces: [
    surface({
      label: "STO",
      is_stop: true,
      semi_diameter: 0.008,
      thickness: 0.002,
    }),
    surface({
      element: "L1",
      radius: 0.05,
      thickness: 0.006,
      material: "N-BK7",
      variables: ["radius"],
    }),
    surface({
      element: "L1",
      radius: -0.05,
      thickness: 0.1,
      pickups: { radius: { source: 1, parameter: null, scale: -1, offset: 0 } },
      solves: { thickness: { kind: "marginal_height", target: 0 } },
    }),
  ],
  object_distance: null,
  object_height: 0,
  field_angle: 0.05,
  entrance_pupil_diameter: null,
  wavelengths: [550e-9],
  first_surface_position: 0,
  analysis_settings: system.analysis_settings,
};

function jsonResponse(data: unknown, ok = true, status = 200) {
  const r = {
    ok,
    status,
    statusText: ok ? "OK" : "Bad Request",
    json: async () => data,
    clone: () => r,
  };
  return r as unknown as Response;
}

describe("lens data API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("lensFromSystem posts the system", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ lens }));
    const result = await lensFromSystem(system);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/lens/from-system",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(
      (fetchMock.mock.calls[0][1] as RequestInit).body as string,
    );
    expect(body).toEqual({ system });
    expect(result.lens.surfaces).toHaveLength(3);
  });

  it("resolveLens posts the lens and returns lens, system and first order", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        lens,
        system,
        first_order: { efl: 0.05, image_z: 0.108 },
      }),
    );
    const result = await resolveLens(lens);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/lens/resolve",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(
      (fetchMock.mock.calls[0][1] as RequestInit).body as string,
    );
    expect(body.lens.surfaces[2].solves.thickness.kind).toBe("marginal_height");
    expect(result.system.image_plane.position).toBe(0.2);
    expect(result.first_order.efl).toBe(0.05);
  });

  it("optimizeLens sends bounds and max_evaluations", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        lens,
        system,
        first_order: {},
        rms_spot_before: 2e-5,
        rms_spot_after: 1e-5,
      }),
    );
    const result = await optimizeLens(lens, { "1.radius": [0.02, 1] }, 50);
    const body = JSON.parse(
      (fetchMock.mock.calls[0][1] as RequestInit).body as string,
    );
    expect(fetchMock.mock.calls[0][0]).toBe("/api/lens/optimize");
    expect(body.bounds).toEqual({ "1.radius": [0.02, 1] });
    expect(body.max_evaluations).toBe(50);
    expect(result.rms_spot_after).toBeLessThan(result.rms_spot_before);
  });

  it("surfaces the backend's error detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        { detail: "Exactly one surface must be the aperture stop" },
        false,
        400,
      ),
    );
    await expect(resolveLens(lens)).rejects.toThrow(
      "Failed to resolve lens data: Exactly one surface must be the aperture stop",
    );
  });
});

describe("lens edits", () => {
  it("insertSurface shifts pickup sources at or after the insertion", () => {
    const out = insertSurface(lens, 1);
    expect(out.surfaces).toHaveLength(4);
    expect(out.surfaces[1].label).toBe("");
    expect(out.surfaces[3].pickups.radius.source).toBe(2);
    expect(lens.surfaces[2].pickups.radius.source).toBe(1); // input untouched
  });

  it("insertSurface before the source keeps it, after the end appends", () => {
    expect(insertSurface(lens, 2).surfaces[3].pickups.radius.source).toBe(1);
    expect(insertSurface(lens, 99).surfaces).toHaveLength(4);
  });

  it("deleteSurface drops pickups from the deleted surface and reindexes", () => {
    const out = deleteSurface(lens, 1);
    expect(out.surfaces).toHaveLength(2);
    expect(out.surfaces[1].pickups).toEqual({});
    const withPickupLater = insertSurface(lens, 0); // source now 2, row 3 picks it
    const out2 = deleteSurface(withPickupLater, 0);
    expect(out2.surfaces[2].pickups.radius.source).toBe(1);
  });

  it("deleteSurface refuses the stop", () => {
    expect(() => deleteSurface(lens, 0)).toThrow(/stop/);
  });

  it("setStop moves the stop", () => {
    const out = setStop(lens, 2);
    expect(out.surfaces.map((s) => s.is_stop)).toEqual([false, false, true]);
  });

  it("setModifier makes a parameter variable, solved or picked up exclusively", () => {
    let s = lens.surfaces[1];
    expect(getModifier(s, "radius")).toEqual({ kind: "variable" });
    s = setModifier(s, "radius", {
      kind: "solve",
      solve: { kind: "f_number", target: 4 },
    });
    expect(s.variables).toEqual([]);
    expect(getModifier(s, "radius")).toEqual({
      kind: "solve",
      solve: { kind: "f_number", target: 4 },
    });
    s = setModifier(s, "radius", {
      kind: "pickup",
      pickup: { source: 0, scale: 1, offset: 0 },
    });
    expect(s.solves).toEqual({});
    expect(getModifier(s, "radius").kind).toBe("pickup");
    s = setModifier(s, "radius", { kind: "fixed" });
    expect(getModifier(s, "radius")).toEqual({ kind: "fixed" });
    expect(countVariables(lens)).toBe(1);
  });
});
