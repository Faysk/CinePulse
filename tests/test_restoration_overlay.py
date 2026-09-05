from cinepulse.restoration_overlay import (
    DetectionEvidence,
    OverlayRegion,
    build_delogo_filters,
    build_overlay_removal_filtergraph,
    select_overlay_candidates,
)


def evidence(region, *, persistence=0.9, stability=0.9, edges=0.8, text=0.8, qr=0.0):
    return DetectionEvidence(
        region=region,
        persistence=persistence,
        edge_density=edges,
        temporal_stability=stability,
        text_confidence=text,
        qr_confidence=qr,
    )


def test_region_pixel_conversion_is_bounded():
    region = OverlayRegion(0.9, 0.9, 0.1, 0.1)
    assert region.to_pixels(1920, 1080) == (1728, 972, 192, 108)


def test_detection_classifies_qr_when_qr_signal_dominates():
    item = evidence(
        OverlayRegion(0.75, 0.72, 0.15, 0.20),
        text=0.55,
        qr=0.94,
    )
    classified = item.classified_region()
    assert classified.kind == "qr"
    assert classified.confidence > 0.8


def test_low_temporal_evidence_does_not_pass_default_threshold():
    item = evidence(
        OverlayRegion(0.1, 0.1, 0.1, 0.05),
        persistence=0.15,
        stability=0.1,
        edges=1.0,
        text=1.0,
    )
    assert select_overlay_candidates([item]) == ()


def test_candidate_selection_deduplicates_overlapping_regions():
    first = evidence(OverlayRegion(0.1, 0.1, 0.20, 0.08), text=0.95)
    second = evidence(OverlayRegion(0.11, 0.105, 0.20, 0.08), text=0.85)
    selected = select_overlay_candidates([second, first])
    assert len(selected) == 1
    assert selected[0].confidence == first.score


def test_candidate_selection_rejects_dangerously_large_regions():
    item = evidence(OverlayRegion(0.05, 0.05, 0.7, 0.5), text=1.0)
    assert select_overlay_candidates([item]) == ()


def test_delogo_filters_expand_and_clamp_padding():
    regions = (
        OverlayRegion(0.0, 0.0, 0.1, 0.1, kind="logo", confidence=0.9),
        OverlayRegion(0.9, 0.9, 0.1, 0.1, kind="qr", confidence=0.9),
    )
    filters = build_delogo_filters(regions, frame_width=1000, frame_height=500, padding=10)
    assert filters == (
        "delogo=x=0:y=0:w=110:h=60:show=0",
        "delogo=x=890:y=440:w=110:h=60:show=0",
    )


def test_filtergraph_chains_multiple_regions():
    regions = (
        OverlayRegion(0.1, 0.1, 0.1, 0.1),
        OverlayRegion(0.4, 0.4, 0.1, 0.1),
    )
    graph = build_overlay_removal_filtergraph(
        regions,
        frame_width=1920,
        frame_height=1080,
        padding=0,
    )
    assert graph == (
        "delogo=x=192:y=108:w=192:h=108:show=0,"
        "delogo=x=768:y=432:w=192:h=108:show=0"
    )


def test_invalid_region_outside_frame_is_rejected():
    try:
        OverlayRegion(0.95, 0.2, 0.1, 0.1)
    except ValueError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("expected ValueError")
