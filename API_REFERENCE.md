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

#### POST /api/analyze/mtf, /through-focus-mtf, /mtf-vs-field

Wavelength-weighted diffraction MTF over the field table, by `method`
"fft" (pupil autocorrelation) or "hopkins" (direct integration of the pupil
overlap with the real wavefront; matches the diffraction-limited closed
form to ~1e-4). `/mtf` gives tangential, sagittal and diffraction-limit
curves for a `field`; `/through-focus-mtf` the MTF at `frequency_mm` against
image-plane shift (default scan finds the peak, flags `peak_at_scan_edge`);
`/mtf-vs-field` the MTF at `frequencies_mm` from axis to edge.

#### POST /api/analyze/psf

`{ "system", "field": 0, "grid": 64, "image_size": 65, "extent_airy": null }`
→ the wavelength-weighted diffraction PSF of a field-table entry (peak 1)
about the reference chief ray, with `encircled` and `ensquared` energy
against `radius_mm`, the `diffraction_limited_encircled` energy
(1 − J0² − J1²), `radius_80_mm`, `airy_radius_mm` and the Strehl ratio per
wavelength. The view fits the energy unless `extent_airy` is given.
`exceeds_window` is true when the blur is wider than the diffraction
calculation's window: the image is aberration-limited and the spot diagram
describes it.

#### POST /api/analyze/field-plots

`{ "system", "points": 11 }` → against field: `distortion` (relative to the
paraxial image height), `ftheta_distortion` (object at infinity:
(y − fθ)/fθ), `lateral_colour_mm` (chief-ray offset of each wavelength from
the reference, real rays) and `relative_illumination` with `cos4`.

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

`{ "lens": {...}, "configuration": 0 }` → `{ "lens", "system",
"first_order", "configuration" }`: pickups and solves applied, automatic
semi-diameters filled, the component-based `system` for every other
analysis endpoint, and EFL, BFL, F-numbers, image position and pupils. For
a multi-configuration lens, `system` and `first_order` are those of
`configuration` (0-based); `/api/lens/optimize` and the tolerancing
endpoints take the same field.

#### POST /api/lens/global-optimize

`{ "lens", "starts": 16, "max_evaluations": 200, "bounds": {}, "ranges":
{}, "seed": 0, "keep": 5, "workers": 1 }` → `{ "solutions": [{ "lens",
"merit", "variables", "start", "first_order" }], "starts", "feasible",
"distinct", "evaluations" }`. Local optimizations run from the lens as
given (`start` 0) and from `starts` Sobol points over the variables'
ranges. The response holds the distinct designs that meet every
constraint, best merit first. `bounds` limit every local optimization (as
for `/api/lens/optimize`); `ranges` set where starts are drawn (radii as
curvatures in 1/m).

#### POST /api/lens/substitute-glasses

`{ "lens", "surfaces": null, "candidates": 8, "vendors": null,
"include_inquiry": false, "max_evaluations": 150, "passes": 2 }` → `{
"lens", "system", "first_order", "merit_before", "merit_after",
"substitutions": [{ "surface", "from", "to", "merit" }], "evaluations" }`:
the glass expert.

A desensitizing term is set on the lens (`merit.desensitize`: `weight`,
`tolerances` as for `/api/lens/tolerance`, `rings`; wavefront merit
only). `/api/lens/merit` reports it per tolerance.

#### POST /api/analyze/polarization

`{ "system", "field": 0, "wavelength": null, "grid": 21 }` → pupil maps of
`transmittance`, `diattenuation` and `retardance` (rad; null outside the
pupil) and `summary` (pupil-averaged transmittance per wavelength and
weighted). Lens surfaces take a `coating`: `{ "name", "layers": [{
"material" | "n", "k", "thickness" (m) }] }`, layers in the order light
meets them.

#### POST /api/lens/environment

`{ "lens", "temperatures": [..], "pressure": 101325, "mount_cte": null,
"configuration": 0, "system_at": null }` → `{ "rows": [{ "temperature",
"pressure", "efl", "bfl", "focus_shift", "rms_wavefront",
"depth_of_focus" }], "system"? }`. `focus_shift` is the paraxial focus
minus the image plane. Systems carry `environment: { "temperature",
"pressure" }`.

#### POST /api/analyze/ghost-trace

