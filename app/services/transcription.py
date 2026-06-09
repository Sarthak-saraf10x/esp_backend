from faster_whisper import WhisperModel
from app.config import Config

whisper_model = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        print("Loading Whisper Model...")
        whisper_model = WhisperModel(Config.WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
        print("Whisper Model loaded.")
    return whisper_model

def transcribe_audio(file_path):
    model = get_whisper_model()
    segments, info = model.transcribe(file_path, language="en")
    user_text = " ".join(seg.text for seg in segments).strip()
    return user_text
