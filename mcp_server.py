from mcp.server.fastmcp import FastMCP
from datetime import datetime
import httpx
import asyncio

mcp = FastMCP("ESP32 Tools Server")

@mcp.tool()
def get_time() -> str:
    """Get the current local time and date."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %I:%M %p")

@mcp.tool()
async def get_weather(location: str) -> str:
    """Get the current weather for a specified location.
    
    Args:
        location: The name of the city or location (e.g., 'London', 'New York', 'Pune').
    """
    try:
        # Using Open-Meteo API which does not require an API key
        async with httpx.AsyncClient() as client:
            # First get coordinates for the location
            geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
            geo_response = await client.get(geocode_url)
            geo_data = geo_response.json()
            
            if not geo_data.get('results'):
                return f"Could not find coordinates for {location}."
                
            lat = geo_data['results'][0]['latitude']
            lon = geo_data['results'][0]['longitude']
            name = geo_data['results'][0]['name']
            country = geo_data['results'][0].get('country', '')
            
            # Now get the current weather
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation,wind_speed_10m&temperature_unit=celsius"
            weather_response = await client.get(weather_url)
            weather_data = weather_response.json()
            
            temp = weather_data['current']['temperature_2m']
            wind = weather_data['current']['wind_speed_10m']
            
            location_str = f"{name}, {country}" if country else name
            return f"The current temperature in {location_str} is {temp} degrees Celsius, with a wind speed of {wind} km/h."
            
    except Exception as e:
        return f"Error fetching weather for {location}: {str(e)}"

import os
import sys

# Add local path so we can import doc_generator
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from doc_generator import generate_docx, generate_pdf
from duckduckgo_search import DDGS

@mcp.tool()
def web_search(query: str, max_results: int = 3) -> str:
    """Perform a web search to gather background information on a topic.
    
    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
    """
    try:
        results = DDGS().text(query, max_results=max_results)
        if not results:
            return "No results found."
        
        formatted_results = []
        for i, res in enumerate(results):
            formatted_results.append(f"Result {i+1}:\\nTitle: {res['title']}\\nSummary: {res['body']}\\nLink: {res['href']}")
            
        return "\\n\\n".join(formatted_results)
    except Exception as e:
        return f"Error performing web search: {str(e)}"

async def send_document_to_phone(filepath: str, caption: str = "Here is your generated document.") -> str:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id or bot_token == "your_telegram_bot_token_here":
        return "Telegram credentials not configured."
        
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        async with httpx.AsyncClient() as client:
            with open(filepath, 'rb') as f:
                files = {'document': (os.path.basename(filepath), f)}
                data = {'chat_id': chat_id, 'caption': caption}
                response = await client.post(url, data=data, files=files)
                response.raise_for_status()
                return "Successfully delivered to your phone via Telegram."
    except Exception as e:
        return f"Document generated but delivery failed: {str(e)}"

@mcp.tool()
async def sync_text_to_clipboard(text: str) -> str:
    """Send text directly to the user's smartphone clipboard.
    
    Args:
        text: The text message to copy to the clipboard.
    """
    api_key = os.environ.get("JOIN_API_KEY")
    device_id = os.environ.get("JOIN_DEVICE_ID")
    if not api_key or not device_id or api_key == "your_join_api_key_here":
        return "Join API credentials not configured."
        
    url = "https://joinjoaomgcd.appspot.com/_ah/api/messaging/v1/sendPush"
    params = {
        'apikey': api_key,
        'deviceId': device_id,
        'clipboard': text
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return "Successfully copied to your phone's clipboard."
    except Exception as e:
        return f"Error copying to clipboard: {str(e)}"

@mcp.tool()
async def generate_document(title: str, content: str, file_type: str) -> str:
    """Generate a formatted document (docx or pdf) and save it to the server.
    
    Args:
        title: The title of the document.
        content: The text content of the document (markdown supported).
        file_type: 'docx' or 'pdf'
    """
    try:
        if file_type.lower() == 'docx':
            path = generate_docx(title, content)
            msg = f"Successfully generated Word document at {path}."
        elif file_type.lower() == 'pdf':
            path = generate_pdf(title, content)
            msg = f"Successfully generated PDF document at {path}."
        else:
            return "Unsupported file type. Use 'docx' or 'pdf'."
            
        delivery_msg = await send_document_to_phone(path, caption=f"Here is your generated document: {title}")
        return f"{msg} {delivery_msg}"
    except Exception as e:
        return f"Error generating document: {str(e)}"
if __name__ == "__main__":
    mcp.run(transport='stdio')
