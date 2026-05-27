from faster_whisper import WhisperModel
from app.config import Config

print("Loading Whisper Model...")
whisper_model = WhisperModel(Config.WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
print("Whisper Model loaded.")

def transcribe_audio(file_path):
    segments, info = whisper_model.transcribe(file_path, language="en")
    user_text = " ".join(seg.text for seg in segments).strip()
    return user_text
