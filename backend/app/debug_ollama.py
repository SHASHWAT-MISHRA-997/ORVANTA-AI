import asyncio
import httpx

async def test_ollama():
    ollama_url = "http://ollama:11434/api/generate"
    payload = {
        "model": "mistral",
        "prompt": "hi",
        "stream": False
    }
    
    print(f"Connecting to {ollama_url}...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(ollama_url, json=payload)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            response.raise_for_status()
    except Exception as e:
        print(f"Error Type: {type(e)}")
        print(f"Error Message: '{str(e)}'")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ollama())
