"""Hand-curated brand context for the AgentHackathon ecosystem."""
from __future__ import annotations

_FLUXA = {
    "name": "FluxA",
    "one_liner": (
        "The native payment layer for proactive AI agents — agent wallets, "
        "USDC settlement on Base, embedded payments in MCP/A2A calls via AEP2 protocol."
    ),
    "key_products": [
        "FluxA Agent Wallet — co-wallet for AI agents",
        "AgentCard — single-use virtual cards for agents",
        "FluxA Monetize — turn MCP servers into paid endpoints",
        "AEP2 Protocol — embedded payment mandates in agent calls",
        "OneShot Skill — one-time paid skills for agents",
    ],
    "ecosystem_partners": {
        "TokenRouter": (
            "PaleBlueDot's unified inference router — 60+ models through one "
            "OpenAI-compatible API. FluxA agents often use TokenRouter as their LLM layer."
        ),
        "AgentHansa": (
            "Marketplace where agents complete real B2B tasks for USDC. "
            "FluxA is the payment rail."
        ),
        "BotLearn": (
            "Bot University — agents learn skills, FluxA handles their economic activity."
        ),
    },
    "tone": (
        "Technical, builder-focused, no corporate fluff. Sentences are short. "
        "Confident but not hype-y."
    ),
    "voice_samples": [
        "Give your agent a co-wallet. Set one budget, get everything done.",
        "Make every agent interaction into a measurable, priceable transaction.",
        "Zero-fee stablecoin micropayments. AI autonomous quote-pay-receipt.",
    ],
    "banned_phrases": [
        "leverage", "synergy", "revolutionize", "cutting-edge",
        "in this digital age", "let's talk", "reach out",
    ],
    "preferred_phrases": [
        "agent-native", "payment rail", "MCP-monetized",
        "settles in USDC", "agent wallet",
    ],
    "what_to_never_claim": [
        "Do not invent specific transaction fees, latency numbers, or partnership names not listed above",
        "Do not promise integrations with services not in ecosystem_partners",
        "Do not make legal or compliance claims about USDC or Base",
    ],
    "signature": "—FluxA",
    "accent_color": "#ff2d4a",
    "emoji": "💓",
    "search_keywords": ["FluxA", "AEP2", "agent wallet", "AgentCard", "FluxA Monetize"],
}

_TOKENROUTER = {
    "name": "TokenRouter",
    "one_liner": (
        "PaleBlueDot's unified inference router — 60+ frontier models through one "
        "OpenAI-compatible API, with auto-routing across cost/quality lanes and built-in fallbacks."
    ),
    "key_products": [
        "TokenRouter API — drop-in OpenAI-compatible endpoint",
        "Auto-routing — picks the cheapest model that meets your quality bar",
        "Provider fallback — silently fails over when a provider is down",
        "Spend dashboard — per-call cost + latency + provider attribution",
    ],
    "ecosystem_partners": {
        "FluxA": (
            "Agent payment platform. FluxA agents commonly use TokenRouter "
            "as their inference layer."
        ),
        "AgentHansa": (
            "Marketplace for agents. AgentHansa-listed agents route inference "
            "through TokenRouter to keep costs predictable."
        ),
        "BotLearn": (
            "Bot University. Skill-trained agents use TokenRouter to call models "
            "during execution."
        ),
    },
    "tone": (
        "Developer-first, performance-oriented. Talk in p50/p99, $/1M tokens, "
        "and concrete provider names. No marketing fluff."
    ),
    "voice_samples": [
        "Drop-in OpenAI-compatible. Change the base_url, route 60+ models.",
        "Auto-routing picks the cheapest model that hits your quality bar.",
        "When Anthropic 503s, your call doesn't.",
    ],
    "banned_phrases": [
        "leverage", "synergy", "revolutionize", "best-in-class",
        "harness the power", "AI-powered",
    ],
    "preferred_phrases": [
        "auto-routed", "drop-in OpenAI-compatible", "per-call cost",
        "provider fallback", "$/1M tokens",
    ],
    "what_to_never_claim": [
        "Do not invent specific p50/p99 latency numbers",
        "Do not promise specific model availability we don't actually have",
        "Do not undercut a provider's posted pricing without data",
    ],
    "signature": "—TokenRouter",
    "accent_color": "#5b8def",
    "emoji": "🛰",
    "search_keywords": ["TokenRouter", "PaleBlueDot", "model routing", "LLM gateway"],
}

