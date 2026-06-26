# Bot and Project Knowledge Base

PROJECT_AND_USER_KNOWLEDGE = """
=== BOT & USER KNOWLEDGE (RAG CONTEXT) ===
Bot Identity:
- Name: ESP32-S3 AI Desktop Bot
- Primary Role: Voice Assistant and Autonomous Productivity Agent.
- Creator / Developer: Sarthak Rajesh Saraf (Master of Computer Application, Semester-IV, Academic Year 2025-2026).
- Institution: Alard Institute of Management and Sciences, Pune.
- Affiliation: Savitribai Phule Pune University.
- Project Guide: Prof. Ashwini Khedkar.
- Project Title: ESP32-S3 AI Desktop Bot (Research Project / Capstone Project).

Hardware Architecture:
- Microcontroller: ESP32-S3-DevKitC-1-N16R8 (Dual-Core Xtensa LX7 @ 240MHz, 16MB Flash, 8MB Octal PSRAM).
- Microphone (Input): INMP441 digital I2S microphone (captures 16kHz mono 16-bit PCM).
- Speaker/Amplifier (Output): MAX98357A Class D digital I2S amplifier driving a 3W-5W speaker.
- Display: 128x64 SSD1306 OLED via I2C (renders animated eyes/facial expressions based on status).
- Communication: Bidirectional full-duplex WebSockets.

Software/AI Stack:
- Edge Firmware: C++ / FreeRTOS (Core 0 handles WebSocket I/O & ring-buffering; Core 1 handles U8g2 OLED and I2S playback).
- Backend Framework: FastAPI (Python 3.9+).
- Speech-to-Text (STT): Faster-Whisper (CTranslate2 running in-memory).
- Brain / LLM: Google Gemini (2.5-flash / 2.0-flash) with tool-calling capabilities.
- Text-to-Speech (TTS): Piper TTS (ONNX runtime) with NumPy-based linear resampling (22.05kHz to 16kHz).
- Database: MongoDB (for persistent session history tracking).

Your Registered Capabilities & Tools:
1. Conversation: General Q&A, reasoning, and context retention across turns.
2. Web Search (`web_search`): Search Wikipedia, DuckDuckGo, and OpenStreetMap for real-time information.
3. Weather (`get_weather`): Fetch temperature and wind speed via Open-Meteo geocoding.
4. User Location (`get_location`): Geolocate server IP address.
5. Push to Clipboard (`sync_text_to_clipboard`): Push text directly to Sarthak's phone clipboard using Join API.
6. Generate Document (`generate_document`): Create structured Word (.docx) or PDF files and deliver them to Sarthak's Gmail (gotosarthaks@gmail.com).
=========================================


=== OWNER/CREATOR PROFILE ===
Name: Sarthak Rajesh Saraf
Role: Student (MCA, 1st Year, 2025-26)
Area of Interest: Artificial Intelligence, Machine Learning, AI/IoT.
Email: gotosarthaks@gmail.com
Mobile No: +91 9373287144

== Bot Woking ==
Detailed Step-by-Step Pipeline

### 1. Connection & Session Handshake
*   **Endpoint:** `/ws/conversation` (defined in `app/routes/ws_routes.py`).
*   **Authentication:** The client opens a WebSocket connection and passes a custom header `x-bot-secret-key`. The server verifies it against the configured key.
*   **Session Management:** An in-memory session identifier (`session_id`) tracks conversation state and history in MongoDB to maintain memory across turns.

### 2. Audio Ingestion (ESP32 → Backend)
*   The ESP32 continuously samples the microphone and streams raw **16 kHz, mono, 16-bit PCM** binary chunks (1024 bytes / 32 ms each) over the WebSocket connection.
*   The backend's async receive loop reads these binary frames and appends them to an in-memory `pcm_buffer` byte array.

### 3. Silence Detection & Speech Ingestion
*   When the ESP32 detects silence (no voice activity for a configured timeout), it halts the audio stream and transmits a JSON control frame:
    ```json
    {"event": "speech_done"}
    ```
*   Upon receipt of `speech_done`, the backend:
    1. Extracts the raw PCM bytes from the accumulated buffer and clears the buffer.
    2. Runs **Faster-Whisper** (`tiny.en`) in a separate CPU thread to perform transcription.
    3. Sends the transcribed text back to the ESP32 in a JSON frame: `{"event": "transcript", "text": "..."}`.

### 4. Agentic LLM Loop (Gemini + Persistent MCP)
*   The transcript is passed to the LLM agent (`app/services/llm_agent.py`).
*   **Agentic Search/RAG:**
    1. If the prompt requires real-time data, Gemini utilizes tools registered in the **persistent MCP server** (e.g., `web_search`, `get_weather`).
    2. Instead of spawning slow Python subprocesses, tool calls are routed directly to the active, background-running MCP session, keeping latencies under ~300ms.
    3. The tool's output is fed back to the LLM to complete the query.
*   **Sentence Splitting:** To stream audio as quickly as possible, the generator yields text chunks and splits them into individual sentences at punctuation boundaries (`.`, `?`, `!`, `,`, `;`, `:`).

### 5. On-the-fly Text-to-Speech (TTS)
*   As each sentence becomes available, it is forwarded to the **Piper TTS engine** (`app/services/audio_generation.py`).
*   Piper synthesizes the text to PCM audio at **22050 Hz**.
*   **NumPy Linear Resampling:** The backend uses pure-NumPy linear interpolation (`np.interp`) to resample the audio to **16000 Hz** in-memory.
*   The resampled PCM bytes are split into 4 KB chunks and immediately written to the WebSocket as binary packets.

### 6. Playback Completion
*   The ESP32 receives the binary frames and places them into a **1 MB PSRAM ring buffer**. The background core plays these chunks to the I2S speaker.
*   Once the LLM generator finishes yielding all chunks, the server sends:
    ```json
    {"event": "audio_done", "end_conversation": false}
    ```
*   The ESP32 continues playing the buffered audio to completion, then switches back to the listening state.

=== MCP TOOLS ===
@mcp_tool
def web_search(query: str) -> str:

Performs a web search using DuckDuckGo and returns the top 5 results.
Returns plain text, prioritizing titles and URLs.


@mcp_tool
def get_weather(location: str, units: str = "celsius") -> str:

Fetches current weather for a location using Open-Meteo.

Args:
  location: City name or zip code (e.g., "Pune", "New York").
            The backend will attempt to geocode it.
  units: "celsius" or "fahrenheit".


@mcp_tool
def sync_text_to_clipboard(text: str) -> str:

Sends text directly to the user's Android clipboard using the Join API.


@mcp_tool
def generate_document(content: str) -> str:

Generates a Word document (.docx) or PDF from provided text.
Detailed Step-by-Step Pipeline

### 1. Connection & Session Handshake
*   **Endpoint:** `/ws/conversation` (defined in `app/routes/ws_routes.py`).
*   **Authentication:** The client opens a WebSocket connection and passes a custom header `x-bot-secret-key`. The server verifies it against the configured key.
*   **Session Management:** An in-memory session identifier (`session_id`) tracks conversation state and history in MongoDB to maintain memory across turns.

### 2. Audio Ingestion (ESP32 → Backend)
*   The ESP32 continuously samples the microphone and streams raw **16 kHz, mono, 16-bit PCM** binary chunks (1024 bytes / 32 ms each) over the WebSocket connection.
*   The backend's async receive loop reads these binary frames and appends them to an in-memory `pcm_buffer` byte array.

### 3. Silence Detection & Speech Ingestion
*   When the ESP32 detects silence (no voice activity for a configured timeout), it halts the audio stream and transmits a JSON control frame:
    ```json
    {"event": "speech_done"}
    ```
*   Upon receipt of `speech_done`, the backend:
    1. Extracts the raw PCM bytes from the accumulated buffer and clears the buffer.
    2. Runs **Faster-Whisper** (`tiny.en`) in a separate CPU thread to perform transcription.
    3. Sends the transcribed text back to the ESP32 in a JSON frame: `{"event": "transcript", "text": "..."}`.

### 4. Agentic LLM Loop (Gemini + Persistent MCP)
*   The transcript is passed to the LLM agent (`app/services/llm_agent.py`).
*   **Agentic Search/RAG:**
    1. If the prompt requires real-time data, Gemini utilizes tools registered in the **persistent MCP server** (e.g., `web_search`, `get_weather`).
    2. Instead of spawning slow Python subprocesses, tool calls are routed directly to the active, background-running MCP session, keeping latencies under ~300ms.
    3. The tool's output is fed back to the LLM to complete the query.
*   **Sentence Splitting:** To stream audio as quickly as possible, the generator yields text chunks and splits them into individual sentences at punctuation boundaries (`.`, `?`, `!`, `,`, `;`, `:`).

### 5. On-the-fly Text-to-Speech (TTS)
*   As each sentence becomes available, it is forwarded to the **Piper TTS engine** (`app/services/audio_generation.py`).
*   Piper synthesizes the text to PCM audio at **22050 Hz**.
*   **NumPy Linear Resampling:** The backend uses pure-NumPy linear interpolation (`np.interp`) to resample the audio to **16000 Hz** in-memory.
*   The resampled PCM bytes are split into 4 KB chunks and immediately written to the WebSocket as binary packets.

### 6. Playback Completion
*   The ESP32 receives the binary frames and places them into a **1 MB PSRAM ring buffer**. The background core plays these chunks to the I2S speaker.
*   Once the LLM generator finishes yielding all chunks, the server sends:
    ```json
    {"event": "audio_done", "end_conversation": false}
    ```
*   The ESP32 continues playing the buffered audio to completion, then switches back to the listening state.



"""