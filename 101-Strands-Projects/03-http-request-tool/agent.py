from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands_tools import http_request
from strands.models.ollama import OllamaModel

# Create an Ollama model instance
ollama_model = OllamaModel(
    host="http://localhost:11434",  # Ollama server address
    model_id="glm-4.7-flash",    #"glm-4.7-flash" #            # Specify which model to use
    temperature=0.3,
    top_p=0.8
)

app = BedrockAgentCoreApp()
# Create an agent using the Ollama model
agent = None

# Define a location-focused system prompt
ZIPCODE_SYSTEM_PROMPT = """You are a ZIP code assistant with HTTP capabilities. You can:

1. Make HTTP requests to the zippopotam.us Service API
2. Process and display location of zip code data
3. Provide information for locations in the United States

When retrieving location information:
1. First get the coordinates or grid information using https://api.zippopotam.us/us/{zipcode}
2. Then use the returned zipcode URL to get the actual information about the location

When displaying responses:
- Format location data in a human-readable way
- Highlight important information like place name and state
- Handle errors appropriately
- Convert technical terms to user-friendly language

Provide context for the location information.
"""

agent = Agent(
    model=ollama_model, 
    system_prompt=ZIPCODE_SYSTEM_PROMPT,
    tools=[http_request],
              callback_handler=None)

@app.entrypoint
async def strands_agent_bedrock(payload):
    """
    Invoke the agent with payload
    
    :param payload: Description
    """
    user_inut = payload.get("prompt")
    agent_stream = agent.stream_async(user_inut)

    tool_name=None
    try:
        async for event in agent_stream:
            if (
                "current_tool_user" in event
                and event["current_tool_use"].get("name") != tool_name
            ):
                tool_name = event["current_tool_use"]["name"]
                yield f"\n\n Using tool: {tool_name}\n\n"

            if "data" in event:
                tool_name = None
                yield event["data"]
    except Exception as e:
        yield f"Error: {str(e)}"

if __name__ == "__main__":
    print("Starting the application")
    app.run(host="0.0.0.0")

