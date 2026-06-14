import os
import asyncio
import time
import threading
from google import genai
from google.genai import types
import sys
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from app.config import Config
from app.utils.helpers import get_pruned_history

from app.utils.db import get_user_profile

# ============================================================
# API Key Rotation System
# Rotates through multiple free Gemini API keys to avoid
# hitting the per-key rate limit during viva/demo sessions.
# ============================================================

class GeminiKeyManager:
    """Manages multiple Gemini API keys with automatic rotation on rate limit."""
    
    # Models to try in order of preference:
    # gemini-2.0-flash has 15 RPM free tier (higher than 2.5-flash's ~10 RPM)
    MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]
    
    def __init__(self):
        self.api_keys = Config.get_api_keys()
        self.current_key_index = 0
        self.current_model_index = 0
        self.clients = {}  # key -> genai.Client
        self.rate_limited_until = {}  # key -> timestamp when rate limit expires
        self.lock = threading.Lock()
        
        if not self.api_keys:
            raise ValueError("No Gemini API keys configured! Set GEMINI_API_KEY or GEMINI_API_KEYS in .env")
        
        print(f"[KeyManager] Loaded {len(self.api_keys)} API key(s)")
        print(f"[KeyManager] Models: {self.MODELS}")
        
        # Pre-create a client for the first key
        self._get_client(self.api_keys[0])
    
    def _get_client(self, api_key):
        """Get or create a genai.Client for a given API key."""
        if api_key not in self.clients:
            self.clients[api_key] = genai.Client(api_key=api_key)
        return self.clients[api_key]
    
    def _is_rate_limited(self, key):
        """Check if a key is currently rate-limited."""
        if key in self.rate_limited_until:
            if time.time() < self.rate_limited_until[key]:
                return True
            else:
                # Rate limit expired, remove it
                del self.rate_limited_until[key]
        return False
    
    def mark_rate_limited(self, key, cooldown_seconds=65):
        """Mark a key as rate-limited for a given cooldown period."""
        with self.lock:
            self.rate_limited_until[key] = time.time() + cooldown_seconds
            print(f"[KeyManager] Key ...{key[-6:]} rate-limited for {cooldown_seconds}s")
    
    def get_available_client_and_model(self):
        """
        Get the next available client + model combination.
        Tries all keys with preferred model first, then falls back to alternate models.
        Returns: (client, api_key, model_name) or raises if all exhausted.
        """
        with self.lock:
            # Try each model
            for model_idx, model in enumerate(self.MODELS):
                # Try each key
                for offset in range(len(self.api_keys)):
                    idx = (self.current_key_index + offset) % len(self.api_keys)
                    key = self.api_keys[idx]
                    
                    if not self._is_rate_limited(key):
                        client = self._get_client(key)
                        # Update current index so next call starts from the next key
                        self.current_key_index = (idx + 1) % len(self.api_keys)
                        print(f"[KeyManager] Using key ...{key[-6:]} with model {model}")
                        return client, key, model
            
            # All keys are rate-limited, find the one that expires soonest
            soonest_key = min(self.rate_limited_until, key=self.rate_limited_until.get)
            wait_time = self.rate_limited_until[soonest_key] - time.time()
            raise Exception(
                f"All {len(self.api_keys)} API keys are rate-limited. "
                f"Nearest recovery in {wait_time:.0f}s. "
                f"Add more keys to GEMINI_API_KEYS in .env to avoid this."
            )


print("Loading Gemini Key Manager...")
key_manager = GeminiKeyManager()
# Keep backward compatibility
gemini_client = key_manager._get_client(key_manager.api_keys[0])
print("Gemini Key Manager loaded.")

sessions = {}


def _is_rate_limit_error(e):
    """Check if an exception is a rate limit error."""
    err_str = str(e)
    return any(code in err_str for code in ["429", "RESOURCE_EXHAUSTED", "quota", "rate"])


def _is_overload_error(e):
    """Check if an exception is a server overload error."""
    err_str = str(e)
    return any(code in err_str for code in ["503", "UNAVAILABLE", "overloaded"])
