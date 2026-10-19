/**
 * Pure edits on a LensData prescription (no backend calls), used by the
 * lens data editor: inserting and deleting rows with pickup sources kept
 * pointing at the same surfaces, and the variable / solve / pickup flag
 * of a single parameter.
 */

import type { LensData, LensSurface, Pickup, Solve, SurfaceType } from "../../types";

/** How a parameter's value is determined. */
export type Modifier =
  | { kind: "fixed" }
  | { kind: "variable" }
  | { kind: "solve"; solve: Solve }
  | { kind: "pickup"; pickup: Pickup };

/** Parameters each surface type has (mirrors lens_data.PARAMETERS, minus aspheric terms). */
export const SURFACE_PARAMETERS: Record<SurfaceType, string[]> = {
  standard: ["radius", "thickness", "conic", "semi_diameter"],
  even_asphere: ["radius", "thickness", "conic", "semi_diameter"],
  paraxial: ["focal_length", "thickness", "semi_diameter"],
  coordinate_break: ["thickness"],
  component: ["thickness"],
};

export function hasParameter(surface: LensSurface, param: string): boolean {
  return SURFACE_PARAMETERS[surface.surface_type].includes(param);
}

export function newSurface(): LensSurface {
  return {
    label: "",
    element: null,
    surface_type: "standard",
    radius: 0,
    conic: 0,
    aspheric_coefficients: [],
    thickness: 0,
    material: null,
    semi_diameter: null,
    is_stop: false,
    variables: [],
    solves: {},
    pickups: {},
    semi_diameter_auto: false,
  };
}

function mapPickups(
  surface: LensSurface,
  remap: (source: number) => number | null,
): LensSurface {
  const pickups: Record<string, Pickup> = {};
  for (const [param, p] of Object.entries(surface.pickups)) {
    const source = remap(p.source);
    if (source !== null) pickups[param] = { ...p, source };
  }
  return { ...surface, pickups };
}

/** Insert a new surface so that it becomes surface `index`. */
export function insertSurface(lens: LensData, index: number, surface: LensSurface = newSurface()): LensData {
  const i = Math.max(0, Math.min(index, lens.surfaces.length));
  const shifted = lens.surfaces.map((s) => mapPickups(s, (src) => (src >= i ? src + 1 : src)));
  return { ...lens, surfaces: [...shifted.slice(0, i), surface, ...shifted.slice(i)] };
}

/**
 * Delete surface `index`. Pickups from it are dropped (the picked-up value
 * stays as a fixed value); the stop cannot be deleted.
 */
export function deleteSurface(lens: LensData, index: number): LensData {
  if (index < 0 || index >= lens.surfaces.length) return lens;
  if (lens.surfaces[index].is_stop) {
    throw new Error("The aperture stop cannot be deleted; move the stop to another surface first");
  }
  if (lens.surfaces.length <= 1) throw new Error("A lens needs at least one surface");
  const surfaces = lens.surfaces
    .filter((_, k) => k !== index)
    .map((s) => mapPickups(s, (src) => (src === index ? null : src > index ? src - 1 : src)));
  return { ...lens, surfaces };
}

/** Make surface `index` the (only) aperture stop. */
export function setStop(lens: LensData, index: number): LensData {
  return {
    ...lens,
    surfaces: lens.surfaces.map((s, k) => (s.is_stop === (k === index) ? s : { ...s, is_stop: k === index })),
  };
}

export function getModifier(surface: LensSurface, param: string): Modifier {
  if (surface.variables.includes(param)) return { kind: "variable" };
  const solve = surface.solves[param];
  if (solve) return { kind: "solve", solve };
  const pickup = surface.pickups[param];
  if (pickup) return { kind: "pickup", pickup };
  return { kind: "fixed" };
}

/** The surface with `param` made fixed, variable, solved or picked up (exclusive). */
export function setModifier(surface: LensSurface, param: string, modifier: Modifier): LensSurface {
  const variables = surface.variables.filter((v) => v !== param);
  const solves = { ...surface.solves };
  const pickups = { ...surface.pickups };
  delete solves[param];
  delete pickups[param];
  if (modifier.kind === "variable") variables.push(param);
  if (modifier.kind === "solve") solves[param] = modifier.solve;
  if (modifier.kind === "pickup") pickups[param] = modifier.pickup;
  return { ...surface, variables, solves, pickups };
}

/** Number of parameters flagged as variables. */
export function countVariables(lens: LensData): number {
  return lens.surfaces.reduce((n, s) => n + s.variables.length, 0);
}
