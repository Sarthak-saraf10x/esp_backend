import asyncio
import json
import os
import re
import sys
import time
import numpy as np
import websockets
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from google.genai import types

# Import from existing app modules
sys.path.insert(0, os.path.abspath('.'))
from app.config import Config
from app.services.transcription import get_whisper_model
from app.services.audio_generation import get_piper_voice
from app.services.llm_agent import key_manager, _is_rate_limit_error, _is_overload_error
from app.utils.db import get_user_profile
from app.utils.helpers import get_pruned_history

# Global configurations
PORT = 5001
HOST = "0.0.0.0"

# Maintain chat history globally or per session
ws_chat_histories = {}

async def handle_connection(websocket):
    print(f"Client connected from {websocket.remote_address}")
    
    # Setup MCP client parameters
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[Config.MCP_SERVER_SCRIPT],
        env=os.environ.copy()
    )
    
    session_id = f"ws_session_{int(time.time())}"
    audio_buffer = bytearray()
    is_speaking = False
    
    # Initialize connection to the MCP tool server
    print("Starting MCP Client stdio bridge...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP Client session initialized.")
            
            # Fetch tools
            mcp_tools = await session.list_tools()
            gemini_tools = []
            for t in mcp_tools.tools:
                gemini_tools.append({
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema
                })
            print(f"Loaded {len(gemini_tools)} tools for Gemini.")
            
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
            
            # Connection loop
            try:
                async for message in websocket:
                    if isinstance(message, str):
                        # JSON control frame
                        data = json.loads(message)
                        status = data.get("status")
                        print(f"Received control status: {status}")
                        
                        if status == "start_talking":
                            audio_buffer.clear()
                            is_speaking = True
                            await websocket.send(json.dumps({"status": "ready"}))
                            print("Ready to receive audio stream.")
                            
                        elif status == "done_talking":
                            is_speaking = False
                            if not audio_buffer:
                                print("Received done_talking but audio buffer is empty.")
                                await websocket.send(json.dumps({"status": "error", "message": "No audio received"}))
                                continue
                            
                            # Process the collected audio in a background task so we don't block socket loops
                            print(f"Audio buffer finished. Processing {len(audio_buffer)} bytes of speech...")
                            asyncio.create_task(
                                process_audio_and_reply(
                                    websocket, 
                                    audio_buffer, 
                                    session_id, 
                                    session, 
                                    gemini_tools, 
                                    system_instruction
                                )
                            )
                            
                    elif isinstance(message, bytes):
                        # Binary raw PCM audio frame
                        if is_speaking:
                            audio_buffer.extend(message)
                            
            except websockets.exceptions.ConnectionClosed:
                print(f"Connection closed for session {session_id}")
            except Exception as e:
                print(f"Exception in connection handler: {e}")

