"""
WebSocket Conversation Route
-----------------------------
Single WebSocket endpoint replaces the old /audio_stream HTTP route.

Protocol (ESP32 ↔ Backend):
  ESP32 → server:  binary frames = raw 16 kHz mono int16 PCM chunks
  ESP32 → server:  text frame   = JSON control event
  server → ESP32:  binary frames = raw 16 kHz mono int16 PCM audio chunks
  server → ESP32:  text frame   = JSON status/control event

Control events (ESP32 → server):
  {"event": "speech_done"}         — user finished speaking, transcribe + respond
  {"event": "end_conversation"}    — client-initiated conversation close

Control events (server → ESP32):
  {"event": "transcript", "text": "..."}           — STT result (for display)
  {"event": "no_speech"}                           — nothing heard
  {"event": "error", "message": "..."}             — server error
  {"event": "audio_done", "end_conversation": bool} — all audio chunks sent
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.config import Config
from app.services.transcription import transcribe_pcm_buffer
from app.services.llm_agent import stream_gemini_with_mcp
from app.services.audio_generation import stream_tts_chunks

logger = logging.getLogger(__name__)
router = APIRouter()


async def _send_json(ws: WebSocket, data: dict):
    try:
        await ws.send_text(json.dumps(data))
    except Exception:
        pass  # Connection may already be closing


@router.websocket("/ws/conversation")
async def conversation_ws(websocket: WebSocket):
    # --- Auth (check header before accepting) ---
    secret = websocket.headers.get("x-bot-secret-key", "")
    if secret != Config.BOT_SECRET_KEY:
        logger.warning("[WS] Unauthorized connection attempt")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    session_id = websocket.headers.get("x-session-id", "default")

    await websocket.accept()
    logger.info("[WS] Client connected — session: %s", session_id)

    pcm_buffer = bytearray()

    try:
        while True:
            message = await websocket.receive()

            # ── Binary frame: raw PCM chunk from ESP32 mic ──────────────
            if message.get("bytes"):
                pcm_buffer.extend(message["bytes"])

            # ── Text frame: JSON control event ───────────────────────────
            elif message.get("text"):
                try:
                    event = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("[WS] Invalid JSON: %s", message["text"][:80])
                    continue

                ev_type = event.get("event", "")
                logger.info("[WS] Event received: %s (pcm buffer: %d bytes)",
                            ev_type, len(pcm_buffer))

                # ── Client-initiated close ──────────────────────────────
                if ev_type == "end_conversation":
                    logger.info("[WS] Client ended conversation")
                    break

                # ── User finished speaking ──────────────────────────────
                if ev_type == "speech_done":
                    captured = bytes(pcm_buffer)
                    pcm_buffer.clear()

                    # STT — runs in thread pool (CPU-bound Whisper)
                    user_text = await asyncio.to_thread(
                        transcribe_pcm_buffer, captured
                    )

                    if not user_text:
                        logger.info("[WS] No speech detected")
                        await _send_json(websocket, {"event": "no_speech"})
                        continue

                    logger.info("[WS] Transcript: '%s'", user_text)
                    await _send_json(websocket, {
                        "event": "transcript",
                        "text": user_text,
                    })

                    # LLM → sentence chunks → TTS → WS binary frames
                    end_convo = False
                    try:
                        async for sentence, is_last in stream_gemini_with_mcp(
                            user_text, session_id
                        ):
                            if "[END_CONVO]" in sentence:
                                sentence = sentence.replace("[END_CONVO]", "").strip()
                                end_convo = True

                            if not sentence:
                                continue

                            logger.info("[WS] TTS sentence: '%s'", sentence[:60])

                            # Stream TTS chunks for this sentence
                            async for pcm_chunk in stream_tts_chunks(sentence):
                                await websocket.send_bytes(pcm_chunk)

                    except Exception as e:
                        logger.error("[WS] LLM/TTS pipeline error: %s", e)
                        await _send_json(websocket, {
                            "event": "error",
                            "message": "Internal pipeline error. Please try again.",
                        })
                        continue

                    # Signal end of audio stream
                    await _send_json(websocket, {
                        "event": "audio_done",
                        "end_conversation": end_convo,
                    })

                    if end_convo:
                        break

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected — session: %s", session_id)
    except Exception as e:
        logger.error("[WS] Unhandled error in session %s: %s", session_id, e)
    finally:
        pcm_buffer.clear()
        logger.info("[WS] Session %s closed", session_id)
