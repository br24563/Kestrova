# Scripting

Kestrova has a Python scripting API for automating studies: sweeps,
batch optimisation, custom merit checks and reports. It plays the role
of a macro language. The API is the `kestrova` package in `backend/`.

You can use it in two places:

- **The Script tab** (in the analysis tabs). `lens` is the lens open in
  the Lens Data Editor. When a script changes `lens`, **Send lens to the
  editor** puts the result back in the editor.
- **Any Python session started in `backend/`**, using the same calls:

```python
import kestrova as ks

lens = ks.open_lens("my_design.seq")      # or ks.sample("geiser-triplet")
print(lens.efl * 1e3, "mm, F/", lens.f_number)
```

## Conventions

- Values are SI: metres and radians. Temperatures are in °C, and RMS
  wavefront is in waves.
- Surfaces are numbered from 0, in the order of the Lens Data Editor.
- Methods that change the lens (`set`, `vary`, `optimize`, ...) return
  the lens, so you can chain them. Analysis methods return numbers or
  plain dicts.
- `lens.copy()` gives an independent copy to experiment on.

## Calls

| Call | What it does |
| --- | --- |
| `ks.sample(id)`, `ks.samples()` | Open a bundled reference lens, or list them (Geiser triplet, double Gauss, Petzval, phone lens, Hubble). |
| `ks.open_lens(path)` | Read a Code V `.seq`, Zemax `.zmx` or Kestrova `.json` file. `lens.warnings` lists anything the file held that Kestrova does not. |
| `lens.save(path)` | Write `.seq`, `.zmx` or `.json`. Returns warnings for anything the format cannot hold. |
| `lens[i]`, `lens.surfaces` | Surface rows. They are editable: `lens[2].material = "N-SF5"`. |
| `lens.get(i, name)`, `lens.set(i, name, value)` | Read or change a parameter: radius, curvature, thickness, conic, A4…, decenter_x, tilt_x, … |
| `lens.set_material(i, glass)` | Set the medium after surface `i` (`None` for air). |
| `lens.vary(i, name, on=True)`, `lens.variables()` | Make a parameter an optimisation variable, or read the current variables. |
| `lens.first_order()` | EFL, BFL, F-number, working F-number, image position and height, magnification, pupils, NA. |
| `lens.efl`, `lens.bfl`, `lens.f_number` | Shortcuts. |
| `lens.value(kind, field=None, surface=None)` | Any merit or constraint property: efl, bfl, working_f_number, magnification, total_track, center/edge_thickness, distortion, chief_ray_angle, image_height, spot_rms, wavefront_rms, lateral/axial_color, seidel_S1–S5. |
| `lens.spot_rms(field)`, `lens.wavefront_rms(field)` | RMS spot radius (m) and RMS wavefront (waves) at a field. With no field: the edge field. |
| `lens.fields()` | Per field: chief ray, distortion, polychromatic spot, vignetting. |
| `lens.mtf(field, frequencies)` | Polychromatic diffraction MTF, tangential and sagittal, in cycles/mm. |
| `lens.seidel()` | Third-order aberrations and Seidel sums. |
| `lens.merit()` | The merit function report. |
| `lens.optimize(max_iterations=100)` | Damped least squares over the variables and constraints. Updates the lens. |
| `lens.global_search(starts=16)` | Multi-start global search. Returns the distinct solutions as Lens objects. |
| `lens.tolerance(tolerances=None, trials=20000)` | Sensitivity and Monte Carlo analysis (uses `lens.default_tolerances()` when none are given). |
| `lens.environment(temperatures, pressure, mount_cte)` | Focus, EFL and wavefront at each temperature. |
| `lens.ghosts(field)`, `lens.polarization(field)`, `lens.beam(waist)` | Ghosts, polarization transmittance, Gaussian beam. |
| `lens.configuration(k)` | Configuration `k` of a zoom lens. |
| `lens.report(path=None, ...)` | The HTML design report (see below). |
| `lens.drawings()` | ISO 10110 element drawings. |
| `lens.system()` | The engine's component system, for direct use of the `optics` modules. |

The Script tab's **API reference** button lists every call with its
signature, generated from the code.

## Examples

Sweep an air gap:

```python
for t in np.linspace(0.95, 1.05, 5) * lens.get(1, "thickness"):
    trial = lens.copy().set(1, "thickness", t)
    print(f"{t * 1e3:.3f} mm  spot {trial.spot_rms(0) * 1e6:.2f} um")
```

Optimize every radius, then write the result:

```python
for i, s in enumerate(lens.surfaces):
    if s.radius:
        lens.vary(i, "radius")
lens.optimize()
lens.save("optimized.seq")
```

Compare the samples:

```python
for s in ks.samples():
    L = ks.sample(s["id"])
    print(f"{s['id']:28s} EFL {L.efl * 1e3:9.3f} mm  F/{L.f_number:.2f}")
```

## The console

- Every run starts fresh in its own process. It has `ks` (the kestrova
  module), `np` (NumPy) and `lens`. Nothing carries over between runs
  except the lens you send to the editor.
- Starting the process takes about 2–3 seconds.
- A run stops after 2 minutes. An endless loop or a crash cannot take
  the engine down.
- Scripts run with your permissions on your computer, like any Python
  program. They can read and write files, which is how `save` and
  `report` work.
- The engine accepts scripts only from its own pages on this computer.
  It checks the loopback client, the Host header and the Origin, so a
  web site open in your browser cannot send it code.
- To turn scripting off, set the environment variable
  `KESTROVA_DISABLE_SCRIPTING=1`.

## Reports and drawings

`lens.report("design.html")`, or the **Report** tab, builds a
self-contained HTML design report. It has these sections:

- system data;
- first-order properties;
- the prescription;
- field performance;
- polychromatic MTF;
- Seidel sums;
- the tolerance budget, from the default tolerance set with back-focus
  compensation;
- ISO 10110 element drawings.

The Report tab previews the report. **Save PDF** writes a PDF: the
desktop app saves it directly, and in a browser it opens the print
dialog. **Save HTML** downloads the HTML.

The **Drawings** tab and `lens.drawings()` give one ISO 10110 drawing
per glass. A cemented doublet gives two. Each drawing has a to-scale
section with the centre and edge thickness, the clear aperture and the
outer diameter, plus the data table:

- radii with CX/CC and ⌀e;
- 3/ surface form, in fringes of power from the tolerance set;
- 4/ centring, in arc minutes from the surface and element tilts;
- 5/ surface imperfections;
- the coating;
- nd and νd with their tolerances;
- 0/, 1/, 2/ material imperfections;
- the centre thickness tolerance.

The design does not set 5/, 0/, 1/, 2/ or the irregularity. They print
as "—" unless you fill them in (the `notes` argument, or the fields in
the Drawings tab). Past its clear aperture, an element is drawn with a
flat land out to the outer diameter. The outer diameter is the clear
diameter plus the edge margin, 1 mm by default.
