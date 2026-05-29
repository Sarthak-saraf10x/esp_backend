import os
from google import genai
from google.genai import types
from app.config import Config

client = genai.Client(api_key=Config.GEMINI_API_KEY)

chat = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        tools=[{
            "function_declarations": [
                {
                    "name": "get_weather",
                    "description": "Get the weather for a location",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "location": {
                                "type": "STRING",
                                "description": "The city name"
                            }
                        },
                        "required": ["location"]
                    }
                }
            ]
        }]
    )
)

response = chat.send_message('What is the weather in Pune?')
print(response.function_calls)

if response.function_calls:
    fc = response.function_calls[0]
    # Send function response
    resp = chat.send_message(
        [types.Part.from_function_response(
            name=fc.name,
            response={"result": "It is sunny and 30 degrees."}
        )]
    )
    print("Final:", resp.text)