async def ask_gemini_with_mcp(user_text, session_id):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[Config.MCP_SERVER_SCRIPT],
        env=os.environ.copy()
    )
    
    history = sessions.get(session_id, [])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            mcp_tools = await session.list_tools()
            
            gemini_tools = []
            for t in mcp_tools.tools:
                gemini_tools.append({
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema
                })
            
            # Fetch user profile
            profile = get_user_profile()
            profile_text = ""
            if profile:
                profile_text = f"\nUser Profile:\nName: {profile.get('full_name', '')}\nRole: {profile.get('role', '')}\nSignature: {profile.get('document_signature', '')}\n"

            system_instruction = (
                "You are an Autonomous Productivity Agent and voice assistant. You can engage in general conversation, "
                "answer questions, and perform complex tasks like generating documents (reports, emails, etc.) or sending texts to the user's phone clipboard.\n"
                "When asked to write or create something:\n"
                "1. If you need background information, use the web_search tool to gather facts first.\n"
                "2. If you need specific personal details or scope from the user, ASK clarifying questions (interview the user) before generating.\n"
                "3. If the user asks for a short message, draft, or text to be copied/sent to their phone (e.g. 'Draft a short text saying I will be 10 minutes late and copy it'), use the sync_text_to_clipboard tool. Do NOT create a full document for short messages.\n"
                "4. If the user asks for a full document, report, or formal file, use the generate_document tool to create a .docx or .pdf file. The system will automatically deliver it to their phone via Telegram.\n"
                "5. If the user asks for weather, restaurants, or local information without specifying a location, use the get_location tool to find their current location first.\n"
                f"{profile_text}"
                "Remember your responses will be spoken aloud! To minimize processing delay, keep your conversational replies EXTREMELY concise (1-2 short sentences maximum). Never use bullet points or long paragraphs unless explicitly asked.\n"
                "IMPORTANT: If the user says goodbye, or if you are wrapping up the conversation naturally, "
                "you MUST include the exact keyword [END_CONVO] in your response."
            )
            
            print(f"Sending query to Gemini with {len(gemini_tools)} tools...")
            
            # ============================================================
            # Try with key rotation: if current key is rate-limited, 
            # automatically rotate to the next available key + model
            # ============================================================
            last_error = None
            max_attempts = len(key_manager.api_keys) * len(GeminiKeyManager.MODELS) + 1
            
            for attempt in range(max_attempts):
                try:
                    client, api_key, model_name = key_manager.get_available_client_and_model()
                except Exception as e:
                    # All keys exhausted
                    return "I'm sorry, all my API keys are temporarily rate-limited. Please wait about a minute and try again. [END_CONVO]"
                
                try:
                    chat = client.chats.create(
                        model=model_name,
                        history=history,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0,
                            tools=[{"function_declarations": gemini_tools}] if gemini_tools else None
                        )
                    )
                    
                    # Helper function for sending message with retries on transient errors
                    def send_with_retry(content, max_retries=2):
                        for retry in range(max_retries):
                            try:
                                return chat.send_message(content)
                            except Exception as e:
                                if retry == max_retries - 1:
                                    raise e
                                if _is_rate_limit_error(e) or _is_overload_error(e):
                                    time.sleep(2)
                                else:
                                    raise e

                    response = send_with_retry(user_text)
                    
                    while response.function_calls:
                        tool_responses = []
                        for tool_call in response.function_calls:
                            print(f"Gemini requested tool: {tool_call.name} with args: {tool_call.args}")
                            try:
                                result = await session.call_tool(
                                    tool_call.name,
                                    tool_call.args
                                )
                                result_text = result.content[0].text if result.content else "Executed successfully."
                                print(f"Tool returned: {result_text}")
                            except Exception as e:
                                print(f"Tool error: {e}")
                                result_text = f"Error: {e}"
                                
                            tool_responses.append(types.Part.from_function_response(
                                name=tool_call.name,
                                response={"result": result_text}
                            ))
                        
                        print("Getting next response...")
                        response = send_with_retry(tool_responses)
                    
                    sessions[session_id] = get_pruned_history(chat.get_history())
                    if response.text:
                        return response.text
                    return "I have completed the task."
                
                except Exception as e:
                    last_error = e
                    if _is_rate_limit_error(e):
                        print(f"[KeyManager] Rate limit hit on key ...{api_key[-6:]} model {model_name}: {e}")
                        key_manager.mark_rate_limited(api_key, cooldown_seconds=65)
                        continue  # Try next key/model
                    elif _is_overload_error(e):
                        print(f"[KeyManager] Server overload on model {model_name}: {e}")
                        time.sleep(2)
                        continue  # Try next key/model
                    else:
                        raise e
            
            # If we get here, all attempts failed
            if last_error and (_is_rate_limit_error(last_error) or _is_overload_error(last_error)):
                return "I'm sorry, all my API keys are temporarily rate-limited. Please wait about a minute and try again. [END_CONVO]"
            raise last_error
