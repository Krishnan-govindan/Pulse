"""Hand-curated brand context. Drives draft tone + ecosystem awareness."""
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
}

_REGISTRY = {"FluxA": _FLUXA, "fluxa": _FLUXA}

def load_brand_context(brand_name: str) -> dict:
    return _REGISTRY.get(brand_name, _REGISTRY.get(brand_name.lower(), _FLUXA))
