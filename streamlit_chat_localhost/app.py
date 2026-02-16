import json
import re
import time
import uuid
from typing import Dict, Iterator, List

import requests
import streamlit as st
from streamlit.logger import get_logger

from database import init_db
from auth import authenticate, create_user
from session_manager import (
    create_session,
    get_sessions,
    update_session,
    delete_session,
)

logger = get_logger(__name__)
logger.setLevel("INFO")

url = 'http://localhost:8080/invocations' # Example streaming API endpoint


# Page config
st.set_page_config(
    page_title="Local AgentCore Chat",
    page_icon="static/gen-ai-dark.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Remove Streamlit deployment components
st.markdown(
    """
      <style>
        .stAppDeployButton {display:none;}
        #MainMenu {visibility: hidden;}
      </style>
    """,
    unsafe_allow_html=True,
)

HUMAN_AVATAR = "static/user-profile.svg"
AI_AVATAR = "static/gen-ai-dark.svg"

def clean_response_text(text: str, show_thinking: bool = True) -> str:
    """Clean and format response text for better presentation"""
    if not text:
        return text

    # Handle the consecutive quoted chunks pattern
    # Pattern: "word1" "word2" "word3" -> word1 word2 word3
    text = re.sub(r'"\s*"', "", text)
    text = re.sub(r'^"', "", text)
    text = re.sub(r'"$', "", text)

    # Replace literal \n with actual newlines
    text = text.replace("\\n", "\n")

    # Replace literal \t with actual tabs
    text = text.replace("\\t", "\t")

    # Clean up multiple spaces
    text = re.sub(r" {3,}", " ", text)

    # Fix newlines that got converted to spaces
    text = text.replace(" \n ", "\n")
    text = text.replace("\n ", "\n")
    text = text.replace(" \n", "\n")

    # Handle numbered lists
    text = re.sub(r"\n(\d+)\.\s+", r"\n\1. ", text)
    text = re.sub(r"^(\d+)\.\s+", r"\1. ", text)

    # Handle bullet points
    text = re.sub(r"\n-\s+", r"\n- ", text)
    text = re.sub(r"^-\s+", r"- ", text)

    # Handle section headers
    text = re.sub(r"\n([A-Za-z][A-Za-z\s]{2,30}):\s*\n", r"\n**\1:**\n\n", text)

    # Clean up multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Clean up thinking

    if not show_thinking:
        text = re.sub(r"<thinking>.*?</thinking>", "", text)

    return text.strip()


def extract_text_from_response(data) -> str:
    """Extract text content from response data in various formats"""
    if isinstance(data, dict):
        # Handle format: {'role': 'assistant', 'content': [{'text': 'Hello!'}]}
        if "role" in data and "content" in data:
            content = data["content"]
            if isinstance(content, list) and len(content) > 0:
                if isinstance(content[0], dict) and "text" in content[0]:
                    return str(content[0]["text"])
                else:
                    return str(content[0])
            elif isinstance(content, str):
                return content
            else:
                return str(content)

        # Handle other common formats
        if "text" in data:
            return str(data["text"])
        elif "content" in data:
            content = data["content"]
            if isinstance(content, str):
                return content
            else:
                return str(content)
        elif "message" in data:
            return str(data["message"])
        elif "response" in data:
            return str(data["response"])
        elif "result" in data:
            return str(data["result"])

    return str(data)


def parse_streaming_chunk(chunk: str) -> str:
    """Parse individual streaming chunk and extract meaningful content"""
    logger.debug(f"parse_streaming_chunk: received chunk: {chunk}")
    logger.debug(f"parse_streaming_chunk: chunk type: {type(chunk)}")

    try:
        # Try to parse as JSON first
        if chunk.strip().startswith("{"):
            logger.debug("parse_streaming_chunk: Attempting JSON parse")
            data = json.loads(chunk)
            logger.debug(f"parse_streaming_chunk: Successfully parsed JSON: {data}")

            # Handle the specific format: {'role': 'assistant', 'content': [{'text': '...'}]}
            if isinstance(data, dict) and "role" in data and "content" in data:
                content = data["content"]
                if isinstance(content, list) and len(content) > 0:
                    first_item = content[0]
                    if isinstance(first_item, dict) and "text" in first_item:
                        extracted_text = first_item["text"]
                        logger.debug(
                            f"parse_streaming_chunk: Extracted text: {extracted_text}"
                        )
                        return extracted_text
                    else:
                        return str(first_item)
                else:
                    return str(content)
            else:
                # Use the general extraction function for other formats
                return extract_text_from_response(data)

        # If not JSON, return the chunk as-is
        logger.debug("parse_streaming_chunk: Not JSON, returning as-is")
        return chunk
    except json.JSONDecodeError as e:
        logger.error(f"parse_streaming_chunk: JSON decode error: {e}")

        # Try to handle Python dict string representation (with single quotes)
        if chunk.strip().startswith("{") and "'" in chunk:
            logger.debug(
                "parse_streaming_chunk: Attempting to handle Python dict string"
            )
            try:
                # Try to convert single quotes to double quotes for JSON parsing
                # This is a simple approach - might need refinement for complex cases
                json_chunk = chunk.replace("'", '"')
                data = json.loads(json_chunk)
                logger.debug(
                    f"parse_streaming_chunk: Successfully converted and parsed: {data}"
                )

                # Handle the specific format
                if isinstance(data, dict) and "role" in data and "content" in data:
                    content = data["content"]
                    if isinstance(content, list) and len(content) > 0:
                        first_item = content[0]
                        if isinstance(first_item, dict) and "text" in first_item:
                            extracted_text = first_item["text"]
                            logger.debug(
                                f"parse_streaming_chunk: Extracted text from converted dict: {extracted_text}"
                            )
                            return extracted_text
                        else:
                            return str(first_item)
                    else:
                        return str(content)
                else:
                    return extract_text_from_response(data)
            except json.JSONDecodeError:
                logger.debug(
                    "parse_streaming_chunk: Failed to convert Python dict string"
                )
                pass

        # If all parsing fails, return the chunk as-is
        logger.debug("parse_streaming_chunk: All parsing failed, returning chunk as-is")
        return chunk


def invoke_agent_streaming(
    prompt: str,
    runtime_session_id: str,
    show_tool: bool = True,
) -> Iterator[str]:
    """Invoke agent and yield streaming response chunks"""
    try:
        with requests.post(url, json=prompt, stream=True) as response:
        # Check if the request was successful
            if response.status_code == 200:
                # Iterate over lines of the response
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        logger.debug(f"Raw line: {line}")
                        if line.startswith("data: "):
                            line = line[6:]
                            logger.debug(f"Line after removing 'data: ': {line}")
                            # Parse and clean each chunk
                            parsed_chunk = parse_streaming_chunk(line)
                            if parsed_chunk.strip():  # Only yield non-empty chunks
                                if "🔧 Using tool:" in parsed_chunk and not show_tool:
                                    yield ""
                                else:
                                    yield parsed_chunk
                        else:
                            logger.debug(
                                f"Line doesn't start with 'data: ', skipping: {line}"
                            )
            else:
                logger.debug("Using non-streaming response path")
                # Handle non-streaming JSON response
                try:
                    response_obj = requests.post(url, json=prompt, stream=False)
                    logger.debug(f"response_obj type: {type(response_obj)}")

                    if hasattr(response_obj, "read"):
                        # Read the response content
                        content = response_obj.read()
                        if isinstance(content, bytes):
                            content = content.decode("utf-8")

                        logger.debug(f"Raw content: {content}")

                        try:
                            # Try to parse as JSON and extract text
                            response_data = json.loads(content)
                            logger.debug(f"Parsed JSON: {response_data}")

                            # Handle the specific format we're seeing
                            if isinstance(response_data, dict):
                                # Check for 'result' wrapper first
                                if "result" in response_data:
                                    actual_data = response_data["result"]
                                else:
                                    actual_data = response_data

                                # Extract text from the nested structure
                                if "role" in actual_data and "content" in actual_data:
                                    content_list = actual_data["content"]
                                    if (
                                        isinstance(content_list, list)
                                        and len(content_list) > 0
                                    ):
                                        first_item = content_list[0]
                                        if (
                                            isinstance(first_item, dict)
                                            and "text" in first_item
                                        ):
                                            extracted_text = first_item["text"]
                                            logger.debug(
                                                f"Extracted text: {extracted_text}"
                                            )
                                            yield extracted_text
                                        else:
                                            yield str(first_item)
                                    else:
                                        yield str(content_list)
                                else:
                                    # Use general extraction
                                    text = extract_text_from_response(actual_data)
                                    yield text
                            else:
                                yield str(response_data)

                        except json.JSONDecodeError as e:
                            logger.error(f"JSON decode error: {e}")
                            # If not JSON, yield raw content
                            yield content
                    elif isinstance(response_obj, dict):
                        # Direct dict response
                        text = extract_text_from_response(response_obj)
                        yield text
                    else:
                        logger.debug(f"Unexpected response_obj type: {type(response_obj)}")
                        yield "No response content"

                except Exception as e:
                    logger.error(f"Exception in non-streaming: {e}")
                    yield f"Error reading response: {e}"

    except Exception as e:
        yield f"Error invoking agent: {e}"

# Initialize database
init_db()

# Session state initialization
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = None


# ----------------------------
# LOGIN SCREEN
# ----------------------------

def login_screen():

    st.title("Login")

    tab1, tab2 = st.tabs(["Login", "Signup"])

    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login"):

            if authenticate(username, password):

                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Login successful")
                st.rerun()

            else:
                st.error("Invalid credentials")

    with tab2:

        username = st.text_input("New Username")
        password = st.text_input("New Password", type="password")

        if st.button("Create Account"):

            if create_user(username, password):
                st.success("Account created")
            else:
                st.error("User already exists")


# ----------------------------
# HOME SCREEN
# ----------------------------

def home_screen():

    # Main area
    st.logo("static/agentcore-service-icon.png", size="large")
    st.title("Ollama Strands Agent Chat")

    # Sidebar for settings
    with st.sidebar:
        st.header("Settings")

        st.sidebar.title(f"Welcome {st.session_state.username}")

        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        # Sidebar
        st.sidebar.title("Session Manager")

        sessions = get_sessions(st.session_state.username)

        session_dict = {f"{name}": sid for sid, name in sessions}

        selected = st.sidebar.selectbox(
            "Select Session",
            ["None"] + list(session_dict.keys())
        )

        with st.expander("Create/Update Sessions", expanded=False):
            # Create session

            st.write("### Session Details")

            if selected != "None":
                sid = session_dict[selected]
                st.write("Session ID:", sid)
                st.session_state.runtime_session_id=sid

            else:
                st.write("No session selected") 

            st.subheader("Create Session")

            new_name = st.text_input("Session Name")

            if st.button("Create"):
                sid = create_session(st.session_state.username, new_name)
                st.success(f"Created {sid}")
                st.rerun()

            # Update session
            if selected != "None":

                sid = session_dict[selected]

                st.subheader("Modify Session")

                new_name = st.text_input("New Name")

                if st.button("Update"):
                    update_session(sid, new_name)
                    st.success("Updated")
                    st.rerun()

                st.subheader("Delete Session")

                if st.button("Delete"):
                    delete_session(sid)
                    st.success("Deleted")
                    st.rerun()        


        # Response formatting options
        # st.subheader("Display Options")
        with st.expander("Display Options", expanded=False):
            auto_format = st.checkbox(
                "Auto-format responses",
                value=True,
                help="Automatically clean and format responses",
            )
            show_raw = st.checkbox(
                "Show raw response",
                value=False,
                help="Display the raw unprocessed response",
            )
            show_tools = st.checkbox(
                "Show tools",
                value=True,
                help="Display tools used",
            )
            show_thinking = st.checkbox(
                "Show thinking",
                value=False,
                help="Display the AI thinking text",
            )

            # Clear chat button
            if st.button("🗑️ Clear Chat"):
                st.session_state.messages = []
                st.rerun()

    if selected == "None":
        st.title(f"Welcome {st.session_state.username}")
        st.write("Select a session from sidebar to start a chat")
    else:

        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Display chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"], avatar=message["avatar"]):
                st.markdown(message["content"])

        # Chat input
        if prompt := st.chat_input("Type your message here..."):
            # if not agent_arn:
            #     st.error("Please select an agent in the sidebar first.")
            #     return

            # Add user message to chat history
            st.session_state.messages.append(
                {"role": "user", "content": prompt, "avatar": HUMAN_AVATAR}
            )
            with st.chat_message("user", avatar=HUMAN_AVATAR):
                st.markdown(prompt)

            # Generate assistant response
            with st.chat_message("assistant", avatar=AI_AVATAR):
                message_placeholder = st.empty()
                chunk_buffer = ""

                try:
                    # Stream the response
                    for chunk in invoke_agent_streaming(
                        {"prompt": prompt},
                        st.session_state.runtime_session_id,
                        show_tools,
                    ):
                        # Let's see what we get
                        logger.debug(f"MAIN LOOP: chunk type: {type(chunk)}")
                        logger.debug(f"MAIN LOOP: chunk content: {chunk}")

                        # Ensure chunk is a string before concatenating
                        if not isinstance(chunk, str):
                            logger.debug(
                                f"MAIN LOOP: Converting non-string chunk to string"
                            )
                            chunk = str(chunk)

                        # Add chunk to buffer
                        chunk_buffer += chunk

                        # Only update display every few chunks or when we hit certain characters
                        if (
                            len(chunk_buffer) % 3 == 0
                            or chunk.endswith(" ")
                            or chunk.endswith("\n")
                        ):
                            if auto_format:
                                # Clean the accumulated response
                                cleaned_response = clean_response_text(
                                    chunk_buffer, show_thinking
                                )
                                message_placeholder.markdown(cleaned_response + " ▌")
                            else:
                                # Show raw response
                                message_placeholder.markdown(chunk_buffer + " ▌")

                        time.sleep(0.01)  # Reduced delay since we're batching updates

                    # Final response without cursor
                    if auto_format:
                        full_response = clean_response_text(chunk_buffer, show_thinking)
                    else:
                        full_response = chunk_buffer

                    message_placeholder.markdown(full_response)

                    # Show raw response in expander if requested
                    if show_raw and auto_format:
                        with st.expander("View raw response"):
                            st.text(chunk_buffer)

                except Exception as e:
                    error_msg = f"❌ **Error:** {str(e)}"
                    message_placeholder.markdown(error_msg)
                    full_response = error_msg

            # Add assistant response to chat history
            st.session_state.messages.append(
                {"role": "assistant", "content": full_response, "avatar": AI_AVATAR}
            )


# ----------------------------
# MAIN ROUTER
# ----------------------------

if st.session_state.logged_in:
    home_screen()
else:
    login_screen()
