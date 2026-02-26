"""
MCP Calculator Example

This example demonstrates how to:
1. Create a simple MCP server that provides calculator functionality
2. Connect a Strands agent to the MCP server
3. Use the calculator tools through natural language

from: https://github.com/strands-agents/docs/blob/main/docs/examples/python/mcp_calculator.py
"""

import threading
import time
from mcp.client.streamable_http import streamable_http_client
from mcp.server import FastMCP
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
from strands.models.ollama import OllamaModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

model = OllamaModel(
    host="http://localhost:11434",  # Ollama server address
    model_id="glm-4.7-flash", #"gpt-oss-safeguard:20b",    #"glm-4.7-flash, gpt-oss-safeguard:20b" #            # Specify which model to use
    temperature=0.3,
    top_p=0.8
)
app = BedrockAgentCoreApp()

def start_calculator_server():
    """
    Initialize and start an MCP calculator server.

    This function creates a FastMCP server instance that provides calculator tools
    for performing basic arithmetic operations. The server uses Streamable HTTP
    transport for communication.
    """
    # Create an MCP server with a descriptive name
    mcp = FastMCP("Calculator Server")

    # Define a simple addition tool
    @mcp.tool(description="Add two numbers together")
    def add(x: int, y: int) -> int:
        """Add two numbers and return the result.

        Args:
            x: First number
            y: Second number

        Returns:
            The sum of x and y
        """
        return x + y

    # Define a subtraction tool
    @mcp.tool(description="Subtract one number from another")
    def subtract(x: int, y: int) -> int:
        """Subtract y from x and return the result.

        Args:
            x: Number to subtract from
            y: Number to subtract

        Returns:
            The difference (x - y)
        """
        return x - y

    # Define a multiplication tool
    @mcp.tool(description="Multiply two numbers together")
    def multiply(x: int, y: int) -> int:
        """Multiply two numbers and return the result.

        Args:
            x: First number
            y: Second number

        Returns:
            The product of x and y
        """
        return x * y

    # Define a division tool
    @mcp.tool(description="Divide one number by another")
    def divide(x: float, y: float) -> float:
        """Divide x by y and return the result.

        Args:
            x: Numerator
            y: Denominator (must not be zero)

        Returns:
            The quotient (x / y)

        Raises:
            ValueError: If y is zero
        """
        if y == 0:
            raise ValueError("Cannot divide by zero")
        return x / y

    # Run the server with Streamable HTTP transport on the default port (8000)
    print("Starting MCP Calculator Server on http://localhost:8000")
    mcp.run(transport="streamable-http")


server_thread = threading.Thread(target=start_calculator_server, daemon=True)
server_thread.start()

# Wait for the server to start
print("Waiting for MCP server to start...")
time.sleep(2)

# Connect to the MCP server using Streamable HTTP transport
print("Connecting to MCP server...")

def create_streamable_http_transport():
    return streamable_http_client("http://localhost:8000/mcp/")

streamable_http_mcp_client = MCPClient(create_streamable_http_transport)

# Create a system prompt that explains the calculator capabilities
system_prompt = """
You are a helpful calculator assistant that can perform basic arithmetic operations.
You have access to the following calculator tools:
- add: Add two numbers together
- subtract: Subtract one number from another
- multiply: Multiply two numbers together
- divide: Divide one number by another

When asked to perform calculations, use the appropriate tool rather than calculating the result yourself.
Explain the calculation and show the result clearly.

NOTE: 
* Please do not answer anything except numerical calculation.
* Do not halucinate if you don't know the answer
"""

# Use the MCP client in a context manager
with streamable_http_mcp_client:
    # Get the tools from the MCP server
    tools = streamable_http_mcp_client.list_tools_sync()
    print(f"Available MCP tools: {[tool.tool_name for tool in tools]}")
    # Create an agent with the MCP tools
    agent = Agent(model=model,system_prompt=system_prompt, tools=tools, callback_handler=None)


@app.entrypoint
async def chat_invocation(payload):
    user_input = payload.get("prompt")
    with streamable_http_mcp_client:
        # print("The input to llm is ", user_input)
        agent_stream = agent.stream_async(user_input)

        tool_name=None
        try:
            async for event in agent_stream:
                # print(event)
                if (
                    "current_tool_user" in event
                    and event["current_tool_use"].get("name") != tool_name
                ):
                    tool_name = event["current_tool_use"]["name"]
                    yield f"\n\n Using tool: {tool_name}\n\n"

                if "data" in event:
                    tool_name = None
                    # print(event["data"])
                    yield event["data"]
        except Exception as e:
            yield f"Error: {str(e)}"

if __name__ == "__main__":
    try:
        print("Starting the application")
        # setup_project()

        app.run(host="0.0.0.0")

    except KeyboardInterrupt:
        print("\nExiting...")






# if __name__ == "__main__":
#     try:
#         setup_project()
#     except KeyboardInterrupt:
#         print("\nExiting...")