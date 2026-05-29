# ESP32-S3 Desktop Bot Backend

This repository contains the backend service for an interactive, conversational ESP32-S3 Desktop Bot. The system is built with Flask/FastAPI and leverages Google Gemini, local machine learning models (Whisper and Piper), and the Model Context Protocol (MCP) to provide a rich, responsive voice assistant experience.

## Overview

The ESP32-S3 acts as the edge device—capturing voice audio using Voice Activity Detection (VAD) and playing back responses. This backend server handles the heavy lifting: transcribing the audio, running reasoning via an LLM to understand intent and context, calling external tools if necessary, and generating high-quality synthesized speech to return to the bot.

## Detailed Workflow Architecture

The lifecycle of a single interaction flows through the following stages:

### 1. Audio Capture & Transmission (ESP32 -> Server)
*   **Voice Activity Detection:** The ESP32 listens for speech and captures audio until the user stops speaking.
*   **Streaming Request:** The ESP32 sends the captured audio (as a `.wav` file) via an HTTP POST request to the backend's `/audio_stream` endpoint.
*   **Session Tracking:** The request includes an `X-Session-Id` header to maintain conversational context across multiple turns.

### 2. Speech-to-Text (Transcription)
*   **Temporary Storage:** The backend receives the audio chunk and saves it as a temporary `.wav` file.
*   **Transcription:** The `faster-whisper` model (running locally on the CPU) processes the audio and transcribes the speech into text.

### 3. Reasoning & Tool Execution (LLM & MCP)
*   **Gemini Integration:** The transcribed text is sent to Google's **Gemini 2.5 Flash** model. 
*   **Model Context Protocol (MCP):** The system spins up an MCP server (`mcp_server.py`) that exposes several real-world tools to the LLM:
    *   `get_time`: Fetches the current time and date.
    *   `get_weather`: Retrieves real-time weather data for a specific location using the Open-Meteo API.
    *   `web_search`: Conducts web searches via DuckDuckGo to answer general knowledge questions.
    *   `sync_text_to_clipboard`: Uses the Join API to push text directly to the user's smartphone clipboard.
    *   `generate_document`: Generates formatted `.docx` or `.pdf` reports and automatically sends them to the user's phone via Telegram.
*   **Tool Calling Flow:** If Gemini determines it needs external information (e.g., "What is the weather in Pune?"), it invokes the corresponding tool. The MCP server executes the function and returns the result to Gemini, which then formulates the final conversational response.
*   **Graceful Degradation:** If Gemini experiences rate limits (429) or high demand (503), the backend catches these exceptions and gracefully returns a friendly audio message to the user instead of crashing.

### 4. Session & Memory Management
*   **Context Pruning:** To prevent the LLM context window from overflowing during long interactions, the conversation history is pruned while preserving recent context.
*   **Session State:** Conversation histories are stored in-memory, keyed by the `X-Session-Id` provided by the ESP32.

### 5. Text-to-Speech (Audio Generation)
*   **Piper TTS:** The final text response from Gemini is synthesized into speech using the local **Piper TTS** model (e.g., `en_US-lessac-medium.onnx`).
*   **Audio Conversion:** Because the ESP32 requires specific audio formats, the backend utilizes `ffmpeg` to convert the raw synthesized audio into a 16kHz, 16-bit PCM `.wav` format.
*   **Streaming Output:** The generated audio is chunked and streamed back to the ESP32 in real-time.

### 6. Conversation Control
*   **End of Conversation:** If Gemini decides the interaction is naturally concluding or the user says goodbye, it appends an `[END_CONVO]` token.
*   **Signaling the Bot:** The backend strips this token from the final audio and instead sets the `X-End-Conversation` HTTP header to `true`. The ESP32 reads this header and knows to stop listening and return to a standby state.

## Project Structure

```
app/
├── routes/
│   └── audio_routes.py       # Flask endpoints for handling incoming audio streams
├── services/
│   ├── audio_generation.py   # Text-to-Speech logic using Piper and FFmpeg
│   ├── llm_agent.py          # Gemini integration, session management, and MCP client
│   └── transcription.py      # Speech-to-Text logic using faster-whisper
├── utils/
│   └── helpers.py            # Utility functions for text cleaning and history pruning
├── __init__.py               # Flask app factory
└── config.py                 # Configuration and environment variables

mcp_server.py                 # FastMCP server defining all available tools
doc_generator.py              # Logic for generating PDF and DOCX files
run.py                        # Entry point to start the Flask server
```

## Requirements & Setup

1. **Python Environment**: Python 3.9+ is recommended. 
2. **Dependencies**: Install required packages using `pip install -r requirements.txt`. Note that `ffmpeg` must also be installed on the host system.
3. **Environment Variables**: Create a `.env` file with the following configurations:
    *   `GEMINI_API_KEY`: Your Google Gemini API key.
    *   `TELEGRAM_BOT_TOKEN`: Token for your Telegram Bot (for document delivery).
    *   `TELEGRAM_CHAT_ID`: Your Telegram Chat ID.
    *   `JOIN_API_KEY`: Join API Key (for clipboard syncing).
    *   `JOIN_DEVICE_ID`: Target device ID for Join.
4. **Models**: Ensure the Piper TTS ONNX model (`en_US-lessac-medium.onnx`) is present in the project directory.
5. **Run the Server**: Execute `python run.py`. The server will start on `0.0.0.0:5000`.
