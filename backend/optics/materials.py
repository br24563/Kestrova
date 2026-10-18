"""
Optical materials and refractive index data.

This is the single source of refractive-index data for the engine. Every
material comes from one of two places, and nothing is estimated:

1. **Manufacturer glass catalogs** (Schott, Ohara, Hoya, CDGM), copied
   into ``data/glass_catalog.json`` by ``tools/build_glass_catalog.py``.
   Index, Abbe number, dispersion constants and physical properties are
   the vendor's published values.
2. **Crystals, IR materials, polymers and water** in :data:`LITERATURE`,
   each with the dispersion formula and validity range of a cited
   peer-reviewed measurement (formulas as compiled in the public-domain
   refractiveindex.info database).

Indices are relative to air, as in the vendor catalogs and in sequential
design programs; ``air`` is therefore exactly 1.

Wavelengths are in meters. The reference wavelength is the helium d-line,
587.5618 nm.
"""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Fraunhofer / spectral-line wavelengths (meters)
D_LINE = 587.5618e-9   # helium d
E_LINE = 546.0740e-9   # mercury e
F_LINE = 486.1327e-9   # hydrogen F
C_LINE = 656.2725e-9   # hydrogen C
G_LINE = 435.8343e-9   # mercury g


# ---------------------------------------------------------------------------
# Dispersion formulas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dispersion:
    """
    A dispersion formula, wavelength in micrometres.

    ``sellmeier``:    n^2 = A + sum_i B_i * l^p_i / (l^2 - C_i)
                      (the classic Sellmeier form is A = 1, p_i = 2)
    ``power_series``: n^2 = sum_i A_i * l^p_i
                      (Hoya: powers 0, 2, -2, -4, -6, -8)
    ``cauchy``:       n = sum_i A_i * l^p_i
    """

    kind: str
    A: float = 1.0
    B: tuple = ()
    C: tuple = ()
    P: tuple = ()
    range_um: Optional[tuple] = None   # (min, max) validity range

    def n(self, lam_um: float) -> float:
        l2 = lam_um * lam_um
        if self.kind == "sellmeier":
            powers = self.P or (2,) * len(self.B)
            n2 = self.A + sum(b * lam_um ** p / (l2 - c)
                              for b, c, p in zip(self.B, self.C, powers))
        elif self.kind == "power_series":
            n2 = sum(a * lam_um ** p for a, p in zip(self.B, self.P))
        elif self.kind == "cauchy":
            return sum(a * lam_um ** p for a, p in zip(self.B, self.P))
        else:
            raise ValueError(f"Unknown dispersion formula '{self.kind}'")
        if n2 <= 0:
            raise ValueError(f"Dispersion formula gives n^2 = {n2:.4g} at {lam_um} um")
        return math.sqrt(n2)


# ---------------------------------------------------------------------------
# Material record
# ---------------------------------------------------------------------------

