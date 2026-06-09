import asyncio
import os
import sys

# Add the current directory to path so we can import backend
sys.path.insert(0, os.path.abspath('.'))

from backend import ask_gemini_with_mcp

async def test():
    print("Testing time...")
    response1 = await ask_gemini_with_mcp("What time is it right now?")
    print("Response 1:", response1)
    
    print("\nTesting weather...")
    response2 = await ask_gemini_with_mcp("What is the weather in Pune?")
    print("Response 2:", response2)

if __name__ == "__main__":
    asyncio.run(test())
