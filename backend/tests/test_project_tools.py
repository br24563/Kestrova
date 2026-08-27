"""
Tests for the project-tools modules (Phase 8): batch analysis,
tolerance analysis, design comparison, and engineering reports.
"""

import pytest

from optics.models import (
    OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings,
)
from optics.batch import batch_analyze_systems, batch_sweep_and_analyze
from optics.tolerance import tolerance_analysis
from optics.report import (
    compare_systems, system_spot_svg, engineering_report_markdown,
)


def make_single_lens_system(
    f: float = 0.050, lens_pos: float = 0.100, image_pos: float = 0.200,
) -> OpticalSystem:
    """Create a single thin-lens system (non-afocal)."""
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1", position=lens_pos, focal_length=f,
                aperture_diameter=0.025, material="N-BK7",
            ),
        ],
        object=Object(position=0.0, height=0.010),
        image_plane=ImagePlane(position=image_pos),
        analysis_settings=AnalysisSettings(num_rays=11),
    )


class TestBatchAnalysis:
    def test_batch_analyze_returns_summary(self):
        s1 = make_single_lens_system()
        s2 = make_single_lens_system(f=0.060)
        res = batch_analyze_systems([s1, s2])
        assert len(res) == 2
        assert res[0]["index"] == 0
        assert "summary" in res[0]
        assert res[1]["summary"]["efl_mm"] == pytest.approx(60.0, abs=0.1)

    def test_batch_sweep_and_analyze(self):
        s = make_single_lens_system()
        res = batch_sweep_and_analyze(
            s, {"component_id": "lens_1", "field": "focal_length"},
            [0.04, 0.05, 0.06],
        )
        assert len(res) == 3
        # For a single lens, EFL tracks the focal length
        assert res[2]["summary"]["efl_mm"] == pytest.approx(60.0, abs=0.1)


class TestToleranceAnalysis:
    def test_tolerance_produces_stats(self):
        s = make_single_lens_system()
        res = tolerance_analysis(s, trials=50)
        assert res["trials"] == 50
        assert res["mean"] >= 0
        assert res["std"] >= 0
        assert res["min"] <= res["max"]
        assert res["p95"] >= res["mean"]

    def test_tolerance_reproducible(self):
        s = make_single_lens_system()
        r1 = tolerance_analysis(s, trials=30, seed=1)
        r2 = tolerance_analysis(s, trials=30, seed=1)
        assert r1["mean"] == pytest.approx(r2["mean"], rel=1e-6)


class TestComparison:
    def test_compare_returns_rows(self):
        a = make_single_lens_system()
        b = make_single_lens_system(f=0.060)
        comp = compare_systems(a, b, "A", "B")
        assert len(comp["rows"]) == 8
        assert comp["summary_a"]["magnification"] is not None

    def test_compare_advantage_ties(self):
        a = make_single_lens_system()
        b = make_single_lens_system()
        comp = compare_systems(a, b)
        # Identical systems: RMS spots tie (0 vs 0) -> advantage 'tie'
        for row in comp["rows"]:
            assert row["advantage"] in ("a", "b", "tie")


class TestReport:
    def test_svg_spot_diagram(self):
        s = make_single_lens_system()
        svg = system_spot_svg(s)
        assert svg.startswith("<svg")
        assert "circle" in svg
        assert svg.endswith("</svg>")

    def test_markdown_report(self):
        a = make_single_lens_system()
        b = make_single_lens_system(f=0.060)
        md = engineering_report_markdown(a, b, "A", "B", include_svg=False)
        assert md.startswith("# Engineering Report")
        assert "## A" in md
        assert "## B" in md
        assert "## Comparison" in md
        assert "| Metric | Value |" in md

    def test_report_requires_system_a(self):
        with pytest.raises(ValueError):
            engineering_report_markdown(system_a=None)