@dataclass
class Material:
    """
    One optical material. Fields the source does not publish are ``None``.

    Units: density g/cm^3; cte 1e-6/K; dn_dT 1e-6/K (absolute, d-line,
    20 C); thermal_conductivity W/(m K); specific_heat J/(kg K);
    youngs_modulus GPa.
    """

    name: str
    manufacturer: str
    nd: Optional[float]
    vd: Optional[float]
    dispersion: Optional[Dispersion]
    source: str
    material_type: str = "crown"
    status: Optional[str] = None
    relative_price: Optional[float] = None
    melt_frequency: Optional[str] = None
    density: Optional[float] = None
    cte: Optional[float] = None
    dn_dT: Optional[float] = None
    dn_dT_constants: Optional[dict] = None
    thermal_conductivity: Optional[float] = None
    specific_heat: Optional[float] = None
    youngs_modulus: Optional[float] = None
    poissons_ratio: Optional[float] = None
    knoop_hardness: Optional[float] = None
    internal_transmittance_10mm: Optional[dict] = None   # {nm: tau}
    notes: str = ""

    def absorption_coefficient(self, wavelength: float) -> float:
        """
        Bulk absorption coefficient alpha (1/m) at a wavelength (meters) from
        the vendor's internal transmittance of a 10 mm sample,
        alpha = -ln(tau) / 0.01, interpolated linearly in alpha between the
        tabulated wavelengths. Raises ValueError outside the tabulated range
        or when the vendor publishes no data.
        """
        import numpy as np
        t = self.internal_transmittance_10mm
        if not t:
            raise ValueError(f"No published internal transmittance for '{self.name}'")
        wl = np.array(sorted(float(k) for k in t))
        alpha = np.array([-math.log(max(t[str(int(w))], 1e-12)) / 0.01 for w in wl])
        x = wavelength * 1e9
        if not wl[0] <= x <= wl[-1]:
            raise ValueError(f"{self.name}: {x:.0f} nm is outside the tabulated "
                             f"transmittance range {wl[0]:.0f}-{wl[-1]:.0f} nm")
        return float(np.interp(x, wl, alpha))

    # Backward-compatible views of the dispersion constants
    @property
    def sellmeier_b(self) -> list:
        d = self.dispersion
        return list(d.B) if d is not None and d.kind == "sellmeier" else []

    @property
    def sellmeier_c(self) -> list:
        d = self.dispersion
        return list(d.C) if d is not None and d.kind == "sellmeier" else []

    @property
    def transmission_range(self) -> Optional[tuple]:
        """Validity range of the dispersion data in nm (None if unpublished)."""
        if self.dispersion is None or self.dispersion.range_um is None:
            return None
        lo, hi = self.dispersion.range_um
        return (lo * 1000.0, hi * 1000.0)

    def index(self, wavelength: float = D_LINE) -> float:
        return refractive_index(self.name, wavelength)


def classify_glass(name: str, nd: float, vd: Optional[float]) -> str:
    """
    Glass family by the conventional glass-map rule.

    Crowns have vd > 50 (nd < 1.60) or vd > 55 (nd >= 1.60); everything else
    is a flint. Lanthanum-bearing families are recognised from the vendors'
    naming conventions (Schott/Ohara/CDGM 'LA', Hoya 'LA' and 'TA').
    """
    family = re.sub(r"^[A-Z]{1,2}-", "", name.upper())
    if "LA" in family or re.match(r"^(TAC|TAF|TAFD)\d", family):
        return "lanthanum"
    if vd is None:
        return "crown"
    if (nd < 1.60 and vd > 50.0) or (nd >= 1.60 and vd > 55.0):
        return "crown"
    return "flint"


def _schott_dn_dT(n: float, lam_um: float, k: Optional[dict]) -> Optional[float]:
    """Absolute dn/dT at 20 C from the Schott thermal constants, 1e-6/K."""
    if not k:
        return None
    d = lam_um * lam_um - k["lambda_tk"] ** 2
    return (n * n - 1.0) / (2.0 * n) * (k["D0"] + k["E0"] / d) * 1e6


# ---------------------------------------------------------------------------
# Literature materials
# ---------------------------------------------------------------------------

def _sq(*c):
    return tuple(x * x for x in c)


