"""
Tests for lens meshes and CAD export (optics.nsc.cad.lens_mesh, export).

Expected values come from independent references:
- the volume of a spherical lens from the cap integral
  V = integral_0^a 2 pi r (t + s2(r) - s1(r)) dr, with
  integral_0^a 2 pi r s(r) dr = pi a^2 R - sgn(R) (2 pi / 3)(|R|^3 - (R^2 - a^2)^(3/2));
- the mesh's enclosed volume from the divergence theorem
  (sum of v0 . (v1 x v2) / 6 over outward triangles);
- a closed, consistently oriented surface uses every directed edge once
  and its reverse once;
- files are read back by the project's importers and, for PLY, by a parser
  written here from the PLY specification.
"""

import math
import struct
from collections import Counter

import numpy as np
import pytest

from optics.models import (
    AnalysisSettings,
    ImagePlane,
    Mirror,
    Object,
    OpticalSystem,
    ThickLens,
    ThinLens,
)
from optics.nsc.cad import (
    export_mesh,
    export_obj,
    export_ply,
    export_stl,
    import_cad_file,
    import_obj,
    import_stl,
)
from optics.nsc.cad.lens_mesh import merge_meshes, system_meshes

R1, R2, T, D = 0.05, -0.08, 0.006, 0.025


def system(*components):
    return OpticalSystem(
        components=list(components),
        wavelengths=[587.6e-9],
        object=Object(position=0.0, height=0.001),
        image_plane=ImagePlane(position=0.5),
        analysis_settings=AnalysisSettings(wavelength=587.6e-9),
    )


def lens(**kw):
    args = dict(id="L1", position=0.1, radius1=R1, radius2=R2, thickness=T,
                aperture_diameter=D, material="N-BK7")
    args.update(kw)
    return ThickLens(**args)


def cap_integral(R, a):
    """integral_0^a 2 pi r s(r) dr for a sphere of signed radius R."""
    return math.pi * a * a * R - math.copysign(1.0, R) * (2 * math.pi / 3) * (
        abs(R) ** 3 - (R * R - a * a) ** 1.5
    )


def analytic_volume(r1, r2, t, a):
    return math.pi * a * a * t + cap_integral(r2, a) - cap_integral(r1, a)


def mesh_volume(mesh):
    v = 0.0
    for tri in mesh.triangles:
        a = np.array([tri.v0.x, tri.v0.y, tri.v0.z])
        b = np.array([tri.v1.x, tri.v1.y, tri.v1.z])
        c = np.array([tri.v2.x, tri.v2.y, tri.v2.z])
        v += a @ np.cross(b, c) / 6.0
    return v


def directed_edges(mesh):
    edges = Counter()
    for tri in mesh.triangles:
        vs = [(v.x, v.y, v.z) for v in (tri.v0, tri.v1, tri.v2)]
        for i in range(3):
            edges[(vs[i], vs[(i + 1) % 3])] += 1
    return edges


def triangles_of(mesh):
    return np.array([[[v.x, v.y, v.z] for v in (t.v0, t.v1, t.v2)] for t in mesh.triangles])


class TestLensMesh:

    def test_closed_and_consistently_oriented(self):
        (m,), skipped = system_meshes(system(lens()), rings=8, segments=32)
        edges = directed_edges(m)
        assert skipped == []
        assert all(n == 1 for n in edges.values())
        assert all(edges[(b, a)] == 1 for a, b in edges)

    @pytest.mark.parametrize("r1,r2", [(R1, R2), (0.04, 0.2), (-0.2, -0.05)])
    def test_volume_matches_the_cap_integral(self, r1, r2):
        exact = analytic_volume(r1, r2, T, D / 2) * 1e9  # mm^3
        coarse = mesh_volume(system_meshes(system(lens(radius1=r1, radius2=r2)),
                                           rings=16, segments=64)[0][0])
        fine = mesh_volume(system_meshes(system(lens(radius1=r1, radius2=r2)),
                                         rings=48, segments=256)[0][0])
        # inscribed polygons: relative error ~ (2 pi / n)^2 / 6, so 4x finer
        # in angle is ~16x closer
        assert fine == pytest.approx(exact, rel=3e-4)
        assert abs(fine - exact) < abs(coarse - exact) / 8

    def test_vertices_lie_on_the_surfaces(self):
        (m,), _ = system_meshes(system(lens()), rings=6, segments=12)
        z0, z1 = 100.0, 106.0  # mm
        for tri in m.triangles:
            for v in (tri.v0, tri.v1, tri.v2):
                r = math.hypot(v.x, v.y)
                s1 = 50.0 - math.sqrt(50.0**2 - r * r)
                s2 = -(80.0 - math.sqrt(80.0**2 - r * r))
                on = min(abs(v.z - (z0 + s1)), abs(v.z - (z1 + s2)))
                assert on < 1e-9 or r == pytest.approx(12.5, abs=1e-9)

    def test_parabolic_mirror_is_an_open_surface_on_its_sag(self):
        mirror = Mirror(id="M", position=0.3, width=0.05, radius=-0.4, conic=-1.0,
                        aperture_diameter=0.05)
        (m,), _ = system_meshes(system(mirror), rings=5, segments=20)
        edges = directed_edges(m)
        boundary = [e for e in edges if (e[1], e[0]) not in edges]
        assert len(boundary) == 20
        for tri in m.triangles:
            for v in (tri.v0, tri.v1, tri.v2):
                r2 = v.x**2 + v.y**2
                assert v.z == pytest.approx(300.0 + r2 / (2 * -400.0), abs=1e-9)

    def test_thin_lens_is_skipped_and_merge_keeps_every_triangle(self):
        meshes, skipped = system_meshes(
            system(lens(), lens(id="L2", position=0.2), ThinLens(id="T", position=0.3,
                                                                focal_length=0.1,
                                                                aperture_diameter=0.02)),
            rings=4, segments=8,
        )
        assert [s[0] for s in skipped] == ["T"]
        merged = merge_meshes(meshes)
        assert merged.num_triangles == sum(m.num_triangles for m in meshes)

    def test_negative_edge_thickness_is_refused(self):
        with pytest.raises(ValueError, match="edge thickness"):
            system_meshes(system(lens(radius1=0.015, radius2=-0.015, thickness=0.002)))

    def test_aperture_beyond_the_sphere_is_refused(self):
        with pytest.raises(ValueError, match="extent"):
            system_meshes(system(lens(radius1=0.01)))


