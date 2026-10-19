# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed (accuracy and data integrity)
- Glass data rebuilt from the vendors' own catalog files: 820 SCHOTT, OHARA,
  HOYA and CDGM glasses (the 0.2.0 entry's "321 materials" and per-kg costs
  were not catalog data). Literature materials now cite their sources;
  unknown properties are left empty instead of estimated.
- New sequential engine: exact 3D real-ray tracing with ray aiming; ideal
  thin lenses are now aberration-free at every conjugate.
- Seidel sums per Welford; PSF/MTF from the real wavefront by FFT; the
  diffraction limit uses Strehl >= 0.8 (Maréchal).
- Relative illumination from the projected solid angle of the real bundle
  (matches the exact off-axis disk irradiance).
- Tolerancing adds errors to nominal values; compensators re-optimized.
- Coatings (transfer matrix), polarization, Gaussian beams, fibers, GRIN,
  non-sequential tracing, ghosts and PST corrected; invented presets and
  reference designs removed.
- CAD export writes real lens meshes (STL/OBJ/PLY); STEP/IGES writers that
  produced invalid files now refuse.
- API returns null for infinite values (afocal systems) instead of failing.
- Tests rewritten against independent references.

### Fixed (tests)
- Tolerancing: a compensator that does not improve the metric no longer
  moves to an arbitrary point.
- Backend coverage raised to the 80% target with tests against independent
  references (Zernike tables, exact Strehl, tilted-plate shift, lensmaker,
  mesh volume, compiled kernel versus NumPy).

### Added (Code V parity)
- Fast tolerancing of a prescription (Code V TOR style): DLF, DLR, DLT,
  DLN, DLV, surface and element decenters and tilts, back-focus and
  thickness compensators, a sensitivity table, the predicted RMS wavefront
  distribution and inverse sensitivity, plus an exact Monte Carlo reference
  (`/api/lens/tolerance`, `/tolerance/monte-carlo`, `/tolerance/defaults`).
- Perturbed glasses (`PERTURB:<glass>:<dn>:<dVd>`) with exact nd and Vd
  shifts.
- Constrained optimizer (Code V style): exact EFL, BFL, F-number,
  magnification, track and centre/edge-thickness constraints by damped least
  squares on the KKT system; radii varied as curvatures.
- Model glasses (`MODEL:<nd>:<vd>`, normal-line partial dispersion) as
  variables inside the catalog glass map, and snapping to the nearest real
  glass (`/api/lens/snap-glasses`, `/api/lens/constraints`).

### Removed
- STEP/IGES "full" importers: they turned B-rep vertices into arbitrary
  triangles (STEP) or loose points (IGES) rather than the model's geometry.
  STEP and IGES import now refuse with a clear message (convert to STL/OBJ).
- Unused 2D sag/intersect methods on the advanced surface models; the
  engine's exact surfaces in `raytrace.py` were always the ones traced.
- BOM cost estimates (no published prices), fabricated GRIN materials,
  numeric "reference" prescriptions in the AI verifier.

## [0.2.0] - 2024-09-02

### Added
- **321 optical materials** from Schott, Ohara, Hoya, CDGM
- **Enhanced material properties**: thermal, mechanical, transmission, cost
- **Desktop app**: Electron wrapper for one-click launch
- **Launcher scripts**: Linux/Mac (launch.sh), Windows (launch.bat, launch.ps1)
- **Troubleshoot script**: Automated diagnostics
- **Ghost reflection analysis**: Identify problematic surface pairs
- **Stray light path analysis**: Non-image-forming ray paths
- **Point Source Transmittance (PST)**: Stray light rejection
- **Narcissus analysis**: IR system cold return
- **High-yield optimization**: Nominal + tolerance sensitivity
- **Pareto optimization**: Multi-objective trade-offs
- **Sensitivity analysis**: Tornado analysis and ranking
- **Compensator support**: Focus shift, air space adjustment
- **ZMX import/export**: Zemax file compatibility
- **Code V sequence import/export**
- **SVG lens drawings**
- **ISO 10110 optical drawings**
- **Bill of Materials (BOM)** with cost estimates
- **Sag tables**
- **Engineering reports**: HTML/Markdown
- **AI Copilot**: Explain, suggest, verify, NL-to-prescription
- **Dark mode**
- **Keyboard shortcuts**
- **Undo/Redo** (50 states)
- **Interactive 2D layout**: Drag-to-edit
- **320+ tests**: Comprehensive test coverage
- **CI/CD pipeline**: GitHub Actions

### Changed
- Expanded from ~40 to 321 materials
- Optimized performance
- Improved error handling
- Enhanced documentation

### Fixed
- Infinity focal length now allowed (flat surfaces)
- Improved numerical stability
- Better input validation

## [0.1.0] - 2024-08-01

### Added
- Initial release
- Basic ray tracing
- Optical analysis
- Optimization
- Tolerance analysis
- SQLite persistence
- REST API
- React frontend

---

## [Unreleased]

### Planned
- Aspheric surfaces
- Diffractive optical elements
- GRIN materials
- Non-sequential ray tracing
- Physical optics
- Polarization analysis
- CAD export
- PDF reports
