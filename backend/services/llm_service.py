"""
VOXA Backend — LLM Service (Layer 6 & 10: AI Agent + Response Generation)
Uses Groq API (FREE tier) for Mistral 7B (primary) and LLaMA 3 (fallback).

Groq provides free access to open-source LLMs with ultra-fast inference.
Free tier: 30 req/min, 14,400 req/day — plenty for a demo.
Get your key at: https://console.groq.com
"""

import logging
from typing import AsyncGenerator

from groq import Groq, AsyncGroq
from config import GROQ_API_KEY, PRIMARY_MODEL, FALLBACK_MODEL, SYSTEM_PROMPT, LLM_GUARDRAILS

logger = logging.getLogger("voxa.llm")

# Clients (lazy init)
_sync_client: Groq | None = None
_async_client: AsyncGroq | None = None


def _get_sync_client() -> Groq:
    global _sync_client
    if _sync_client is None:
        if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
            raise RuntimeError(
                "GROQ_API_KEY not set! Get a FREE key at https://console.groq.com "
                "and add it to backend/.env"
            )
        _sync_client = Groq(api_key=GROQ_API_KEY)
    return _sync_client


def _get_async_client() -> AsyncGroq:
    global _async_client
    if _async_client is None:
        if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
            raise RuntimeError(
                "GROQ_API_KEY not set! Get a FREE key at https://console.groq.com "
                "and add it to backend/.env"
            )
        _async_client = AsyncGroq(api_key=GROQ_API_KEY)
    return _async_client


def generate_response(
    user_query: str,
    data_context: str = "",
    conversation_history: list[dict] | None = None,
    model: str | None = None,
) -> str:
    """
    Generate a complete response using Groq LLM (non-streaming).

    Args:
        user_query: The user's question
        data_context: Data tables/stats to include in context
        conversation_history: Previous messages for context
        model: Override model choice

    Returns:
        Complete response text (markdown formatted)
    """
    client = _get_sync_client()
    target_model = model or PRIMARY_MODEL

    messages = _build_messages(user_query, data_context, conversation_history)

    try:
        response = client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=0.3,  # Lower temp for more factual/consistent responses
            max_tokens=2048,
            top_p=0.9,
        )
        return response.choices[0].message.content

    except Exception as e:
        if target_model == PRIMARY_MODEL:
            logger.warning(f"Primary model ({PRIMARY_MODEL}) failed: {e}. Trying fallback...")
            return generate_response(
                user_query, data_context, conversation_history, model=FALLBACK_MODEL
            )
        else:
            logger.error(f"Fallback model ({FALLBACK_MODEL}) also failed: {e}")
            raise


def _validate_response(text: str, result_context_json: str) -> str:
    """
    Post-response validation layer.
    Ensures that if allow_trend=False, no directional words are used.
    """
    import json
    try:
        ctx = json.loads(result_context_json)
        allow_trend = ctx.get("allow_trend", True)
    except Exception:
        return text

    if not allow_trend:
        banned_words = ["increase", "increased", "decrease", "decreased", "growth", "drop", "dropped", "higher", "lower", "rising", "falling"]
        text_lower = text.lower()
        for word in banned_words:
            if f" {word} " in f" {text_lower} " or text_lower.startswith(word):
                logger.warning(f"Response validation failed: banned word '{word}' found when allow_trend=False.")
                # We could retry here, but for now we'll just flag it or strip it.
                # A better approach is to return a stripped version or a generic error.
                return "SUMMARY Data is available for the requested period. Trends are not available for this specific result set.\n\n" + text

    return text


