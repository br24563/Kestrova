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
  "thin_lens" | "spherical_surface" | "thick_lens" | "aperture" | "mirror";

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

export interface ThickLens extends OpticalComponentBase {
  type: "thick_lens";
  radius1: number; // meters
  radius2: number; // meters
  thickness: number; // meters
  aperture_diameter: number; // meters
  material: string;
}

export interface ApertureStop extends OpticalComponentBase {
  type: "aperture";
  diameter: number; // meters
}

export interface Mirror extends OpticalComponentBase {
  type: "mirror";
  width: number; // meters
  radius?: number; // meters, 0 = flat (backend default 0)
  conic?: number; // conic constant, 0 sphere, -1 paraboloid (default 0)
  aperture_diameter?: number | null; // meters (defaults to width)
}

export type OpticalComponent =
  ThinLens | SphericalSurface | ThickLens | ApertureStop | Mirror;

// ---------------------------------------------------------------------------
// Object and Image Plane
// ---------------------------------------------------------------------------

export interface OpticalObject {
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

/** One field point (Code V field table); units follow `field_type`. */
export interface FieldPoint {
  x: number;
  y: number;
  weight?: number;
  vux?: number; // Code V vignetting factors, each in [0, 1)
  vlx?: number;
  vuy?: number;
  vly?: number;
}

export type FieldType = "object_height" | "angle" | "paraxial_image_height";

export interface OpticalSystem {
  components: OpticalComponent[];
  wavelengths: number[];
  object: OpticalObject;
  image_plane: ImagePlane;
  analysis_settings: AnalysisSettings;
  /** Field table; null/absent = 0, 0.7 and 1 of the object height. */
  fields?: FieldPoint[] | null;
  /** Units of the field points; null = angle at infinity, else object height. */
  field_type?: FieldType | null;
  /** One weight per wavelength; null = equal. */
  wavelength_weights?: number[] | null;
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

// The backend sends null for infinite values (JSON has no infinity), e.g.
// the focal length of an afocal system or an image at infinity.
export interface AnalysisResult {
  effective_focal_length: number | null;
  magnification: number | null;
  image_distance: number | null;
  object_distance: number | null;
  f_number: number | null;
  numerical_aperture: number;
  aperture_diameter: number;
  working_distance: number | null;
  rms_spot_radius: number;
  /** Real-ray [x, y] image-plane intercepts relative to the centroid (m). */
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

export interface ChromaticAberrationResult {
  wavelengths: number[];
  image_positions: number[];
  image_heights: number[];
  lca: number;
  tca: number;
}

export type OptimizeObjective = "rms_spot" | "magnification" | "efl";

export interface OptimizeRequest {
  system: OpticalSystem;
  objective: OptimizeObjective;
  target?: number;
  params: { component_id: string; field: string }[];
  bounds: [number, number][];
}

export interface OptimizeResult {
  params: number[];
  objective: number;
  system: OpticalSystem;
  success: boolean;
}

export interface SweepRequest {
  system: OpticalSystem;
  param: { component_id: string; field: string };
  values: number[];
  num_rays?: number;
  aperture_fraction?: number;
}

export interface SweepPoint {
  value: number;
  analysis: AnalysisResult;
}

// ---------------------------------------------------------------------------
// Diffraction Analysis Types
// ---------------------------------------------------------------------------

export interface PSFData {
  r: number[]; // radial distances (meters)
  intensity: number[]; // normalized intensity
}

export interface EncircledEnergyData {
  r: number[]; // radial distances (meters)
  energy: number[]; // fraction of total energy
}

export interface MTFData {
  frequency: number[]; // spatial frequency (cycles/meter)
  mtf: number[]; // system MTF (tangential) from the FFT of the pupil function
  tangential?: number[];
  sagittal?: number[];
  diffraction_limit?: number[]; // aberration-free MTF for the same NA
  cutoff: number; // cutoff frequency 2 NA / lambda (cycles/meter)
}

export interface DiffractionLimitedCheck {
  airy_disk_radius: number; // meters
  rms_spot_radius: number; // meters (geometric, for reference)
  strehl_ratio: number;
  rms_wavefront: number; // meters
  rms_wavefront_waves: number;
  criterion: string; // "Strehl >= 0.8 (Marechal)"
  is_diffraction_limited: boolean;
  margin: number | null; // Airy radius / RMS spot (null = infinite)
}

export interface DiffractionResult {
  psf: PSFData;
  encircled_energy: EncircledEnergyData;
  mtf: MTFData;
  airy_disk_radius: number;
  strehl_ratio: number;
  rms_wavefront: number;
  na_image: number;
  working_f_number: number;
  diffraction_limited: DiffractionLimitedCheck;
}

// ---------------------------------------------------------------------------
// Seidel Aberration Types
// ---------------------------------------------------------------------------

export interface SphericalAberrationData {
  longitudinal: number; // meters
  transverse: number; // meters
}

export interface SeidelResult {
  spherical_aberration: SphericalAberrationData;
  coma: number; // meters
  astigmatism: number; // meters
  field_curvature: number; // meters
  distortion: number; // dimensionless fraction
  paraxial_image_position: number; // meters
  paraxial_image_height: number; // meters
  tangential_focus: number; // meters, relative to the paraxial image
  sagittal_focus: number; // meters, relative to the paraxial image
  petzval_field_curvature: number; // meters
  longitudinal_color: number; // meters
  lateral_color: number; // meters
}

// ---------------------------------------------------------------------------
// Tolerance Analysis Types
// ---------------------------------------------------------------------------

export interface ToleranceResult {
  mean: number;
  std: number;
  min: number;
  max: number;
  p95: number;
  trials: number;
  trend: number[];
}

export interface ToleranceRequest {
  system: OpticalSystem;
  tolerances?: Record<string, number>;
  trials?: number;
  seed?: number;
}

// ---------------------------------------------------------------------------
// System Comparison Types
// ---------------------------------------------------------------------------

export interface ComparisonRow {
  metric: string;
  a: number;
  b: number;
  advantage: "a" | "b" | "tie";
}

export interface SystemSummary {
  label: string;
  magnification: number;
  efl_mm: number;
  f_number: number;
  numerical_aperture: number;
  rms_spot_um: number;
  image_distance_mm: number;
  working_distance_mm: number;
  is_image_real: boolean;
  is_image_inverted: boolean;
  num_components: number;
}

export interface ComparisonResult {
  rows: ComparisonRow[];
  summary_a: SystemSummary;
  summary_b: SystemSummary;
}

export interface CompareRequest {
  system_a: OpticalSystem;
  system_b: OpticalSystem;
  label_a?: string;
  label_b?: string;
}

// ---------------------------------------------------------------------------
// Unit Conversion Helpers
// ---------------------------------------------------------------------------

export const MM_TO_M = 0.001;
export const M_TO_MM = 1000;
export const NM_TO_M = 1e-9;
export const M_TO_NM = 1e9;

// Supported display units for length. Each maps to its factor TO meters.
export type LengthUnit = "nm" | "um" | "mm" | "cm" | "m";

export const LENGTH_UNIT_FACTORS: Record<LengthUnit, number> = {
  nm: 1e-9,
  um: 1e-6,
  mm: 1e-3,
  cm: 1e-2,
  m: 1.0,
};

export const LENGTH_UNIT_LABELS: Record<LengthUnit, string> = {
  nm: "nm",
  um: "μm",
  mm: "mm",
  cm: "cm",
  m: "m",
};

export const DEFAULT_LENGTH_UNIT: LengthUnit = "mm";

/**
 * Convert a value in meters to the given display unit.
 */
export function fromMeters(meters: number, unit: LengthUnit): number {
  return meters / LENGTH_UNIT_FACTORS[unit];
}

/** Format a number that may be null (infinite in the backend) as "∞". */
export function fmtNum(
  value: number | null | undefined,
  digits: number,
): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "∞";
  return value.toFixed(digits);
}

/** Format a length in meters (null = infinite) in the given display unit. */
export function fmtLen(
  meters: number | null | undefined,
  unit: LengthUnit,
  digits: number,
): string {
  if (meters === null || meters === undefined || !Number.isFinite(meters))
    return "∞";
  return fromMeters(meters, unit).toFixed(digits);
}

/**
 * Convert a value in the given display unit to meters.
 */
export function toMeters(value: number, unit: LengthUnit): number {
  return value * LENGTH_UNIT_FACTORS[unit];
}

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

// ---------------------------------------------------------------------------
// Lens Data (surface-by-surface prescription, mirrors optics/lens_data.py)
// ---------------------------------------------------------------------------

export type SurfaceType =
  "standard" | "even_asphere" | "paraxial" | "coordinate_break" | "component";

export type SolveKind =
  | "marginal_height"
  | "chief_height"
  | "marginal_angle"
  | "chief_angle"
  | "f_number";

export const THICKNESS_SOLVES: SolveKind[] = [
  "marginal_height",
  "chief_height",
];
export const RADIUS_SOLVES: SolveKind[] = [
  "marginal_angle",
  "chief_angle",
  "f_number",
];

/** A parameter computed from a paraxial ray (target: m, slope, or F-number). */
export interface Solve {
  kind: SolveKind;
  target: number;
}

/** parameter = scale * (surface `source`'s `parameter`) + offset. */
export interface Pickup {
  source: number; // 0-based surface index
  parameter?: string | null; // default: the same parameter
  scale: number;
  offset: number;
}

/** One row of the lens data editor. Lengths in meters, angles in radians. */
export interface LensSurface {
  label: string;
  element?: string | null;
  surface_type: SurfaceType;
  radius: number; // 0 = flat
  conic: number;
  aspheric_coefficients: number[];
  thickness: number; // to the next surface
  material: string | null; // medium after; null = air, "MIRROR" reflects
  semi_diameter: number | null; // null = automatic
  is_stop: boolean;
  focal_length?: number | null;
  ideal_lens_glass?: string;
  decenter_x?: number;
  decenter_y?: number;
  decenter_z?: number;
  tilt_x?: number;
  tilt_y?: number;
  tilt_z?: number;
  break_order?: string;
  component?: Record<string, unknown> | null;
  variables: string[];
  solves: Record<string, Solve>;
  pickups: Record<string, Pickup>;
  semi_diameter_auto: boolean;
}

export interface LensData {
  name: string;
  surfaces: LensSurface[];
  object_distance: number | null; // null = object at infinity
  object_height: number;
  field_angle: number; // rad, for an object at infinity
  entrance_pupil_diameter: number | null;
  wavelengths: number[];
  first_surface_position: number;
  analysis_settings: AnalysisSettings;
}

export interface LensFirstOrder {
  efl: number | null;
  bfl: number | null;
  f_number: number | null;
  working_f_number: number | null;
  image_z: number | null;
  image_height: number | null;
  magnification: number | null;
  entrance_pupil_diameter: number;
  exit_pupil_z: number | null;
}

export interface LensResolveResult {
  lens: LensData;
  system: OpticalSystem;
  first_order: LensFirstOrder;
}

export interface LensOptimizeResult extends LensResolveResult {
  variables: Record<string, number>;
  merit_before: number;
  merit_after: number;
  rms_spot_before: number; // meters
  rms_spot_after: number; // meters
  evaluations: number;
  success: boolean;
  message: string;
}
