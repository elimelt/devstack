"""Augment agent runner for internal API.

Starts an Augment chat agent that reads from and writes to chat channels.
"""

import asyncio
import logging
import os
import random
from datetime import UTC, datetime

from api import db, state
from api.producers.chat_producer import build_chat_message, publish_chat_message

_logger = logging.getLogger("api.agents.augment")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    _handler.setFormatter(_fmt)
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO)
_logger.propagate = False


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


async def _fetch_recent_messages_by_tokens(
    channel: str, token_limit: int, limit: int = 500
) -> list[tuple[str, str, datetime]]:
    """Fetch recent messages up to a token limit."""
    rows = await db.fetch_chat_history(channel=channel, before_iso=None, limit=limit)
    out: list[tuple[str, str, datetime]] = []
    total_tokens = 0

    for m in reversed(rows):
        ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        text = m.get("text") or ""
        sender = m.get("sender") or ""
        msg_tokens = _estimate_tokens(text) + _estimate_tokens(sender) + 30
        if total_tokens + msg_tokens > token_limit:
            break
        out.append((sender, text, ts))
        total_tokens += msg_tokens

    return list(reversed(out))


def _build_prompt(channel: str, history: list[tuple[str, str, datetime]], sender: str) -> str:
    """Build a prompt for the Augment AI model."""
    lines = [f"You are an AI assistant named '{sender}' participating in the #{channel} chat channel."]
    lines.append("")
    lines.append("IMPORTANT RULES:")
    lines.append("- You are here to have interesting, engaging conversations with visitors")
    lines.append("- Do NOT comment on the conversation structure or say things like 'this is a recursive loop'")
    lines.append("- Do NOT repeat or paraphrase what you've already said recently")
    lines.append("- If the conversation is quiet, bring up an interesting topic, ask a question, or share something fun")
    lines.append("- Be friendly, curious, and conversational - like a good chat room participant")
    lines.append("- Keep responses concise (1-3 sentences usually)")
    lines.append("")
    lines.append("Recent messages (oldest first):")
    for msg_sender, text, ts in history[-200:]:
        ts_str = ts.astimezone(UTC).isoformat()
        lines.append(f"[{ts_str}] {msg_sender}: {text}")
    lines.append("")
    lines.append("Write your next message to the chat:")
    return "\n".join(lines)


async def _run_augment_agent_loop(stop_event: asyncio.Event) -> None:
    """Main loop for the Augment agent."""
    api_token = _env("AUGMENT_API_TOKEN", "")
    if not api_token:
        _logger.info("AUGMENT_API_TOKEN not set; augment agent disabled")
        return

    sender = _env("AUGMENT_AGENT_SENDER", "agent:augment")
    channels = [c.strip() for c in _env("AUGMENT_AGENT_CHANNELS", "general").split(",") if c.strip()]
    min_sleep = int(_env("AUGMENT_AGENT_MIN_SLEEP_SEC", "3600"))
    max_sleep = int(_env("AUGMENT_AGENT_MAX_SLEEP_SEC", "3600"))
    token_limit = int(_env("AUGMENT_AGENT_HISTORY_TOKEN_LIMIT", "10000"))
    model = _env("AUGMENT_AGENT_MODEL", "sonnet4.5")

    _logger.info(
        "Augment agent started sender=%s channels=%s model=%s sleep=[%ss..%ss]",
        sender, channels, model, min_sleep, max_sleep
    )

    first_run = True
    while not stop_event.is_set():
        try:
            # Sleep first, except on first run
            if not first_run:
                sleep_time = random.randint(min_sleep, max_sleep)
                _logger.debug("[%s] Sleeping for %ds", sender, sleep_time)

                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=sleep_time)
                    break  # stop_event was set
                except asyncio.TimeoutError:
                    pass  # Normal timeout, continue
            first_run = False

            if state.event_bus is None:
                _logger.debug("[%s] Skipping; event_bus not ready", sender)
                continue

            channel = random.choice(channels)
            _logger.info("[%s] Session channel=%s", sender, channel)

            history = await _fetch_recent_messages_by_tokens(channel, token_limit)
            if not history:
                _logger.debug("[%s] No history found for channel=%s", sender, channel)
                continue

            prompt = _build_prompt(channel, history, sender)

            # Call Augment API synchronously in a thread
            text = await asyncio.to_thread(_call_augment_sync, api_token, model, prompt)

            if text:
                _logger.info("[%s] Generated response len=%d", sender, len(text))
                event = build_chat_message(channel=channel, sender=sender, text=text)
                await publish_chat_message(state.event_bus, channel, event)
            else:
                _logger.warning("[%s] No response from Augment", sender)

        except Exception:
            _logger.exception("[%s] Error in agent loop", sender)
            await asyncio.sleep(5)


# All tools to disable for chat-only mode
_ALL_TOOLS = [
    # Core Tools
    "codebase-retrieval", "remove-files", "save-file", "apply_patch",
    "str-replace-editor", "view",
    # Process Tools
    "launch-process", "kill-process", "read-process", "write-process", "list-processes",
    # Integration Tools
    "web-search", "github-api", "web-fetch",
    # Task Management
    "view_tasklist", "reorganize_tasklist", "update_tasks", "add_tasks",
    # Advanced Tools
    "sub-agent",
]


def _call_augment_sync(api_token: str, model: str, prompt: str) -> str | None:
    """Call Augment API synchronously (chat-only, no tools)."""
    try:
        from auggie_sdk import Auggie
        _logger.debug("Creating Auggie client with model=%s (no tools)", model)
        client = Auggie(
            model=model,
            api_key=api_token,
            timeout=300,
            removed_tools=_ALL_TOOLS,  # Disable all tools for chat-only
        )
        _logger.debug("Calling Auggie.run with prompt len=%d", len(prompt))
        response = client.run(prompt, return_type=str)
        _logger.debug("Auggie response: %s", response[:200] if response else None)
        return response or None
    except Exception as e:
        import traceback
        _logger.error("Augment API error: %s\n%s", e, traceback.format_exc())
        return None


async def start_augment_agent(stop_event: asyncio.Event) -> list[asyncio.Task]:
    """Start the Augment agent and return its task."""
    api_token = _env("AUGMENT_API_TOKEN", "")
    if not api_token:
        _logger.info("AUGMENT_API_TOKEN not set; skipping augment agent")
        return []

    task = asyncio.create_task(_run_augment_agent_loop(stop_event))
    return [task]

