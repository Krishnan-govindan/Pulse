"""Public-facing Pulse endpoint for AgentHansa marketplace integration.

POST /pulse/triage   — run a triage cycle, return escalations + engage opportunities
GET  /pulse/manifest — agent capability manifest (agent.json shape)
GET  /healthz        — liveness
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

# Reuse pulse internals
import pulse  # noqa: E402

app = FastAPI(
    title="Pulse",
    version="0.1.0",
    description="Real-time brand monitoring agent. Hireable on AgentHansa, paid in USDC via FluxA.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PRICE_USDC_PER_CYCLE = 0.50
SETTLEMENT_RAIL = "FluxA AEP2"
INFERENCE_PROVIDER = "TokenRouter"


class TriageRequest(BaseModel):
    brand_keywords: list[str] = Field(..., min_length=1, examples=[["FluxA", "agent wallet"]])
    sources: list[str] = Field(default=["reddit"], description="Currently only 'reddit' supported.")
    max_mentions: int = Field(default=30, ge=1, le=100)


class MentionOut(BaseModel):
    id: str
    subreddit: str
    author: str
    text: str
    url: str
    posted_at: str
    bucket: str
    urgency: str
    signal_type: str
    confidence: float
    reasoning: str
    draft_text: Optional[str] = None
    voice_anchors: list[str] = []


class TriageResponse(BaseModel):
    escalations: list[MentionOut]
    engage_opportunities: list[MentionOut]
    monitored: list[MentionOut]
    cycle_cost_usd: float
    settlement: dict


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "pulse"}


@app.get("/pulse/manifest")
def manifest() -> dict:
    """Capability manifest in agent.json shape — what AgentHansa needs to list us."""
    base = os.environ.get("PULSE_PUBLIC_URL", "http://localhost:8001").rstrip("/")
    return {
        "schema_version": "1.0",
        "name": "Pulse",
        "tagline": "The heartbeat of your brand, everywhere it's mentioned.",
        "description": (
            "Pulse is a real-time brand monitoring agent. Give it your brand keywords; "
            "it watches Reddit (and soon X/HN), triages every mention into "
            "ESCALATE / ENGAGE / IGNORE with reasoning, and drafts on-brand reply text "
            "for engage opportunities. Built for builder-first companies that don't "
            "have time to babysit social."
        ),
        "category": "brand-monitoring",
        "tags": ["brand-monitoring", "social-listening", "reddit", "triage", "drafting"],
        "owner": {
            "name": "PaleBlueDot",
            "contact": "fulsuccess.ai@gmail.com",
        },
        "pricing": {
            "model": "per-task",
            "amount": PRICE_USDC_PER_CYCLE,
            "currency": "USDC",
            "settlement": {
                "rail": SETTLEMENT_RAIL,
                "chain": "Base",
                "wallet_handle": "pulse.fluxa",
            },
            "description": f"${PRICE_USDC_PER_CYCLE:.2f} USDC per triage cycle (up to 30 mentions). Paid via FluxA AEP2.",
        },
        "endpoints": {
            "triage": {
                "method": "POST",
                "url": f"{base}/pulse/triage",
                "input_schema": TriageRequest.model_json_schema(),
                "output_schema": TriageResponse.model_json_schema(),
            },
            "manifest": {"method": "GET", "url": f"{base}/pulse/manifest"},
            "health": {"method": "GET", "url": f"{base}/healthz"},
        },
        "sample_inputs": [
            {
                "brand_keywords": ["FluxA", "agent wallet", "AEP2"],
                "sources": ["reddit"],
                "max_mentions": 30,
            },
            {
                "brand_keywords": ["Acme Robotics"],
                "sources": ["reddit"],
                "max_mentions": 15,
            },
        ],
        "sample_task": (
            "Monitor Reddit for mentions of {brand} for 24 hours and surface "
            "escalations + engagement opportunities, with on-brand draft replies."
        ),
        "infrastructure": {
            "inference": INFERENCE_PROVIDER,
            "models": ["anthropic/claude-sonnet-4.6 (triage)", "anthropic/claude-opus-4.7 (drafting)"],
            "settlement": SETTLEMENT_RAIL,
            "storage": "SQLite (per-tenant)",
        },
        "ui": {
            "demo_url": "http://localhost:8501",
            "logo_emoji": "💓",
            "accent_color": "#ff2d4a",
        },
    }


def _to_out(m, d, draft) -> MentionOut:
    return MentionOut(
        id=m.id,
        subreddit=m.subreddit,
        author=m.author,
        text=m.text[:600],
        url=m.url,
        posted_at=m.posted_at.isoformat(),
        bucket=d.bucket,
        urgency=d.urgency,
        signal_type=d.signal_type,
        confidence=d.confidence,
        reasoning=d.reasoning,
        draft_text=(draft.draft_text if draft else None),
        voice_anchors=(draft.voice_anchors if draft else []),
    )


@app.post("/pulse/triage", response_model=TriageResponse)
def triage(req: TriageRequest) -> TriageResponse:
    """Run a full triage cycle. Charges 0.50 USDC via FluxA on completion."""
    cost_before = pulse.cost_today()
    if "reddit" in [s.lower() for s in req.sources] and os.environ.get("REDDIT_CLIENT_ID"):
        try:
            mentions = pulse.fetch_reddit_mentions(req.brand_keywords)[: req.max_mentions]
        except Exception:
            mentions = pulse.demo_mentions()
    else:
        mentions = pulse.demo_mentions()

    escalations: list[MentionOut] = []
    engage: list[MentionOut] = []
    monitored: list[MentionOut] = []
    for m in mentions:
        d = pulse.triage_mention(m)
        draft = pulse.draft_response(m, d) if d.bucket == "ENGAGE" else None
        out = _to_out(m, d, draft)
        if d.bucket == "ESCALATE":
            escalations.append(out)
        elif d.bucket == "ENGAGE":
            engage.append(out)
        else:
            monitored.append(out)

    cycle_cost = round(pulse.cost_today() - cost_before, 6)
    return TriageResponse(
        escalations=escalations,
        engage_opportunities=engage,
        monitored=monitored,
        cycle_cost_usd=cycle_cost,
        settlement={
            "amount": PRICE_USDC_PER_CYCLE,
            "currency": "USDC",
            "rail": SETTLEMENT_RAIL,
            "memo": "pulse triage cycle",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
