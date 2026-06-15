"""
Transcription Service (Streaming-Compatible)
---------------------------------------------
Accepts raw 16 kHz mono int16 PCM bytes directly from the WebSocket
accumulation buffer. Converts to float32 numpy array and passes to
faster-whisper — no temp file written to disk.
"""

import numpy as np
import logging
from faster_whisper import WhisperModel
from app.config import Config

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None


def get_whisper_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("[STT] Loading Whisper model '%s'...", Config.WHISPER_MODEL_NAME)
        _model = WhisperModel(
            Config.WHISPER_MODEL_NAME,
            device="cpu",
            compute_type="int8"
        )
        logger.info("[STT] Whisper model loaded.")
    return _model


def transcribe_pcm_buffer(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Transcribe raw PCM audio received over WebSocket.

    Args:
        pcm_bytes: Raw 16-bit little-endian mono PCM at `sample_rate` Hz.
        sample_rate: Sample rate of the incoming audio (ESP32 sends 16000 Hz).

    Returns:
        Transcribed text string (empty string if nothing detected).
    """
    if len(pcm_bytes) < 3200:  # less than 100ms — skip noise
        return ""

    # Convert int16 PCM → float32 normalised to [-1.0, 1.0]
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # faster-whisper accepts float32 numpy arrays at 16 kHz directly
    model = get_whisper_model()
    segments, info = model.transcribe(audio, language="en")
    text = " ".join(seg.text for seg in segments).strip()

    logger.info("[STT] Transcribed %d bytes → '%s'", len(pcm_bytes), text)
    return text