@pytest.fixture
def mesh():
    (m,), _ = system_meshes(system(lens()), rings=4, segments=10)
    return m


class TestExport:

    @pytest.mark.parametrize("binary", [True, False])
    def test_stl_round_trip(self, mesh, tmp_path, binary):
        path = tmp_path / "lens.stl"
        export_stl(mesh, path, binary=binary)
        back = import_stl(path)
        assert back.num_triangles == mesh.num_triangles
        np.testing.assert_allclose(triangles_of(back), triangles_of(mesh), rtol=1e-6, atol=1e-5)
        if binary:
            assert path.stat().st_size == 84 + 50 * mesh.num_triangles

    def test_obj_round_trip_shares_vertices(self, mesh, tmp_path):
        path = tmp_path / "lens.obj"
        export_obj(mesh, path)
        lines = path.read_text().splitlines()
        n_v = sum(1 for ln in lines if ln.startswith("v "))
        # closed genus-0 triangle mesh: V - E + F = 2 with E = 3F/2
        assert n_v == 2 + mesh.num_triangles // 2
        back = import_obj(path)
        np.testing.assert_allclose(triangles_of(back), triangles_of(mesh), atol=1e-12)

    @pytest.mark.parametrize("binary", [False, True])
    def test_ply_read_back_per_specification(self, mesh, tmp_path, binary):
        path = tmp_path / "lens.ply"
        export_ply(mesh, path, binary=binary)
        data = path.read_bytes()
        head, body = data.split(b"end_header\n", 1)
        header = head.decode("ascii").splitlines()
        n_v = int(next(h for h in header if h.startswith("element vertex")).split()[-1])
        n_f = int(next(h for h in header if h.startswith("element face")).split()[-1])
        assert n_f == mesh.num_triangles
        if binary:
            verts = np.array(struct.unpack(f"<{3 * n_v}f", body[: 12 * n_v])).reshape(-1, 3)
            faces = [struct.unpack("<B3i", body[12 * n_v + 13 * i: 12 * n_v + 13 * (i + 1)])
                     for i in range(n_f)]
            assert len(body) == 12 * n_v + 13 * n_f
            rtol = 1e-6
        else:
            rows = body.decode("ascii").splitlines()
            verts = np.array([[float(x) for x in r.split()] for r in rows[:n_v]])
            faces = [tuple(int(x) for x in r.split()) for r in rows[n_v:]]
            rtol = 1e-12
        tris = np.array([[verts[i] for i in f[1:]] for f in faces])
        assert all(f[0] == 3 for f in faces)
        np.testing.assert_allclose(tris, triangles_of(mesh), rtol=rtol, atol=1e-5)

    @pytest.mark.parametrize("suffix", ["stl", "obj", "ply"])
    def test_export_mesh_picks_the_format_from_the_suffix(self, mesh, tmp_path, suffix):
        path = tmp_path / f"lens.{suffix}"
        export_mesh(mesh, path)
        assert path.stat().st_size > 0

    @pytest.mark.parametrize("suffix", ["step", "stp", "iges", "igs"])
    def test_brep_formats_are_refused(self, mesh, tmp_path, suffix):
        with pytest.raises(NotImplementedError):
            export_mesh(mesh, tmp_path / f"lens.{suffix}")

    def test_unknown_format_is_refused(self, mesh, tmp_path):
        with pytest.raises(ValueError):
            export_mesh(mesh, tmp_path / "lens.xyz")


class TestImportRefusals:

    @pytest.mark.parametrize("suffix", ["step", "stp", "iges", "igs"])
    def test_brep_import_is_refused(self, tmp_path, suffix):
        path = tmp_path / f"part.{suffix}"
        path.write_text("ISO-10303-21;\n")
        with pytest.raises(NotImplementedError, match="STL or OBJ"):
            import_cad_file(path)

    def test_missing_and_unknown_files(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            import_cad_file(tmp_path / "missing.stl")
        other = tmp_path / "part.xyz"
        other.write_text("x")
        with pytest.raises(ValueError):
            import_cad_file(other)
