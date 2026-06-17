import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    # Multiple API keys for rotation to avoid rate limits
    # Set GEMINI_API_KEYS as comma-separated keys in .env
    # Falls back to single GEMINI_API_KEY if not set
    @staticmethod
    def get_api_keys():
        keys_str = os.environ.get("GEMINI_API_KEYS", "")
        if keys_str:
            keys = [k.strip() for k in keys_str.split(",") if k.strip()]
            if keys:
                return keys
        # Fallback to single key
        single = os.environ.get("GEMINI_API_KEY", "")
        return [single] if single else []
    
    WHISPER_MODEL_NAME = "tiny.en"
    PIPER_VOICE_PATH = (
        "./en_US-lessac-low.onnx"
        if os.path.exists("./en_US-lessac-low.onnx")
        else "./en_US-lessac-medium.onnx"
    )
    MCP_SERVER_SCRIPT = "./mcp_server.py"
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
    RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "gotosarthaks@gmail.com")
    JOIN_API_KEY = os.environ.get("JOIN_API_KEY")
    JOIN_DEVICE_ID = os.environ.get("JOIN_DEVICE_ID")
    MONGODB_URI = os.environ.get("MONGODB_URI")
    BOT_SECRET_KEY = os.environ.get("BOT_SECRET_KEY")
