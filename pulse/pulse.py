"""
Pulse — the heartbeat of your brand, everywhere it's mentioned.
Single-file Streamlit app: Reddit ingest → TokenRouter triage → drafted replies.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / ".env")

# ----------------------------- Config ---------------------------------------

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "pulse.db"

TOKENROUTER_BASE_URL = "https://api.tokenrouter.com/v1"
TRIAGE_MODEL = "auto"
DRAFT_MODEL = "claude-opus-4-7"

BRAND = "FluxA"
BRAND_KEYWORDS = ["FluxA", "FluxAPay", "fluxapay", "AEP2"]
SUBREDDITS = ["all", "SaaS", "MachineLearning", "LocalLLaMA", "startups"]

WALLET_START_USDC = 47.32
WALLET_DECREMENT_USDC = 0.12

# Approximate per-token pricing (USD) for cost estimation.  Real billing comes
# from TokenRouter; this is just for the live spend ticker.
PRICING = {
    "auto": (3e-6, 15e-6),  # treated as sonnet-ish until response.model overrides
    "claude-opus-4-7": (15e-6, 75e-6),
    "claude-sonnet-4-6": (3e-6, 15e-6),
    "claude-haiku-4-5": (0.8e-6, 4e-6),
    "gpt-5": (5e-6, 20e-6),
    "gpt-5-mini": (0.25e-6, 1e-6),
}

# ----------------------------- Models ---------------------------------------


class Mention(BaseModel):
    id: str
    source: str
    brand: str
    author: str
    text: str
    url: str
    posted_at: str  # ISO-8601 UTC
    subreddit: Optional[str] = None


class Decision(BaseModel):
    bucket: str  # IGNORE | ENGAGE | ESCALATE
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    urgency: str  # LOW | MED | HIGH
    signal_type: str


class Draft(BaseModel):
    draft_text: str
    rationale: str
    risk_flags: list[str] = Field(default_factory=list)


# ----------------------------- Storage --------------------------------------


def db() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS mentions (
            id TEXT PRIMARY KEY, source TEXT, brand TEXT, author TEXT,
            text TEXT, url TEXT, posted_at TEXT, subreddit TEXT,
            fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS decisions (
            mention_id TEXT PRIMARY KEY, bucket TEXT, confidence REAL,
            reasoning TEXT, urgency TEXT, signal_type TEXT, decided_at TEXT
        );
        CREATE TABLE IF NOT EXISTS drafts (
            mention_id TEXT PRIMARY KEY, draft_text TEXT, rationale TEXT,
            risk_flags TEXT, status TEXT, drafted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requested_model TEXT, used_model TEXT,
            latency_ms REAL, prompt_tokens INTEGER, completion_tokens INTEGER,
            cost_usd REAL, purpose TEXT, called_at TEXT
        );
        """
    )
    return con


