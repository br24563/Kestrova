# User Guide

Kestrova is a free, local-first optical design program. This guide walks
through the app. [QUICKSTART.md](./QUICKSTART.md) covers installing it,
[SCRIPTING.md](./SCRIPTING.md) automating it, and [OPTICS.md](./OPTICS.md)
the conventions and methods behind every number.

## The window

| Area | What it holds |
|------|---------------|
| Header | Presets, display units, Save/Load, Undo/Redo, dark mode |
| Left panel | The AI assistant and saved projects |
| Lens Data Editor | The surface-by-surface prescription (it can be collapsed) |
| Analysis tabs | Every analysis of the current lens (listed below) |
| Right panel | First-order data, the spot diagram, diffraction and Seidel |

### Describing a system

The **Lens Data Editor** holds the lens: one row per surface, as in
Code V or Zemax. A **Preset** from the header loads a first-order
layout, and **From components** turns it into lens data.

**Resolve** applies the lens data: it computes the solves and pickups,
fills automatic apertures and drives the analysis tabs and the right
panel. A lens that has been edited but not resolved is marked as
changed.

### The component editor (hidden)

The original component editor is hidden by default: the component list,
the optical bench, the Advanced Optimization tab and the component
tolerance, comparison and optimizer panels. To show it again, run
`localStorage.setItem("kestrova.componentEditor", "1")` in the developer
console and reload.

## The Lens Data Editor

### Rows

Each row is a surface. Its columns are type, radius, thickness, material
(a catalog glass, empty for air, `MIRROR` to reflect), semi-diameter,
conic and the stop flag. Thickness is the distance to the next surface.

- **Insert before / after** and **Delete** edit the rows.
- Click a cell's **f** marker to make it a variable, or to give it a
  solve or a pickup.
- Selecting a row opens its surface details:
  - aspheric, Q, Zernike, XY polynomial and diffractive terms;
  - toroid radii;
  - decentres and tilts;
  - obscurations and rectangular or elliptical apertures;
  - a thin-film coating (layers by material or index, or a quarter-wave
    AR layer).
- Object distance, object height and entrance pupil diameter sit above
  the table. The field table and wavelengths come with the lens or a
  sample.

### Files

| Button | What it does |
|--------|--------------|
| **Samples** | Published lenses with their sources: the Geiser triplet, a double Gauss (US 2,784,643), Kidger's Petzval, a phone camera lens with aspheres (US 7,535,658) and the Hubble telescope |
| **Open .seq / .zmx** | Reads Code V and Zemax files; anything not carried over is listed |
| **Save .seq / .zmx** | Writes them back, listing anything the format cannot hold |
| **STEP / IGES** | The elements and mirrors as CAD solids (STEP) or surfaces (IGES) in millimetres. Each element has a flat land and a cylindrical edge 0.5 mm outside its clear aperture, and mirrors a substrate D/8 thick. Tilted and non-rotationally-symmetric surfaces are left out and listed |

### Undo and redo

The editor's **Undo** and **Redo** step through its edits, resolves,
optimizations and imports. The header buttons and Ctrl+Z /
Ctrl+Shift+Z act on whatever was edited last: the lens or the component
system. Inside a text field, Ctrl+Z undoes typing as usual.

### Configurations

**Configurations** turns the lens into a zoom or multi-configuration
lens:

- each configuration overrides chosen values: any surface parameter
  (thicknesses, radii, ...) and the object distance, object height,
  field angle and entrance pupil diameter;
- configurations carry weights in the merit function;
- constraints can apply to a single configuration.

### Optimization

1. Mark the variables: radii, thicknesses, conics, aspheric terms, and
   nd/νd on model glasses.
2. Optionally edit the **Merit function**:
   - the image term is transverse ray error or wavefront variance (from
     the chief ray or the spot centroid);
   - add weighted operands, such as distortion or colour.
3. Add **Constraints** that must hold exactly: EFL, BFL, working
   F-number, magnification, track, centre and edge thickness, distortion,
   chief-ray angle, image height and others. **Check** shows their
   current values.
4. **Optimize** runs damped least squares. The report shows the merit
   before and after and the convergence.
5. **Global search** starts the optimizer from many points (Sobol
   sampling, in parallel worker processes) and keeps the distinct
   solutions.
6. **Substitute glasses** tries nearby catalog glasses on each glass,
   re-optimizing each, and keeps the ones that help.
7. **Desensitize** (in the merit function, with the wavefront merit)
   adds the predicted tolerance degradation, so the optimizer prefers
   designs that are easier to build.

### Tolerancing

**Analyse with default tolerances** gives the lens's tolerance budget:

- **Default tolerances:** for each element, power in fringes, thickness,
  index, Abbe number, surface tilt, element decentre and element tilt.
  **Load default tolerances** puts them in the table to edit.
- **Sensitivity:** how much each tolerance raises the RMS wavefront,
  with the back-focus compensator (**Refocus limit**).
- **Predicted distribution:** of the RMS wavefront over many builds
  (**Builds**), checked against exact Monte Carlo.
