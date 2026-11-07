"""
Tests for Code V (.seq) and Zemax (.zmx) lens files (optics.io.lensfile).

References:
- a lens written and read back must keep its first-order properties and
  Seidel sums (computed independently from each prescription) to round-off,
  and writing it again must give the same file;
- hand-written files in other units (inches) are checked against the values
  converted by hand: 1 in = 25.4 mm; an even asphere coefficient of r^(2k+4)
  scales as length^-(2k+3);
- Zemax vignetting maps to Code V's factors by VD = (vl - vu)/2,
  VC = (vu + vl)/2 (both describe the pupil -(1 - vl) .. (1 - vu)).
"""

import math

import pytest

from optics import lens_data as ld
from optics import raytrace as rt
from optics.io import lensfile as LF
from optics.lens_data import FieldPoint, LensData, LensSurface, Solve
from optics.materials import C_LINE, D_LINE, F_LINE


def doublet():
    return LensData(
        name="Test doublet",
        surfaces=[
            LensSurface(label="STO", is_stop=True, semi_diameter=0.01, thickness=0.002),
            LensSurface(element="D", radius=0.06131, thickness=0.006, material="N-BK7",
                        variables=["radius"]),
            LensSurface(element="D", radius=-0.04385, thickness=0.0025,
                        material="MODEL:1.65:34", surface_type="even_asphere",
                        conic=-0.3, aspheric_coefficients=[1.2e-3, -4e-6]),
            LensSurface(element="D", radius=-0.12886, thickness=0.095,
                        solves={"thickness": Solve(kind="marginal_height")}),
        ],
        object_distance=None, field_angle=math.radians(1),
        wavelengths=[F_LINE, D_LINE, C_LINE], wavelength_weights=[1, 2, 1],
        fields=[FieldPoint(y=0), FieldPoint(y=math.radians(0.7), weight=2),
                FieldPoint(y=math.radians(1), vuy=0.1, vly=0.2)],
        field_type="angle", analysis_settings={"wavelength": D_LINE},
    )


def cassegrain():
    return LensData(
        surfaces=[
            LensSurface(label="M1", radius=-1.0, conic=-1.0, material="MIRROR",
                        is_stop=True, semi_diameter=0.05, thickness=-0.35),
            LensSurface(label="M2", radius=-0.4, conic=-2.5, material="MIRROR",
                        thickness=0.6),
        ],
        object_distance=None, field_angle=math.radians(0.2),
        wavelengths=[D_LINE], analysis_settings={"wavelength": D_LINE},
    )


def tilted():
    return LensData(
        surfaces=[
            LensSurface(label="STO", is_stop=True, semi_diameter=0.005, thickness=0.01),
            LensSurface(label="CB", surface_type="coordinate_break", decenter_y=1e-4,
                        tilt_x=math.radians(0.5), thickness=0.0),
            LensSurface(element="L", radius=0.05, thickness=0.004, material="N-SF5"),
            LensSurface(element="L", radius=-0.05, thickness=0.09),
        ],
        object_distance=0.2, object_height=0.002,
        wavelengths=[D_LINE], analysis_settings={"wavelength": D_LINE},
    )


def summary(lens):
    s = ld.to_system(lens)
    fo = rt.first_order(s)
    out = [fo.efl, fo.image_z]
    try:
        ss = rt.seidel_sums(s)
        out += [ss.S1, ss.S2, ss.S3, ss.S4]
    except ValueError:
        pass
    return out


FORMATS = {
    "seq": (LF.write_codev, LF.read_codev),
    "zmx": (LF.write_zemax, LF.read_zemax),
}


