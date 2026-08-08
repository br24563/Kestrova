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
} from "./types";

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
