/**
 * TypeScript type definitions for the optical design engine.
 *
 * These types mirror the Python Pydantic models in the backend.
 * All length values are in meters (SI base unit).
 * All angle values are in radians (SI base unit).
 */

// ---------------------------------------------------------------------------
// Optical Components
// ---------------------------------------------------------------------------

export type ComponentType =
  | "thin_lens"
  | "spherical_surface"
  | "aperture"
  | "mirror";

export interface OpticalComponentBase {
  id: string;
  position: number; // meters along optical axis
}

export interface ThinLens extends OpticalComponentBase {
  type: "thin_lens";
  focal_length: number; // meters
  aperture_diameter: number; // meters
  material: string;
}

export interface SphericalSurface extends OpticalComponentBase {
  type: "spherical_surface";
  radius: number; // meters
  thickness: number; // meters
  material: string;
}

export interface ApertureStop extends OpticalComponentBase {
  type: "aperture";
  diameter: number; // meters
}

export interface Mirror extends OpticalComponentBase {
  type: "mirror";
  width: number; // meters
}

export type OpticalComponent =
  | ThinLens
  | SphericalSurface
  | ApertureStop
  | Mirror;

// ---------------------------------------------------------------------------
// Object and Image Plane
// ---------------------------------------------------------------------------

export interface Object {
  position: number; // meters
  height: number; // meters
  orientation: number; // radians
}

export interface ImagePlane {
  position: number; // meters
}

// ---------------------------------------------------------------------------
// Analysis Settings
// ---------------------------------------------------------------------------

export interface AnalysisSettings {
  num_rays: number;
  ray_types: string[];
  aperture_fraction: number;
  wavelength: number; // meters
}

// ---------------------------------------------------------------------------
// Optical System
// ---------------------------------------------------------------------------

export interface OpticalSystem {
  components: OpticalComponent[];
  wavelengths: number[];
  object: Object;
  image_plane: ImagePlane;
  analysis_settings: AnalysisSettings;
}

// ---------------------------------------------------------------------------
// Ray Tracing Models
// ---------------------------------------------------------------------------

export interface Ray {
  y: number; // meters
  theta: number; // radians
  z: number; // meters
  wavelength: number; // meters
  ray_type: string;
}

export interface RayPath {
  points: [number, number][]; // [z, y] points in meters
  ray_type: string;
  wavelength: number;
  initial_y: number;
  initial_theta: number;
  final_y: number;
  final_theta: number;
}

export interface RayTraceResult {
  ray_paths: RayPath[];
  image_position: number;
  image_height: number;
  paraxial_image_height: number;
}

// ---------------------------------------------------------------------------
// Analysis Result
// ---------------------------------------------------------------------------

export interface AnalysisResult {
  effective_focal_length: number;
  magnification: number;
  image_distance: number;
  object_distance: number;
  f_number: number;
  numerical_aperture: number;
  aperture_diameter: number;
  working_distance: number;
  rms_spot_radius: number;
  spot_points: [number, number][];
  is_image_real: boolean;
  is_image_inverted: boolean;
}

// ---------------------------------------------------------------------------
// API Response Types
// ---------------------------------------------------------------------------

export interface SystemResponse {
  system: OpticalSystem;
  warnings: string[];
}

export interface TraceRequest {
  system: OpticalSystem;
  num_rays?: number;
  aperture_fraction?: number;
}

export interface AnalyzeRequest {
  system: OpticalSystem;
  num_rays?: number;
  aperture_fraction?: number;
}

// ---------------------------------------------------------------------------
// Unit Conversion Helpers
// ---------------------------------------------------------------------------

export const MM_TO_M = 0.001;
export const M_TO_MM = 1000;
export const NM_TO_M = 1e-9;
export const M_TO_NM = 1e9;

export function toMM(meters: number): number {
  return meters * M_TO_MM;
}

export function toM(mm: number): number {
  return mm * MM_TO_M;
}

export function toNm(meters: number): number {
  return meters * M_TO_NM;
}

export function formatValue(value: number, decimals: number = 3): string {
  return value.toFixed(decimals);
}
