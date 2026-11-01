from openai import OpenAI
import time

try:
    print("Testing Ollama connection with OpenAI client...")
    client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    )
    
    # Try to create a simple completion
    print("Attempting to call llama3.2:latest...")
    response = client.chat.completions.create(
        model="llama3.2:latest",
        messages=[{"role": "user", "content": "Say 'test' and nothing else"}],
        max_tokens=10,
        temperature=0
    )
    print(f"✓ Connection successful!")
    print(f"Response: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
