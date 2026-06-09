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
    if users_collection.count_documents({"user_id": "default_user"}) == 0:
        users_collection.insert_one({
            "user_id": "default_user",
            "full_name": "Sarthak Saraf",
            "role": "Lead Developer",
            "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", "8880692559"),
            "document_signature": "Best regards,\nSarthak Saraf\nLead Developer"
        })

def get_user_profile(user_id="default_user"):
    """Fetch the user profile."""
    return users_collection.find_one({"user_id": user_id})

def log_document(user_id, doc_type, file_path, summary):
    """Log generated documents to the registry."""
    documents_collection.insert_one({
        "user_id": user_id,
        "timestamp": datetime.datetime.utcnow(),
        "document_type": doc_type,
        "file_path": file_path,
        "summary": summary
    })

# Initialize the db on module load
init_db()
