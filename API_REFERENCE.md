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

Hybrid global+local optimization.

#### POST /api/optimize/high-yield

High-yield optimization with tolerances.

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