#: Non-catalog materials with published dispersion formulas.
#: B/C follow the generalized Sellmeier form documented on :class:`Dispersion`.
#: Densities (g/cm^3) are room-temperature values from the CRC Handbook of
#: Chemistry and Physics; polymer densities vary by grade and are omitted.
LITERATURE: dict[str, dict] = {
    "FusedSilica": dict(
        disp=Dispersion("sellmeier", 1.0, (0.6961663, 0.4079426, 0.8974794),
                        _sq(0.0684043, 0.1162414, 9.896161), range_um=(0.21, 6.7)),
        type="uv", density=2.201,
        source="I. H. Malitson, J. Opt. Soc. Am. 55, 1205 (1965); 20 C"),
    "CaF2": dict(
        disp=Dispersion("sellmeier", 1.0, (0.5675888, 0.4710914, 3.8484723),
                        _sq(0.050263605, 0.1003909, 34.649040), range_um=(0.23, 9.7)),
        type="uv", density=3.18,
        source="I. H. Malitson, Appl. Opt. 2, 1103 (1963); 24 C"),
    "MgF2": dict(
        disp=Dispersion("sellmeier", 1.0, (0.48755108, 0.39875031, 2.3120353),
                        _sq(0.04338408, 0.09461442, 23.793604), range_um=(0.2, 7.0)),
        type="uv", density=3.18,
        source="M. J. Dodge, Appl. Opt. 23, 1980 (1984); ordinary ray, 19 C",
        notes="Birefringent; ordinary-ray index."),
    "BaF2": dict(
        disp=Dispersion("sellmeier", 1.0, (0.643356, 0.506762, 3.8261),
                        _sq(0.057789, 0.10968, 46.3864), range_um=(0.2652, 10.346)),
        type="ir", density=4.89,
        source="I. H. Malitson, J. Opt. Soc. Am. 54, 628 (1964); 25 C"),
    "LiF": dict(
        disp=Dispersion("sellmeier", 1.0, (0.92549, 6.96747),
                        _sq(0.07376, 32.790), range_um=(0.10, 11.0)),
        type="uv", density=2.64,
        source="H. H. Li, J. Phys. Chem. Ref. Data 5, 329 (1976); 24 C"),
    "Sapphire": dict(
        disp=Dispersion("sellmeier", 1.0, (1.4313493, 0.65054713, 5.3414021),
                        _sq(0.0726631, 0.1193242, 18.028251), range_um=(0.20, 5.0)),
        type="uv", density=3.98,
        source="I. H. Malitson and M. J. Dodge, J. Opt. Soc. Am. 62, 1405 "
               "(1972); ordinary ray, 20 C",
        notes="Birefringent; ordinary-ray index."),
    "ZnSe": dict(
        disp=Dispersion("sellmeier", 1.0, (4.45813734, 0.467216334, 2.89566290),
                        _sq(0.200859853, 0.391371166, 47.1362108), range_um=(0.54, 18.2)),
        type="ir", density=5.27,
        source="J. Connolly et al., Proc. SPIE 181, 141 (1979); fit by "
               "B. Tatian, Appl. Opt. 23, 4477 (1984); CVD ZnSe, 23 C"),
    "ZnS": dict(
        disp=Dispersion("sellmeier", 8.393, (0.14383, 4430.99),
                        _sq(0.2421, 36.71), (0, 0), range_um=(0.405, 13.0)),
        type="ir", density=4.09,
        source="M. Debenham, Appl. Opt. 23, 2238 (1984); equation by "
               "C. A. Klein, Appl. Opt. 25, 1873 (1986); cubic ZnS, 20 C"),
    "Si": dict(
        disp=Dispersion("sellmeier", 11.67316, (1.0, 0.004482633),
                        (0.0, 1.108205 ** 2), (0, 0), range_um=(2.5, 22.222)),
        type="ir", density=2.329,
        source="D. Chandler-Horowitz and P. M. Amirtharaj, J. Appl. Phys. 97, "
               "123526 (2005); room temperature"),
    "Ge": dict(
        disp=Dispersion("sellmeier", 1.0, (0.4886331, 14.5142535, 0.0091224),
                        (1.393959, 0.1626427, 752.190), range_um=(2.0, 14.0)),
        type="ir", density=5.323,
        source="J. H. Burnett et al., Proc. SPIE 9974, 99740X (2016); 22 C"),
    "GaAs": dict(
        disp=Dispersion("sellmeier", 1.0 + 4.372514, (5.466742, 0.02429960, 1.957522),
                        _sq(0.4431307, 0.8746453, 36.9166), range_um=(0.97, 17.0)),
        type="ir", density=5.32,
        source="T. Skauli et al., J. Appl. Phys. 94, 6447 (2003); 22 C"),
    "TiO2": dict(
        disp=Dispersion("sellmeier", 5.913, (0.2441,), (0.0803,), (0,), range_um=(0.43, 1.53)),
        type="coating", density=4.23,
        source="J. R. Devore, J. Opt. Soc. Am. 41, 416 (1951); rutile, ordinary ray",
        notes="Bulk rutile; deposited TiO2 films are typically lower in index."),
    "Si3N4": dict(
        disp=Dispersion("sellmeier", 1.0, (3.0249, 40314.0), _sq(0.1353406, 1239.842),
                        range_um=(0.310, 5.504)),
        type="coating", density=None,
        source="K. Luke et al., Opt. Lett. 40, 4823 (2015); LPCVD film"),
    "HfO2": dict(
        disp=Dispersion("cauchy", B=(1.875, 6.28e-3, 5.80e-4), P=(0, -2, -4), range_um=(0.2, 2.0)),
        type="coating", density=None,
        source="M. F. Al-Kuhaili, Opt. Mater. 27, 383 (2004); e-beam film"),
    "PMMA": dict(
        disp=Dispersion("sellmeier", 1.0, (1.1819,), (0.011313,), range_um=(0.4368, 1.052)),
        type="polymer", density=None,
        source="N. Sultanova et al., Acta Phys. Pol. A 116, 585 (2009); 20 C"),
    "Polycarbonate": dict(
        disp=Dispersion("sellmeier", 1.0, (1.4182,), (0.021304,), range_um=(0.4368, 1.052)),
        type="polymer", density=None,
        source="N. Sultanova et al., Acta Phys. Pol. A 116, 585 (2009); 20 C"),
    "Polystyrene": dict(
        disp=Dispersion("sellmeier", 1.0, (1.4435,), (0.020216,), range_um=(0.4368, 1.052)),
        type="polymer", density=None,
        source="N. Sultanova et al., Acta Phys. Pol. A 116, 585 (2009); 20 C"),
    "Water": dict(
        disp=Dispersion("sellmeier", 1.0,
                        (5.684027565e-1, 1.726177391e-1, 2.086189578e-2, 1.130748688e-1),
                        (5.101829712e-3, 1.821153936e-2, 2.620722293e-2, 1.069792721e1),
                        range_um=(0.182, 1.129)),
        type="liquid", density=0.998,
        source="M. Daimon and A. Masumura, Appl. Opt. 46, 3811 (2007); 20 C"),
}

