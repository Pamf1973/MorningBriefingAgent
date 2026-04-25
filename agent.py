import os
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel

# Load environment variables from .env
load_dotenv()

# Configure LiteLLMModel pointing at OpenRouter's API base
model = LiteLLMModel(
    model_id="openrouter/tencent/hy3-preview:free",
    params={
        "api_key": os.getenv("OPENROUTER_API_KEY"),
        "api_base": "https://openrouter.ai/api/v1"
    }
)

@tool
def get_weather(city: str) -> str:
    """
    Get the current weather for a given city.
    
    Args:
        city: The name of the city to get the weather for.
        
    Returns:
        A string describing the current weather.
    """
    return "72°F and sunny"

# Instantiate the Strands Agent
agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant. Use your tools to answer questions about the world.",
    tools=[get_weather]
)

if __name__ == "__main__":
    response = agent("What's the weather like in New York?")
    print(response)
