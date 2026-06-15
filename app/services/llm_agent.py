"""
LLM Agent Service (Streaming + Persistent MCP)
------------------------------------------------
Primary change from v1:
  - stream_gemini_with_mcp(): async generator that yields (sentence, is_last)
    tuples as Gemini produces tokens, chunked at sentence boundaries.
  - Uses the persistent MCP session from mcp_manager (no subprocess spawn).
  - GeminiKeyManager unchanged — full key rotation still works.
  - Old ask_gemini_with_mcp() removed (replaced by streaming variant).
"""

import asyncio
import time
import threading
import logging
from typing import AsyncGenerator, Tuple

from google import genai
from google.genai import types

from app.config import Config
from app.services.mcp_manager import get_mcp_session
from app.utils.db import get_user_profile
from app.utils.helpers import get_pruned_history
from app.utils.bot_knowledge import PROJECT_AND_USER_KNOWLEDGE

logger = logging.getLogger(__name__)

# ============================================================
# API Key Rotation System  (unchanged from v1)
# ============================================================

class GeminiKeyManager:
    """Manages multiple Gemini API keys with automatic rotation on rate limit."""

    MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

    def __init__(self):
        self.api_keys = Config.get_api_keys()
        self.current_key_index = 0
        self.clients: dict[str, genai.Client] = {}
        self.rate_limited_until: dict[str, float] = {}
        self.lock = threading.Lock()

        if not self.api_keys:
            raise ValueError(
                "No Gemini API keys configured! Set GEMINI_API_KEY or GEMINI_API_KEYS in .env"
            )

        logger.info("[KeyManager] Loaded %d API key(s)", len(self.api_keys))
        logger.info("[KeyManager] Models: %s", self.MODELS)
        self._get_client(self.api_keys[0])

    def _get_client(self, api_key: str) -> genai.Client:
        if api_key not in self.clients:
            self.clients[api_key] = genai.Client(api_key=api_key)
        return self.clients[api_key]

    def _is_rate_limited(self, key: str) -> bool:
        if key in self.rate_limited_until:
            if time.time() < self.rate_limited_until[key]:
                return True
            del self.rate_limited_until[key]
        return False

    def mark_rate_limited(self, key: str, cooldown_seconds: int = 65):
        with self.lock:
            self.rate_limited_until[key] = time.time() + cooldown_seconds
            logger.warning("[KeyManager] Key ...%s rate-limited for %ds", key[-6:], cooldown_seconds)

    def get_available_client_and_model(self) -> tuple[genai.Client, str, str]:
        with self.lock:
            for model in self.MODELS:
                for offset in range(len(self.api_keys)):
                    idx = (self.current_key_index + offset) % len(self.api_keys)
                    key = self.api_keys[idx]
                    if not self._is_rate_limited(key):
                        client = self._get_client(key)
                        self.current_key_index = (idx + 1) % len(self.api_keys)
                        logger.info("[KeyManager] Using key ...%s with model %s", key[-6:], model)
                        return client, key, model

            soonest = min(self.rate_limited_until, key=self.rate_limited_until.get)
            wait = self.rate_limited_until[soonest] - time.time()
            raise RuntimeError(
                f"All {len(self.api_keys)} API keys rate-limited. "
                f"Nearest recovery in {wait:.0f}s."
            )


def _is_rate_limit_error(e: Exception) -> bool:
    return any(c in str(e) for c in ["429", "RESOURCE_EXHAUSTED", "quota", "rate"])


def _is_overload_error(e: Exception) -> bool:
    return any(c in str(e) for c in ["503", "UNAVAILABLE", "overloaded"])


# Module-level singletons
logger.info("Loading Gemini Key Manager...")
key_manager = GeminiKeyManager()
sessions: dict[str, list] = {}
logger.info("Gemini Key Manager loaded.")


# ============================================================
# Sentence boundary characters — triggers immediate TTS chunk
# ============================================================
_SENTENCE_ENDS = frozenset(".?!,;:")
_MIN_CHUNK_LEN = 8  # don't send tiny fragments


# ============================================================
# Streaming LLM function
# ============================================================

