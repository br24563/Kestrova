/**
 * System properties shared by constraints and merit operands (mirrors
 * lens_data.ConstraintKind): labels, units and display conversion.
 */
import { LENGTH_UNIT_LABELS, fromMeters, toMeters } from "../../types";
import type { LengthUnit, LensConstraintKind } from "../../types";

export const PROPERTY_LABELS: Record<LensConstraintKind, string> = {
  efl: "Effective focal length",
  bfl: "Back focal length",
  working_f_number: "Working F-number",
  magnification: "Magnification",
  total_track: "Total track",
  center_thickness: "Centre thickness",
  edge_thickness: "Edge thickness",
  distortion: "Distortion",
  chief_ray_angle: "Chief-ray angle",
  image_height: "Real image height",
  spot_rms: "RMS spot radius",
  wavefront_rms: "RMS wavefront",
  lateral_color: "Lateral colour",
  axial_color: "Axial colour",
  seidel_S1: "Seidel S-I (spherical)",
  seidel_S2: "Seidel S-II (coma)",
  seidel_S3: "Seidel S-III (astigmatism)",
  seidel_S4: "Seidel S-IV (Petzval)",
  seidel_S5: "Seidel S-V (distortion)",
};

type Unit = "length" | "angle" | "fraction" | "waves" | "number";

const UNITS: Record<LensConstraintKind, Unit> = {
  efl: "length",
  bfl: "length",
  working_f_number: "number",
  magnification: "number",
  total_track: "length",
  center_thickness: "length",
  edge_thickness: "length",
  distortion: "fraction",
  chief_ray_angle: "angle",
  image_height: "length",
  spot_rms: "length",
  wavefront_rms: "waves",
  lateral_color: "length",
  axial_color: "length",
  seidel_S1: "length",
  seidel_S2: "length",
  seidel_S3: "length",
  seidel_S4: "length",
  seidel_S5: "length",
};

/** Properties measured at one field (default: the last of the field table). */
export const FIELD_PROPERTIES: LensConstraintKind[] = [
  "distortion",
  "chief_ray_angle",
  "image_height",
  "spot_rms",
  "wavefront_rms",
  "lateral_color",
];

export function isLengthProperty(kind: LensConstraintKind): boolean {
  return UNITS[kind] === "length";
}

/** A property value (SI: m, rad, fraction, waves) in display units. */
export function toDisplayValue(
  kind: LensConstraintKind,
  v: number,
  unit: LengthUnit,
): number {
  switch (UNITS[kind]) {
    case "length":
      return fromMeters(v, unit);
    case "angle":
      return (v * 180) / Math.PI;
    case "fraction":
      return v * 100;
    default:
      return v;
  }
}

/** The SI value of a property shown in display units. */
export function fromDisplayValue(
  kind: LensConstraintKind,
  v: number,
  unit: LengthUnit,
): number {
  switch (UNITS[kind]) {
    case "length":
      return toMeters(v, unit);
    case "angle":
      return (v * Math.PI) / 180;
    case "fraction":
      return v / 100;
    default:
      return v;
  }
}

/** The unit label of a property in display units ("" for pure numbers). */
export function unitLabel(kind: LensConstraintKind, unit: LengthUnit): string {
  switch (UNITS[kind]) {
    case "length":
      return LENGTH_UNIT_LABELS[unit];
    case "angle":
      return "°";
    case "fraction":
      return "%";
    case "waves":
      return "waves";
    default:
      return "";
  }
}

/** A value for display, 8 significant figures. */
export function showValue(
  kind: LensConstraintKind,
  v: number | null | undefined,
  unit: LengthUnit,
): string {
  if (v === null || v === undefined) return "";
  return String(Number(toDisplayValue(kind, v, unit).toPrecision(8)));
}
