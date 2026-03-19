import json
import os
import re
import time
from datetime import datetime
from uuid import uuid4

import requests
import streamlit as st

API_URL = "https://router.huggingface.co/v1/chat/completions"
MODEL_NAME = "meta-llama/Llama-3.2-1B-Instruct"
SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the conversation history to remember "
    "user details like their name and preferences, and refer to them later."
)
CHAT_DIR = "chats"
MEMORY_JSON_PATH = "memory.json"
DEFAULT_CHAT_TITLE = "New Chat"


def get_hf_token():
    try:
        token = st.secrets["HF_TOKEN"]
    except KeyError:
        return None, "Missing `HF_TOKEN` in `.streamlit/secrets.toml`."
    if not token:
        return None, "`HF_TOKEN` is empty in `.streamlit/secrets.toml`."
    return token, None


def stream_hf_chat(hf_token, messages, max_tokens=512):
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        response = requests.post(
            API_URL, headers=headers, json=payload, timeout=60, stream=True
        )
    except requests.RequestException as exc:
        return None, f"Request failed: {exc}"

    if not response.ok:
        return None, f"HTTP {response.status_code}: {response.text}"

    def stream_generator():
        try:
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data:"):
                    data = line[len("data:") :].strip()
                else:
                    continue
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = payload["choices"][0].get("delta", {})
                except (KeyError, IndexError, TypeError, AttributeError):
                    continue
                content = delta.get("content")
                if content:
                    yield content
        finally:
            response.close()

    return stream_generator(), None


def ensure_chat_dir():
    os.makedirs(CHAT_DIR, exist_ok=True)


def chat_path(chat_id):
    return os.path.join(CHAT_DIR, f"{chat_id}.json")