def upsert_mention(m: Mention) -> None:
    con = db()
    con.execute(
        """INSERT OR REPLACE INTO mentions
           (id, source, brand, author, text, url, posted_at, subreddit, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (m.id, m.source, m.brand, m.author, m.text, m.url, m.posted_at,
         m.subreddit, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


def save_decision(mention_id: str, d: Decision) -> None:
    con = db()
    con.execute(
        """INSERT OR REPLACE INTO decisions
           (mention_id, bucket, confidence, reasoning, urgency, signal_type, decided_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (mention_id, d.bucket, d.confidence, d.reasoning, d.urgency,
         d.signal_type, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


def save_draft(mention_id: str, draft: Draft, status: str = "pending") -> None:
    con = db()
    con.execute(
        """INSERT OR REPLACE INTO drafts
           (mention_id, draft_text, rationale, risk_flags, status, drafted_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (mention_id, draft.draft_text, draft.rationale,
         json.dumps(draft.risk_flags), status,
         datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


def log_llm_call(requested: str, used: str, latency_ms: float,
                 in_tok: int, out_tok: int, cost: float, purpose: str) -> None:
    con = db()
    con.execute(
        """INSERT INTO llm_calls
           (requested_model, used_model, latency_ms, prompt_tokens,
            completion_tokens, cost_usd, purpose, called_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (requested, used, latency_ms, in_tok, out_tok, cost, purpose,
         datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


def recent_calls(limit: int = 10) -> list[dict]:
    con = db()
    rows = con.execute(
        """SELECT used_model, latency_ms, cost_usd, purpose, called_at
           FROM llm_calls ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    con.close()
    return [dict(zip(["model", "latency_ms", "cost_usd", "purpose", "called_at"], r))
            for r in rows]


def spend_today() -> float:
    con = db()
    today = datetime.now(timezone.utc).date().isoformat()
    row = con.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE called_at >= ?",
        (today + "T00:00:00",),
    ).fetchone()
    con.close()
    return float(row[0] or 0.0)


def routing_split() -> tuple[float, float]:
    """Return (cheap_pct, strong_pct) of today's calls."""
    con = db()
    today = datetime.now(timezone.utc).date().isoformat()
    rows = con.execute(
        """SELECT used_model, COUNT(*) FROM llm_calls
           WHERE called_at >= ? GROUP BY used_model""",
        (today + "T00:00:00",),
    ).fetchall()
    con.close()
    if not rows:
        return (0.0, 0.0)
    total = sum(c for _, c in rows)
    strong_models = ("opus", "gpt-5")
    strong = sum(c for m, c in rows if any(s in (m or "").lower() for s in strong_models))
    return ((total - strong) / total * 100, strong / total * 100)


# ----------------------------- TokenRouter ----------------------------------


def tokenrouter():
    from openai import OpenAI
    api_key = os.environ.get("TOKENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TOKENROUTER_API_KEY not set in .env")
    return OpenAI(api_key=api_key, base_url=TOKENROUTER_BASE_URL)


def estimate_cost(model: str, in_tok: int, out_tok: int) -> float:
    key = (model or "").lower()
    for k, (pi, po) in PRICING.items():
        if k in key:
            return in_tok * pi + out_tok * po
    pi, po = PRICING["auto"]
    return in_tok * pi + out_tok * po


def call_json(messages: list[dict], model: str, purpose: str,
              max_tokens: int = 400) -> dict:
    client = tokenrouter()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        temperature=0.2,
    )
    latency_ms = (time.time() - t0) * 1000
    used_model = getattr(resp, "model", None) or model
    usage = getattr(resp, "usage", None)
    in_tok = getattr(usage, "prompt_tokens", 0) or 0
    out_tok = getattr(usage, "completion_tokens", 0) or 0
    cost = estimate_cost(used_model, in_tok, out_tok)
    log_llm_call(model, used_model, latency_ms, in_tok, out_tok, cost, purpose)
    raw = resp.choices[0].message.content or "{}"
    return _parse_json(raw)


def _parse_json(s: str) -> dict:
    s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


# ----------------------------- Triage ---------------------------------------

TRIAGE_SYSTEM = """You are Pulse, a triage agent for B2B brand monitoring. You see a public mention of FluxA (an AI agent payment platform — agent wallets, USDC settlement, MCP server monetization, AEP2 protocol). Decide:

- IGNORE: unrelated to FluxA the company (e.g., flux capacitor, flux core welding, different "FluxA"), spam, or already-resolved.
- ENGAGE: clear authentic opportunity — someone asking about agent payments / USDC / MCP monetization, comparing to FluxA, or expressing pain FluxA solves.
- ESCALATE: complaint, accusation, bug report, viral negative, or any PR risk.

Conservative: prefer ESCALATE over ENGAGE when uncertain. Prefer IGNORE over ENGAGE for noise.

Return strict JSON: {"bucket": "...", "confidence": 0.0-1.0, "reasoning": "1-2 sentences", "urgency": "LOW|MED|HIGH", "signal_type": "positive_review|customer_question|competitor_mention|pain_point|complaint|bug_report|news|irrelevant"}"""

TRIAGE_FEWSHOTS = [
    {
        "role": "user",
        "content": 'MENTION (r/welding, by u/welder42): "I love using flux core welding wire for thick steel — flux a beats flux b every time."',
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "bucket": "IGNORE",
            "confidence": 0.99,
            "reasoning": "Welding-wire context, no relation to FluxA the AI payments platform.",
            "urgency": "LOW",
            "signal_type": "irrelevant",
        }),
    },
    {
        "role": "user",
        "content": 'MENTION (r/MachineLearning, by u/ai_builder): "How do I monetize an MCP server I built? Wrapping it in a paid REST API feels gross — I want true per-call settlement so agents can just pay and consume."',
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "bucket": "ENGAGE",
            "confidence": 0.92,
            "reasoning": "Direct MCP monetization pain point — exactly FluxA's wedge.",
            "urgency": "MED",
            "signal_type": "customer_question",
        }),
    },
    {
        "role": "user",
        "content": 'MENTION (r/SaaS, by u/burned_dev): "@FluxA my agent wallet got debited 12 USDC but the AEP2 settlement returned 500. Three days, no support reply. Considering a chargeback through my issuer."',
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "bucket": "ESCALATE",
            "confidence": 0.97,
            "reasoning": "Payment failure, lost funds, and stalled support — clear PR and trust risk.",
            "urgency": "HIGH",
            "signal_type": "complaint",
        }),
    },
    {
        "role": "user",
        "content": 'MENTION (r/startups, by u/yc_lurker): "Saw something about an agent payments thing on TechCrunch the other day, can\'t remember the name."',
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "bucket": "IGNORE",
            "confidence": 0.7,
            "reasoning": "Too vague to action — no FluxA-specific signal worth a reply.",
            "urgency": "LOW",
            "signal_type": "irrelevant",
        }),
    },
]


