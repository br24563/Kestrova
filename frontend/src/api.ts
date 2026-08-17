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

const API_BASE = "/api";

/**
 * Fetch the default two-lens optical system from the backend.
 */
export async function getDefaultSystem(): Promise<SystemResponse> {
  const response = await fetch(`${API_BASE}/system/default`);
  if (!response.ok) {
    throw new Error(`Failed to fetch default system: ${response.statusText}`);
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
    throw new Error(`Failed to trace rays: ${response.statusText}`);
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
    throw new Error(`Failed to analyze system: ${response.statusText}`);
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
    throw new Error(`Failed to validate system: ${response.statusText}`);
  }
  return response.json();
}

/**
 * List all saved optical system projects.
 */
export async function listSystems(): Promise<SystemMetadata[]> {
  const response = await fetch(`${API_BASE}/systems`);
  if (!response.ok) {
    throw new Error(`Failed to list systems: ${response.statusText}`);
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
    throw new Error(`Failed to save system: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Load a saved optical system project by id.
 */
export async function loadSystem(id: number): Promise<SavedSystemResponse> {
  const response = await fetch(`${API_BASE}/systems/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to load system: ${response.statusText}`);
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
    throw new Error(`Failed to delete system: ${response.statusText}`);
  }
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
    throw new Error(`Failed to analyze aberration: ${response.statusText}`);
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
    throw new Error(`Failed to interpret prompt: ${response.statusText}`);
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
    throw new Error(`Failed to execute AI command: ${response.statusText}`);
  }
  return response.json();
}
