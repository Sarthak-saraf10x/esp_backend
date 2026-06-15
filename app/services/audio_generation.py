"""
Audio Generation Service (Streaming, No ffmpeg)
-------------------------------------------------
Synthesises text with Piper TTS and yields raw 16 kHz mono int16 PCM
chunks for direct WebSocket binary frame transmission.

Key changes from v1:
  - No ffmpeg subprocess call (replaced with pure-numpy linear resample)
  - No temp files written to disk
  - Async generator: yields CHUNK_BYTES-sized PCM frames as they are ready
  - Piper synthesis runs in a thread pool (asyncio.to_thread) so it does
    not block the FastAPI event loop
"""

import asyncio
import logging
import numpy as np
from typing import AsyncGenerator
import piper
from app.config import Config

logger = logging.getLogger(__name__)

# Size of each PCM chunk pushed over WebSocket (≈ 128 ms at 16 kHz mono int16)
CHUNK_BYTES = 4096

_voice: piper.PiperVoice | None = None


def get_piper_voice() -> piper.PiperVoice:
    global _voice
    if _voice is None:
        logger.info("[TTS] Loading Piper voice from %s ...", Config.PIPER_VOICE_PATH)
        _voice = piper.PiperVoice.load(Config.PIPER_VOICE_PATH)
        logger.info("[TTS] Piper voice loaded (native rate: %d Hz)",
                    getattr(_voice.config, 'sample_rate', 22050))
    return _voice


# ---------------------------------------------------------------------------
# Sync helpers (run inside asyncio.to_thread)
# ---------------------------------------------------------------------------

def _synth_to_pcm(text: str) -> tuple[bytes, int]:
    """
    Synthesise `text` synchronously with Piper.
    Returns (raw_int16_pcm_bytes, native_sample_rate).
    """
    voice = get_piper_voice()
    native_sr: int = getattr(voice.config, 'sample_rate', 22050)
    buf = bytearray()

    for chunk in voice.synthesize(text):
        data: bytes | None = None

        if hasattr(chunk, 'audio_int16_bytes') and chunk.audio_int16_bytes:
            data = chunk.audio_int16_bytes
        elif hasattr(chunk, '_audio_int16_bytes') and chunk._audio_int16_bytes:
            data = chunk._audio_int16_bytes
        elif hasattr(chunk, 'audio_int16_array') and chunk.audio_int16_array is not None:
            data = chunk.audio_int16_array.tobytes()
        elif hasattr(chunk, '_audio_int16_array') and chunk._audio_int16_array is not None:
            data = chunk._audio_int16_array.tobytes()
        elif hasattr(chunk, 'audio_float_array') and chunk.audio_float_array is not None:
            arr = (chunk.audio_float_array * 32767.0).astype(np.int16)
            data = arr.tobytes()

        if data:
            buf.extend(data)

    return bytes(buf), native_sr


def _resample_pcm(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """
    Linear resample int16 PCM from src_rate to dst_rate using numpy.
    Quality is good enough for TTS speech; use `samplerate` library for
    higher quality if needed (pip install samplerate).
    """
    if src_rate == dst_rate:
        return pcm

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    new_length = int(round(len(samples) * dst_rate / src_rate))
    old_indices = np.arange(len(samples))
    new_indices = np.linspace(0, len(samples) - 1, new_length)
    resampled = np.interp(new_indices, old_indices, samples)
    return resampled.astype(np.int16).tobytes()


def _generate_beep_pcm(sample_rate: int = 16000, duration: float = 0.3,
                        frequency: float = 880.0) -> bytes:
    """Fallback: a simple beep tone as raw PCM bytes."""
    import math
    n = int(sample_rate * duration)
    samples = [int(16000 * math.sin(2 * math.pi * frequency * i / sample_rate))
               for i in range(n)]
    return np.array(samples, dtype=np.int16).tobytes()


# ---------------------------------------------------------------------------
# Public async generator
# ---------------------------------------------------------------------------

async def stream_tts_chunks(text: str) -> AsyncGenerator[bytes, None]:
    """
    Async generator: synthesise `text`, resample to 16 kHz if needed,
    then yield CHUNK_BYTES-sized raw PCM frames for WebSocket transmission.

    Usage:
        async for chunk in stream_tts_chunks("Hello world"):
            await websocket.send_bytes(chunk)
    """
    if not text or not text.strip():
        return

    try:
        raw_pcm, native_sr = await asyncio.to_thread(_synth_to_pcm, text)

        if len(raw_pcm) <= 0:
            logger.warning("[TTS] Empty synthesis output for: '%s' — sending beep", text)
            raw_pcm = _generate_beep_pcm()
            native_sr = 16000

        # Resample to 16 kHz (ESP32 speaker rate)
        if native_sr != 16000:
            raw_pcm = await asyncio.to_thread(_resample_pcm, raw_pcm, native_sr, 16000)

        logger.info("[TTS] '%s' → %d bytes @ 16kHz", text[:40], len(raw_pcm))

        # Yield in fixed-size chunks to keep WebSocket frames small
        for offset in range(0, len(raw_pcm), CHUNK_BYTES):
            yield raw_pcm[offset:offset + CHUNK_BYTES]
            await asyncio.sleep(0)  # Yield event loop between frames

    except Exception as e:
        logger.error("[TTS] Error synthesising '%s': %s", text[:40], e)
        # Yield a beep so the ESP32 knows audio is coming
        beep = _generate_beep_pcm()
        for offset in range(0, len(beep), CHUNK_BYTES):
            yield beep[offset:offset + CHUNK_BYTES]
            await asyncio.sleep(0)
