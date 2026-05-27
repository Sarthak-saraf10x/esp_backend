import os

class Config:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyBbxn4Y5xzS9RgNSV6FtTjjl63wJopMMSs")
    WHISPER_MODEL_NAME = "base.en"
    PIPER_VOICE_PATH = "./en_US-lessac-medium.onnx"
    MCP_SERVER_SCRIPT = "./mcp_server.py"
