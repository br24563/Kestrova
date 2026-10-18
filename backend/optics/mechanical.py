import math
from dataclasses import dataclass, field

from .nsc.cad.mesh import Mesh, Triangle, Vertex
from .models import OpticalSystem, ThinLens, ThickLens


@dataclass
class LensMount:
    inner_diameter: float
    outer_diameter: float
    thickness: float
    edge_width: float = 0.5e-3
    material: str = "Aluminum 6061"


@dataclass
class BarrelSection:
    inner_diameter: float
    outer_diameter: float
    length: float
    position: float = 0.0
    thread_pitch: float = 0.0


@dataclass
class ISO10110Symbol:
    symbol_type: str
    label: str = ""
    tolerance: float = 0.0


@dataclass
class ISO10110Drawing:
    element_name: str = "Lens"
    symbols: list = field(default_factory=list)
    dimensions: dict = field(default_factory=dict)


def generate_lens_mount(
    lens_diameter, lens_thickness, clearance=0.05e-3, edge_width=0.5e-3
):
    inner_diameter = lens_diameter + 2 * clearance
    outer_diameter = inner_diameter + 2 * edge_width
    return LensMount(
        inner_diameter=inner_diameter,
        outer_diameter=outer_diameter,
        thickness=lens_thickness + 0.5e-3,
        edge_width=edge_width,
    )


def generate_barrel_from_system(
    system,
    wall_thickness=2.0e-3,
    clearance=0.1e-3,
    thread_pitch=0.5e-3,
    seat_allowance=1.0e-3,
):
    """Barrel sections around each lens; ``seat_allowance`` is added to the
    element thickness for the seat (a mechanical design choice)."""
    sections = []
    components = sorted(system.components, key=lambda c: c.position)
    for comp in components:
        if isinstance(comp, (ThinLens, ThickLens)):
            lens_diameter = getattr(comp, "aperture_diameter", 25e-3)
            from .glass_catalog import _component_geometry

            lens_thickness = _component_geometry(comp)[1]
            inner_d = lens_diameter + 2 * clearance
            outer_d = inner_d + 2 * wall_thickness
            length = lens_thickness + seat_allowance
            sections.append(
                BarrelSection(
                    inner_diameter=inner_d,
                    outer_diameter=outer_d,
                    length=length,
                    position=comp.position,
                    thread_pitch=thread_pitch,
                )
            )
    return sections


def generate_barrel_mesh(section, n_segments=64):
    vertices = []
    triangles = []
    r_inner = section.inner_diameter / 2
    r_outer = section.outer_diameter / 2
    z_start = section.position
    z_end = section.position + section.length
    for i in range(n_segments):
        angle = 2 * math.pi * i / n_segments
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        vertices.append(Vertex(r_inner * cos_a, r_inner * sin_a, z_start))
        vertices.append(Vertex(r_inner * cos_a, r_inner * sin_a, z_end))
        vertices.append(Vertex(r_outer * cos_a, r_outer * sin_a, z_start))
        vertices.append(Vertex(r_outer * cos_a, r_outer * sin_a, z_end))
    for i in range(n_segments):
        i0 = i * 4
        i1 = ((i + 1) % n_segments) * 4
        triangles.append(Triangle(vertices[i0], vertices[i1], vertices[i0 + 1]))
        triangles.append(Triangle(vertices[i1], vertices[i1 + 1], vertices[i0 + 1]))
        triangles.append(Triangle(vertices[i0 + 2], vertices[i0 + 3], vertices[i1 + 2]))
        triangles.append(Triangle(vertices[i1 + 2], vertices[i0 + 3], vertices[i1 + 3]))
        triangles.append(Triangle(vertices[i0], vertices[i0 + 2], vertices[i1]))
        triangles.append(Triangle(vertices[i1], vertices[i0 + 2], vertices[i1 + 2]))
        triangles.append(Triangle(vertices[i0 + 1], vertices[i1 + 1], vertices[i0 + 3]))
        triangles.append(Triangle(vertices[i1 + 1], vertices[i1 + 3], vertices[i0 + 3]))
    return Mesh(name="barrel", vertices=vertices, triangles=triangles)


def create_iso10110_drawing(system, element_index=0, tolerance_codes=None):
    """
    ISO 10110 data for one lens element: diameter, centre thickness and
    glass from the design. Tolerance codes (e.g. {"surface_form": "3/0.5",
    "surface_quality": "5/3x0.1"}) are manufacturing choices and are added
    only when supplied. A thin (ideal) lens is given the centre thickness of
    the equiconvex lens of zero edge thickness.
    """
    from .glass_catalog import _component_geometry

    components = sorted(system.components, key=lambda c: c.position)
    lenses = [c for c in components if isinstance(c, (ThinLens, ThickLens))]
    if element_index >= len(lenses):
        return None
    lens = lenses[element_index]
    drawing = ISO10110Drawing(element_name=getattr(lens, "id", "Lens"))
    for kind, label in (tolerance_codes or {}).items():
        drawing.symbols.append(ISO10110Symbol(symbol_type=kind, label=label))
    diameter, thickness = _component_geometry(lens)
    drawing.dimensions["diameter"] = diameter
    drawing.dimensions["thickness"] = thickness
    drawing.dimensions["material"] = lens.material
    return drawing


def iso10110_to_svg(drawing, filename):
    svg = []
    svg.append(
        chr(60)
        + "svg xmlns="
        + chr(34)
        + "http://www.w3.org/2000/svg"
        + chr(34)
        + " width="
        + chr(34)
        + "400"
        + chr(34)
        + " height="
        + chr(34)
        + "300"
        + chr(34)
        + chr(62)
    )
    svg.append(
        chr(60)
        + "rect width="
        + chr(34)
        + "100%"
        + chr(34)
        + " height="
        + chr(34)
        + "100%"
        + chr(34)
        + " fill="
        + chr(34)
        + "white"
        + chr(34)
        + "/"
        + chr(62)
    )
    svg.append(
        chr(60)
        + "text x="
        + chr(34)
        + "10"
        + chr(34)
        + " y="
        + chr(34)
        + "20"
        + chr(34)
        + chr(62)
        + drawing.element_name
        + chr(60)
        + "/text"
        + chr(62)
    )
    y_pos = 50
    for sym in drawing.symbols:
        svg.append(
            chr(60)
            + "text x="
            + chr(34)
            + "10"
            + chr(34)
            + " y="
            + chr(34)
            + str(y_pos)
            + chr(34)
            + chr(62)
            + sym.label
            + chr(60)
            + "/text"
            + chr(62)
        )
        y_pos += 20
    svg.append(chr(60) + "/svg" + chr(62))
    with open(filename, "w") as f:
        f.write(chr(10).join(svg))
    return svg
