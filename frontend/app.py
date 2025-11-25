import streamlit as st
import queue
from streamlit_autorefresh import st_autorefresh
from ws_manager import WebSocketManager

# ----------------------------
# SESSION STATE INIT
# ----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "ws_message_queue" not in st.session_state:
    st.session_state.ws_message_queue = queue.Queue(maxsize=500)

if "ws_manager" not in st.session_state:
    st.session_state.ws_manager = WebSocketManager(
        message_queue=st.session_state.ws_message_queue,
    )
    st.session_state.ws_manager.start()

ws = st.session_state.ws_manager

st_autorefresh(interval=500, key="ws_refresh")


# ----------------------------
# DRAIN WS QUEUE INTO SESSION
# ----------------------------
def drain_queue_to_session():
    q = st.session_state.ws_message_queue
    while True:
        try:
            data = q.get_nowait()
        except queue.Empty:
            break
        if isinstance(data, list):
            st.session_state.messages.extend(data)
        else:
            st.session_state.messages.append(data)

drain_queue_to_session()


# ----------------------------
# DETECT consecutive function_call messages at end
# ----------------------------
def get_trailing_function_call_indices(messages):
    indices = []
    for i in range(len(messages) - 1, -1, -1):
        if "function_call" in messages[i]:
            indices.append(i)
        else:
            break
    return set(indices)

trailing_fc_indices = get_trailing_function_call_indices(st.session_state.messages)


# ----------------------------
# RENDER UI
# ----------------------------
st.title("YB Browser")

for idx, message in enumerate(st.session_state.messages):

    # ----- REGULAR TEXT MESSAGE -----
    if message.get("text"):
        st.chat_message(message["role"]).write(message["text"])
        continue

    # ----- FUNCTION CALL MESSAGE -----
    if "function_call" in message:
        fn = message["function_call"]
        args = fn.get("args", {})

        url = args.get("url", "Unknown URL")
        goal = args.get("goal", "No goal specified")

        # Pretty message formatting
        pretty_text = (
            f"**Web Automation Started**\n\n"
            f"- **URL:** `{url}`\n"
            f"- **Goal:** {goal}"
        )

        chat = st.chat_message("agent")

        # If this function call is in trailing group => show loader
        if idx in trailing_fc_indices:
            with chat:
                with st.spinner("Running automation..."):
                    st.markdown(pretty_text)
        else:
            # Completed state
            chat.success(pretty_text)


# ----------------------------
# USER INPUT HANDLING
# ----------------------------
user_input = st.chat_input("How can I help you...")

if user_input:
    st.chat_message("user").write(user_input)
    st.session_state.messages.append({"role": "user", "text": user_input})
    ws.send({"role": "user", "text": user_input})