def triage_mention(m: Mention) -> Decision:
    user_msg = (
        f'MENTION (r/{m.subreddit or "?"}, by u/{m.author}): "{m.text}"'
    )
    messages = (
        [{"role": "system", "content": TRIAGE_SYSTEM}]
        + TRIAGE_FEWSHOTS
        + [{"role": "user", "content": user_msg}]
    )
    data = call_json(messages, model=TRIAGE_MODEL, purpose="triage", max_tokens=250)
    try:
        return Decision(**data)
    except Exception:
        return Decision(
            bucket="IGNORE", confidence=0.0,
            reasoning="Triage parse failure — defaulted to IGNORE.",
            urgency="LOW", signal_type="irrelevant",
        )


# ----------------------------- Drafter --------------------------------------

DRAFT_SYSTEM = (
    "You draft a Reddit reply for FluxA — agent payment infrastructure "
    "(agent wallets, USDC settlement, MCP server monetization, AEP2). "
    "Helpful first, promotional last. Match Reddit's culture: conversational, "
    "low-key, 1-3 sentences max. Never invent product facts. Disclose affiliation "
    "if you mention FluxA. Return strict JSON: "
    '{"draft_text": "...", "rationale": "1 sentence", "risk_flags": ["..."]}'
)


def draft_response(m: Mention, d: Decision, regenerate_hint: str = "") -> Draft:
    user_msg = (
        f'MENTION (r/{m.subreddit or "?"} by u/{m.author}): "{m.text}"\n'
        f"TRIAGE: {d.bucket} / {d.signal_type} / urgency={d.urgency}\n"
        f"REASONING: {d.reasoning}\n"
        + (f"REGENERATE_HINT: {regenerate_hint}\n" if regenerate_hint else "")
        + "Write a single Reddit reply."
    )
    messages = [
        {"role": "system", "content": DRAFT_SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    data = call_json(messages, model=DRAFT_MODEL, purpose="draft", max_tokens=350)
    try:
        return Draft(**data)
    except Exception:
        return Draft(
            draft_text=data.get("draft_text", "") or "(draft failed — please retry)",
            rationale=data.get("rationale", ""),
            risk_flags=data.get("risk_flags", []) or ["draft_parse_error"],
        )


# ----------------------------- Reddit ingest --------------------------------


def fetch_reddit_mentions(brand_keywords: list[str], limit_per_sub: int = 15,
                          total_cap: int = 30) -> list[Mention]:
    import praw
    reddit = praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
        user_agent=os.environ.get("REDDIT_USER_AGENT", "pulse-monitor/0.1"),
        check_for_async=False,
    )
    seen: set[str] = set()
    out: list[Mention] = []
    for sub in SUBREDDITS:
        for kw in brand_keywords:
            try:
                results = reddit.subreddit(sub).search(
                    kw, sort="new", time_filter="month", limit=limit_per_sub,
                )
                for s in results:
                    sid = f"reddit:{s.id}"
                    if sid in seen:
                        continue
                    seen.add(sid)
                    title = (s.title or "").strip()
                    body = (getattr(s, "selftext", "") or "").strip()
                    text = (title + ("\n\n" + body if body else ""))[:1500]
                    out.append(Mention(
                        id=sid, source="reddit", brand=BRAND,
                        author=str(s.author) if s.author else "[deleted]",
                        text=text,
                        url=f"https://reddit.com{s.permalink}",
                        posted_at=datetime.fromtimestamp(
                            s.created_utc, tz=timezone.utc).isoformat(),
                        subreddit=str(s.subreddit) if s.subreddit else sub,
                    ))
                    if len(out) >= total_cap:
                        return out
            except Exception:
                continue
    return out


# ----------------------------- Demo mode ------------------------------------


def _ago(seconds: int) -> str:
    return datetime.fromtimestamp(time.time() - seconds, tz=timezone.utc).isoformat()


DEMO_MENTIONS: list[Mention] = [
    Mention(
        id="demo:escalate-1", source="reddit", brand=BRAND, author="burned_dev",
        text=("@FluxA my agent wallet got debited 14.20 USDC but the AEP2 "
              "settlement returned 500 from the merchant. Three days, no support "
              "reply. Considering a chargeback through my issuer. This is the "
              "second time this month."),
        url="https://reddit.com/r/SaaS/comments/demo1",
        posted_at=_ago(60 * 18), subreddit="SaaS",
    ),
    Mention(
        id="demo:engage-1", source="reddit", brand=BRAND, author="ai_builder",
        text=("How do I monetize an MCP server I built? Wrapping it in a paid "
              "REST API feels gross. I want true per-call settlement so agents "
              "can just pay and consume — heard FluxA does this, anyone tried it?"),
        url="https://reddit.com/r/MachineLearning/comments/demo2",
        posted_at=_ago(60 * 90), subreddit="MachineLearning",
    ),
    Mention(
        id="demo:engage-2", source="reddit", brand=BRAND, author="indie_hacker",
        text=("Building an agent that buys ad-keyword data on demand. Need "
              "real machine-to-machine USDC settlement, not Stripe with extra "
              "steps. FluxA vs Skyfire — anyone done a real bake-off in prod?"),
        url="https://reddit.com/r/startups/comments/demo3",
        posted_at=_ago(60 * 240), subreddit="startups",
    ),
    Mention(
        id="demo:ignore-1", source="reddit", brand=BRAND, author="welder42",
        text=("The flux a (sic) wire is way better than flux b for thick "
              "stainless. Don't @ me — 20 years of MIG experience here."),
        url="https://reddit.com/r/welding/comments/demo4",
        posted_at=_ago(60 * 320), subreddit="welding",
    ),
    Mention(
        id="demo:ignore-2", source="reddit", brand=BRAND, author="yc_lurker",
        text=("Saw something about an agent payments thing on TechCrunch the "
              "other day, can't remember the name. Looked interesting though, "
              "might dig in this weekend."),
        url="https://reddit.com/r/SaaS/comments/demo5",
        posted_at=_ago(60 * 480), subreddit="SaaS",
    ),
]


# ----------------------------- UI helpers -----------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --pulse-red: #ef4444;
  --pulse-red-dim: #b91c1c;
  --bg-card: #141417;
  --border: #27272a;
}