_AGENTHANSA = {
    "name": "AgentHansa",
    "one_liner": (
        "The first economy for agents — a marketplace where AI agents complete "
        "real B2B tasks for USDC. List your agent, browse open quests, get paid."
    ),
    "key_products": [
        "Agent listings — register an agent with a manifest, pricing, and endpoint",
        "Quests — open B2B tasks agents can pick up and complete",
        "USDC payouts — settled per task, no invoicing",
        "Reputation — on-chain track record of completed quests",
    ],
    "ecosystem_partners": {
        "FluxA": "The payment rail — every quest payout settles via FluxA in USDC.",
        "TokenRouter": "Listed agents use TokenRouter for cost-controlled inference.",
        "BotLearn": "Agents trained at BotLearn list their skills on AgentHansa.",
    },
    "tone": (
        "Marketplace voice — practical, builder-focused, agent-first. "
        "Talk about quests, listings, payouts. No fluff."
    ),
    "voice_samples": [
        "List your agent. Pick up quests. Get paid in USDC.",
        "The first economy where agents earn.",
        "From manifest to first payout in under 10 minutes.",
    ],
    "banned_phrases": [
        "leverage", "synergy", "revolutionize", "Web3 platform",
        "decentralized future",
    ],
    "preferred_phrases": [
        "list your agent", "open quest", "USDC payout", "agent reputation",
    ],
    "what_to_never_claim": [
        "Do not promise specific quest volume or payout amounts",
        "Do not make tax/regulatory claims about agent income",
    ],
    "signature": "—AgentHansa",
    "accent_color": "#3ddc84",
    "emoji": "🏛",
    "search_keywords": ["AgentHansa", "agent marketplace", "agent quest"],
}

_BOTLEARN = {
    "name": "BotLearn",
    "one_liner": (
        "Bot University — where agents learn skills. Take a course, pass the eval, "
        "ship the skill to your agent."
    ),
    "key_products": [
        "Skill courses — short, eval-graded curricula for agent capabilities",
        "Skill packs — drop-in skills your agent can install",
        "Agent transcripts — verifiable record of which skills your agent has passed",
        "Instructor mode — teach a skill, get paid when agents enroll",
    ],
    "ecosystem_partners": {
        "FluxA": "Course payments and instructor payouts settle via FluxA in USDC.",
        "TokenRouter": "Skill execution at runtime routes through TokenRouter.",
        "AgentHansa": "BotLearn-certified skills surface on agent listings.",
    },
    "tone": (
        "Educational but tight. Sounds like a sharp instructor, not a brochure. "
        "Concrete skills, concrete evals, concrete outcomes."
    ),
    "voice_samples": [
        "Your agent doesn't know SQL. Teach it in 20 minutes.",
        "Pass the eval. Ship the skill. Earn the badge.",
        "Skills your agent can actually run, not vibes.",
    ],
    "banned_phrases": [
        "leverage", "synergy", "transformative", "next-gen",
        "AI-powered learning", "learn at your own pace",
    ],
    "preferred_phrases": [
        "skill course", "eval-graded", "skill pack", "agent transcript",
    ],
    "what_to_never_claim": [
        "Do not promise specific job-placement outcomes from skills",
        "Do not invent skill names or course catalog entries",
    ],
    "signature": "—BotLearn",
    "accent_color": "#ffb547",
    "emoji": "🎓",
    "search_keywords": ["BotLearn", "Bot University", "agent skill", "agent training"],
}

_BRANDS = [_FLUXA, _TOKENROUTER, _AGENTHANSA, _BOTLEARN]
_REGISTRY = {b["name"]: b for b in _BRANDS}
_REGISTRY.update({k.lower(): v for k, v in list(_REGISTRY.items())})


def load_brand_context(brand_name: str) -> dict:
    return _REGISTRY.get(brand_name) or _REGISTRY.get(brand_name.lower(), _FLUXA)


def all_brands() -> list[dict]:
    return list(_BRANDS)


def brand_names() -> list[str]:
    return [b["name"] for b in _BRANDS]
