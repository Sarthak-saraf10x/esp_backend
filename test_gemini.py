import google.generativeai as genai

genai.configure(api_key="AIzaSyDywvUeobY84f0X-qlYrGTblxQUYiStXUE")
model = genai.GenerativeModel("gemini-2.5-flash")

# Test standard function calling
response = model.generate_content("What is the weather in Pune?", tools=[{
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
}])

print(response.candidates[0])
