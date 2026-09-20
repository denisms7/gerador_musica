import pytest

from musicgen.domain.models import (
    GenerationRequest,
    InferenceSpec,
    JobStatus,
    MusicalSpec,
)


def test_bpm_out_of_range_rejected():
    with pytest.raises(ValueError):
        MusicalSpec(bpm=500)


def test_duration_out_of_range_rejected():
    with pytest.raises(ValueError):
        MusicalSpec(duration_s=900)


def test_inference_bounds():
    with pytest.raises(ValueError):
        InferenceSpec(steps=0)
    with pytest.raises(ValueError):
        InferenceSpec(batch_size=99)


def test_empty_lyrics_rejected_unless_instrumental():
    with pytest.raises(ValueError):
        GenerationRequest(lyrics="   ")
    assert GenerationRequest(lyrics="", instrumental=True)


def test_terminal_status():
    assert JobStatus.SUCCEEDED.terminal
    assert not JobStatus.RUNNING.terminal