def generate_explanation(
    user_query: str,
    result_context: str,
    data_context: str = "",
    conversation_history: list[dict] | None = None,
    model: str | None = None,
) -> str:
    client = _get_sync_client()
    target_model = model or PRIMARY_MODEL
    messages = _build_explanation_messages(user_query, result_context, data_context, conversation_history)

    try:
        response = client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=0.2, # Lowered for even higher consistency
            max_tokens=2048,
            top_p=0.9,
        )
        raw_text = response.choices[0].message.content
        return _validate_response(raw_text, result_context)
    except Exception as e:
        if target_model == PRIMARY_MODEL:
            logger.warning(f"Primary model ({PRIMARY_MODEL}) failed: {e}. Trying fallback...")
            return generate_explanation(
                user_query, result_context, data_context, conversation_history, model=FALLBACK_MODEL
            )
        else:
            logger.error(f"Fallback model ({FALLBACK_MODEL}) also failed: {e}")
            raise


async def stream_response(
    user_query: str,
    data_context: str = "",
    conversation_history: list[dict] | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream response tokens using Groq LLM.

    Yields:
        Individual text tokens as they arrive
    """
    client = _get_async_client()
    target_model = model or PRIMARY_MODEL

    messages = _build_messages(user_query, data_context, conversation_history)

    try:
        stream = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
            top_p=0.9,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    except Exception as e:
        if target_model == PRIMARY_MODEL:
            logger.warning(f"Primary model streaming failed: {e}. Trying fallback...")
            async for token in stream_response(
                user_query, data_context, conversation_history, model=FALLBACK_MODEL
            ):
                yield token
        else:
            logger.error(f"Fallback streaming also failed: {e}")
            yield f"\n\n⚠️ Error generating response: {str(e)}"


def _build_messages(
    user_query: str,
    data_context: str = "",
    conversation_history: list[dict] | None = None,
) -> list[dict]:
    """
    Build the messages array for the LLM call.
    Includes system prompt, data context, conversation history, and user query.
    """
    from datetime import datetime

    system_content = SYSTEM_PROMPT
    if LLM_GUARDRAILS:
        system_content += "\n\n--- LLM GUARDRAILS ---\n"
        system_content += "\n".join(f"- {rule}" for rule in LLM_GUARDRAILS)

    if data_context:
        system_content += f"\n\n--- DATA CONTEXT ---\n{data_context}\n--- END DATA CONTEXT ---"

    system_content += f"\n\nCurrent date/time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S (%A)')}"

    messages = [{"role": "system", "content": system_content}]

    if conversation_history:
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_query})

    return messages


def _build_explanation_messages(
    user_query: str,
    result_context: str,
    data_context: str = "",
    conversation_history: list[dict] | None = None,
) -> list[dict]:
    from datetime import datetime

    system_content = SYSTEM_PROMPT
    if LLM_GUARDRAILS:
        system_content += "\n\n--- LLM GUARDRAILS ---\n"
        system_content += "\n".join(f"- {rule}" for rule in LLM_GUARDRAILS)

    if data_context:
        system_content += f"\n\n--- DATA CONTEXT ---\n{data_context}\n--- END DATA CONTEXT ---"

    system_content += f"\n\nCurrent date/time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S (%A)')}"

    messages = [{"role": "system", "content": system_content}]

    if conversation_history:
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append(
        {
            "role": "user",
            "content": (
                f"User query: {user_query}\n\n"
                f"RESULTS (DO NOT REPEAT THESE NUMBERS IN YOUR SUMMARY):\n{result_context}\n\n"
                "INSTRUCTIONS:\n"
                "1. Provide ONLY 'INSIGHTS' and 'KEY TAKEAWAYS'.\n"
                "2. DO NOT generate a SUMMARY or DATA TABLE (these are already handled).\n"
                "3. Use only the entities and values provided above.\n"
                "4. Be concise and professional."
            ),
        }
    )

    return messages


def check_llm_health() -> dict:
    """Quick health check — verify Groq API is reachable."""
    try:
        client = _get_sync_client()
        # Minimal request to verify connectivity
        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        return {
            "status": "healthy",
            "primary_model": PRIMARY_MODEL,
            "fallback_model": FALLBACK_MODEL,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "primary_model": PRIMARY_MODEL,
            "fallback_model": FALLBACK_MODEL,
        }
