import os
import datetime
from pymongo import MongoClient
from app.config import Config
# Create a client
client = MongoClient(Config.MONGODB_URI)
db = client["esp32_agent_db"]
users_collection = db["users"]
documents_collection = db["generated_documents"]

def init_db():
    """Initialize the database with a default user profile if it doesn't exist."""
    if Config.MONGODB_URI:
        try:
            if users_collection.count_documents({"user_id": "default_user"}) == 0:
                users_collection.insert_one({
                    "user_id": "default_user",
                    "full_name": "Sarthak Saraf",
                    "role": "Lead Developer",
                    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", "8880692559"),
                    "document_signature": "Best regards,\nSarthak Saraf\nLead Developer"
                })
        except Exception as e:
            print(f"Database initialization failed (MongoDB unreachable): {e}")
    else:
        print("Warning: MONGODB_URI not set. Database features will be disabled.")

def get_user_profile(user_id="default_user"):
    """Fetch the user profile."""
    try:
        if Config.MONGODB_URI:
            return users_collection.find_one({"user_id": user_id})
    except Exception:
        pass
    return None

def log_document(user_id, doc_type, file_path, summary):
    """Log generated documents to the registry."""
    try:
        if Config.MONGODB_URI:
            documents_collection.insert_one({
                "user_id": user_id,
                "timestamp": datetime.datetime.utcnow(),
                "document_type": doc_type,
                "file_path": file_path,
                "summary": summary
            })
    except Exception as e:
        print(f"Failed to log document to DB: {e}")

# Initialize the db on module load
init_db()
