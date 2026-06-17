from mcp.server.fastmcp import FastMCP
from datetime import datetime
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

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

@mcp.tool()
async def get_location() -> str:
    """Get the current physical location of the user (city, region, country, latitude, longitude) based on their IP address."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://ip-api.com/json/")
            data = response.json()
            if data.get("status") == "success":
                city = data.get("city", "Unknown City")
                region = data.get("regionName", "Unknown Region")
                country = data.get("country", "Unknown Country")
                lat = data.get("lat", "Unknown")
                lon = data.get("lon", "Unknown")
                return f"User is currently located in {city}, {region}, {country}. (Latitude: {lat}, Longitude: {lon})"
            else:
                return "Could not determine current location."
    except Exception as e:
        return f"Error fetching location: {str(e)}"

import os
import sys

# Add local path so we can import doc_generator and db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from doc_generator import generate_docx, generate_pdf
from app.utils.db import log_document
from duckduckgo_search import DDGS

import wikipedia

@mcp.tool()
def web_search(query: str, max_results: int = 3) -> str:
    """Perform a web search to gather background information on a topic.
    
    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
    """
    results_text = []
    
    # 1. Try Wikipedia
    try:
        wiki_search = wikipedia.search(query, results=max_results)
        for w in wiki_search:
            try:
                page = wikipedia.page(w, auto_suggest=False)
                results_text.append(f"Source: Wikipedia\\nTitle: {page.title}\\nSummary: {page.summary[:500]}...")
            except:
                pass
    except Exception:
        pass
        
    # 2. Try Nominatim for places
    if not results_text or any(x in query.lower() for x in [' in ', ' near ', ' at ', 'restaurants', 'hotels', 'coffee']):
        try:
            import urllib.parse
            import urllib.request
            import json
            req = urllib.request.Request(
                f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit={max_results}",
                headers={'User-Agent': 'ESP32AgentBot/1.0'}
            )
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                for item in data:
                    results_text.append(f"Source: OpenStreetMap\\nLocation: {item.get('display_name')}\\nType: {item.get('type')}")
        except Exception:
            pass

    # 3. Fallback to DDGS
    if not results_text:
        try:
            from duckduckgo_search import DDGS
            ddgs_results = DDGS().text(query, max_results=max_results)
            if ddgs_results:
                for res in ddgs_results:
                    results_text.append(f"Source: DuckDuckGo\\nTitle: {res.get('title', '')}\\nSummary: {res.get('body', '')}")
        except Exception:
            pass

    if not results_text:
        return "No results found. The search APIs might be blocking the request or rate-limiting."
        
    return "\\n\\n".join(results_text)

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def _send_email_blocking(filepath: str, caption: str) -> str:
    sender_email = "gotosarthaks@gmail.com"
    receiver_email = os.environ.get("RECEIVER_EMAIL", "gotosarthaks@gmail.com")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not app_password:
        return "Gmail app password not configured in environment."

    app_password = app_password.replace(" ", "")

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"Generated Document: {os.path.basename(filepath)}"

    body = f"Hello Sarthak,\n\nHere is your generated document: {os.path.basename(filepath)}.\n\nDescription: {caption}\n\nBest regards,\nESP32-S3 Bot"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with open(filepath, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(filepath)}",
            )
            msg.attach(part)
    except Exception as e:
        import traceback
        import sys
        sys.stderr.write("[_send_email_blocking] Error attaching file:\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return f"Failed to attach file to email: {str(e)}"

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        return "Successfully delivered to your Gmail."
    except Exception as e:
        import traceback
        import sys
        sys.stderr.write("[_send_email_blocking] SMTP sending failed:\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return f"Document generated but Gmail delivery failed: {str(e)}"

async def send_document_via_email(filepath: str, caption: str = "Here is your generated document.") -> str:
    return await asyncio.to_thread(_send_email_blocking, filepath, caption)

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
async def generate_document(title: str, content: str, file_type: str = "pdf", summary: str = "No summary") -> str:
    """Generate a formatted document (docx or pdf), save it to the server, and automatically deliver it to Sarthak's Gmail (gotosarthaks@gmail.com).
    
    Args:
        title: The title of the document.
        content: The text content of the document (markdown supported).
        file_type: The format of the file. Must be 'docx' or 'pdf'. Defaults to 'pdf'.
        summary: A short summary of the document for the database registry. Defaults to 'No summary'.
    """
    import sys
    import traceback

    # Normalize arguments to handle potential None values
    file_type = (file_type or "pdf").lower()
    summary = summary or "No summary"
    title = title or "Untitled Document"
    content = content or ""

    try:
        sys.stderr.write(f"[generate_document] Generating {file_type} document: Title='{title}', Summary='{summary}'\n")
        sys.stderr.flush()

        if file_type == 'docx':
            path = generate_docx(title, content)
            msg = f"Successfully generated Word document at {path}."
        elif file_type == 'pdf':
            path = generate_pdf(title, content)
            msg = f"Successfully generated PDF document at {path}."
        else:
            sys.stderr.write(f"[generate_document] Unsupported file type: {file_type}\n")
            sys.stderr.flush()
            return "Unsupported file type. Use 'docx' or 'pdf'."
            
        # Log to database
        try:
            log_document("default_user", f"{file_type.upper()} Document", path, summary)
        except Exception as db_err:
            sys.stderr.write(f"[generate_document] DB log failed: {db_err}\n")
            sys.stderr.flush()
        
        sys.stderr.write(f"[generate_document] Delivering document: {path}\n")
        sys.stderr.flush()

        delivery_msg = await send_document_via_email(path, caption=f"Here is your generated document: {title}")
        
        sys.stderr.write(f"[generate_document] Delivery result: {delivery_msg}\n")
        sys.stderr.flush()

        return f"{msg} Registry updated. {delivery_msg}"
    except Exception as e:
        sys.stderr.write("[generate_document] Exception occurred:\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return f"Error generating document: {str(e)}"
if __name__ == "__main__":
    mcp.run(transport='stdio')
