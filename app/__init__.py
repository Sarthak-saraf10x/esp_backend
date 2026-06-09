from flask import Flask, request, jsonify
from app.config import Config

def create_app():
    app = Flask(__name__)
    
    @app.before_request
    def require_bot_secret():
        # Require the X-Bot-Secret-Key header for all requests (or specific ones)
        secret_key = request.headers.get('X-Bot-Secret-Key')
        if not secret_key or secret_key != Config.BOT_SECRET_KEY:
            return jsonify({"error": "Unauthorized"}), 401

    # Import and register blueprints
    from app.routes.audio_routes import audio_bp
    app.register_blueprint(audio_bp)
    
    return app
