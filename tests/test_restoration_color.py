from __future__ import annotations

from cinepulse.restoration_color import (
    RestorationColorControls,
    build_restoration_color_filter,
    preset_controls,
)


def _assert_raises(error_type: type[BaseException], callback) -> None:
    try:
        callback()
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__} to be raised")


def test_neutral_controls_do_not_add_filter() -> None:
    assert build_restoration_color_filter(RestorationColorControls()) == ""


def test_faded_preset_adds_contrast_and_saturation() -> None:
    controls = preset_controls("faded")
    filtergraph = build_restoration_color_filter(controls)

    assert "eq=" in filtergraph
    assert "contrast=1.1" in filtergraph
    assert "saturation=1.12" in filtergraph


def test_temperature_uses_bounded_rgb_gains() -> None:
    filtergraph = build_restoration_color_filter(RestorationColorControls(temperature=0.2))

    assert "colorchannelmixer=" in filtergraph
    assert "rr=1.036" in filtergraph
    assert "gg=1" in filtergraph
    assert "bb=0.964" in filtergraph


def test_tint_changes_green_channel() -> None:
    filtergraph = build_restoration_color_filter(RestorationColorControls(tint=0.2))

    assert "rr=1.01" in filtergraph
    assert "gg=0.972" in filtergraph
    assert "bb=1.01" in filtergraph


def test_controls_reject_values_outside_restoration_envelope() -> None:
    _assert_raises(ValueError, lambda: RestorationColorControls(saturation=1.8))
    _assert_raises(ValueError, lambda: RestorationColorControls(temperature=-0.4))


def test_unknown_preset_is_rejected() -> None:
    _assert_raises(ValueError, lambda: preset_controls("cinematic"))  # type: ignore[arg-type]
