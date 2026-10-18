/**
 * API client for the AI Optical Design Engineer backend.
 *
 * This module provides functions to communicate with the FastAPI backend.
 * The backend runs on http://localhost:8000 by default.
 * The Vite dev server proxies /api requests to the backend.
 */

import type {
  OpticalSystem,
  RayTraceResult,
  AnalysisResult,
  SystemResponse,
  TraceRequest,
  AnalyzeRequest,
  ChromaticAberrationResult,
  OptimizeRequest,
  OptimizeResult,
  SweepRequest,
  SweepPoint,
  DiffractionResult,
  SeidelResult,
  ToleranceResult,
  ToleranceRequest,
  ComparisonResult,
  CompareRequest,
} from "./types";

// Persistence types
export interface SystemMetadata {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface SavedSystemResponse {
  id: number;
  name: string;
  system_json: string;
  created_at: string;
  updated_at: string;
}

// AI command types
export type AICommand =
  | { action: "modify_component"; component_id: string; field: string; value: number }
  | { action: "add_component"; component: unknown }
  | { action: "remove_component"; component_id: string }
  | { action: "set_object"; position?: number; height?: number }
  | { action: "set_image_plane"; position: number }
  | { action: "analyze" }
  | {
      action: "optimize";
      objective: "rms_spot" | "magnification" | "efl";
      target?: number;
      params: Record<string, unknown>[];
      bounds: number[][];
    };

export interface AIInterpretResponse {
  commands: AICommand[];
  message: string;
}

export interface AICommandResponse {
  system: OpticalSystem;
  warnings: string[];
  result: Record<string, unknown> | null;
  message: string;
}

export interface AIProviderInfo {
  use_ollama: boolean;
  model: string;
  ollama_url: string;
}

const API_BASE = "/api";

/**
 * The reason a request failed: the backend's `detail` message when it sent
 * one (e.g. "Image space is afocal ..."), otherwise the HTTP status text.
 */
async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.clone().json();
    if (body && typeof body.detail === "string") {
      return Array.isArray(body.errors) && body.errors.length
        ? `${body.detail}: ${body.errors.join("; ")}`
        : body.detail;
    }
  } catch {
    // not JSON; fall through
  }
  return response.statusText;
}

/**
 * Fetch the default two-lens optical system from the backend.
 */
