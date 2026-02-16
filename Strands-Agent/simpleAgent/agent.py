from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool
from strands.models.ollama import OllamaModel

# Create an Ollama model instance
ollama_model = OllamaModel(
    host="http://localhost:11434",  # Ollama server address
    model_id="gpt-oss-safeguard:20b",    #"glm-4.7-flash" #            # Specify which model to use
    temperature=0.3,
    top_p=0.8
)

app = BedrockAgentCoreApp()
# Create an agent using the Ollama model
agent = Agent(model=ollama_model)

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

