FROM python:3.11-slim

WORKDIR /app

# Ensure print() output appears immediately in logs (no buffering)
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for audio processing (ffmpeg) and building packages
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Download the Piper TTS ONNX model and config directly
RUN wget -O en_US-lessac-low.onnx -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx
RUN wget -O en_US-lessac-low.onnx.json -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx.json
# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 7860

# Command to run the application (Hugging Face Spaces defaults to 7860)
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "2", "--timeout", "120", "run:app"]