export async function getDefaultSystem(): Promise<SystemResponse> {
  const response = await fetch(`${API_BASE}/system/default`);
  if (!response.ok) {
    throw new Error(`Failed to fetch default system: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Trace rays through an optical system.
 *
 * @param system - The optical system to trace
 * @param numRays - Number of rays to trace (optional)
 * @param apertureFraction - Fraction of aperture to use (optional)
 * @returns Ray trace results including ray paths and image information
 */
export async function traceRays(
  system: OpticalSystem,
  numRays?: number,
  apertureFraction?: number,
): Promise<RayTraceResult> {
  const request: TraceRequest = { system };
  if (numRays !== undefined) request.num_rays = numRays;
  if (apertureFraction !== undefined) request.aperture_fraction = apertureFraction;

  const response = await fetch(`${API_BASE}/trace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to trace rays: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Analyze an optical system.
 *
 * @param system - The optical system to analyze
 * @param numRays - Number of rays to trace for spot diagram (optional)
 * @param apertureFraction - Fraction of aperture to use (optional)
 * @returns Analysis results including focal length, magnification, etc.
 */
export async function analyzeSystem(
  system: OpticalSystem,
  numRays?: number,
  apertureFraction?: number,
): Promise<AnalysisResult> {
  const request: AnalyzeRequest = { system };
  if (numRays !== undefined) request.num_rays = numRays;
  if (apertureFraction !== undefined) request.aperture_fraction = apertureFraction;

  const response = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to analyze system: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Validate an optical system.
 *
 * @param system - The optical system to validate
 * @returns The system and a list of validation warnings
 */
export async function validateSystem(
  system: OpticalSystem,
): Promise<SystemResponse> {
  const response = await fetch(`${API_BASE}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(system),
  });

  if (!response.ok) {
    throw new Error(`Failed to validate system: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * List all saved optical system projects.
 */
export async function listSystems(): Promise<SystemMetadata[]> {
  const response = await fetch(`${API_BASE}/systems`);
  if (!response.ok) {
    throw new Error(`Failed to list systems: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Save an optical system project to the database.
 */
export async function saveSystem(
  name: string,
  system: OpticalSystem,
): Promise<SystemMetadata> {
  const response = await fetch(`${API_BASE}/systems`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, system }),
  });
  if (!response.ok) {
    throw new Error(`Failed to save system: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Load a saved optical system project by id.
 */
export async function loadSystem(id: number): Promise<SavedSystemResponse> {
  const response = await fetch(`${API_BASE}/systems/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to load system: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Delete a saved optical system project by id.
 */
export async function deleteSystem(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/systems/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete system: ${await errorDetail(response)}`);
  }
}

/**
 * Optimize a set of system parameters to minimize an objective.
 *
 * @param request - The optimization request (system, objective, params, bounds)
 * @returns The optimization result (params, objective, optimized system, success)
 */
export async function optimizeSystem(
  request: OptimizeRequest,
): Promise<OptimizeResult> {
  const response = await fetch(`${API_BASE}/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`Failed to optimize: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Sweep a single parameter across a range of values and analyze each.
 *
 * @param request - The sweep request (system, param, values)
 * @returns A list of sweep points, each with the parameter value and analysis
 */
export async function runSweep(request: SweepRequest): Promise<SweepPoint[]> {
  const response = await fetch(`${API_BASE}/sweep`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`Failed to run sweep: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Analyze chromatic aberration of an optical system.
 *
 * @param system - The optical system to analyze
 * @param wavelengths - Optional list of wavelengths in meters
 * @returns Chromatic aberration result (LCA, TCA, per-wavelength positions/heights)
 */
export async function analyzeAberration(
  system: OpticalSystem,
  wavelengths?: number[],
): Promise<ChromaticAberrationResult> {
  const response = await fetch(`${API_BASE}/analyze/aberration`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ system, wavelengths }),
  });
  if (!response.ok) {
    throw new Error(`Failed to analyze aberration: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Get the current AI interpreter provider configuration.
 *
 * @returns Whether Ollama is enabled, the model, and the Ollama URL
 */
export async function getAIProvider(): Promise<AIProviderInfo> {
  const response = await fetch(`${API_BASE}/ai/provider`);
  if (!response.ok) {
    throw new Error(`Failed to get AI provider: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Interpret a natural-language prompt into structured AI commands.
 *
 * @param system - The current optical system (for context)
 * @param prompt - The user's natural-language request
 * @returns The interpreted commands and a message
 */
export async function interpretPrompt(
  system: OpticalSystem,
  prompt: string,
): Promise<AIInterpretResponse> {
  const response = await fetch(`${API_BASE}/ai/interpret`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ system, prompt }),
  });
  if (!response.ok) {
    throw new Error(`Failed to interpret prompt: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Execute a structured AI command against an optical system.
 *
 * @param system - The optical system to apply the command to
 * @param command - The structured AI command
 * @returns The updated system, warnings, and any result
 */
export async function executeAICommand(
  system: OpticalSystem,
  command: AICommand,
): Promise<AICommandResponse> {
  const response = await fetch(`${API_BASE}/ai/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ system, command }),
  });
  if (!response.ok) {
    throw new Error(`Failed to execute AI command: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Run diffraction analysis (PSF, MTF, OTF, Airy disk) on an optical system.
 *
 * @param system - The optical system to analyze
 * @returns Diffraction analysis results
 */
export async function analyzeDiffraction(
  system: OpticalSystem,
): Promise<DiffractionResult> {
  const request: AnalyzeRequest = { system };
  const response = await fetch(`${API_BASE}/analyze/diffraction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`Failed to analyze diffraction: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Run Seidel (third-order) monochromatic aberration analysis.
 *
 * @param system - The optical system to analyze
 * @returns Seidel aberration results
 */
export async function analyzeSeidel(
  system: OpticalSystem,
): Promise<SeidelResult> {
  const request: AnalyzeRequest = { system };
  const response = await fetch(`${API_BASE}/analyze/seidel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`Failed to analyze Seidel aberrations: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Run Monte-Carlo tolerance analysis on an optical system.
 *
 * @param request - The tolerance request with system and parameters
 * @returns Tolerance analysis results
 */
export async function runToleranceAnalysis(
  request: ToleranceRequest,
): Promise<ToleranceResult> {
  const response = await fetch(`${API_BASE}/tolerance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`Failed to run tolerance analysis: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Compare two optical systems side by side.
 *
 * @param request - The comparison request with two systems
 * @returns Comparison results with metrics and advantage indicators
 */
export async function compareSystems(
  request: CompareRequest,
): Promise<ComparisonResult> {
  const response = await fetch(`${API_BASE}/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`Failed to compare systems: ${await errorDetail(response)}`);
  }
  return response.json();
}

export interface PresetInfo {
  id: string;
  name: string;
  description: string;
  category: string;
}

export interface PresetResponse {
  id: string;
  name: string;
  description: string;
  category: string;
  system: OpticalSystem;
  warnings: string[];
}

/**
 * Get a list of available preset optical systems.
 *
 * @returns List of preset metadata (id, name, description, category)
 */
export async function getPresets(): Promise<PresetInfo[]> {
  const response = await fetch(`${API_BASE}/presets`);
  if (!response.ok) {
    throw new Error(`Failed to get presets: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Get a specific preset optical system by ID.
 *
 * @param presetId - The ID of the preset to load
 * @returns The preset with full system data
 */
export async function getPreset(presetId: string): Promise<PresetResponse> {
  const response = await fetch(`${API_BASE}/presets/${presetId}`);
  if (!response.ok) {
    throw new Error(`Failed to get preset: ${await errorDetail(response)}`);
  }
  return response.json();
}

/**
 * Health check - verify the backend is running.
 *
 * @returns Health status and available features
 */
export async function healthCheck(): Promise<{
  status: string;
  version: string;
  features: Record<string, boolean>;
}> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${await errorDetail(response)}`);
  }
  return response.json();
}

export interface GhostAnalysisResult {
  ghosts: Array<{
    surfaces: number[];
    reflection_count: number;
    relative_intensity: number;
    image_position_offset: number;
    is_in_field: boolean;
    description: string;
  }>;
  n_ghosts: number;
}

export async function analyzeGhosts(
  system: OpticalSystem,
  nReflections: number = 2,
  threshold: number = 1e-4,
): Promise<GhostAnalysisResult> {
  const response = await fetch(`${API_BASE}/analyze/ghosts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ system, n_reflections: nReflections, threshold }),
  });
  if (!response.ok) {
    throw new Error(`Failed to analyze ghosts: ${await errorDetail(response)}`);
  }
  return response.json();
}

export interface StrayLightResult {
  paths: Array<{
    path_id: number;
    source_surface: number;
    scatter_surface: number;
    relative_intensity: number;
    path_type: string;
    description: string;
  }>;
  n_paths: number;
}

export async function analyzeStrayLight(
  system: OpticalSystem,
  sourceAngle: number = 30,
  brdfModel: string = "lambertian",
  diffuseFraction: number = 0.01,
): Promise<StrayLightResult> {
  const response = await fetch(`${API_BASE}/analyze/straylight`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system,
      source_angle: sourceAngle,
      brdf_model: brdfModel,
      diffuse_fraction: diffuseFraction,
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to analyze stray light: ${await errorDetail(response)}`);
  }
  return response.json();
}

export interface PSTResult {
  angles: number[];
  pst_db: number[];
}

export async function computePST(
  system: OpticalSystem,
  angles: number[] = [5, 10, 15, 20, 25, 30, 35, 40, 45],
): Promise<PSTResult> {
  const response = await fetch(`${API_BASE}/analyze/pst`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ system, angles }),
  });
  if (!response.ok) {
    throw new Error(`Failed to compute PST: ${await errorDetail(response)}`);
  }
  return response.json();
}
