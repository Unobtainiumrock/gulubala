"""Audio ingestion pipeline — ported from hackathon audio_utils.py.

6-step chunking approach:
1. Load audio file
2. Resample to 16kHz
3. Silero VAD to detect speech segments
4. Fill gaps for full audio coverage
5. Split segments exceeding 4 seconds
6. Encode chunks as base64 WAV strings

DO NOT modify the VAD/chunking logic — these parameters are non-negotiable per hackathon spec.
"""

import io
import base64
import numpy as np
import soundfile as sf
import torch
import torchaudio

from config.models import SAMPLE_RATE, MAX_CHUNK_SECONDS


def _load_and_resample(path: str) -> np.ndarray:
    """Load an audio file and resample to target sample rate."""
    waveform, sr = torchaudio.load(path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != SAMPLE_RATE:
        resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=SAMPLE_RATE)
        waveform = resampler(waveform)
    return waveform.squeeze().numpy()


def _get_vad_model():
    """Load Silero VAD model."""
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True
    )
    return model, utils


def _detect_speech_segments(audio: np.ndarray, vad_model, get_speech_timestamps) -> list:
    """Run VAD and return speech timestamp segments."""
    tensor = torch.from_numpy(audio).float()
    timestamps = get_speech_timestamps(tensor, vad_model, sampling_rate=SAMPLE_RATE)
    return timestamps


def _fill_gaps(segments: list, total_samples: int) -> list:
    """Fill gaps between segments so entire audio is covered."""
    if not segments:
        return [{"start": 0, "end": total_samples}]

    filled = []
    prev_end = 0
    for seg in segments:
        if seg["start"] > prev_end:
            filled.append({"start": prev_end, "end": seg["start"]})
        filled.append(seg)
        prev_end = seg["end"]
    if prev_end < total_samples:
        filled.append({"start": prev_end, "end": total_samples})
    return filled


def _split_long_segments(segments: list, max_samples: int) -> list:
    """Split segments that exceed max duration."""
    result = []
    for seg in segments:
        start, end = seg["start"], seg["end"]
        while end - start > max_samples:
            result.append({"start": start, "end": start + max_samples})
            start += max_samples
        if start < end:
            result.append({"start": start, "end": end})
    return result


def _encode_chunk(audio: np.ndarray, start: int, end: int) -> str:
    """Encode an audio segment as a base64 WAV string."""
    chunk = audio[start:end]
    buf = io.BytesIO()
    sf.write(buf, chunk, SAMPLE_RATE, format="WAV")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def chunk_audio_file(path: str) -> list[str]:
    """Process an audio file through the full chunking pipeline.

    Returns a list of base64-encoded WAV strings ready for the API.
    """
    audio = _load_and_resample(path)
    vad_model, utils = _get_vad_model()
    get_speech_timestamps = utils[0]

    segments = _detect_speech_segments(audio, vad_model, get_speech_timestamps)
    segments = _fill_gaps(segments, len(audio))

    max_samples = MAX_CHUNK_SECONDS * SAMPLE_RATE
    segments = _split_long_segments(segments, max_samples)

    chunks = [_encode_chunk(audio, seg["start"], seg["end"]) for seg in segments]
    return chunks