`{ "system", "field": 0, "wavelength": null, "rings": 6, "top": null }`
→ `{ "ghosts": [{ "surfaces", "fraction", "power", "rms_radius",
"centroid", "focus_shift", "relative_irradiance" }], "image_rms_radius" }`,
brightest first.

#### POST /api/analyze/gaussian-beam

`{ "system", "waist_radius", "waist_distance": 0, "wavelength": null,
"m2": 1 }` → output waist radius and position (from the image plane),
Rayleigh range, divergence, beam radius at the image plane and along the
axis. `/api/analyze/imaging` also takes `polychromatic`.

#### POST /api/lens/report

`{ "lens", "configuration": 0, "title": null, "author": "", "mtf": true,
"tolerances": true, "trials": 2000, "drawings": true }` → `{ "html" }`:
the design report as one self-contained HTML page (inline CSS and SVG),
laid out for printing to PDF.

#### POST /api/lens/drawings

`{ "lens", "configuration": 0, "tolerances": null, "edge_margin": 0.001,
"notes": {} }` → `{ "drawings": [{ "name", "surfaces", "glass",
"center_thickness", "edge_thickness", "clear_diameter", "outer_diameter",
"left", "material", "right", "svg", "html" }] }`: ISO 10110 data per
glass element. `left`/`material`/`right` are (label, value) rows; `notes`
fills the codes the design does not set (`"0/"`, `"1/"`, `"2/"`, `"5/"`,
`"irregularity"`).

#### POST /api/script/run

`{ "code", "lens": null, "timeout": 120 }` → `{ "output", "error",
"lens", "duration", "timed_out" }`: runs Python with the scripting API
(`ks`, `np`, `lens`) in its own process (see SCRIPTING.md). Refused (403)
unless the client, the Host header and any Origin are this computer's
loopback, or when `KESTROVA_DISABLE_SCRIPTING` is set.

#### GET /api/script/reference

→ `{ "reference": [{ "name", "signature", "doc" }] }`: the scripting API.

#### POST /api/lens/merit

`{ "lens" }` → `{ "configurations": [{ "configuration", "image_kind",
"image_rms", "image_contribution", "operands": [{..., "value",
"contribution", "index"}], "merit" }], "merit" }`: the lens's merit
function (`lens.merit`) term by term. `image_rms` is the RMS spot (m) or
RMS wavefront (waves). `/api/lens/optimize` returns `merit_report_before`
and `merit_report`, and its `rms_spot_before` / `rms_spot_after` are the
image term of the requested configuration.

#### POST /api/lens/configurations

`{ "lens" }` → `{ "configurations": [{ "configuration", "name",
"first_order" }] }`: first-order data of every configuration.

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
- `predicted_fields`, and for each compensator its `nominal` value (the
  nominal lens's own refocus: its best focus need not be the image plane),
  the `mean`, `std` and `max_abs` over the builds, and `max_change`, the
  largest change from `nominal`;
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

#### POST /api/lens/import

Multipart upload of a Code V sequence file (`.seq`) or a Zemax text lens
file (`.zmx`) → `{"lens", "warnings"}`. The lens keeps the surfaces
(standard, even asphere, Zemax odd asphere, toroid and paraxial,
coordinate breaks), catalog and model glasses (Code V `nd:vd`, Zemax `___BLANK`), stop, clear apertures,
entrance pupil, wavelengths with weights, the field table with weights and
vignetting, and Code V's image solve (`PIM`) and variables (`CCY`/`THC`).
`warnings` lists commands or keywords the file contains that were not
interpreted.

#### POST /api/lens/export

`{ "lens", "format": "seq" | "zmx" }` → `{"filename", "content",
"warnings"}`. Solves and pickups the format cannot express here are written
as their current values and listed in `warnings`. Code V has no paraxial
(ideal lens) surface, so such a lens can only be written as `.zmx`. Odd
asphere terms are written to Zemax (`ODDASPH`, up to r^8) and dropped
from Code V files, with a warning either way. Toroids are written to Zemax
(`TOROIDAL`). Q, Zernike, XY polynomial and diffractive terms (and Code V
toroids), obscurations and non-circular apertures are not written yet: the
surface is written as its base conic and each omission is listed in
`warnings`.

#### GET /api/lens/samples

The reference lenses (published designs the engine is validated against):
a list of `{"id", "name", "description", "citation", "url", "notes"}`.

#### GET /api/lens/samples/{id}

One reference lens: the same fields plus `lens` (the prescription). 404
for an unknown id.

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
