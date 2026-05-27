import os
import asyncio
from google import genai
from google.genai import types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from app.config import Config
from app.utils.helpers import get_pruned_history

print("Loading Gemini Model...")
gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
print("Gemini Model loaded.")

sessions = {}

async def ask_gemini_with_mcp(user_text, session_id):
    server_params = StdioServerParameters(
        command="./.venv/bin/python",
        args=[Config.MCP_SERVER_SCRIPT],
        env=os.environ.copy()
    )
    
    history = sessions.get(session_id, [])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            mcp_tools = await session.list_tools()
            
            gemini_tools = []
            for t in mcp_tools.tools:
                gemini_tools.append({
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema
                })
            
            system_instruction = (
                "You are an Autonomous Productivity Agent and voice assistant. You can engage in general conversation, "
                "answer questions, and perform complex tasks like generating documents (reports, emails, etc.).\n"
                "When asked to write or create something:\n"
                "1. If you need background information, use the web_search tool to gather facts first.\n"
                "2. If you need specific personal details or scope from the user, ASK clarifying questions (interview the user) before generating the document.\n"
                "3. Once you have all information, use the generate_document tool to create the final .docx or .pdf file, and tell the user it is ready.\n"
                "Remember your responses will be spoken aloud, so keep your conversational replies concise. "
                "IMPORTANT: If the user says goodbye, or if you are wrapping up the conversation naturally, "
                "you MUST include the exact keyword [END_CONVO] in your response."
            )
            
            print(f"Sending query to Gemini with {len(gemini_tools)} tools...")
            
            chat = gemini_client.chats.create(
                model="gemini-2.5-flash",
                history=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0,
                    tools=[{"function_declarations": gemini_tools}] if gemini_tools else None
                )
            )
            
            try:
                response = chat.send_message(user_text)
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    return "I'm sorry, but I have reached my API rate limit. Please wait a minute and try again. [END_CONVO]"
                raise e
            
            if response.function_calls:
                tool_responses = []
                for tool_call in response.function_calls:
                    print(f"Gemini requested tool: {tool_call.name} with args: {tool_call.args}")
                    try:
                        result = await session.call_tool(
                            tool_call.name,
                            tool_call.args
                        )
                        result_text = result.content[0].text if result.content else "Executed successfully."
                        print(f"Tool returned: {result_text}")
                    except Exception as e:
                        print(f"Tool error: {e}")
                        result_text = f"Error: {e}"
                        
                    tool_responses.append(types.Part.from_function_response(
                        name=tool_call.name,
                        response={"result": result_text}
                    ))
                
                print("Getting final response...")
                try:
                    final_response = chat.send_message(tool_responses)
                    sessions[session_id] = get_pruned_history(chat.get_history())
                    return final_response.text
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        return "I'm sorry, but I have reached my API rate limit. Please wait a minute and try again. [END_CONVO]"
                    raise e
            
            sessions[session_id] = get_pruned_history(chat.get_history())
            return response.text
