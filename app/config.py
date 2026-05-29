import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    WHISPER_MODEL_NAME = "base.en"
    PIPER_VOICE_PATH = "./en_US-lessac-medium.onnx"
    MCP_SERVER_SCRIPT = "./mcp_server.py"
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    JOIN_API_KEY = os.environ.get("JOIN_API_KEY")
    JOIN_DEVICE_ID = os.environ.get("JOIN_DEVICE_ID")