- **Inverse sensitivity:** tolerance limits that fit a **Budget** in
  waves.

## Analysis tabs

| Tab | Contents |
|-----|----------|
| Lens Layout | The lens with its true surface shapes and real rays per field. In 2D, the meridional section with the stop marked; in 3D, the elements and the marginal ray ring (drag to turn) |
| Ray Fan | Transverse ray errors, tangential and sagittal, per field |
| OPD | Optical path difference fans |
| Field Curvature | Tangential and sagittal focus against field |
| MTF | Polychromatic diffraction MTF (FFT or Hopkins), against frequency, through focus and across the field |
| PSF | Diffraction PSF and encircled energy |
| Distortion & Colour | Distortion, F-theta distortion, lateral colour and relative illumination against field |
| Polarization | Transmittance, diattenuation and retardance over the pupil, and transmittance per wavelength (Fresnel losses and coatings) |
| Environment | Focus drift, EFL and wavefront from -20 to 60 °C (or any range) and at any pressure, with an optional housing CTE |
| Gaussian Beam | A beam's waist, Rayleigh range and size through the lens (with M²) |
| Image Simulation | A test target imaged through the lens: wavelength-weighted PSF, illumination, distortion and sensor noise |
| Chromatic | Longitudinal and lateral colour |
| Ghosts | Every double reflection traced exactly with coating or Fresnel reflectances, brightest first; and the component-system ghost analysis |
| Advanced Optimization | Global and hybrid optimization of the component system |
| Report | The design report (prescription, first order, fields, MTF, Seidel, tolerance budget, drawings) as PDF or HTML, and the component-system engineering report |
| Drawings | ISO 10110 drawings of every glass element, with codes you can fill in (surface imperfections, bubbles, ...) |
| Script | A Python console with the scripting API on the editor's lens (Ctrl+Enter runs; see [SCRIPTING.md](./SCRIPTING.md)) |

Analyses that need the lens data (Lens Layout, Environment, Report,
Drawings, Script) ask for a lens when there is none.

## Presets

| Preset | Description |
|--------|-------------|
| Single Thin Lens | One ideal lens |
| Keplerian Telescope | Two positive lenses, afocal |
| Galilean Telescope | Positive objective, negative eyepiece |
| Compound Microscope (thin lenses) | Objective and eyepiece |
| Beam Expander (Keplerian, 3x) | Expands a collimated beam |
| 4f Relay | Two identical lenses 2f apart |
| Collimator | Collimates a point source |
| Thin-Lens Achromat (N-BK7 / N-SF5) | Cemented achromat from first-order design |
| Thick Biconvex Lens | A real singlet |
| Parabolic Mirror Telescope (prime focus) | A paraboloid without spherical aberration |

Thin lenses are ideal (aberration-free). Use thick lenses, surfaces,
mirrors or the samples to see real aberrations.

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+S / Ctrl+L | Save / load the project in the browser |
| Ctrl+Z | Undo (the lens or the system, whichever was edited last) |
| Ctrl+Shift+Z or Ctrl+Y | Redo |
| Ctrl+D | Dark mode |
| Ctrl+R | Refresh the simulation |
| Ctrl+Enter | Run the script (Script tab) |
| Escape | Clear the error message |

## Conventions

- Light travels left to right along z, and heights are positive above
  the axis.
- A radius is positive when its centre of curvature lies to the right.
- Thicknesses are signed. They turn negative after a mirror, as in
  Code V and Zemax.
- The engine works in SI units (metres, radians). The units menu only
  changes the display. Scripts and the API use metres.

[OPTICS.md](./OPTICS.md) has the full conventions.

## AI assistant

The assistant in the left panel:

- explains results ("Why does MTF drop at the field edge?");
- suggests design families ("Suggest a design for 5x at f/2.8");
- verifies claims ("Verify that the EFL is 100 mm");
- edits the component system ("move lens_1 to 150 mm").

Every number comes from the engine, and each answer says whether it was
computed or is a rule of thumb. It works offline with a rule-based
parser. A local LLM is optional (see
[DEVELOPMENT.md](./DEVELOPMENT.md#environment-variables)).

## Troubleshooting

| Problem | What to do |
|---------|------------|
| "Failed to fetch default system" or nothing loads | The backend must be running on port 8000 (the desktop app starts its own) |
| An analysis says the image space is afocal | Image-plane analyses need a focusing lens. Telescopes in afocal mode have no image |
| No rays reach the image | Check the semi-diameters (fixed apertures can block the beam) and the field size |
| The first analysis after starting is slow | The compiled ray trace compiles once and is then cached |
| Optimization does not improve the merit | Check the variables are free to move (constraints may pin them), or try Global search |
| A file opens with warnings | The warnings list what was not carried over from the Code V or Zemax file |

Bug reports and feature requests go to the repository's Issues page.

## References

- W. T. Welford, *Aberrations of Optical Systems*
- W. J. Smith, *Modern Optical Engineering*
- M. Born and E. Wolf, *Principles of Optics*
- ISO 10110, *Optics and photonics: Preparation of drawings for optical
  elements and systems*
