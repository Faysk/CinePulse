from __future__ import annotations

from cinepulse.restoration_color import RestorationColorControls
from cinepulse.restoration_overlay import DetectionEvidence, OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPolicy, build_preview_restoration_plan


def _evidence(score_kind: str = "text") -> DetectionEvidence:
    return DetectionEvidence(
        region=OverlayRegion(x=0.10, y=0.80, width=0.30, height=0.08),
        persistence=0.90,
        edge_density=0.80,
        temporal_stability=0.92,
        text_confidence=0.85 if score_kind == "text" else 0.10,
        qr_confidence=0.85 if score_kind == "qr" else 0.10,
    )


def test_plan_combines_overlay_and_color_filters() -> None:
    plan = build_preview_restoration_plan(
        (_evidence(),),
        frame_width=1920,
        frame_height=1080,
        color=RestorationColorControls(contrast=1.08, saturation=1.05),
    )

    assert plan.has_overlay_work
    assert plan.has_color_work
    assert plan.has_work
    assert "delogo=" in plan.filtergraph
    assert ",eq=" in plan.filtergraph
    assert plan.regions[0].kind == "text"


def test_plan_can_apply_color_without_overlay_candidate() -> None:
    weak = DetectionEvidence(
        region=OverlayRegion(x=0.1, y=0.1, width=0.1, height=0.1),
        persistence=0.2,
        edge_density=0.2,
        temporal_stability=0.2,
        text_confidence=0.2,
    )
    plan = build_preview_restoration_plan(
        (weak,),
        frame_width=1280,
        frame_height=720,
        color=RestorationColorControls(gamma=1.05),
    )

    assert not plan.has_overlay_work
    assert plan.has_color_work
    assert plan.filtergraph.startswith("eq=")


def test_neutral_plan_with_no_candidates_has_no_work() -> None:
    plan = build_preview_restoration_plan((), frame_width=640, frame_height=360)

    assert not plan.has_work
    assert plan.filtergraph == ""


def test_policy_can_raise_overlay_threshold() -> None:
    plan = build_preview_restoration_plan(
        (_evidence(),),
        frame_width=1920,
        frame_height=1080,
        policy=PreviewRestorationPolicy(minimum_overlay_score=0.99),
    )

    assert not plan.has_overlay_work
