# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added (global search)
- Global search on the lens prescription (`/api/lens/global-optimize`):
  constrained local optimizations from Sobol-spread starts. It returns the
  distinct feasible designs, best merit first, and can run starts in
  parallel processes. In the lens editor, "Global search" lists the designs
  found and loads the chosen one.

### Added (merit functions)
- Merit function choices (`lens.merit`): transverse ray error from the
  chief ray or the spot centroid, or wavefront variance; pupil rings; the
  image term's weight; and weighted operands (Code V's user constraints in
  the error function) for any property (`/api/lens/merit`).
- New properties for operands and exact constraints, at a chosen field:
  distortion, chief-ray angle, real image height, RMS spot, RMS wavefront,
  lateral colour. Also axial colour and Seidel S-I to S-V.
- Lens editor: a Merit function panel (image term, sampling, operands with
  current values, Evaluate). Constraints take the new properties and a
  field. The optimize report shows a wavefront merit in waves.

### Changed
- The default merit's field and wavelength weights are normalised to sum
  1, so the reported RMS spot is the weighted RMS over the field table
  (before, the squares were summed over fields). The optimum is unchanged.

### Added (configurations)
- Multi-configuration lenses (zoom positions, focus settings, alternate
  fields): a zoom table of surface or system parameters with one value per
  configuration, analyses of any configuration with apertures covering all
  of them, optimization of every configuration together (zoomed variables,
  per-configuration constraints) and tolerancing of one configuration
  (`/api/lens/configurations`; `configuration` on resolve, optimize and
  tolerance requests). In the lens editor, a Configurations panel edits the
  table, picks the configuration the analyses show and compares their
  first-order data; constraints take a configuration.

### Fixed
- The optimizer took the whole constraint-correcting step even when a
  strongly curved constraint (a focal length against a spacing) made it
  overshoot, and stalled; it now also tries half and quarter steps. A merit
  that starts at zero (ideal lenses) no longer turns round-off into steps.

### Added (follow-up)
- Mirrors with aspheric, odd aspheric, Q, toroidal, Zernike and XY
  polynomial shapes (off-axis and freeform mirrors), read back from the
  component model; validated by a paraboloid's perfect focus and a toroidal
  mirror's two focal lines.

### Changed
- Hopkins MTF integration splits its quadrature at the edges of blocked
  parts of the pupil and integrates all frequencies together: an obscured
  pupil's MTF now matches O'Neill's to 5e-4 at the default sampling (was
  about 4e-3) and runs about 4x faster, and unobscured lenses are no
  slower.

### Added (surface types)
- Lens editor surface types: Q asphere (Forbes Qbfs / Qcon), toroid and
  cylinder, Zernike sag on a base conic, XY polynomial freeform and
  diffractive (radial phase on a curved base), each with its terms as
  variables. A "Surface details" panel under the table edits the terms
  (also the even and odd asphere coefficients, which had no editor), the
  normalisation radius and the clear aperture.
- Central obscurations and rectangular / elliptical clear apertures on any
  surface, in the NumPy and compiled tracers; a chief ray behind an
  obscuration still serves as the wavefront reference.
- Zemax toroids (`TOROIDAL`) read and written.

### Fixed
- The Forbes Qbfs basis was built with a quadrature that dropped its end
  points, leaving the polynomials about 3e-4 off orthonormal; it now
  matches Forbes' recurrence to round-off.
- Edge-thickness constraints included only even aspheric terms; they now
  use each surface's full sag (odd asphere terms were left out before).

### Added (validation)
- Reference lenses with their published results: a Geiser triplet and a
  US 7,535,658 phone lens (checked against ray-optics' first-order data,
  paraxial rays, Seidel sums and exact real rays), a Smith double Gauss, a
  Kidger Petzval and the Hubble Space Telescope (`optics/reference_lenses.py`,
  `tests/test_reference_lenses.py`). In the lens editor, "Samples" opens
  any of them with its source (`/api/lens/samples`).
- Odd aspheres (r^3 .. r^19 on top of the even terms) in the lens editor,
  the optimizer and tolerancing; read and written as Zemax `ODDASPH`.

## [0.4.0] - 2026-11-07

### Added (file interchange)
- Code V (.seq) and Zemax (.zmx) lens files read into and written from the
  surface prescription, keeping wavelength weights, the full field table
  with weights and vignetting, model glasses, coordinate breaks and (Code V)
  the image solve and variables; anything not carried over is reported
  (`/api/lens/import`, `/api/lens/export`). In the lens editor: "Open .seq
  / .zmx" (the lens is resolved straight away) and "Save .seq" / "Save .zmx",
  with the warnings listed under the table.

### Added
- Lens data editor: constraint rows (EFL, BFL, working F-number,
  magnification, track, centre and edge thickness) with a current-value
  check; nd / Vd variables on model glasses and snapping to catalog glass;
  an optimization report (constraints, RMS before and after, convergence
  chart); a tolerancing panel (default or edited tolerances, refocus limit,
  sensitivity table, predicted distribution, inverse limits from a budget,
  and an exact Monte Carlo check).

- MTF tab: wavelength-weighted MTF curves, through-focus MTF and MTF
  across the field, by FFT or Hopkins direct integration
  (`/api/analyze/mtf`, `/through-focus-mtf`, `/mtf-vs-field`).
- PSF tab: wavelength-weighted diffraction PSF per field (linear or log),
  encircled and ensquared energy against the diffraction limit, 80 %
  energy radius and Strehl per wavelength; blur wider than the diffraction
  window is flagged (`/api/analyze/psf`).
- Distortion & Colour tab: distortion, F-θ distortion, lateral colour per
  wavelength and relative illumination against field
  (`/api/analyze/field-plots`).
- The app shows the name Kestrova and its real version.

### Fixed
- Tolerancing reports the nominal lens's own refocus separately from what
  tolerances add (`nominal`, `max_change`); `max_abs` mixed the two.

## [0.3.0] - 2026-10-28

### Added (desktop)
- Windows and macOS (Apple Silicon and Intel) installers with the optics
  engine bundled (Python, NumPy, SciPy and Numba frozen with PyInstaller),
  built and smoke-tested in CI and published for version tags. Unsigned
  for now. Projects are kept in the per-user data folder.
- Backend tests run on Ubuntu, Windows and macOS.

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