class TestRoundTrip:

    @pytest.mark.parametrize("fmt", FORMATS)
    @pytest.mark.parametrize("make", [doublet, cassegrain])
    def test_optics_survive_and_files_are_stable(self, fmt, make):
        write, read = FORMATS[fmt]
        lens = make()
        text, _ = write(lens)
        back = read(text)
        assert back.warnings == []
        assert summary(back.lens) == pytest.approx(summary(lens), rel=1e-12, abs=1e-15)
        assert write(back.lens)[0] == write(read(write(back.lens)[0]).lens)[0]

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_system_data_survive(self, fmt):
        write, read = FORMATS[fmt]
        back = read(write(doublet())[0]).lens
        assert back.name == "Test doublet"
        assert back.wavelengths == pytest.approx([F_LINE, D_LINE, C_LINE], rel=1e-9)
        assert back.wavelength_weights == [1, 2, 1]
        assert back.analysis_settings.wavelength == pytest.approx(D_LINE, rel=1e-9)
        assert [f.weight for f in back.fields] == [1, 2, 1]
        assert back.fields[2].y == pytest.approx(math.radians(1), rel=1e-9)
        assert (back.fields[2].vuy, back.fields[2].vly) == pytest.approx((0.1, 0.2))
        s = back.surfaces[2]
        assert s.material == "MODEL:1.65:34"
        assert s.conic == pytest.approx(-0.3)
        assert s.aspheric_coefficients == pytest.approx([1.2e-3, -4e-6], rel=1e-9)
        assert back.surfaces[0].is_stop and back.surfaces[0].semi_diameter == pytest.approx(0.01)

    def test_codev_keeps_variables_and_the_image_solve(self):
        text, warnings = LF.write_codev(doublet())
        assert warnings == []
        assert "PIM" in text and "CCY S2 0" in text
        back = LF.read_codev(text).lens
        assert back.surfaces[1].variables == ["radius"]
        assert back.surfaces[3].solves["thickness"].kind == "marginal_height"

    def test_zemax_reports_what_it_writes_as_values(self):
        _, warnings = LF.write_zemax(doublet())
        assert any("variable radius" in w for w in warnings)
        assert any("thickness solve written as its current value" in w for w in warnings)

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_coordinate_breaks_round_trip(self, fmt):
        write, read = FORMATS[fmt]
        back = read(write(tilted())[0]).lens
        cb = back.surfaces[1]
        assert cb.surface_type == "coordinate_break"
        assert cb.decenter_y == pytest.approx(1e-4)
        assert cb.tilt_x == pytest.approx(math.radians(0.5))
        a = rt.build_sequence(ld.to_system(tilted()))
        b = rt.build_sequence(ld.to_system(back))
        assert b.image_origin == pytest.approx(a.image_origin, abs=1e-12)


class TestHandWrittenFiles:

    def test_codev_in_inches(self):
        text = """! a singlet in inches
LEN NEW
TITLE 'Inch singlet'
DIM I
WL 656.27 587.56 486.13
REF 2
WTW 1 1 1
EPD 1.0
YAN 0 5
SO 0 1e20
STO 4.0 0.2 NBK7_SCHOTT
S -4.0 3.8
  CIR 0.6
  ASP
  A 1.0E-3
SI 0 0
PIM
THC S1 0
POL Y
GO
"""
        res = LF.read_codev(text)
        lens = res.lens
        inch = 25.4e-3
        assert lens.name == "Inch singlet"
        assert lens.entrance_pupil_diameter == pytest.approx(inch)
        assert lens.surfaces[0].material == "N-BK7"
        assert lens.surfaces[0].radius == pytest.approx(4 * inch)
        assert lens.surfaces[1].semi_diameter == pytest.approx(0.6 * inch)
        # A (r^4) in in^-3 -> m^-3
        assert lens.surfaces[1].aspheric_coefficients[0] == pytest.approx(1e-3 / inch**3)
        assert lens.fields[1].y == pytest.approx(math.radians(5))
        assert lens.surfaces[0].variables == ["thickness"]
        assert lens.analysis_settings.wavelength == pytest.approx(587.56e-9)
        assert res.warnings == ["Code V command POL not interpreted (1x)"]

    def test_codev_solve_and_variable_on_one_thickness(self):
        res = LF.read_codev(
            "SO 0 1e20\nSTO 50 5 NBK7_SCHOTT\nS -50 90\nSI 0 0\nPIM\nTHC S2 0\n"
        )
        last = res.lens.surfaces[1]
        assert "thickness" in last.solves and last.variables == []
        assert any("kept the solve" in w for w in res.warnings)

    def test_codev_model_glass_and_object_height(self):
        text = "DIM M\nWL 587.56\nYOB 0 2\nSO 0 200\nSTO 50 5 1.62:36.3\nS -50 90\nSI 0 0\n"
        lens = LF.read_codev(text).lens
        assert lens.surfaces[0].material == "MODEL:1.62:36.3"
        assert lens.object_distance == pytest.approx(0.2)
        assert lens.field_type == "object_height" and lens.fields[1].y == pytest.approx(2e-3)

    def test_zemax_in_inches_with_vignetting(self):
        text = """VERS 0
NAME Inch lens
UNIT IN
ENPD 1
WAVM 1 0.58756 2
PWAV 1
FTYP 1 0 2 1 0 0 0
YFLN 0 0.1
XFLN 0 0
FWGN 1 1
VDYN 0 0.05
VCYN 0 0.15
SURF 0
  TYPE STANDARD
  DISZ 10
SURF 1
  STOP
  TYPE EVENASPH
  CURV 0.25
  PARM 2 1e-3
  GLAS ___BLANK 1 0 1.62 36.3 0 0 0 0 0 0
  DISZ 0.2
SURF 2
  TYPE PARAXIAL
  PARM 1 4
  DISZ 4
SURF 3
  TYPE STANDARD
  DISZ 0
"""
        lens = LF.read_zemax(text).lens
        inch = 25.4e-3
        s = lens.surfaces[0]
        assert s.radius == pytest.approx(4 * inch)
        assert s.aspheric_coefficients[0] == pytest.approx(1e-3 / inch**3)
        assert s.material == "MODEL:1.62:36.3"
        assert lens.surfaces[1].surface_type == "paraxial"
        assert lens.surfaces[1].focal_length == pytest.approx(4 * inch)
        assert lens.object_distance == pytest.approx(10 * inch)
        assert lens.entrance_pupil_diameter == pytest.approx(inch)
        f = lens.fields[1]
        assert f.y == pytest.approx(0.1 * inch)
        # VD = 0.05, VC = 0.15 -> vu = VC - VD = 0.10, vl = VC + VD = 0.20
        assert (f.vuy, f.vly) == pytest.approx((0.10, 0.20))

    def test_vignetting_conversion_is_inverse(self):
        for vu, vl in ((0.1, 0.2), (0.0, 0.5), (0.3, 0.3)):
            assert LF._vignetting_from_zemax(*LF._vignetting_to_zemax(vu, vl)) == \
                pytest.approx((vu, vl))

    def test_asphere_units_in_the_file(self):
        text, _ = LF.write_codev(doublet())
        # 1.2e-3 m^-3 = 1.2e-12 mm^-3
        assert "A 1.2000000000E-12" in text


