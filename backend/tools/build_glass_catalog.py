"""
Build ``optics/data/glass_catalog.json`` from the manufacturers' own
catalog spreadsheets.

Every number in the generated file is copied from a vendor-published
catalog; nothing is estimated or filled in. A field the vendor does not
publish for a glass is stored as ``null``.

Source files (as published by each manufacturer, and redistributed in the
``opticalglass`` package, https://github.com/mjhoptics/opticalglass):

    SCHOTT  schott-optical-glass-overview-excel-format-en 202501113.xlsx
    OHARA   ohara-catalog-20250312-S-6dec.xlsx
    HOYA    HOYA20260401.xlsx
    CDGM    CDGM202409.xlsx

Usage:
    python tools/build_glass_catalog.py <directory containing the files>

Requires ``openpyxl``. Run from the ``backend`` directory.
"""

import json
import math
import sys
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent.parent / "optics" / "data" / "glass_catalog.json"

SCHOTT_FILE = "schott-optical-glass-overview-excel-format-en 202501113.xlsx"
OHARA_FILE = "ohara-catalog-20250312-S-6dec.xlsx"
HOYA_FILE = "HOYA20260401.xlsx"
CDGM_FILE = "CDGM202409.xlsx"

D_LINE_UM = 0.5875618


def num(v):
    """Return a float for a numeric cell, else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        s = v.strip().replace("−", "-")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def text(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def rows(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return list(wb[sheet].iter_rows(values_only=True))


def sellmeier_n(B, C, lam_um):
    l2 = lam_um * lam_um
    return math.sqrt(1.0 + sum(b * l2 / (l2 - c) for b, c in zip(B, C)))


def laurent_n(terms, lam_um):
    """Hoya formula: n^2 = A0 + A1 l^2 + A2 l^-2 + A3 l^-4 + A4 l^-6 + A5 l^-8."""
    powers = (0, 2, -2, -4, -6, -8)
    return math.sqrt(sum(a * lam_um ** p for a, p in zip(terms, powers)))


def check(name, formula, nd):
    """Reject a record whose dispersion formula does not reproduce its nd."""
    if formula["type"] == "sellmeier":
        n = sellmeier_n(formula["B"], formula["C"], D_LINE_UM)
    else:
        n = laurent_n(formula["A"], D_LINE_UM)
    if abs(n - nd) > 2e-5:
        raise ValueError(f"{name}: formula gives nd={n:.6f}, catalog nd={nd:.6f}")


def tau_table(row, cols):
    """{wavelength_nm: internal transmittance at 10 mm} for published values."""
    out = {}
    for c, wl in cols:
        v = num(row[c])
        if v is not None:
            out[str(int(wl))] = v
    return out or None


def kj(cp):
    """J/(g K) -> J/(kg K)."""
    return cp * 1000.0 if cp is not None else None


def thermal(D0, D1, D2, E0, E1, ltk):
    vals = [D0, D1, D2, E0, E1, ltk]
    if any(v is None for v in vals):
        return None
    return {"D0": D0, "D1": D1, "D2": D2, "E0": E0, "E1": E1, "lambda_tk": ltk}


def record(vendor, name, nd, vd, formula, **props):
    check(name, formula, nd)
    rec = {"vendor": vendor, "nd": nd, "vd": vd, "dispersion": formula}
    rec.update(props)
    return rec


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

def schott(path):
    out = {}
    for sheet, status in (("Preferred glasses", "preferred"),
                          ("Inquiry glasses", "inquiry")):
        data = rows(path, sheet)
        head = [text(h) or "" for h in data[3]]

        def col(prefix, start=0):
            for j in range(start, len(head)):
                if head[j].startswith(prefix):
                    return j
            raise KeyError(prefix)

        c_density = col("Density")
        c_alpha = col("alpha -30/70")
        c_cond = col("Heat conductivity")
        c_cp = col("Heat capacity")
        c_E = col("Young")
        c_mu = col("Poisson")
        c_hk = col("Knoop")
        c_price = col("rel. Price")
        c_dndt_abs_e = 28   # absolute dn/dT, e-line, +20/+40 C
        tau_cols = [(j, float(h.split("/")[1])) for j, h in enumerate(head)
                    if h.startswith("TAUI10/")]
        for r in data[4:]:
            name = text(r[0])
            nd = num(r[1])
            B = [num(r[j]) for j in (6, 7, 8)]
            C = [num(r[j]) for j in (9, 10, 11)]
            if not name or nd is None or None in B or None in C:
                continue
            name = name.replace("�", "").strip()
            out[name] = record(
                "Schott", name, nd, num(r[3]),
                {"type": "sellmeier", "B": B, "C": C},
                status=status,
                relative_price=num(r[c_price]),
                melt_frequency=None,
                density=num(r[c_density]),
                cte=num(r[c_alpha]),
                dn_dT_abs_e=num(r[c_dndt_abs_e]),
                dn_dT_constants=thermal(*[num(r[j]) for j in range(12, 18)]),
                thermal_conductivity=num(r[c_cond]),
                specific_heat=kj(num(r[c_cp])),
                internal_transmittance_10mm=tau_table(r, tau_cols),
                youngs_modulus=num(r[c_E]),
                poissons_ratio=num(r[c_mu]),
                knoop_hardness=num(r[c_hk]),
            )
    return out


def ohara(path):
    out = {}
    data = rows(path, "Recommended glasses 6桁")
    tau_cols = [(j, data[1][j]) for j in range(80, 112) if isinstance(data[1][j], (int, float))]
    for r in data[2:]:
        name = text(r[1])
        if name:
            name = name.replace(" ", "")   # catalog prints "S-FPM 2" for S-FPM2
        nd = num(r[16])
        B = [num(r[j]) for j in (60, 61, 62)]
        C = [num(r[j]) for j in (63, 64, 65)]
        if not name or nd is None or None in B or None in C:
            continue
        cte = num(r[279])
        out[name] = record(
            "Ohara", name, nd, num(r[26]),
            {"type": "sellmeier", "B": B, "C": C},
            status="recommended",
            relative_price=None,
            melt_frequency=None,
            density=num(r[335]),
            cte=cte / 10.0 if cte is not None else None,     # 1e-7/K -> 1e-6/K
            dn_dT_abs_e=None,
            dn_dT_constants=thermal(*[num(r[j]) for j in range(268, 274)]),
            thermal_conductivity=num(r[321]),
            specific_heat=None,
            internal_transmittance_10mm=tau_table(r, tau_cols),
            youngs_modulus=num(r[322]),
            poissons_ratio=num(r[324]),
            knoop_hardness=num(r[325]),
        )
    return out


def hoya(path):
    out = {}
    data = rows(path, "20260401data_table1")
    for r in data[4:]:
        name = text(r[2])
        nd = num(r[4])
        coeffs = []
        for j in range(30, 42, 2):
            a, p = num(r[j]), num(r[j + 1])
            coeffs.append(None if a is None or p is None else a * 10.0 ** p)
        if not name or nd is None or None in coeffs:
            continue
        cte = num(r[107])
        out[name] = record(
            "Hoya", name, nd, num(r[5]),
            {"type": "hoya_laurent", "A": coeffs},
            status="recommended" if text(r[0]) == "◎" else "catalog",
            relative_price=None,
            melt_frequency=None,
            density=num(r[369]),
            cte=cte / 10.0 if cte is not None else None,     # 1e-7/K -> 1e-6/K
            dn_dT_abs_e=None,
            dn_dT_constants=thermal(*[num(r[j]) for j in range(118, 124)]),
            thermal_conductivity=num(r[109]),
            specific_heat=kj(num(r[110])),
            internal_transmittance_10mm=None,
            youngs_modulus=num(r[114]),
            poissons_ratio=num(r[116]),
            knoop_hardness=num(r[111]),
        )
    return out


def cdgm(path):
    out = {}
    data = rows(path, "optical glass")
    head = [text(h) or "" for h in data[0]]
    c_melt = head.index("Melt Frequency")
    c_tau = head.index("τ(10mm)")
    tau_cols = [(j, data[1][j]) for j in range(c_tau, c_tau + 40)
                if j < len(data[1]) and isinstance(data[1][j], (int, float))]
    c_price = head.index("Relative Price")
    for r in data[2:]:
        name = text(r[0])
        nd = num(r[13])
        B = [num(r[j]) for j in (27, 29, 31)]
        C = [num(r[j]) for j in (28, 30, 32)]
        if not name or nd is None or None in B or None in C:
            continue
        cte = num(r[77])
        E = num(r[84])
        price = num(r[c_price])
        out[name] = record(
            "CDGM", name, nd, num(r[23]),
            {"type": "sellmeier", "B": B, "C": C},
            status="catalog",
            # CDGM publishes price relative to H-K9L = 10; store it on the
            # same scale as Schott's (reference glass = 1).
            relative_price=price / 10.0 if price is not None else None,
            melt_frequency=text(r[c_melt]),
            density=num(r[88]),
            cte=cte / 10.0 if cte is not None else None,     # 1e-7/K -> 1e-6/K
            dn_dT_abs_e=None,
            dn_dT_constants=thermal(*[num(r[j]) for j in range(40, 46)]),
            thermal_conductivity=num(r[79]),
            specific_heat=None,
            internal_transmittance_10mm=tau_table(r, tau_cols),
            youngs_modulus=E / 100.0 if E is not None else None,  # 1e7 Pa -> GPa
            poissons_ratio=num(r[86]),
            knoop_hardness=num(r[82]),
        )
    return out


def main(src):
    src = Path(src)
    glasses = {}
    for fn, f in ((schott, SCHOTT_FILE), (ohara, OHARA_FILE),
                  (hoya, HOYA_FILE), (cdgm, CDGM_FILE)):
        part = fn(src / f)
        clash = set(part) & set(glasses)
        if clash:
            raise ValueError(f"Duplicate glass names across vendors: {sorted(clash)}")
        glasses.update(part)
        print(f"{f}: {len(part)} glasses")

    payload = {
        "description": (
            "Optical glass data copied from manufacturer catalogs. Units: "
            "density g/cm^3; cte 1e-6/K (-30..+70 C); thermal_conductivity "
            "W/(m K); specific_heat J/(kg K); youngs_modulus GPa; knoop_hardness as published by "
            "the vendor; dn_dT_abs_e 1e-6/K (e-line, +20..+40 C, Schott "
            "only); dn_dT_constants are the Schott-formula constants D0, D1, "
            "D2, E0, E1, lambda_tk (um). internal_transmittance_10mm maps "
            "wavelength (nm) to the internal transmittance of a 10 mm sample. relative_price is the vendor's own "
            "index (Schott: N-BK7 = 1; CDGM: H-K9L = 1). Dispersion: "
            "'sellmeier' n^2 = 1 + sum B l^2/(l^2 - C); 'hoya_laurent' "
            "n^2 = A0 + A1 l^2 + A2 l^-2 + A3 l^-4 + A4 l^-6 + A5 l^-8; "
            "wavelength l in micrometres."),
        "sources": {
            "Schott": SCHOTT_FILE,
            "Ohara": OHARA_FILE,
            "Hoya": HOYA_FILE,
            "CDGM": CDGM_FILE,
        },
        "glasses": dict(sorted(glasses.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(glasses)} glasses to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
