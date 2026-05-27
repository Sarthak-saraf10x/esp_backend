import os
from google import genai
from google.genai import types

client = genai.Client(api_key="AIzaSyDywvUeobY84f0X-qlYrGTblxQUYiStXUE")

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='What is the weather in Pune?',
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

print(response.function_calls)
