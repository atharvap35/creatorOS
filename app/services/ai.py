"""Optional AI provider abstraction.

The product must be fully usable with no API key. `BuiltinProvider` is a
deterministic, template-driven writer used by default; OpenAI and Anthropic
providers are opt-in via environment variables. Every provider returns plain
text that the creator can edit before it is saved anywhere.
"""

import os
import re
from abc import ABC, abstractmethod

HOOK_PATTERNS = [
    "Stop doing {topic} until you see this",
    "I tested {topic} for 30 days — here's what actually worked",
    "The {topic} mistake costing you results",
    "3 {topic} lessons I wish I knew sooner",
    "Nobody talks about this {topic} problem",
    "Why your {topic} isn't working (and the fix)",
]


class AIProvider(ABC):
    name = "base"

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 700) -> str:
        ...

    def available(self) -> bool:
        return True


class BuiltinProvider(AIProvider):
    """Deterministic offline writer. No network, no keys, no surprises."""

    name = "builtin"

    def complete(self, prompt: str, max_tokens: int = 700) -> str:
        topic = self._topic(prompt)
        kind = self._kind(prompt)

        if "hook" in kind:
            return "\n".join(f"{i + 1}. {p.format(topic=topic)}" for i, p in enumerate(HOOK_PATTERNS[:5]))
        if "repurpos" in kind:
            return self._repurposing_plan(topic)
        if "caption" in kind:
            return (
                f"{topic}\n\n"
                "Here's what I learned building this — and the part most people skip.\n\n"
                "• The mistake that cost me the most time\n"
                "• The shortcut that actually worked\n"
                "• What I'd do differently next time\n\n"
                "Save this for later, and tell me in the comments which part you want a deep dive on."
            )
        if "script" in kind:
            return self._script(topic)
        if "follow" in kind or "email" in kind or "outreach" in kind:
            return self._follow_up(topic)
        if "summar" in kind:
            return self._summary(prompt)
        return self._outline(topic)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _topic(prompt: str) -> str:
        cleaned = re.sub(r"^(generate|write|create|draft|create an?)\s+", "", prompt.strip(), flags=re.I)
        cleaned = re.sub(r"^(hooks?|an? outline|an? script|a caption|repurposing plan)\s*(for|about|on)?\s*", "", cleaned, flags=re.I)
        return (cleaned.split("\n")[0].strip() or "this topic").strip(" .:,-")[:80]

    @staticmethod
    def _kind(prompt: str) -> str:
        lowered = prompt.lower()
        for token in ("hook", "repurpos", "caption", "script", "follow", "outreach", "summar"):
            if token in lowered:
                return token
        return "outline"

    def _outline(self, topic: str) -> str:
        return (
            f"## Outline — {topic}\n\n"
            "1. Hook (0-3s): the single line that earns attention\n"
            "2. Stakes: why this matters to the viewer right now\n"
            "3. Point 1: the main idea, one sentence each\n"
            "4. Proof: a number, a result, or a personal example\n"
            "5. Point 2: the counter-intuitive take\n"
            "6. Proof 2\n"
            "7. Recap in one line\n"
            "8. CTA: one specific ask, not a vague 'follow for more'"
        )

    def _script(self, topic: str) -> str:
        return (
            f"## Script — {topic}\n\n"
            "**Hook**\nOpen with a direct claim about {t}.\n\n"
            "**Context (10s)**\nExplain who this is for and what they'll leave with.\n\n"
            "**Body**\n"
            "- Point one with a concrete example\n"
            "- Point two with a concrete example\n"
            "- Point three: the mistake and the fix\n\n"
            "**Proof**\nShow a result — a screenshot, a number, a before/after.\n\n"
            "**Close + CTA**\nSummarise in one line, then ask for one specific action.".format(t=topic)
        )

    def _repurposing_plan(self, topic: str) -> str:
        return (
            f"## Repurposing plan — {topic}\n\n"
            "**Short-form (3 pieces)**\n"
            "1. The single strongest claim, as a 30s reel\n"
            "2. The mistake most people make, as a reel with a text hook\n"
            "3. The result/case study, as a reel with proof on screen\n\n"
            "**Written (3 pieces)**\n"
            "4. LinkedIn post — the lesson in first person\n"
            "5. X thread — one idea per post, 5 posts, hook on post 1\n"
            "6. Newsletter section — the framework version\n\n"
            "**Community (2 pieces)**\n"
            "7. Story poll — which mistake have you made?\n"
            "8. Comment reply video to the best question\n\n"
            "**Next ideas to capture**\n"
            "9. A deeper piece on the sub-point that got the most comments\n"
        )

    def _follow_up(self, topic: str) -> str:
        return (
            f"Subject: Following up — {topic}\n\n"
            "Hi there,\n\n"
            f"Shooting a quick note about {topic}. Last time we spoke, the conversation was still open, "
            "and I wanted to check in rather than go quiet.\n\n"
            "Where things stand on my side:\n"
            "• I can turn this around within the agreed window\n"
            "• I've included a short outline so you can see exactly what you'd get\n\n"
            "If the timing isn't right, a quick 'not this month' is genuinely useful — I'll follow up "
            "when it makes sense.\n\n"
            "Would either of the next two weeks work for a quick call?\n\n"
            "Best,\n"
        )

    def _summary(self, prompt: str) -> str:
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", prompt) if len(s.strip()) > 25]
        key_points = sentences[:5]
        body = "\n".join(f"- {s[:180]}" for s in key_points) or "- (paste a transcript or script to summarise)"
        return f"## Summary\n\n{body}\n\n## Angles worth reusing\n- Each point above can become one short-form piece."


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, max_tokens: int = 700) -> str:
        import httpx

        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a concise writing assistant for independent creators. Return plain, usable copy.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-latest"):
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, max_tokens: int = 700) -> str:
        import httpx

        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        blocks = response.json().get("content", [])
        return "\n".join(block.get("text", "") for block in blocks).strip()


def get_provider() -> AIProvider:
    """Pick a provider from the environment; never fail hard."""
    choice = (os.getenv("AI_PROVIDER") or "builtin").lower()
    try:
        if choice == "openai" and os.getenv("OPENAI_API_KEY"):
            return OpenAIProvider(os.environ["OPENAI_API_KEY"], os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        if choice == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
            return AnthropicProvider(os.environ["ANTHROPIC_API_KEY"], os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"))
    except Exception:
        pass
    return BuiltinProvider()


def ai_status() -> dict:
    provider = get_provider()
    return {
        "provider": provider.name,
        "builtin": provider.name == "builtin",
        "hint": (
            "Using the built-in offline writer. Set AI_PROVIDER=openai (or anthropic) with an API key to upgrade."
            if provider.name == "builtin"
            else f"Using {provider.name}."
        ),
    }
