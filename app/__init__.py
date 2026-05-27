from flask import Flask

def create_app():
    app = Flask(__name__)
    
    # Import and register blueprints
    from app.routes.audio_routes import audio_bp
    app.register_blueprint(audio_bp)
    
    return app
