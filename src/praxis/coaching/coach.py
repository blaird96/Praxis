"""Coaching system prompt construction and OpenAI chat-completions streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from praxis.errors import PraxisError
from praxis.models import Assignment, CheckResult

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 30.0

# Keep the coach honest: it can see the assignment and the last check result,
# but it must never fabricate having run the student's code itself.
_GROUND_RULES = """\
You are Praxis Coach, an on-the-side mentor for a hands-on technical training \
exercise (Git, Docker, or Kubernetes). Act as a coach, not an answer key:

- Ask guiding questions and explain the underlying concepts before giving away \
a solution outright.
- Prefer small nudges (a command to inspect state, a concept to look up) over \
dumping the full solution, unless the student explicitly asks for the direct \
answer or is clearly stuck after a few exchanges.
- You cannot see the student's terminal or repository in real time, and you \
never actually run commands yourself. Only the "Check" button in the app can \
truly verify progress - never claim to have run Check or to know the exercise \
passed unless that information is given to you below.
- If the objectives below show an objective as failing, help the student reason \
about why, using the failure detail if present.
- Keep responses focused and concise; this is a sidebar chat, not a lecture.
"""


def build_system_prompt(
    assignment: Assignment,
    module: str,
    scenario_id: str,
    difficulty: str | None,
    concepts: list[str],
    check: CheckResult | None,
) -> str:
    lines = [
        _GROUND_RULES,
        "",
        f"Module: {module}",
        f"Scenario: {scenario_id}",
    ]
    if difficulty:
        lines.append(f"Difficulty: {difficulty}")
    if concepts:
        lines.append(f"Concepts: {', '.join(concepts)}")
    lines.extend(
        [
            "",
            f"Assignment: {assignment.title}",
            assignment.summary,
        ]
    )
    if assignment.objectives:
        lines.append("")
        lines.append("Objectives (as given to the student):")
        lines.extend(f"- {item}" for item in assignment.objectives)

    if check is not None:
        lines.append("")
        lines.append(
            f"Most recent Check result: {'PASSED' if check.passed else 'NOT PASSED'}"
        )
        for objective in check.objectives:
            status = "PASS" if objective.passed else "FAIL"
            detail = f" ({objective.detail})" if objective.detail else ""
            lines.append(f"  [{status}] {objective.description}{detail}")
    else:
        lines.append("")
        lines.append("The student has not run Check yet during this session.")

    return "\n".join(lines)


class CoachApiError(PraxisError):
    """The OpenAI API call failed (auth, network, rate limit, etc.)."""


def _extract_delta_content(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) else None


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream assistant response text chunks from OpenAI chat completions."""
    payload = {"model": model, "messages": messages, "stream": True}
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST", OPENAI_CHAT_COMPLETIONS_URL, json=payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise CoachApiError(
                        f"OpenAI request failed ({response.status_code}): "
                        f"{body.decode('utf-8', errors='replace')[:300]}"
                    )
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    content = _extract_delta_content(chunk)
                    if content:
                        yield content
    except httpx.HTTPError as exc:
        raise CoachApiError(f"Could not reach OpenAI: {exc}") from exc


async def test_connection(api_key: str, model: str) -> None:
    """Minimal, cheap request to confirm the key/model work. Raises on failure."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                OPENAI_CHAT_COMPLETIONS_URL, json=payload, headers=headers
            )
    except httpx.HTTPError as exc:
        raise CoachApiError(f"Could not reach OpenAI: {exc}") from exc

    if response.status_code != 200:
        detail = response.text[:300]
        raise CoachApiError(f"OpenAI request failed ({response.status_code}): {detail}")
