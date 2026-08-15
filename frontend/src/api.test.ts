import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getDefaultSystem,
  traceRays,
  analyzeSystem,
  validateSystem,
  listSystems,
  saveSystem,
  loadSystem,
  deleteSystem,
} from "./api";
import type { OpticalSystem } from "./types";

// A minimal valid optical system for testing
const mockSystem: OpticalSystem = {
  components: [
    {
      type: "thin_lens",
      id: "lens_1",
      position: 0.1,
      focal_length: 0.05,
      aperture_diameter: 0.025,
      material: "N-BK7",
    },
  ],
  wavelengths: [550e-9],
  object: { position: 0.0, height: 0.01, orientation: 0.0 },
  image_plane: { position: 0.2 },
  analysis_settings: {
    num_rays: 11,
    ray_types: ["chief", "marginal", "fill"],
    aperture_fraction: 1.0,
    wavelength: 550e-9,
  },
};

// Helper to mock a successful JSON response
function mockFetchResponse(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => data,
  } as Response;
}

describe("API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("getDefaultSystem fetches the default system", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({ system: mockSystem, warnings: [] }),
    );
    const result = await getDefaultSystem();
    expect(fetchMock).toHaveBeenCalledWith("/api/system/default");
    expect(result.system.components[0].id).toBe("lens_1");
  });

  it("traceRays posts the system and returns ray paths", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({ ray_paths: [], image_position: 0.2, image_height: -0.01, paraxial_image_height: -0.01 }),
    );
    const result = await traceRays(mockSystem, 11, 1.0);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trace",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.image_position).toBe(0.2);
  });

  it("analyzeSystem posts the system and returns analysis", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({ effective_focal_length: 0.05, magnification: -1.0 }),
    );
    const result = await analyzeSystem(mockSystem);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/analyze",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.effective_focal_length).toBe(0.05);
  });

  it("validateSystem posts the system and returns warnings", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({ system: mockSystem, warnings: ["warning"] }),
    );
    const result = await validateSystem(mockSystem);
    expect(result.warnings).toEqual(["warning"]);
  });

  it("listSystems returns metadata", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse([{ id: 1, name: "proj", created_at: "t", updated_at: "t" }]),
    );
    const result = await listSystems();
    expect(fetchMock).toHaveBeenCalledWith("/api/systems");
    expect(result[0].name).toBe("proj");
  });

  it("saveSystem posts name and system", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({ id: 1, name: "proj", created_at: "t", updated_at: "t" }),
    );
    const result = await saveSystem("proj", mockSystem);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/systems",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.id).toBe(1);
  });

  it("loadSystem fetches a saved system by id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({ id: 1, name: "proj", system_json: "{}", created_at: "t", updated_at: "t" }),
    );
    const result = await loadSystem(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/systems/1");
    expect(result.id).toBe(1);
  });

  it("deleteSystem sends a DELETE request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({ message: "deleted" }),
    );
    await deleteSystem(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/systems/1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("throws an error when a request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockFetchResponse({}, false, 500),
    );
    await expect(getDefaultSystem()).rejects.toThrow("Failed to fetch default system");
  });
});