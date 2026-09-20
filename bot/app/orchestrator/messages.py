"""LangChain message helpers for API / audit JSON."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

def user_message_count(messages: list | None) -> int:
    """Count user turns in a LangChain or dict transcript."""
    n = 0
    for m in messages or []:
        if isinstance(m, HumanMessage):
            n += 1
        elif isinstance(m, dict) and m.get("role") == "user":
            n += 1
    return n


# convert LangChain message objects into a list of user/assistant dicts for session JSON output
def transcript_from_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    """Flatten chat history to user/assistant dicts for session JSON."""
    out: list[dict[str, str]] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": _text_content(m.content)})
        elif isinstance(m, AIMessage):
            out.append({"role": "assistant", "content": _text_content(m.content)})
    return out

# helper function to handle different message content types
def _text_content(content: str | list[str | dict]) -> str:
    if isinstance(content, str): # if content is a string, return it
        return content
    if isinstance(content, list): # if content is a list, join the strings and dicts
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "".join(parts)
    return str(content) 


# get all turns strictly before the latest user message for generator context
def conversation_history_before_last_user(
    messages: list[BaseMessage],
) -> list[dict[str, str]]:
    if not messages: # if no messages, return empty list
        return []
    idx = None
    for i in range(len(messages) - 1, -1, -1): # iterate backwards through messages
        if isinstance(messages[i], HumanMessage):
            idx = i
            break
    if idx is None: 
        return transcript_from_messages(messages)
    return transcript_from_messages(messages[:idx]) # takes everything up to but not including the last human message
                                                    # converts to clean dicts for session JSON with transcript_from_messages