class TestErrors:

    def test_codev_has_no_paraxial_surface(self):
        lens = LensData(
            surfaces=[LensSurface(surface_type="paraxial", focal_length=0.1, is_stop=True,
                                  semi_diameter=0.005, thickness=0.1)],
            object_distance=None, wavelengths=[D_LINE],
            analysis_settings={"wavelength": D_LINE})
        with pytest.raises(ValueError, match="paraxial"):
            LF.write_codev(lens)
        assert "TYPE PARAXIAL" in LF.write_zemax(lens)[0]

    def test_incomplete_or_unknown_files(self):
        with pytest.raises(ValueError, match="object surface"):
            LF.read_codev("S 10 1\nSI 0 0\n")
        with pytest.raises(ValueError, match="image surface"):
            LF.read_codev("SO 0 1e20\nS 10 1\n")
        with pytest.raises(ValueError, match="not in the material catalog"):
            LF.read_codev("SO 0 1e20\nSTO 10 1 UNOBTAINIUM\nSI 0 0\n")
        with pytest.raises(ValueError, match="not supported"):
            LF.read_zemax("SURF 0\nDISZ INFINITY\nSURF 1\nTYPE TOROIDAL\nSURF 2\n")
        with pytest.raises(ValueError, match="Unsupported"):
            LF.read_lens_file("x", "lens.txt")

    def test_missing_stop_is_reported(self):
        res = LF.read_codev("SO 0 1e20\nS 50 5 NBK7_SCHOTT\nS -50 90\nSI 0 0\n")
        assert res.lens.surfaces[0].is_stop
        assert any("No stop" in w for w in res.warnings)


def test_endpoints():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    lens = doublet()
    for fmt in ("seq", "zmx"):
        r = client.post("/api/lens/export", json={"lens": lens.model_dump(), "format": fmt})
        assert r.status_code == 200
        body = r.json()
        assert body["filename"] == f"Test_doublet.{fmt}"
        up = client.post("/api/lens/import",
                         files={"file": (body["filename"], body["content"], "text/plain")})
        assert up.status_code == 200
        back = LensData.model_validate(up.json()["lens"])
        assert summary(back) == pytest.approx(summary(lens), rel=1e-12, abs=1e-15)
    bad = client.post("/api/lens/import", files={"file": ("x.seq", "S 1 2\n", "text/plain")})
    assert bad.status_code == 400 and "object surface" in bad.json()["detail"]
    para = LensData(
        surfaces=[LensSurface(surface_type="paraxial", focal_length=0.1, is_stop=True,
                              semi_diameter=0.005, thickness=0.1)],
        object_distance=None, wavelengths=[D_LINE], analysis_settings={"wavelength": D_LINE})
    r = client.post("/api/lens/export", json={"lens": para.model_dump(), "format": "seq"})
    assert r.status_code == 400