async def process_audio_and_reply(websocket, audio_bytes, session_id, mcp_session, gemini_tools, system_instruction):
    try:
        # Step 2: Speech-to-Text
        print("Transcribing audio buffer...")
        # Convert raw int16 PCM to float32 NumPy array normalized to [-1.0, 1.0]
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        loop = asyncio.get_running_loop()
        whisper_model = get_whisper_model()
        
        # Run transcription in a thread executor so it doesn't block the async event loop
        def run_transcribe():
            segments, info = whisper_model.transcribe(audio_np, language="en")
            return " ".join(seg.text for seg in segments).strip()
            
        user_text = await loop.run_in_executor(None, run_transcribe)
        print(f"User said: '{user_text}'")
        
        if not user_text:
            print("No speech detected.")
            await websocket.send(json.dumps({"status": "done", "reason": "no_speech_detected"}))
            return
            
        await websocket.send(json.dumps({"status": "transcription", "text": user_text}))
        
        # Step 3 & 4: Query LLM with stream=True and handle tool execution
        history = ws_chat_histories.get(session_id, [])
        
        # Select client and model with rotation
        max_attempts = len(key_manager.api_keys) * len(key_manager.MODELS) + 1
        client = None
        model_name = None
        api_key = None
        
        for attempt in range(max_attempts):
            try:
                client, api_key, model_name = key_manager.get_available_client_and_model()
                break
            except Exception as e:
                if attempt == max_attempts - 1:
                    print("All keys exhausted.")
                    await websocket.send(json.dumps({"status": "error", "message": "Rate limits exceeded"}))
                    return
                await asyncio.sleep(1)
        
        chat = client.chats.create(
            model=model_name,
            history=history,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0,
                tools=[{"function_declarations": gemini_tools}] if gemini_tools else None
            )
        )
        
        # Helper to get responses, handling key-rotation/overload retries
        def get_stream(content):
            return chat.send_message_stream(content)
            
        def get_chat_response(content):
            return chat.send_message(content)
            
        print("Sending request to Gemini...")
        response = await loop.run_in_executor(None, get_chat_response, user_text)
        
        # Handle tool calls first (if any) before generating final response stream
        while response.function_calls:
            tool_responses = []
            for tool_call in response.function_calls:
                print(f"Gemini requested tool: {tool_call.name} with args: {tool_call.args}")
                await websocket.send(json.dumps({"status": "tool_call", "tool": tool_call.name}))
                try:
                    result = await mcp_session.call_tool(
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
            
            print("Sending tool execution results back to Gemini...")
            response = await loop.run_in_executor(None, get_chat_response, tool_responses)

        # Once tool calls are done, stream the final response text
        # To get the final content as a stream, we send the final history turns
        # Wait, since send_message_stream requires content, let's just ask Gemini to produce the final response
        print("Getting streaming LLM response...")
        response_stream = await loop.run_in_executor(None, get_stream, "Please output the final response based on the tool result.")
        
        # Setup TTS voice configuration
        voice = get_piper_voice()
        sample_rate = getattr(voice.config, 'sample_rate', 22050)
        
        # Tell the client we are starting the speech output stream
        await websocket.send(json.dumps({
            "status": "start_response", 
            "sample_rate": sample_rate
        }))
        
        sentence_buffer = ""
        
        async def process_sentence(sentence):
            # Strip end convo keyword for synthesized audio, but keep track of it
            end_conversation = "[END_CONVO]" in sentence
            clean_sentence = sentence.replace("[END_CONVO]", "").strip()
            
            if not clean_sentence:
                return end_conversation
                
            print(f"Synthesizing sentence: '{clean_sentence}'")
            # Run Piper synthesis
            def run_synthesis():
                return list(voice.synthesize(clean_sentence))
                
            chunks = await loop.run_in_executor(None, run_synthesis)
            
            # Send each audio chunk back over the websocket
            for chunk in chunks:
                audio_data = None
                if hasattr(chunk, 'audio_int16_bytes') and chunk.audio_int16_bytes:
                    audio_data = chunk.audio_int16_bytes
                elif hasattr(chunk, '_audio_int16_bytes') and chunk._audio_int16_bytes:
                    audio_data = chunk._audio_int16_bytes
                elif hasattr(chunk, 'audio_int16_array') and chunk.audio_int16_array is not None:
                    audio_data = chunk.audio_int16_array.tobytes()
                elif hasattr(chunk, '_audio_int16_array') and chunk._audio_int16_array is not None:
                    audio_data = chunk._audio_int16_array.tobytes()
                
                if audio_data:
                    # Send raw binary PCM chunk
                    await websocket.send(audio_data)
                    # Yield control briefly to ensure network buffers don't get choked
                    await asyncio.sleep(0.001)
            
            return end_conversation

        end_convo_detected = False
        
        # Stream the LLM chunks
        for chunk in response_stream:
            text = chunk.text
            if not text:
                continue
                
            # Append and split into sentences
            sentence_buffer += text
            
            # Send intermediate text chunk to the client for caption/UI display
            await websocket.send(json.dumps({"status": "text_chunk", "text": text}))
            
            # Check for sentence boundaries (. ! ? or newlines)
            sentences = re.split(r'(?<=[.?!])\s+', sentence_buffer)
            if len(sentences) > 1:
                for s in sentences[:-1]:
                    ended = await process_sentence(s)
                    if ended:
                        end_convo_detected = True
                sentence_buffer = sentences[-1]
                
        # Process any remaining text in buffer
        if sentence_buffer.strip():
            ended = await process_sentence(sentence_buffer)
            if ended:
                end_convo_detected = True
                
        # Send end_response signal
        await websocket.send(json.dumps({
            "status": "end_response",
            "end_conversation": end_convo_detected
        }))
        
        # Save history
        ws_chat_histories[session_id] = get_pruned_history(chat.get_history())
        print(f"Completed streaming response for session {session_id}.")
        
    except Exception as e:
        print(f"Error processing audio request: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send(json.dumps({"status": "error", "message": str(e)}))
        except:
            pass

async def main():
    print(f"Starting Streaming WebSocket Server on ws://{HOST}:{PORT}...")
    async with websockets.serve(handle_connection, HOST, PORT):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWebSocket Server stopped.")
