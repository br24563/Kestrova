/**
 * Prescription Types.
 *
 * Types for the optical prescription editor.
 */

export type SurfaceType = 'standard' | 'aspheric' | 'grin' | 'diffractive' | 'aperture' | 'image';

export interface SurfaceRow {
  id: number;
  type: SurfaceType;
  label: string;  // e.g., "OBJ", "STO", "IMG", or custom
  radius: number | null;  // mm, null for infinity
  thickness: number | null;  // mm, null for variable
  material: string | null;  // glass name or "Air"
  conic: number;  // conic constant
  semiDiameter: number | null;  // mm
  apertureRadius: number | null;  // mm
  // Aspheric coefficients
  asphericA4: number;
  asphericA6: number;
  asphericA8: number;
  asphericA10: number;
  // GRIN parameters (if applicable)
  grinN0: number | null;
  grinG: number | null;
  // Solve types
  solveType: 'none' | 'marginal_angle' | 'edge_thickness' | 'pickup' | 'variable';
  solveValue: number | null;
  // Status
  isStop: boolean;
  isVariable: boolean;
  isPickedUp: boolean;
  pickupFrom: number | null;  // surface index to pickup from
}

export interface PrescriptionData {
  surfaces: SurfaceRow[];
  systemSettings: {
    wavelengthPrimary: number;  // nm
    wavelengthWeights: { wavelength: number; weight: number }[];
    entrancePupilDiameter: number;  // mm
    fieldAngle: number;  // degrees
    fNumber: number | null;
    objectDistance: number | null;  // mm, null for infinity
  };
  solves: {
    type: string;
    surface: number;
    value: number;
  }[];
}

export const DEFAULT_SURFACE: Omit<SurfaceRow, 'id'> = {
  type: 'standard',
  label: '',
  radius: null,
  thickness: null,
  material: 'Air',
  conic: 0,
  semiDiameter: null,
  apertureRadius: null,
  asphericA4: 0,
  asphericA6: 0,
  asphericA8: 0,
  asphericA10: 0,
  grinN0: null,
  grinG: null,
  solveType: 'none',
  solveValue: null,
  isStop: false,
  isVariable: false,
  isPickedUp: false,
  pickupFrom: null,
};

export const GLASS_CATALOG = [
  'Air',
  'N-BK7',
  'N-SF11',
  'N-SF2',
  'N-SF5',
  'N-SF6',
  'N-SF57',
  'N-FK5',
  'N-FK51A',
  'N-PK52A',
  'N-LAK8',
  'N-LAK9',
  'N-LAK10',
  'N-LAK33',
  'N-LAF2',
  'N-LAF34',
  'N-LASF44',
  'N-SK5',
  'N-SK16',
  'N-SSK5',
  'N-SSK8',
  'FusedSilica',
  'CaF2',
  'ZnSe',
  'ZnS',
  'Si',
  'Ge',
];
