"""
Application entry point.
Runs FastAPI via uvicorn (replaces Flask's app.run()).
"""

import uvicorn
from app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "run:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
        log_level="info",
    )