async def stream_gemini_with_mcp(
    user_text: str,
    session_id: str,
) -> AsyncGenerator[Tuple[str, bool], None]:
    """
    Async generator — yields (sentence_chunk, is_last) tuples.

    The caller (ws_routes.py) feeds each chunk directly to TTS as it arrives,
    minimising the time between the user speaking and the bot's voice starting.

    Tool-call rounds (MCP) are handled before text streaming begins since
    Gemini needs full tool results before generating a final answer.
    """

    mcp_session, mcp_tools = await get_mcp_session()

    gemini_tools = [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.inputSchema,
        }
        for t in (mcp_tools or [])
    ]

    # --- System prompt ---
    profile = await asyncio.to_thread(get_user_profile)
    profile_text = ""
    if profile:
        profile_text = (
            f"\nUser Profile:\n"
            f"Name: {profile.get('full_name', '')}\n"
            f"Role: {profile.get('role', '')}\n"
            f"Signature: {profile.get('document_signature', '')}\n"
        )

    system_instruction = (
        "You are an Autonomous Productivity Agent and voice assistant.\n"
        f"{PROJECT_AND_USER_KNOWLEDGE}\n"
        "You can engage in general conversation, answer questions, and perform tasks "
        "like generating documents or sending text to the user's phone clipboard.\n"
        "When asked to write or create something:\n"
        "1. If you need background information, use the web_search tool first.\n"
        "2. If you need specific personal details, ASK clarifying questions.\n"
        "3. For short messages to be copied/sent, use sync_text_to_clipboard.\n"
        "4. For full documents, use generate_document (delivers via Telegram).\n"
        "5. For weather/local info without location, use get_location first.\n"
        f"{profile_text}"
        "Remember: your responses are spoken aloud! Keep replies EXTREMELY concise "
        "(1-2 short sentences). Never use bullet points unless explicitly asked.\n"
        "IMPORTANT: If the user says goodbye or you are wrapping up, you MUST include "
        "the exact keyword [END_CONVO] in your response."
    )

    history = sessions.get(session_id, [])

    # --- Key rotation loop ---
    max_attempts = len(key_manager.api_keys) * len(GeminiKeyManager.MODELS) + 1
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            client, api_key, model_name = key_manager.get_available_client_and_model()
        except RuntimeError as e:
            yield "I'm sorry, all my API keys are temporarily rate-limited. Please wait a minute and try again. [END_CONVO]", True
            return

        try:
            chat = await asyncio.to_thread(
                client.chats.create,
                model=model_name,
                history=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0,
                    tools=[{"function_declarations": gemini_tools}] if gemini_tools else None,
                )
            )

            # --- Initial message ---
            response = await asyncio.to_thread(chat.send_message, user_text)

            # --- Agentic tool loop (runs before streaming to client) ---
            while response.function_calls:
                tool_responses = []
                for tc in response.function_calls:
                    logger.info("[LLM] Tool call: %s(%s)", tc.name, tc.args)
                    try:
                        if mcp_session:
                            result = await mcp_session.call_tool(tc.name, tc.args)
                            result_text = result.content[0].text if result.content else "Executed."
                        else:
                            result_text = "Tool service unavailable."
                    except Exception as te:
                        logger.error("[LLM] Tool error: %s", te)
                        result_text = f"Error: {te}"

                    tool_responses.append(
                        types.Part.from_function_response(
                            name=tc.name,
                            response={"result": result_text},
                        )
                    )
                response = await asyncio.to_thread(chat.send_message, tool_responses)

            # --- Save history ---
            sessions[session_id] = get_pruned_history(chat.get_history())

            # --- Yield text as sentence chunks ---
            full_text = response.text or "I have completed the task."
            logger.info("[LLM] Response: '%s'", full_text[:80])

            sentence_buf = ""
            chars = list(full_text)
            for i, char in enumerate(chars):
                sentence_buf += char
                is_last_char = (i == len(chars) - 1)

                if (char in _SENTENCE_ENDS and len(sentence_buf.strip()) >= _MIN_CHUNK_LEN) \
                        or is_last_char:
                    chunk = sentence_buf.strip()
                    sentence_buf = ""
                    if chunk:
                        yield chunk, is_last_char
                        await asyncio.sleep(0)  # Yield event loop

            return  # Success

        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                logger.warning("[LLM] Rate limit on key ...%s: %s", api_key[-6:], e)
                key_manager.mark_rate_limited(api_key, cooldown_seconds=65)
                continue
            elif _is_overload_error(e):
                logger.warning("[LLM] Server overload: %s", e)
                await asyncio.sleep(2)
                continue
            else:
                logger.error("[LLM] Unexpected error: %s", e)
                yield f"Sorry, I encountered an error. Please try again. [END_CONVO]", True
                return

    # All attempts exhausted
    yield "I'm sorry, all my API keys are rate-limited. Please wait a minute. [END_CONVO]", True