#: Alternative names that refer to exactly the same data.
ALIASES = {
    "SiO2": "FusedSilica",
    "Al2O3": "Sapphire",
    "Air": "air",
    "AIR": "air",
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_CATALOG_PATH = Path(__file__).parent / "data" / "glass_catalog.json"


def _load() -> dict[str, Material]:
    mats: dict[str, Material] = {}
    payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    sources = payload["sources"]
    for name, g in payload["glasses"].items():
        f = g["dispersion"]
        # The vendors state their dispersion formulas hold over the range of
        # their tabulated transmittance data; with no table the range is
        # unpublished here and left as None (not checked).
        tau = g.get("internal_transmittance_10mm")
        rng = None
        if tau:
            wl_nm = sorted(float(w) for w in tau)
            rng = (wl_nm[0] / 1000.0, wl_nm[-1] / 1000.0)
        if f["type"] == "sellmeier":
            disp = Dispersion("sellmeier", 1.0, tuple(f["B"]), tuple(f["C"]), range_um=rng)
        else:
            disp = Dispersion("power_series", B=tuple(f["A"]), P=(0, 2, -2, -4, -6, -8),
                              range_um=rng)
        k = g.get("dn_dT_constants")
        mats[name] = Material(
            name=name,
            manufacturer=g["vendor"],
            nd=g["nd"],
            vd=g["vd"],
            dispersion=disp,
            source=f"{g['vendor']} catalog ({sources[g['vendor']]})",
            material_type=classify_glass(name, g["nd"], g["vd"]),
            status=g.get("status"),
            relative_price=g.get("relative_price"),
            melt_frequency=g.get("melt_frequency"),
            density=g.get("density"),
            cte=g.get("cte"),
            dn_dT=_schott_dn_dT(g["nd"], D_LINE * 1e6, k),
            dn_dT_constants=k,
            thermal_conductivity=g.get("thermal_conductivity"),
            specific_heat=g.get("specific_heat"),
            youngs_modulus=g.get("youngs_modulus"),
            poissons_ratio=g.get("poissons_ratio"),
            knoop_hardness=g.get("knoop_hardness"),
            internal_transmittance_10mm=g.get("internal_transmittance_10mm"),
        )
    for name, m in LITERATURE.items():
        disp = m["disp"]
        lo, hi = disp.range_um
        lam_d = D_LINE * 1e6
        if lo <= lam_d <= hi:
            nd = disp.n(lam_d)
            fl, cl = F_LINE * 1e6, C_LINE * 1e6
            vd = (nd - 1.0) / (disp.n(fl) - disp.n(cl)) if lo <= fl and cl <= hi else None
        else:
            nd, vd = None, None   # formula not valid at the d-line (IR material)
        mats[name] = Material(
            name=name, manufacturer="Literature", nd=nd, vd=vd, dispersion=disp,
            source=m["source"], material_type=m["type"], density=m.get("density"),
            cte=m.get("cte"), notes=m.get("notes", ""),
        )
    mats["air"] = Material(
        name="air", manufacturer="N/A", nd=1.0, vd=None, dispersion=None,
        source="Reference medium: indices are relative to air",
        material_type="gas")
    return mats


MATERIALS: dict[str, Material] = _load()

#: d-line indices, kept for callers that only need a quick lookup.
REFRACTIVE_INDICES: dict[str, float] = {k: m.nd for k, m in MATERIALS.items()}


def resolve_material_name(material: str) -> str:
    return ALIASES.get(material, material)


def get_material(material: str) -> Material:
    """Return the :class:`Material` record, raising ValueError if unknown."""
    name = resolve_material_name(material)
    m = MATERIALS.get(name)
    if m is None:
        raise ValueError(
            f"Unknown material: '{material}'. Use a catalog glass name "
            f"(e.g. 'N-BK7', 'S-BSL7', 'H-K9L') or one of: "
            f"{sorted(LITERATURE)} or 'air'.")
    return m


def material_names() -> list[str]:
    return sorted(MATERIALS)


def refractive_index(material: str, wavelength: float = D_LINE) -> float:
    """
    Refractive index (relative to air) of a material at a wavelength.

    The value always comes from the material's published dispersion
    formula, so it is continuous in wavelength.

    Args:
        material: Material name (e.g. "N-BK7", "CaF2", "air").
        wavelength: Wavelength in meters.

    Raises:
        ValueError: Unknown material, or a wavelength outside the range over
            which the source's formula was measured.
    """
    m = get_material(material)
    if m.dispersion is None:
        return m.nd
    lam_um = wavelength * 1e6
    rng = m.dispersion.range_um
    if rng is not None and not (rng[0] - 1e-9 <= lam_um <= rng[1] + 1e-9):
        raise ValueError(
            f"{m.name}: {lam_um * 1000:.1f} nm is outside the measured range "
            f"{rng[0] * 1000:.0f}-{rng[1] * 1000:.0f} nm of {m.source}")
    return m.dispersion.n(lam_um)


def refractive_index_sellmeier(material: str, wavelength: float) -> float:
    """Backward-compatible name for :func:`refractive_index`."""
    m = get_material(material)
    if m.dispersion is None:
        raise ValueError(f"No dispersion formula for material: '{material}'")
    return refractive_index(material, wavelength)


def abbe_number(material: str) -> Optional[float]:
    """Abbe number vd = (nd - 1)/(nF - nC) computed from the dispersion formula."""
    m = get_material(material)
    if m.dispersion is None:
        return None
    try:
        nd = refractive_index(material, D_LINE)
        return (nd - 1.0) / (refractive_index(material, F_LINE)
                             - refractive_index(material, C_LINE))
    except ValueError:
        return None   # formula not valid across the F-C range
