import os
import tempfile
import asyncio
from flask import Blueprint, request, jsonify, Response
from app.services.transcription import transcribe_audio
from app.services.llm_agent import ask_gemini_with_mcp, sessions, gemini_client
from app.services.audio_generation import generate_audio_stream
from app.utils.helpers import clean_text_for_header, get_pruned_history

audio_bp = Blueprint('audio', __name__)

@audio_bp.route('/audio_stream', methods=['POST'])
def process_audio_stream():
    print("\n--- New Streaming Request Received ---")
    print(f"Headers: {dict(request.headers)}")
    
    session_id = request.headers.get("X-Session-Id", "default")
    
    raw_data = request.get_data()
    print(f"Raw data size: {len(raw_data)} bytes")
    
    if 'file' not in request.files:
        print("ERROR: No file in request")
        return jsonify({"error": "No audio file"}), 400
    
    audio_file = request.files['file']
    
    if audio_file.filename == '':
        print("ERROR: Empty filename")
        return jsonify({"error": "Empty filename"}), 400
    
    print(f"Received file: {audio_file.filename}")
    print(f"Content type: {audio_file.content_type}")
    print(f"Content length: {audio_file.content_length}")
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_file.save(tmp.name)
        input_path = tmp.name
        
        saved_size = os.path.getsize(input_path)
        print(f"Saved file size: {saved_size} bytes")
        
        if saved_size == 0:
            print("ERROR: Saved file is empty")
            return jsonify({"error": "Empty audio file"}), 400
    
    try:
        print("Transcribing...")
        user_text = transcribe_audio(input_path)
        print(f"User said: '{user_text}'")
        
        if not user_text:
            print("No speech detected")
            return jsonify({"error": "No speech detected"}), 400
        
        print("Querying Gemini with MCP...")
        try:
            bot_text = asyncio.run(ask_gemini_with_mcp(user_text, session_id))
        except Exception as e:
            print(f"MCP flow failed, falling back to basic chat: {e}")
            import traceback
            traceback.print_exc()
            
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                bot_text = "I'm sorry, but I have reached my API rate limit. Please wait a minute and try again. [END_CONVO]"
            elif "503" in str(e) or "UNAVAILABLE" in str(e):
                bot_text = "I'm sorry, but the model is currently experiencing high demand. Please try again later. [END_CONVO]"
            else:
                try:
                    history = sessions.get(session_id, [])
                    chat = gemini_client.chats.create(
                        model='gemini-2.5-flash',
                        history=history
                    )
                    response = chat.send_message(user_text)
                    bot_text = response.text
                    sessions[session_id] = get_pruned_history(chat.get_history())
                except Exception as fallback_e:
                    if "429" in str(fallback_e) or "RESOURCE_EXHAUSTED" in str(fallback_e):
                        bot_text = "I'm sorry, but I have reached my API rate limit. Please wait a minute and try again. [END_CONVO]"
                    elif "503" in str(fallback_e) or "UNAVAILABLE" in str(fallback_e):
                        bot_text = "I'm sorry, but the model is currently experiencing high demand. Please try again later. [END_CONVO]"
                    else:
                        raise fallback_e
            
        print(f"Bot: {bot_text}")
        
        is_end_convo = "[END_CONVO]" in bot_text
        if is_end_convo:
            bot_text = bot_text.replace("[END_CONVO]", "").strip()
            if not bot_text:
                bot_text = "Goodbye."
        
        header_text = clean_text_for_header(bot_text)
        print(f"Header text: {header_text}")
        
        headers = {
            "X-Bot-Text": header_text,
            "Cache-Control": "no-cache",
            "Content-Disposition": "inline"
        }
        
        if is_end_convo:
            headers["X-End-Conversation"] = "true"
        
        return Response(
            generate_audio_stream(bot_text),
            mimetype="audio/wav",
            headers=headers
        )
        
    except Exception as e:
        print("SERVER ERROR:", e)
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
        
    finally:
        if os.path.exists(input_path):
            os.unlink(input_path)

@audio_bp.route('/audio', methods=['POST'])
def process_audio():
    return jsonify({"error": "Use /audio_stream endpoint"}), 400