.block-container { padding-top: 1.5rem; }

.pulse-wordmark {
  font-size: 64px; font-weight: 800; letter-spacing: -0.04em;
  background: linear-gradient(135deg, #fafafa 0%, #ef4444 60%, #7f1d1d 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  margin: 0; line-height: 1;
}
.pulse-tagline { color: #a1a1aa; font-size: 15px; margin-top: 4px; letter-spacing: 0.01em; }

.brand-banner {
  display: flex; align-items: center; gap: 14px; padding: 18px 22px;
  background: linear-gradient(135deg, #1a0a0a 0%, #141417 70%);
  border: 1px solid #3f1d1d; border-radius: 14px; margin: 18px 0 8px 0;
}
.brand-name { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; color: #fafafa; }
.brand-meta { color: #a1a1aa; font-size: 13px; font-family: 'JetBrains Mono', monospace; }

@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.85); }
  70%  { box-shadow: 0 0 0 18px rgba(239, 68, 68, 0); }
  100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
}
.pulse-dot {
  width: 14px; height: 14px; background: var(--pulse-red); border-radius: 50%;
  display: inline-block; animation: pulse-ring 1.5s infinite;
}

.pill {
  display: inline-block; padding: 3px 10px; border-radius: 999px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  font-family: 'JetBrains Mono', monospace; margin-right: 6px;
}
.pill-high     { background: #450a0a; color: #fecaca; border: 1px solid #7f1d1d; }
.pill-med      { background: #451a03; color: #fed7aa; border: 1px solid #78350f; }
.pill-low      { background: #18181b; color: #a1a1aa; border: 1px solid #3f3f46; }
.pill-ignore   { background: #18181b; color: #71717a; border: 1px solid #27272a; }
.pill-engage   { background: #052e16; color: #86efac; border: 1px solid #166534; }
.pill-escalate { background: #450a0a; color: #fecaca; border: 1px solid #b91c1c; }
.pill-signal   { background: #1e293b; color: #93c5fd; border: 1px solid #1e3a8a; }

.mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #a1a1aa; }

.card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 12px; padding: 14px 16px; margin-bottom: 12px;
}
.card-escalate { border-left: 3px solid var(--pulse-red); }
.card-engage   { border-left: 3px solid #16a34a; }
.card-ignore   { border-left: 3px solid #3f3f46; opacity: 0.85; }

.mention-text { color: #e4e4e7; font-size: 13px; line-height: 1.5; margin: 8px 0; }
.mention-meta { color: #71717a; font-size: 11px; font-family: 'JetBrains Mono', monospace; }

.col-header {
  font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: #a1a1aa; margin-bottom: 10px;
  padding-bottom: 8px; border-bottom: 1px solid var(--border);
}
.col-header-escalate { color: var(--pulse-red); }
.col-header-engage   { color: #4ade80; }

.wallet {
  background: linear-gradient(135deg, #052e16 0%, #14532d 100%);
  border: 1px solid #166534; border-radius: 10px; padding: 12px 14px;
}
.wallet-label { font-size: 10px; color: #86efac; letter-spacing: 0.1em; text-transform: uppercase; }
.wallet-amount { font-family: 'JetBrains Mono', monospace; font-size: 22px;
  font-weight: 600; color: #4ade80; margin-top: 2px; }
.wallet-badge {
  display: inline-block; margin-top: 6px; padding: 2px 8px; border-radius: 4px;
  background: #052e16; color: #86efac; font-size: 9px; letter-spacing: 0.08em;
  font-family: 'JetBrains Mono', monospace; border: 1px solid #166534;
}

.tr-row {
  display: flex; justify-content: space-between; padding: 6px 0;
  border-bottom: 1px solid #27272a; font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}
.tr-row:last-child { border-bottom: none; }
.tr-model { color: #fafafa; }
.tr-meta  { color: #71717a; }

div[data-testid="stMetric"] {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px;
}
div[data-testid="stMetric"] label { color: #a1a1aa !important; font-size: 11px !important;
  letter-spacing: 0.08em; text-transform: uppercase; }

.stButton > button[kind="primary"] {
  background: var(--pulse-red); border-color: var(--pulse-red);
  font-weight: 700; letter-spacing: 0.04em; box-shadow: 0 0 30px rgba(239, 68, 68, 0.3);
}
.stButton > button[kind="primary"]:hover {
  background: var(--pulse-red-dim); border-color: var(--pulse-red-dim);
}
</style>
"""


def pill(label: str, kind: str) -> str:
    return f'<span class="pill pill-{kind}">{label}</span>'


def render_mention_card(m: Mention, d: Decision, kind: str) -> str:
    posted = m.posted_at.replace("T", " ").split(".")[0] + "Z"
    urgency_cls = {"HIGH": "high", "MED": "med", "LOW": "low"}.get(d.urgency, "low")
    return f"""
<div class="card card-{kind}">
  <div>{pill(d.urgency, urgency_cls)}{pill(d.signal_type.replace('_',' '), 'signal')}<span class="mono" style="float:right">conf {d.confidence:.2f}</span></div>
  <div class="mention-text">{_html_escape(m.text)}</div>
  <div class="mention-meta">u/{m.author} · r/{m.subreddit or '?'} · {posted} · <a href="{m.url}" target="_blank" style="color:#71717a">link</a></div>
  <div class="mono" style="margin-top:6px;color:#a1a1aa;">→ {_html_escape(d.reasoning)}</div>
</div>
"""


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ----------------------------- App ------------------------------------------


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("wallet_balance", WALLET_START_USDC)
    ss.setdefault("results", [])  # list of (Mention, Decision, Optional[Draft])
    ss.setdefault("draft_overrides", {})  # mention_id -> str
    ss.setdefault("approved", set())
    ss.setdefault("rejected", set())


def run_pulse(demo: bool) -> list[tuple[Mention, Decision, Optional[Draft]]]:
    if demo:
        mentions = list(DEMO_MENTIONS)
    else:
        try:
            mentions = fetch_reddit_mentions(BRAND_KEYWORDS)
        except Exception as e:
            st.error(f"Reddit fetch failed: {e}. Toggle Demo Mode in the sidebar.")
            return []
    if not mentions:
        st.warning("No mentions returned. Try Demo Mode or widen keywords.")
        return []

    progress = st.progress(0.0, "Triaging mentions…")
    out: list[tuple[Mention, Decision, Optional[Draft]]] = []
    for i, m in enumerate(mentions):
        upsert_mention(m)
        try:
            d = triage_mention(m)
        except Exception as e:
            d = Decision(bucket="IGNORE", confidence=0.0,
                         reasoning=f"Triage error: {e}",
                         urgency="LOW", signal_type="irrelevant")
        save_decision(m.id, d)
        draft: Optional[Draft] = None
        if d.bucket == "ENGAGE":
            try:
                draft = draft_response(m, d)
                save_draft(m.id, draft)
            except Exception as e:
                draft = Draft(draft_text=f"(draft error: {e})",
                              rationale="", risk_flags=["draft_error"])
        out.append((m, d, draft))
        progress.progress((i + 1) / len(mentions),
                          f"Triaged {i+1}/{len(mentions)} — {d.bucket}")
    progress.empty()
    return out


def sidebar() -> bool:
    st.sidebar.markdown("### ⚙️ Pulse Controls")
    demo = st.sidebar.toggle(
        "Demo Mode", value=True,
        help="Replay 5 hardcoded mentions instead of hitting Reddit. "
             "Safety net for stage WiFi.",
    )

    # Wallet
    st.sidebar.markdown("### 💸 FluxA Agent Wallet")
    bal = st.session_state.wallet_balance
    st.sidebar.markdown(
        f"""<div class="wallet">
          <div class="wallet-label">Balance</div>
          <div class="wallet-amount">{bal:.2f} USDC</div>
          <span class="wallet-badge">⚡ Powered by FluxA AEP2</span>
        </div>""",
        unsafe_allow_html=True,
    )

    # TokenRouter live panel
    st.sidebar.markdown("### 🛰️ TokenRouter — Live")
    cheap_pct, strong_pct = routing_split()
    st.sidebar.markdown(
        f"<div class='mono'>Today's spend: <b>${spend_today():.4f}</b></div>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        f"<div class='mono'>Auto-routed: "
        f"<span style='color:#86efac'>{cheap_pct:.0f}% cheap</span> / "
        f"<span style='color:#fca5a5'>{strong_pct:.0f}% strong</span></div>",
        unsafe_allow_html=True,
    )
    calls = recent_calls(10)
    if calls:
        rows = "".join(
            f"<div class='tr-row'>"
            f"<span class='tr-model'>{(c['model'] or '?')[:22]}</span>"
            f"<span class='tr-meta'>{c['latency_ms']:.0f}ms · ${c['cost_usd']:.4f}</span>"
            f"</div>"
            for c in calls
        )
        st.sidebar.markdown(f"<div style='margin-top:6px'>{rows}</div>",
                            unsafe_allow_html=True)
    else:
        st.sidebar.markdown(
            "<div class='mono' style='color:#52525b'>No calls yet. Hit "
            "<b>RUN PULSE</b>.</div>",
            unsafe_allow_html=True,
        )

    return demo


def header() -> None:
    st.markdown(
        """<div style="display:flex;align-items:flex-end;gap:18px;">
            <div class="pulse-wordmark">💓 Pulse</div>
        </div>
        <div class="pulse-tagline">The heartbeat of your brand, everywhere it's mentioned.</div>""",
        unsafe_allow_html=True,
    )


def metric_row(results: list[tuple[Mention, Decision, Optional[Draft]]]) -> None:
    today_count = len(results)
    engage = sum(1 for _, d, _ in results if d.bucket == "ENGAGE")
    escalate = sum(1 for _, d, _ in results if d.bucket == "ESCALATE")
    spend = spend_today()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mentions Today", today_count)
    c2.metric("Engage Opportunities", engage)
    c3.metric("Escalations", escalate, delta=("⚠ attention" if escalate else None),
              delta_color="inverse")
    c4.metric("TokenRouter Spend Today", f"${spend:.4f}")


def brand_banner(results) -> None:
    count = len(results)
    st.markdown(
        f"""<div class="brand-banner">
          <span class="pulse-dot"></span>
          <div>
            <div class="brand-name">FluxA</div>
            <div class="brand-meta">{count} mentions in this run · agent payments · USDC · MCP · AEP2</div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_columns(results: list[tuple[Mention, Decision, Optional[Draft]]]) -> None:
    escalations = [(m, d, dr) for m, d, dr in results if d.bucket == "ESCALATE"]
    engages = [(m, d, dr) for m, d, dr in results if d.bucket == "ENGAGE"]
    monitored = [(m, d, dr) for m, d, dr in results if d.bucket == "IGNORE"]

    col_e, col_g, col_m = st.columns(3)

    with col_e:
        st.markdown(
            f'<div class="col-header col-header-escalate">'
            f'🚨 Escalations ({len(escalations)})</div>',
            unsafe_allow_html=True,
        )
        if not escalations:
            st.markdown('<div class="mono" style="color:#52525b">— clean —</div>',
                        unsafe_allow_html=True)
        for m, d, _ in escalations:
            st.markdown(render_mention_card(m, d, "escalate"), unsafe_allow_html=True)

    with col_g:
        st.markdown(
            f'<div class="col-header col-header-engage">'
            f'💬 Engage Queue ({len(engages)})</div>',
            unsafe_allow_html=True,
        )
        if not engages:
            st.markdown('<div class="mono" style="color:#52525b">— quiet —</div>',
                        unsafe_allow_html=True)
        for m, d, draft in engages:
            render_engage_card(m, d, draft)

    with col_m:
        st.markdown(
            f'<div class="col-header">👁️ Monitored ({len(monitored)})</div>',
            unsafe_allow_html=True,
        )
        if not monitored:
            st.markdown('<div class="mono" style="color:#52525b">— none —</div>',
                        unsafe_allow_html=True)
        for m, d, _ in monitored:
            st.markdown(render_mention_card(m, d, "ignore"), unsafe_allow_html=True)


def render_engage_card(m: Mention, d: Decision, draft: Optional[Draft]) -> None:
    ss = st.session_state
    if m.id in ss.approved:
        status_pill = pill("APPROVED", "engage")
    elif m.id in ss.rejected:
        status_pill = pill("REJECTED", "ignore")
    else:
        status_pill = ""

    st.markdown(render_mention_card(m, d, "engage"), unsafe_allow_html=True)

    if not draft:
        st.markdown('<div class="mono" style="color:#71717a">No draft yet.</div>',
                    unsafe_allow_html=True)
        return

    current_text = ss.draft_overrides.get(m.id, draft.draft_text)
    new_text = st.text_area(
        f"Draft reply — u/{m.author} {status_pill}",
        value=current_text,
        key=f"draft_text_{m.id}",
        height=110,
        label_visibility="collapsed",
    )
    if new_text != current_text:
        ss.draft_overrides[m.id] = new_text

    if draft.risk_flags:
        st.markdown(
            "<div class='mono' style='color:#fca5a5;margin-top:-6px;'>⚠ "
            + " · ".join(draft.risk_flags) + "</div>",
            unsafe_allow_html=True,
        )

    b1, b2, b3 = st.columns([1, 1, 1])
    if b1.button("✅ Approve & Copy", key=f"approve_{m.id}",
                 use_container_width=True):
        ss.approved.add(m.id)
        ss.wallet_balance = max(0.0, ss.wallet_balance - WALLET_DECREMENT_USDC)
        save_draft(m.id, Draft(
            draft_text=ss.draft_overrides.get(m.id, draft.draft_text),
            rationale=draft.rationale, risk_flags=draft.risk_flags,
        ), status="approved")
        st.toast(f"✓ {WALLET_DECREMENT_USDC:.2f} USDC settled via FluxA AEP2",
                 icon="💸")
        st.rerun()
    if b2.button("✏️ Regenerate", key=f"regen_{m.id}",
                 use_container_width=True):
        with st.spinner("Regenerating…"):
            try:
                new = draft_response(m, d, regenerate_hint="Try a different angle, more concise.")
                ss.draft_overrides.pop(m.id, None)
                # update results in place
                for i, (mm, dd, _) in enumerate(ss.results):
                    if mm.id == m.id:
                        ss.results[i] = (mm, dd, new)
                save_draft(m.id, new)
            except Exception as e:
                st.error(f"Regenerate failed: {e}")
        st.rerun()
    if b3.button("❌ Reject", key=f"reject_{m.id}",
                 use_container_width=True):
        ss.rejected.add(m.id)
        save_draft(m.id, draft, status="rejected")
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Pulse", page_icon="💓", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()

    demo = sidebar()
    header()

    metric_row(st.session_state.results)
    brand_banner(st.session_state.results)

    btn_col, _ = st.columns([1, 3])
    if btn_col.button("🔴 RUN PULSE NOW", type="primary",
                      use_container_width=True):
        # Reset per-run state
        st.session_state.draft_overrides = {}
        st.session_state.approved = set()
        st.session_state.rejected = set()
        with st.status("Listening…", expanded=False) as status:
            results = run_pulse(demo=demo)
            status.update(label=f"Triaged {len(results)} mentions ✓",
                          state="complete")
        st.session_state.results = results
        st.rerun()

    if st.session_state.results:
        st.divider()
        render_columns(st.session_state.results)
    else:
        st.markdown(
            "<div class='mono' style='color:#52525b;margin-top:24px;'>"
            "Hit <b>RUN PULSE NOW</b> to start listening. "
            "Demo Mode is on by default — toggle off in the sidebar to hit live Reddit.</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
