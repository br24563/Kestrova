# API Reference

## Base URL

```
http://localhost:8000/api
```

## Endpoints

### System

#### GET /api/system/default

Returns the default two-lens optical system.

**Response:**
```json
{
  "system": { ... },
  "warnings": []
}
```

#### GET /api/health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.2.0",
  "features": {
    "ray_tracing": true,
    "analysis": true,
    ...
  }
}
```

### Fields and wavelength weights

Any `system` (and any `lens`) may carry a field table and wavelength
weights; without them results are unchanged.

```json
{
  "fields": [ { "x": 0, "y": 0 },
              { "x": 0, "y": 0.0698, "weight": 2, "vuy": 0.2, "vly": 0.1 } ],
  "field_type": "angle",
  "wavelength_weights": [1, 2, 1]
}
```

`field_type` is `object_height` (m, finite object), `angle` (rad, object
at infinity; direction tangents tan x, tan y) or `paraxial_image_height`
(m); null picks angle or object height from the object distance. The
vignetting factors `vux`, `vlx`, `vuy`, `vly` limit the pupil to
-(1 - vl) .. (1 - vu) as in Code V. Without a table the fields are 0, 0.7
and 1 of the object height along y.

#### POST /api/analyze/fields

`{ "system", "rings": 8 }` → per field: real chief ray and paraxial image
position, distortion, wavelength-weighted RMS spot and centroid (pupil
integrated by Gaussian quadrature), each wavelength's RMS and the vignetted
fraction; plus `weighted_rms_spot` = sqrt(sum w rms^2 / sum w).

#### POST /api/analyze/field-mtf

`{ "system", "field": 1, "frequencies": [10, 20, 40], "grid": 64 }` →
wavelength-weighted diffraction MTF of one field, tangential along the
field's image direction and sagittal across it (cycles/mm).

### Lens Data (surface-by-surface prescription)

A `lens` is a Code V / Zemax style surface table. Each surface has
`radius` (0 = flat), `thickness` to the next surface, `conic`,
`aspheric_coefficients` (A4, A6, ...), `material` after it (null = air,
`"MIRROR"` reflects), `semi_diameter` (null = automatic from real rays) and
`is_stop` (exactly one surface). Per surface, `variables` lists parameters
the optimizer may change, `solves` maps `thickness` or `radius` to a solve,
and `pickups` maps a parameter to `{source, parameter, scale, offset}`.
Lens-level fields: `object_distance` (null = infinity), `object_height` or
`field_angle` (rad), optional `entrance_pupil_diameter`, `wavelengths`.

Solve kinds: `marginal_height` / `chief_height` (thickness; target height
at the next surface, 0 = paraxial image), `marginal_angle` / `chief_angle`
(radius; target slope after the surface) and `f_number` (radius; working
F-number).

#### POST /api/lens/from-system

`{ "system": {...} }` → `{ "lens": {...} }`, the prescription of a
component-based system (round trip is exact).

#### POST /api/lens/resolve

`{ "lens": {...} }` → `{ "lens", "system", "first_order" }`: pickups and
solves applied, automatic semi-diameters filled, the component-based
`system` for every other analysis endpoint, and EFL, BFL, F-numbers, image
position and pupils.

```json
{
  "lens": {
    "surfaces": [
      { "label": "STO", "is_stop": true, "semi_diameter": 0.008, "thickness": 0.002 },
      { "element": "L1", "radius": 0.05, "thickness": 0.006, "material": "N-BK7",
        "variables": ["radius"] },
      { "element": "L1", "radius": -0.08, "thickness": 0.1,
        "solves": { "radius": { "kind": "f_number", "target": 4 },
                    "thickness": { "kind": "marginal_height" } } }
    ],
    "object_distance": null,
    "field_angle": 0.0873
  }
}
```

#### POST /api/lens/optimize

`{ "lens", "bounds": {"1.radius": [0.02, 1.0]}, "max_evaluations": 300 }`
→ constrained damped least squares over the variables, minimising the
transverse ray errors over fields 0, 0.7 and 1 and all wavelengths with
solves, pickups and the lens's `constraints` held. Radius bounds must not
span a flat surface (radii vary as curvatures). Returns the optimized `lens`
and `system`, `variables`, `rms_spot_before` / `rms_spot_after` (m),
`first_order`, `constraints` (each with its `value` and `satisfied`),
`history` (merit, violation and damping per cycle), `iterations`,
`evaluations`, `success` (all constraints met) and `message`. As in Code V,
only the stop limits the beam while optimizing.

Constraints are part of the lens:

```json
"constraints": [
  {"kind": "efl", "target": 0.1},
  {"kind": "edge_thickness", "surface": 1, "minimum": 0.0015},
  {"kind": "center_thickness", "surface": 2, "minimum": 0.002, "maximum": 0.006}
]
```

Kinds: `efl`, `bfl`, `working_f_number`, `magnification`, `total_track`,
and per surface `center_thickness` and `edge_thickness` (m). Give a
`target`, or a `minimum` and/or `maximum`.

A surface whose `material` is a model glass, `"MODEL:<nd>:<vd>"`, may list
`glass_nd` and `glass_vd` among its `variables`; they stay inside the
catalog glass map.

#### POST /api/lens/tolerance

Fast tolerancing in the manner of Code V's TOR.

`{ "lens", "tolerances": [...], "compensators": [...], "trials": 20000,
"rings": 6, "seed": 0, "rss_budget": 0.05 }`

Tolerances use Code V's names:

| Kind | Meaning |
|---|---|
| `DLF` | Radius error in fringes at `test_wavelength` over `test_diameter` |
| `DLR` | Radius error (m) |
| `DLT` | Thickness error (m) |
| `DLN`, `DLV` | Index and Abbe-number errors of the glass after the surface |
| `DSX`, `DSY` | Surface decenter (m) |
| `TRX`, `TRY` | Surface tilt (rad) |
| `DLX`, `DLY` | Element decenter (m), over `surface`..`last_surface` |
| `BTX`, `BTY` | Element tilt (rad), over `surface`..`last_surface` |

Each tolerance takes a `limit` (±) and a `distribution`: `uniform`,
`gaussian` (σ = limit/2, truncated at the limit) or `end_point`. Without
`tolerances`, the starting set from `/api/lens/tolerance/defaults` is used.

Compensators: `{"kind": "back_focus"}` (the default) or `{"kind":
"thickness", "surface": i}`, with an optional `limit`.

Returns, all in waves:

- `nominal_rms` and `nominal_field_rms`: RMS wavefront error with piston and
  tilt removed, over the fields and wavelengths with their weights;
- `sensitivities`: the traced, compensated RMS at +limit and -limit for
  each tolerance;
- `rss_increase`;
- `predicted`: mean, std, the 50 / 84.13 / 97.72 / 99.87 % percentiles and
  the cumulative curve, from Monte Carlo on a fitted model of the wavefront
  that is quadratic in each tolerance and linear in the compensators;
- `predicted_fields` and `compensators` statistics;
- with `rss_budget`, `inverse_limits`: the limit at which each tolerance
  alone uses an equal share of the budget.

Solves and pickups are frozen before tolerancing.

#### POST /api/lens/tolerance/monte-carlo

Same inputs (`trials` ≤ 500). An exact reference: each trial is perturbed
and traced, and its compensators are re-optimized. Returns the RMS of every
trial, the mean, std and percentiles, and the compensation applied.

#### POST /api/lens/tolerance/defaults

`{ "lens" }` → a starting tolerance set for every element. The values are
editable starting points, not a standard.

#### POST /api/lens/constraints

`{ "lens" }` → `{"constraints": [...]}`, each with its current `value` and
`satisfied`.

#### POST /api/lens/snap-glasses

`{ "lens", "vendors": ["SCHOTT"], "include_inquiry": false }` → the lens with
every model glass replaced by the nearest catalog glass (0.01 in nd counts as
1 in Vd), its glass variables dropped, and `substitutions`
(`[{"surface", "model", "glass"}]`). Re-optimize afterwards.

### Ray Tracing

#### POST /api/trace

Trace rays through an optical system.

**Request:**
```json
{
  "system": { ... },
  "num_rays": 11,
  "aperture_fraction": 1.0
}
```

**Response:**
```json
{
  "ray_paths": [
    {
      "points": [[z, y], ...],
      "ray_type": "chief",
      "wavelength": 5.5e-07
    }
  ],
  "image_position": 0.175,
  "image_height": 0.005
}
```

### Analysis

#### POST /api/analyze

Perform optical analysis.

**Request:**
```json
{
  "system": { ... },
  "num_rays": 11,
  "aperture_fraction": 1.0
}
```

**Response:**
```json
{
  "effective_focal_length": 0.05,
  "magnification": -0.5,
  "image_distance": 0.075,
  "f_number": 2.0,
  "numerical_aperture": 0.124,
  "rms_spot_radius": 0.0001,
  "spot_points": [[0.0, 1.2e-06], ...],
  "is_image_real": true,
  "is_image_inverted": true
}
```

#### POST /api/analyze/diffraction

Diffraction analysis from the real wavefront (FFT PSF and MTF), with the
diffraction limit for the same NA. Afocal systems (image at infinity) are
rejected with 400.

**Response:**
```json
{
  "psf": { "r": [...], "intensity": [...] },
  "encircled_energy": { "r": [...], "energy": [...] },
  "mtf": { "frequency": [...], "mtf": [...], "tangential": [...], "sagittal": [...],
           "diffraction_limit": [...], "cutoff": 363636.0 },
  "airy_disk_radius": 1.34e-06,
  "strehl_ratio": 0.97,
  "rms_wavefront": 2.1e-08,
  "na_image": 0.25,
  "working_f_number": 2.0,
  "diffraction_limited": { "strehl_ratio": 0.97, "criterion": "Strehl >= 0.8 (Marechal)",
                           "is_diffraction_limited": true, ... }
}
```

#### POST /api/analyze/seidel

Seidel aberration analysis.

**Response:**
```json
{
  "spherical_aberration": { "longitudinal": 0.001, "transverse": 0.0001 },
  "coma": 0.0005,
  "astigmatism": 0.0002,
  "field_curvature": 0.0001,
  "tangential_focus": 0.0002,
  "sagittal_focus": 0.0001,
  "distortion": 0.01,
  "seidel_sums": { "S1": ..., "S2": ..., "S3": ..., "S4": ..., "S5": ..., "CL": ..., "CT": ... },
  "real": { "transverse_spherical": ..., ... }
}
```

Third-order values at full aperture and field (meters; distortion is a
fraction); focus positions are relative to the paraxial image. Afocal
systems are rejected with 400.

#### POST /api/analyze/ray-fan

Real-ray transverse ray fans at the system image plane, relative to the
chief ray. Body: `{ "system": ..., "field_fraction": 1.0, "num_rays": 21 }`.

**Response:** `pupil_x` (-1..1), `transverse_t` (y error vs py),
`transverse_s` (x error vs px), `transverse_s_y`, `chief_ray_height`,
`paraxial_image_height`, `field_max` and `field_unit` (`"deg"` for an object
at infinity, else `"m"`). Lengths in meters; null marks a vignetted ray.

#### POST /api/analyze/opd-fan

Same body as `ray-fan`. OPD along the tangential (`opd_t`) and sagittal
(`opd_s`) pupil axes against `pupil`, referenced to the chief ray at the
image plane (meters), plus `opd_rms`, `opd_peak_to_valley` and
`strehl_ratio` over the full 2D pupil and `wavelength`.

#### POST /api/analyze/field-curves

Body: `{ "system": ..., "num_fields": 11 }`. Real tangential, sagittal and
medial foci (relative to the paraxial image, meters), third-order `petzval`,
`astigmatism` and real `distortion` (fraction) at each of `field_fractions`,
plus `field_max` / `field_unit`.

The three endpoints above return 400 when the image is at infinity.


#### POST /api/analyze/aberration

Chromatic aberration analysis.

**Response:**
```json
{
  "wavelengths": [4.86e-07, 5.88e-07, 6.56e-07],
  "image_positions": [0.075, 0.075, 0.074],
  "lca": 0.001,
  "tca": 0.0001
}
```

#### POST /api/analyze/ghosts

Ghost reflection analysis.

**Response:**
```json
{
  "ghosts": [
    {
      "surfaces": [0, 1],
      "reflection_count": 2,
      "relative_intensity": 0.0016,
      "is_in_field": true
    }
  ]
}
```

#### POST /api/analyze/straylight

Stray light path analysis.

#### POST /api/analyze/pst

Point Source Transmittance vs angle.

### Optimization

#### POST /api/optimize

Basic optimization.

**Request:**
```json
{
  "system": { ... },
  "objective": "rms_spot",
  "params": [{ "component_id": "L1", "field": "focal_length" }],
  "bounds": [[0.05, 0.15]],
  "constraints": [{ "type": "efl", "lower": 0.09, "upper": 0.11 }]
}
```

#### POST /api/optimize/hybrid

Hybrid global+local optimization. `objective` is `rms_spot`, `efl` or
`magnification` (the last two need `target`); `global_algorithm` is
`differential_evolution` or `particle_swarm`; `local_algorithm` is
`damped_least_squares`, `l_bfgs_b` or `nelder_mead` (no local step).
A null constraint bound means unbounded on that side.

#### POST /api/optimize/high-yield

High-yield optimization with tolerances (`rms_spot` objective only;
`global_maxiter` default 50, `local_maxiter` default 25).

#### POST /api/optimize/constraints

Body: `{ "system": ..., "constraints": [{ "type": "efl", "surface_index": null, "lower": 0.099, "upper": null, "weight": 1 }] }`.
Returns each operand's current `value`, `violation` and `penalty`
(weight x violation x 1e6, as the hybrid optimizer adds it), or `error`
when it cannot be evaluated for this system.

### Tolerance

#### POST /api/tolerance

Monte Carlo tolerance analysis.

**Request:**
```json
{
  "system": { ... },
  "tolerances": { "L1.position": 0.0001 },
  "trials": 100,
  "seed": 42
}
```

**Response:**
```json
{
  "mean": 0.0001,
  "std": 0.00001,
  "min": 0.00009,
  "max": 0.00011,
  "p95": 0.00012,
  "trials": 100
}
```

### Comparison

#### POST /api/compare

Compare two optical systems.

**Request:**
```json
{
  "system_a": { ... },
  "system_b": { ... },
  "label_a": "Design A",
  "label_b": "Design B"
}
```

### Export

#### POST /api/export

Export to various formats.

**Request:**
```json
{
  "system": { ... },
  "format": "zmx"
}
```

**Supported formats:** `zmx`, `seq`, `svg`, `bom`, `sag`, `iso10110`

### AI Copilot

#### POST /api/ai/explain

Get explanation of system behavior.

**Request:**
```json
{
  "system": { ... },
  "question": "Why does MTF drop?"
}
```

**Response:**
```json
{
  "answer": "Spherical aberration is dominant...",
  "citations": ["Seidel analysis: SA=0.5um"],
  "confidence": 1.0,
  "suggested_actions": ["Run optimization"],
  "verified": true
}
```

`confidence` is 1.0 when every number in the answer was computed by the
optics engine, 0.5 for rule-of-thumb guidance and 0.0 when the request
could not be handled.

Numbers that are infinite (for example the EFL of an afocal system) are
returned as `null` throughout the API.

#### POST /api/ai/suggest

Get design family suggestions.

#### POST /api/ai/nl-to-prescription

Convert natural language to prescription.

#### POST /api/ai/verify

Verify claims about the system.

### Projects

#### GET /api/systems

List saved projects.

#### POST /api/systems

Save a project.

#### GET /api/systems/{id}

Load a project.

#### DELETE /api/systems/{id}

Delete a project.

## Error Responses

All endpoints return standard HTTP status codes:

- `200`: Success
- `400`: Bad request (invalid parameters)
- `404`: Not found
- `500`: Internal server error

**Error format:**
```json
{
  "detail": "Error description"
}
```

## Rate Limiting

No rate limiting is implemented. For production use, add a reverse proxy with rate limiting.

## Authentication

No authentication is implemented. For production use, add authentication middleware.
