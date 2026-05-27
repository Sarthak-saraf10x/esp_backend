import os
import wave
import struct
import numpy as np
import tempfile
import subprocess
import piper
from app.config import Config

print("Loading Piper Model...")
piper_voice = piper.PiperVoice.load(Config.PIPER_VOICE_PATH)
print("Piper Model loaded.")

def generate_beep_wav(output_path):
    """Generate a simple beep as fallback audio"""
    import math
    
    sample_rate = 16000
    duration = 1.0
    frequency = 440
    
    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        num_samples = int(sample_rate * duration)
        for i in range(num_samples):
            t = float(i) / sample_rate
            value = int(32767 * math.sin(2 * math.pi * frequency * t))
            wav_file.writeframes(struct.pack('<h', value))

def generate_beep_response():
    """Generate a beep response file"""
    beep_path = tempfile.NamedTemporaryFile(suffix="_beep.wav", delete=False).name
    generate_beep_wav(beep_path)
    
    output_path = beep_path.replace('_beep.wav', '_beep_8khz.wav')
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", beep_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-f", "wav",
        "-y",
        output_path
    ]
    subprocess.run(ffmpeg_cmd, capture_output=True)
    
    if os.path.exists(beep_path):
        os.unlink(beep_path)
    
    return output_path

def generate_audio_stream(text):
    """Generator function to stream audio chunks"""
    print(f"Generating streaming audio for: {text}")
    
    raw_path = None
    output_path = None
    
    try:
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as raw_temp:
            raw_path = raw_temp.name
        
        with tempfile.NamedTemporaryFile(suffix="_8khz.wav", delete=False) as out_temp:
            output_path = out_temp.name
        
        # Generate audio with Piper
        with wave.open(raw_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            
            # Synthesize audio stream
            audio_stream = piper_voice.synthesize(text)
            
            # Process each audio chunk
            for audio_chunk in audio_stream:
                audio_data = None
                
                # Try each possible attribute that might contain audio data
                if hasattr(audio_chunk, 'audio_int16_bytes') and audio_chunk.audio_int16_bytes:
                    audio_data = audio_chunk.audio_int16_bytes
                elif hasattr(audio_chunk, '_audio_int16_bytes') and audio_chunk._audio_int16_bytes:
                    audio_data = audio_chunk._audio_int16_bytes
                elif hasattr(audio_chunk, 'audio_int16_array') and audio_chunk.audio_int16_array is not None:
                    audio_data = audio_chunk.audio_int16_array.tobytes()
                elif hasattr(audio_chunk, '_audio_int16_array') and audio_chunk._audio_int16_array is not None:
                    audio_data = audio_chunk._audio_int16_array.tobytes()
                elif hasattr(audio_chunk, 'audio_float_array') and audio_chunk.audio_float_array is not None:
                    float_array = audio_chunk.audio_float_array
                    int16_array = (float_array * 32767).astype(np.int16)
                    audio_data = int16_array.tobytes()
                else:
                    continue
                
                if audio_data:
                    wav_file.writeframes(audio_data)
        
        # Check if we actually wrote audio data
        raw_size = os.path.getsize(raw_path)
        print(f"Raw audio generated, size: {raw_size} bytes")
        
        if raw_size <= 44:  # Just the header
            print("ERROR: No audio data generated")
            generate_beep_wav(raw_path)
            print("Generated fallback beep")
        
        # Convert to 16kHz for ESP32 with explicit WAV format
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", raw_path,
            "-ar", "16000",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-f", "wav",
            "-bitexact",  # Force standard WAV header
            "-flags", "+bitexact",
            "-fflags", "+bitexact",
            "-y",
            output_path
        ]
        
        print("Converting audio with ffmpeg...")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            if os.path.exists(raw_path) and os.path.getsize(raw_path) > 44:
                with open(raw_path, 'rb') as f:
                    while True:
                        chunk = f.read(512)
                        if not chunk:
                            break
                        yield chunk
            return
        
        # Verify the converted file has correct header
        with open(output_path, 'rb') as f:
            header = f.read(12)
            if header[0:4] != b'RIFF':
                print("ERROR: Converted file missing RIFF header")
                # Try one more time with different ffmpeg options
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", raw_path,
                    "-ar", "16000",
                    "-ac", "1",
                    "-c:a", "pcm_s16le",
                    "-f", "wav",
                    "-write_bext", "0",
                    "-y",
                    output_path
                ]
                subprocess.run(ffmpeg_cmd, capture_output=True)
        
        converted_size = os.path.getsize(output_path)
        print(f"Converted audio size: {converted_size} bytes")
        
        if converted_size <= 44:
            print("ERROR: Converted audio too small")
            return
        
        # Read the converted file and stream it
        with open(output_path, 'rb') as f:
            chunk_size = 512
            total_sent = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
                total_sent += len(chunk)
                
        print(f"Audio streaming complete, sent {total_sent} bytes")
                
    except Exception as e:
        print(f"Error in generate_audio_stream: {e}")
        import traceback
        traceback.print_exc()
        try:
            beep_path = generate_beep_response()
            with open(beep_path, 'rb') as f:
                while True:
                    chunk = f.read(512)
                    if not chunk:
                        break
                    yield chunk
        except:
            yield b''
        
    finally:
        for path in [raw_path, output_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as e:
                    print(f"Error cleaning up {path}: {e}")