def load_chat_file(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            return None
        if "id" not in data or "messages" not in data:
            return None
        if not isinstance(data.get("messages"), list):
            data["messages"] = []
        if not isinstance(data.get("user_memory"), dict):
            data["user_memory"] = {}
        if not data.get("title"):
            data["title"] = DEFAULT_CHAT_TITLE
        if not data.get("created_at"):
            data["created_at"] = datetime.now().isoformat(timespec="seconds")
        return data
    except (OSError, json.JSONDecodeError):
        return None


def load_chats_from_disk():
    ensure_chat_dir()
    chats = {}
    for filename in os.listdir(CHAT_DIR):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(CHAT_DIR, filename)
        chat = load_chat_file(path)
        if chat is None:
            continue
        chats[chat["id"]] = chat
    order = sorted(
        chats.keys(),
        key=lambda cid: chats[cid].get("created_at", ""),
    )
    return chats, order


def migrate_memory_json():
    if not os.path.exists(MEMORY_JSON_PATH):
        return
    try:
        with open(MEMORY_JSON_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return

    ensure_chat_dir()

    if isinstance(data.get("chats"), dict):
        for chat_id, chat in data["chats"].items():
            if not isinstance(chat, dict):
                continue
            if not chat_id:
                continue
            if os.path.exists(chat_path(chat_id)):
                continue
            normalized = {
                "id": chat_id,
                "title": chat.get("title") or DEFAULT_CHAT_TITLE,
                "created_at": chat.get("created_at")
                or datetime.now().isoformat(timespec="seconds"),
                "messages": chat.get("messages")
                if isinstance(chat.get("messages"), list)
                else [],
                "user_memory": chat.get("user_memory")
                if isinstance(chat.get("user_memory"), dict)
                else {},
            }
            save_chat(normalized)
        return

    if "messages" in data or "user_memory" in data:
        legacy_id = "legacy"
        if os.path.exists(chat_path(legacy_id)):
            return
        legacy_messages = data.get("messages", [])
        legacy_memory = data.get("user_memory", {})
        chat = {
            "id": legacy_id,
            "title": "Imported Chat",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "messages": legacy_messages if isinstance(legacy_messages, list) else [],
            "user_memory": legacy_memory if isinstance(legacy_memory, dict) else {},
        }
        save_chat(chat)


def load_user_memory():
    if not os.path.exists(MEMORY_JSON_PATH):
        return {}
    try:
        with open(MEMORY_JSON_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    if "chats" in data or "messages" in data or "user_memory" in data:
        return {}
    if "traits" in data and isinstance(data["traits"], dict):
        return data["traits"]
    return data


def save_user_memory(traits):
    try:
        with open(MEMORY_JSON_PATH, "w", encoding="utf-8") as file:
            json.dump({"traits": traits}, file, indent=2, ensure_ascii=True)
    except OSError as exc:
        st.warning(f"Could not save memory: {exc}")


def merge_user_memory(existing, updates):
    if not isinstance(updates, dict):
        return existing
    merged = dict(existing)
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_user_memory(merged[key], value)
        elif isinstance(value, list):
            current = merged.get(key, [])
            if not isinstance(current, list):
                current = []
            for item in value:
                if item not in current:
                    current.append(item)
            merged[key] = current
        else:
            merged[key] = value
    return merged


def extract_user_memory(hf_token, user_message):
    system_prompt = (
        "Extract any personal traits or preferences from the user's message. "
        "Return ONLY a JSON object. If none, return {}. "
        "Use short keys, and lists for multiple items."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 128,
    }
    try:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {hf_token}"},
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        return None, f"Request failed: {exc}"
    if not response.ok:
        return None, f"HTTP {response.status_code}: {response.text}"
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None, "Unexpected response format from Hugging Face."
    try:
        return json.loads(content), None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                return json.loads(match.group(0)), None
            except json.JSONDecodeError:
                pass
    return None, "No valid JSON memory extracted."


def save_chat(chat):
    ensure_chat_dir()
    user_memory = (
        st.session_state.user_memory
        if "user_memory" in st.session_state
        else chat.get("user_memory", {})
    )
    payload = {
        "id": chat["id"],
        "title": chat.get("title", DEFAULT_CHAT_TITLE),
        "created_at": chat.get("created_at"),
        "messages": chat.get("messages", []),
        "user_memory": user_memory,
    }
    try:
        with open(chat_path(chat["id"]), "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=True)
    except OSError as exc:
        st.warning(f"Could not save chat: {exc}")


def delete_chat_file(chat_id):
    try:
        os.remove(chat_path(chat_id))
    except OSError:
        return


def update_user_memory(chat, text):
    if "user_memory" not in st.session_state:
        st.session_state.user_memory = {}
    memory = st.session_state.user_memory

    name_match = re.search(
        r"\bmy name is ([A-Za-z][A-Za-z'\- ]{0,40})", text, flags=re.IGNORECASE
    )
    if name_match:
        name = name_match.group(1).strip().rstrip(".,!?")
        if name:
            memory["name"] = name

    like_match = re.search(
        r"\bi like ([A-Za-z][A-Za-z'\- ]{0,40})", text, flags=re.IGNORECASE
    )
    if like_match:
        interest = like_match.group(1).strip().rstrip(".,!?")
        if interest:
            interests = memory.get("interests", [])
            if interest not in interests:
                interests.append(interest)
            memory["interests"] = interests

    st.session_state.user_memory = memory
    chat["user_memory"] = memory


def create_chat():
    chat_id = uuid4().hex
    created_at = datetime.now().isoformat(timespec="seconds")
    return {
        "id": chat_id,
        "title": DEFAULT_CHAT_TITLE,
        "created_at": created_at,
        "messages": [],
        "user_memory": {},
    }


def format_timestamp(iso_timestamp):
    try:
        dt = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return iso_timestamp
    return dt.strftime("%b %d %H:%M")


def get_active_chat():
    chat_id = st.session_state.active_chat_id
    if not chat_id:
        return None
    return st.session_state.chats.get(chat_id)


def build_api_messages():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if st.session_state.get("user_memory"):
        memory_json = json.dumps(st.session_state.user_memory, ensure_ascii=True)
        messages.append(
            {"role": "system", "content": f"User memory (JSON): {memory_json}"}
        )
    active_chat = get_active_chat()
    if active_chat:
        messages.extend(active_chat["messages"])
    return messages


st.set_page_config(page_title="My AI Chat", layout="wide")
st.title("My AI Chat")

token, token_error = get_hf_token()
if token_error:
    st.error(token_error)
    st.stop()

if "memory_loaded" not in st.session_state:
    migrate_memory_json()
    chats, order = load_chats_from_disk()
    st.session_state.chats = chats
    st.session_state.chat_order = order
    st.session_state.active_chat_id = order[-1] if order else None
    st.session_state.memory_loaded = True
if "chats" not in st.session_state:
    st.session_state.chats = {}
if "chat_order" not in st.session_state:
    st.session_state.chat_order = []
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None
if "user_memory" not in st.session_state:
    st.session_state.user_memory = load_user_memory()

with st.sidebar:
    st.header("Chats")
    if st.button("New Chat", use_container_width=True):
        chat = create_chat()
        st.session_state.chats[chat["id"]] = chat
        st.session_state.chat_order.append(chat["id"])
        st.session_state.active_chat_id = chat["id"]
        save_chat(chat)
        st.rerun()

    chat_list = st.container(height=260)
    with chat_list:
        if not st.session_state.chat_order:
            st.caption("No chats yet.")
        for chat_id in st.session_state.chat_order:
            chat = st.session_state.chats.get(chat_id)
            if not chat:
                continue
            is_active = chat_id == st.session_state.active_chat_id
            title = chat.get("title", DEFAULT_CHAT_TITLE)
            timestamp = format_timestamp(chat.get("created_at", ""))
            label = f"{title} - {timestamp}" if timestamp else title
            cols = st.columns([0.86, 0.14])
            with cols[0]:
                if st.button(
                    label,
                    key=f"select_{chat_id}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state.active_chat_id = chat_id
                    st.rerun()
            with cols[1]:
                if st.button("✕", key=f"delete_{chat_id}", use_container_width=True):
                    st.session_state.chats.pop(chat_id, None)
                    st.session_state.chat_order = [
                        cid for cid in st.session_state.chat_order if cid != chat_id
                    ]
                    delete_chat_file(chat_id)
                    if st.session_state.active_chat_id == chat_id:
                        st.session_state.active_chat_id = (
                            st.session_state.chat_order[-1]
                            if st.session_state.chat_order
                            else None
                        )
                    st.rerun()

    with st.expander("User Memory", expanded=True):
        if st.button("Clear Memory", use_container_width=True):
            st.session_state.user_memory = {}
            save_user_memory(st.session_state.user_memory)
            active_chat = get_active_chat()
            if active_chat is not None:
                active_chat["user_memory"] = st.session_state.user_memory
                save_chat(active_chat)
            st.rerun()
        st.json(st.session_state.get("user_memory", {}))

chat_container = st.container(height=520)
with chat_container:
    active_chat = get_active_chat()
    if active_chat:
        for message in active_chat["messages"]:
            with st.chat_message(message["role"]):
                st.write(message["content"])
    else:
        st.info("No active chat. Create one from the sidebar to get started.")

prompt = st.chat_input("Type a message and press Enter")
if prompt:
    active_chat = get_active_chat()
    if active_chat is None:
        st.error("Create a new chat before sending a message.")
    else:
        active_chat["messages"].append({"role": "user", "content": prompt})
        update_user_memory(active_chat, prompt)
        save_user_memory(st.session_state.user_memory)
        if active_chat["title"] == DEFAULT_CHAT_TITLE:
            trimmed = " ".join(prompt.split()[:6]).strip()
            active_chat["title"] = trimmed if trimmed else DEFAULT_CHAT_TITLE
        save_chat(active_chat)
        with chat_container:
            with st.chat_message("user"):
                st.write(prompt)

        with chat_container:
            with st.chat_message("assistant"):
                placeholder = st.empty()
                stream, error = stream_hf_chat(token, build_api_messages())
                if error:
                    st.error(error)
                else:
                    collected = ""
                    for chunk in stream:
                        collected += chunk
                        placeholder.markdown(collected)
                        time.sleep(0.02)
                    if collected:
                        active_chat["messages"].append(
                            {"role": "assistant", "content": collected}
                        )
                        save_chat(active_chat)
                        memory_delta, _ = extract_user_memory(token, prompt)
                        if memory_delta:
                            st.session_state.user_memory = merge_user_memory(
                                st.session_state.user_memory, memory_delta
                            )
                            save_user_memory(st.session_state.user_memory)
                            active_chat["user_memory"] = st.session_state.user_memory
                            save_chat(active_chat)


