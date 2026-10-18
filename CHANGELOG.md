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

### Removed
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
