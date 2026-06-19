---
title: ESP Desktop Bot
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# ESP32-S3 AI Desktop Bot — Backend Service

[![Project Status: Active](https://img.shields.io/badge/Project%20Status-Active-brightgreen.svg)](#)
[![Python Version](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](#)
[![FastAPI Framework](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](#)
[![Academic Project](https://img.shields.io/badge/Academic%20Project-MCA%20Final%20Year-orange.svg)](#)

This repository contains the backend service for the **ESP32-S3 AI Desktop Bot**, an interactive, low-latency, voice-to-voice conversational artificial intelligence assistant and autonomous productivity agent. The backend leverages an asynchronous streaming pipeline to ingest audio, perform speech recognition, invoke cloud reasoning, interact with system tools using the Model Context Protocol (MCP), and synthesize real-time voice responses.

---

> [!IMPORTANT]
> ### 🎓 Academic Context
> This project has been developed and submitted as a **Final Year Capstone Project** in partial fulfillment of the requirements for the degree of **Master of Computer Applications (MCA)**.
> *   **Academic Year:** 2025 - 2026 (Semester IV)
> *   **Developer/Creator:** Sarthak Rajesh Saraf
> *   **Institution:** Alard Institute of Management and Sciences, Pune, Maharashtra, India
> *   **Affiliation:** Savitribai Phule Pune University (SPPU)
> *   **Project Guide:** Prof. Ashwini Khedkar
> *   **Project Title:** ESP32-S3 AI Desktop Bot (Research & Embedded AI Project)
> *   **Focus Areas:** Edge AI, IoT-Cloud Integration, Natural Language Processing, Model Context Protocol (MCP)

---

## 1. System Architecture & End-to-End Workflow

The system is split into two primary segments:
1. **Edge Node (Client):** An ESP32-S3 microcontroller executing a dual-core FreeRTOS C++ application. It manages microphone capture, local Wake-Word detection, OLED animation rendering, and DAC speaker output.
2. **Brain Node (Server):** A FastAPI-based Python backend that coordinates local speech-to-text (STT), Gemini LLM reasoning, background Model Context Protocol (MCP) tools, and local text-to-speech (TTS) engines.

### End-to-End Sequence Diagram

The diagram below maps the bidirectional communication cycle over WebSockets:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant ESP_C0 as [ESP32 Core 0: Control & WS]
    participant ESP_C1 as [ESP32 Core 1: Playback]
    participant PSRAM as [ESP32 PSRAM Ring Buffer]
    participant BE as [FastAPI Backend Server]
    participant Gemini as [Google Gemini LLM Agent]
    participant MCP as [Persistent MCP Tools]
    participant TTS as [Piper TTS + Resampler]

    %% Phase 1: Wake & Start
    Note over User, ESP_C0: Phase 1: Activation
    ESP_C0->>ESP_C0: WakeNet detects local wake word "Hi ESP"
    ESP_C0->>ESP_C1: Play greeting chime
    ESP_C0->>ESP_C0: Pause wake-word engine (sr_pause)
    ESP_C0->>BE: Establish WebSocket to `/ws/conversation` with Auth headers

    %% Phase 2: Recording & Streaming
    Note over User, BE: Phase 2: Audio Ingestion
    loop While User is Speaking (Max 15 seconds)
        ESP_C0->>ESP_C0: Read 1024-byte raw PCM chunk from I2S Mic (16kHz)
        ESP_C0->>BE: Stream binary audio frame over WebSocket
        BE->>BE: Accumulate bytes in memory `pcm_buffer`
        ESP_C0->>ESP_C0: Run local VAD: measure peak amplitude
    end
    Note over ESP_C0: User stops speaking for 1.0 second (silence timer)
    ESP_C0->>BE: Send {"event": "speech_done"} control frame
    ESP_C0->>ESP_C0: Play local confirmation beep & show "Thinking" face

    %% Phase 3: Backend Processing & LLM Tool Loop
    Note over BE, Gemini: Phase 3: AI Inference & Tool Loop
    BE->>BE: Transcribe `pcm_buffer` using Whisper (tiny.en)
    BE->>ESP_C0: Send {"event": "transcript", "text": "..."}
    BE->>Gemini: Pass text query + chat history (SDK: google-genai)
    
    opt When Gemini decides tools are needed (e.g., Clipboard, Web Search, Weather)
        Gemini->>BE: Request tool call (function_calls)
        BE->>MCP: Execute tool on persistent MCP Session
        MCP-->>BE: Return tool output
        BE->>Gemini: Feed tool result back to LLM
    end
    
    Gemini->>BE: Stream output tokens

    %% Phase 4: TTS & Playback
    Note over BE, ESP_C1: Phase 4: Output Synthesis & Playback
    loop Stream Response Sentences
        BE->>BE: Group tokens into sentences (split on `.?!,;:`)
        BE->>TTS: Synthesize sentence using Piper (22.05kHz PCM)
        TTS->>TTS: Resample to 16kHz using NumPy interpolation
        TTS->>BE: Return 16kHz mono PCM chunks
        BE->>ESP_C0: Stream binary audio chunks over WebSocket
        ESP_C0->>PSRAM: Buffer chunks into 1 MB ring buffer (ringWrite)
        
        Note over ESP_C0: When buffer has >=16KB (pre-buffer) or stream done:
        ESP_C0->>ESP_C1: Spawn audioPlaybackTask
        loop Playback
            ESP_C1->>PSRAM: Read PCM bytes (ringRead)
            ESP_C1->>ESP_C1: Apply 3.5x Volume Boost & Clip limits
            ESP_C1->>ESP_C1: Output to I2S Speaker (MAX98357A)
        end
    end

    BE->>ESP_C0: Send {"event": "audio_done", "end_conversation": bool}
    ESP_C1->>ESP_C1: Playback ends, terminate audioPlaybackTask
    ESP_C0->>ESP_C0: Resume local wake-word engine (sr_resume)
```

---

## 2. Hardware Stack (The Edge Assistant)

The desktop bot's hardware is designed for robust offline wake-word processing and responsive I2S audio interfaces:

*   **Microcontroller:** ESP32-S3-DevKitC-1-N16R8 (Xtensa 32-bit LX7 dual-core processor @ 240MHz, 16MB Quad SPI Flash, 8MB Octal SPI PSRAM).
*   **Audio Input (Mic):** INMP441 digital MEMS microphone connected via I2S, capturing raw 16kHz, mono, 16-bit signed PCM audio.
*   **Audio Output (Speaker):** MAX98357A Class-D digital I2S amplifier connected to a 3W-5W full-range physical speaker.
*   **Visual Display:** SSD1306 128x64 OLED screen connected via I2C. Renders micro-animations of eyes (idle, listening, thinking, speaking) synchronized with the bot's system states.
*   **Power/Data:** Direct micro-USB connection supplying continuous 5V power and providing standard UART console logging.

---

## 3. Software & Machine Learning Pipeline

The backend server acts as the central intelligence engine, executing a combination of local lightweight ML models and cloud reasoning interfaces:

| Engine Type | Model/Framework | Computational Platform | Description |
| :--- | :--- | :--- | :--- |
| **Wake Word** | Espressif WakeNet (`wn9_hiesp`) | Edge CPU (ESP32-S3) | Local neural network detecting "Hi ESP" without internet connectivity. |
| **STT (Speech-to-Text)** | Faster-Whisper (`tiny.en`) | Backend CPU (CTranslate2) | Transcribes incoming PCM buffers in-memory. Bypasses disk-write operations to achieve sub-100ms latency. |
| **Core Reasoning** | Google Gemini (2.5-flash / 2.0-flash) | Cloud API (`google-genai` SDK) | Core reasoning, conversational flow, tool selection, and RAG context evaluation. |
| **TTS (Text-to-Speech)** | Piper TTS (`en_US-lessac-medium`) | Backend CPU (ONNX Runtime) | Synthesizes response sentences into voice waves. Uses NumPy-based linear resampling to convert 22.05kHz native TTS audio to 16kHz. |
| **Database** | MongoDB | Backend Server | Persistent storage for user configuration profiles and logs of generated documents. |

### Low-Latency Optimizations
1. **Sentence Splitting:** Rather than waiting for the LLM to complete its entire response, the server yields text chunks and splits them at sentence boundaries (`.`, `?`, `!`, `,`, `;`, `:`). Each sentence is dispatched immediately to Piper, decreasing first-audio latency.
2. **In-Memory Personality RAG:** Injects bot identity data, creator credentials (Sarthak Saraf), and hardware parameters (`app/utils/bot_knowledge.py`) directly into the LLM system prompt context, ensuring instantaneous, zero-database-latency replies for project details.
3. **Key Rotation System:** Leverages a custom key manager (`GeminiKeyManager` in `llm_agent.py`) that monitors and rotates multiple Gemini API keys. If a key encounters rate limits (HTTP 429) or temporary server overloads (HTTP 503), it is put on cooldown and replaced seamlessly.

---

## 4. Model Context Protocol (MCP) Tools

The backend incorporates the **Model Context Protocol (MCP)** via a persistent server process. Instead of spawning new Python subprocesses for every external action (which adds 1-2 seconds of latency), a persistent client-server stdio bridge (`app/services/mcp_manager.py`) is initialized on FastAPI startup and shared across all user sessions.

The registered tools include:

1.  **`web_search(query: str, max_results: int = 3) -> str`**: Performs semantic search using Wikipedia, OpenStreetMap (for geolocation queries), and DuckDuckGo to obtain up-to-date facts.
2.  **`get_weather(location: str) -> str`**: Queries geocoding APIs and calls the Open-Meteo API to return temperature and wind speeds without requiring an API key.
3.  **`sync_text_to_clipboard(text: str) -> str`**: Uses the Join API to push text strings directly to Sarthak's Android clipboard (useful for drafting quick messages or links).
4.  **`generate_document(title: str, content: str, file_type: str = 'pdf', summary: str = 'No summary') -> str`**: Generates a formatted Word document (`.docx`) or a PDF file using markdown parsing. The generated file is logged into MongoDB, and emailed immediately to `gotosarthaks@gmail.com` using secure SMTP SSL.
5.  **`get_location() -> str`**: Uses IP-API geolocator to identify the user's current city, coordinates, and region.
6.  **`get_time() -> str`**: Returns local system date and time.

---

## 5. File Structure & Project Organization

```
project_esp32/
│
├── app/
│   ├── routes/
│   │   ├── __init__.py
│   │   └── ws_routes.py        # WebSocket server protocol handler (/ws/conversation)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── audio_generation.py # Piper TTS synthesis and NumPy linear resampling
│   │   ├── llm_agent.py        # Gemini API client, key rotation, and RAG injection
│   │   └── mcp_manager.py      # Holds persistent FastMCP process & tool bridges
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── bot_knowledge.py    # In-memory personality details and academic context
│   │   ├── db.py               # MongoDB connector for profiles and document logs
│   │   └── helpers.py          # String sanitizers and conversation history pruner
│   │
│   ├── __init__.py             # FastAPI App Factory and startup listeners
│   └── config.py               # Settings loader pulling variables from .env
│
├── documents/                  # Directory containing generated docx/pdf reports
├── doc_generator.py            # PDF (FPDF2) and DOCX (python-docx) formatting engines
├── mcp_server.py               # FastMCP tool declarations (duckduckgo, weather, SMTP, Join)
├── websocket_server.py         # Standalone alternate WebSocket server (alternative to FastAPI run)
├── run.py                      # Main entrypoint script (spawns FastAPI on Uvicorn)
├── requirements.txt            # Python dependencies (ctranslate2, google-genai, mcp, etc.)
└── .env                        # Configuration file containing local secrets
```

---

## 6. Setup & Installation

### Step 1: Install System Dependencies
Install `ffmpeg` and Python on your host operating system:
```bash
# Debian/Ubuntu
sudo apt update
sudo apt install -y ffmpeg python3-pip python3-venv mongodb
```

### Step 2: Clone and Setup Virtual Environment
```bash
git clone <repository_url> project_esp32
cd project_esp32
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Download TTS Model
Download the English voice model files and place them in the project root:
```bash
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

### Step 5: Configure Environment Variables (`.env`)
Create a `.env` file in the root of the project with the following contents:
```ini
# Core API Keys (Separate multiple keys with commas for rotation)
GEMINI_API_KEY="your_primary_gemini_api_key"
GEMINI_API_KEYS="key1,key2,key3"

# WebSocket Authentication
BOT_SECRET_KEY="secure_pre_shared_secret_key_matching_firmware"

# MongoDB Database Connection
MONGODB_URI="mongodb://localhost:27017/"

# Gmail SMTP Configuration (For generate_document tool)
# Note: Use a Gmail App Password, not your account login password.
GMAIL_APP_PASSWORD="abcd efgh ijkl mnop"
RECEIVER_EMAIL="gotosarthaks@gmail.com"

# Join API Configuration (For phone clipboard syncing)
JOIN_API_KEY="your_join_api_key"
JOIN_DEVICE_ID="your_target_device_id"
```

---

## 7. Running the Application

1. **Verify MongoDB is running:**
   ```bash
   sudo systemctl status mongodb
   ```
2. **Start the Unified Backend Server:**
   Launch the FastAPI application using the entry point:
   ```bash
   python run.py
   ```
   This will bind to port `5000` (`http://0.0.0.0:5000`). On startup, the script automatically:
   * Spawns and keeps alive the local persistent **FastMCP** server process (`mcp_server.py`).
   * Loads the in-memory **Faster-Whisper** (`tiny.en`) model onto your CPU.
   * Caches the **Piper ONNX Voice** model to RAM.
   * Exposes the full-duplex WebSocket endpoint at `ws://<your_server_ip>:5000/ws/conversation`.

---

## 8. Development & Diagnostics

To test individual modules without running the full WebSocket firmware, you can utilize the diagnostic files included in the repository:

*   **Test Gemini Connection:**
    ```bash
    python test_gemini.py
    ```
*   **Test Tool-calling (MCP server standalone mode):**
    ```bash
    python mcp_server.py
    ```
*   **Validate Full Pipeline Local Deployment:**
    ```bash
    python test_deployment.py
    ```
