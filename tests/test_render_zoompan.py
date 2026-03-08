"""
Tests for render task zoompan filter (cheap: no FFmpeg run, no API, no DB).
"""

import pytest

from app.utils.ffmpeg_filters import zoompan_vf as _zoompan_vf


def test_zoompan_vf_contains_base_scale_pad():
    vf = _zoompan_vf(5.0, None)
    assert "scale=1080:1920" in vf
    assert "pad=1080:1920" in vf
    assert "zoompan" in vf
    assert "fps=30" in vf


def test_zoompan_vf_default_animation_zoom_expr():
    vf = _zoompan_vf(5.0, None)
    # default zoom 1.0 -> 1.2 over ~150 frames
    assert "zoom" in vf
    assert "1.2" in vf


def test_zoompan_vf_custom_zoom_end():
    vf = _zoompan_vf(10.0, {"zoom_start": 1.0, "zoom_end": 1.5})
    assert "1.5" in vf


def test_zoompan_vf_static_motion():
    vf = _zoompan_vf(5.0, {"motion": "static", "zoom_start": 1.1})
    # static => zoom expression is just the start value (no increment)
    assert "1.1" in vf


def test_zoompan_vf_zero_duration_still_produces_filter():
    vf = _zoompan_vf(0.5, None)
    assert "zoompan" in vf and "1080x1920" in vf
