"""Pulse — real-time brand monitoring agent for FluxA."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from core.brand_context import all_brands, brand_names, load_brand_context

load_dotenv()

# ────────────────────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────────────────────
DEFAULT_BRAND = "FluxA"  # used as fallback if no brand selected
SUBREDDITS = ["all", "SaaS", "MachineLearning", "LocalLLaMA", "startups"]
DB_PATH = Path(__file__).parent / "pulse.db"

TOKENROUTER_BASE_URL = "https://api.tokenrouter.com/v1"
TRIAGE_MODEL = "anthropic/claude-sonnet-4.6"  # cheap/fast lane
DRAFT_MODEL = "anthropic/claude-opus-4.7"     # strong/quality lane

ACCENT = "#ff2d4a"
ACCENT_DIM = "#7a1422"
BG = "#0a0a0c"
PANEL = "#13131a"
BORDER = "#23232e"
TEXT = "#e8e8ee"
MUTED = "#8a8a98"
GREEN = "#3ddc84"

st.set_page_config(
    page_title="Pulse — Brand Heartbeat",
    page_icon="💓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ────────────────────────────────────────────────────────────────────────────
# Styling
# ────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <style>
    :root {{
        --accent: {ACCENT};
        --accent-dim: {ACCENT_DIM};
        --bg: {BG};
        --panel: {PANEL};
        --border: {BORDER};
        --text: {TEXT};
        --muted: {MUTED};
        --green: {GREEN};
    }}
    .stApp {{ background: var(--bg); color: var(--text); }}
    section[data-testid="stSidebar"] {{ background: #08080b; border-right: 1px solid var(--border); }}
    h1, h2, h3, h4 {{ color: var(--text); letter-spacing: -0.01em; }}
    .pulse-wordmark {{
        font-size: 3.2rem; font-weight: 800; letter-spacing: -0.04em;
        background: linear-gradient(90deg, #fff 10%, var(--accent) 80%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin: 0; line-height: 1;
    }}
    .pulse-tagline {{ color: var(--muted); font-size: 0.95rem; margin-top: 0.25rem; }}
    .brand-banner {{
        background: linear-gradient(90deg, rgba(255,45,74,0.12) 0%, rgba(255,45,74,0.02) 100%);
        border: 1px solid var(--accent-dim);
        border-radius: 14px; padding: 1rem 1.4rem; margin: 1.2rem 0;
        display: flex; align-items: center; gap: 1rem;
    }}
    .brand-name {{ font-size: 1.6rem; font-weight: 700; color: #fff; }}
    .brand-meta {{ color: var(--muted); font-size: 0.9rem; }}
    .pulse-dot {{
        width: 12px; height: 12px; border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 0 0 rgba(255,45,74,0.7);
        animation: pulse 1.4s infinite;
        display: inline-block;
    }}
    @keyframes pulse {{
        0%   {{ box-shadow: 0 0 0 0 rgba(255,45,74,0.7); transform: scale(0.95); }}
        70%  {{ box-shadow: 0 0 0 14px rgba(255,45,74,0); transform: scale(1.05); }}
        100% {{ box-shadow: 0 0 0 0 rgba(255,45,74,0); transform: scale(0.95); }}
    }}
    .metric-card {{
        background: var(--panel); border: 1px solid var(--border);
        border-radius: 14px; padding: 1rem 1.2rem;
    }}
    .metric-label {{ color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; }}
    .metric-value {{ color: #fff; font-size: 1.9rem; font-weight: 700; margin-top: 0.3rem; font-feature-settings: "tnum"; }}
    .metric-value.mono {{ font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .pill {{
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em;
        text-transform: uppercase; margin-right: 4px;
    }}
    .pill-low    {{ background: rgba(61,220,132,0.12); color: var(--green); border: 1px solid rgba(61,220,132,0.3); }}
    .pill-med    {{ background: rgba(255,193,7,0.10); color: #ffc107;  border: 1px solid rgba(255,193,7,0.3); }}
    .pill-high   {{ background: rgba(255,45,74,0.14); color: var(--accent); border: 1px solid var(--accent-dim); }}
    .pill-signal {{ background: #1a1a22; color: var(--muted); border: 1px solid var(--border); }}
    .mention-card {{
        background: var(--panel); border: 1px solid var(--border);
        border-radius: 12px; padding: 0.9rem 1rem; margin-bottom: 0.8rem;
    }}
    .mention-card.escalate {{ border-left: 3px solid var(--accent); }}
    .mention-card.engage   {{ border-left: 3px solid var(--green); }}
    .mention-meta {{
        color: var(--muted); font-size: 0.78rem; margin-bottom: 0.4rem;
        font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    .mention-text {{ color: var(--text); font-size: 0.92rem; line-height: 1.45; }}
    .mention-reasoning {{ color: var(--muted); font-size: 0.82rem; margin-top: 0.5rem; font-style: italic; }}
    .wallet-card {{
        background: linear-gradient(135deg, #0d2618 0%, #061410 100%);
        border: 1px solid rgba(61,220,132,0.25);
        border-radius: 12px; padding: 1rem; margin: 0.5rem 0;
    }}
    .wallet-label {{ color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }}
    .wallet-balance {{
        color: var(--green); font-size: 1.6rem; font-weight: 700;
        font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
        margin-top: 0.2rem;
    }}
    .powered-by {{
        display: inline-block; margin-top: 0.5rem;
        background: rgba(61,220,132,0.10); color: var(--green);
        padding: 2px 8px; border-radius: 6px; font-size: 0.7rem; font-weight: 600;
    }}
    .tr-row {{
        display: flex; justify-content: space-between; gap: 0.5rem;
        padding: 6px 8px; border-bottom: 1px solid var(--border);
        font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 0.75rem; color: var(--muted);
    }}
    .tr-row:last-child {{ border-bottom: none; }}
    .stButton>button {{
        background: var(--accent); color: #fff; border: none;
        font-weight: 600; border-radius: 10px; padding: 0.5rem 1rem;
    }}
    .stButton>button:hover {{ background: #ff556e; color: #fff; }}
    .run-button .stButton>button {{
        font-size: 1.05rem; padding: 0.85rem 1.4rem;
        box-shadow: 0 0 24px rgba(255,45,74,0.35);
    }}
    .col-header {{
        font-size: 0.85rem; color: var(--muted);
        text-transform: uppercase; letter-spacing: 0.1em;
        border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 0.8rem;
    }}
    .col-header.escalate {{ color: var(--accent); }}
    .col-header.engage   {{ color: var(--green); }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ────────────────────────────────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────────────────────────────────
class Mention(BaseModel):
    id: str
    source: str
    brand: str
    author: str
    text: str
    url: str
    posted_at: datetime
    subreddit: str

class Decision(BaseModel):
    bucket: Literal["IGNORE", "ENGAGE", "ESCALATE"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    urgency: Literal["LOW", "MED", "HIGH"]
    signal_type: str

class Draft(BaseModel):
    draft_text: str
    rationale: str
    risk_flags: list[str] = []
    voice_anchors: list[str] = Field(
        default_factory=list,
        description="1-2 voice_samples or preferred_phrases from brand context this draft drew from.",
    )

# ────────────────────────────────────────────────────────────────────────────
# Storage
# ────────────────────────────────────────────────────────────────────────────
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, model_requested TEXT, model_used TEXT,
            kind TEXT, latency_ms INTEGER,
            prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL
        )""")
    conn.commit()
    return conn

def log_call(model_req: str, model_used: str, kind: str, latency_ms: int,
             p_tok: int, c_tok: int, cost: float) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO calls(ts, model_requested, model_used, kind, latency_ms, prompt_tokens, completion_tokens, cost_usd) VALUES(?,?,?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), model_req, model_used, kind, latency_ms, p_tok, c_tok, cost),
    )
    conn.commit()

def recent_calls(n: int = 10) -> list[tuple]:
    return db().execute(
        "SELECT ts, model_requested, model_used, kind, latency_ms, cost_usd FROM calls ORDER BY id DESC LIMIT ?",
        (n,),
    ).fetchall()

def cost_today() -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    row = db().execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE ts LIKE ?",
        (f"{today}%",),
    ).fetchone()
    return float(row[0] or 0.0)

def routing_split() -> tuple[int, int, int]:
    rows = db().execute("SELECT model_used FROM calls").fetchall()
    cheap = strong = total = 0
    for (m,) in rows:
        total += 1
        m_lower = (m or "").lower()
        if "opus" in m_lower or "gpt-4" in m_lower:
            strong += 1
        else:
            cheap += 1
    return cheap, strong, total

# ────────────────────────────────────────────────────────────────────────────
# TokenRouter client
# ────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def tokenrouter_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("TOKENROUTER_API_KEY", ""),
        base_url=TOKENROUTER_BASE_URL,
    )

def _completion(model: str, system: str, user: str, kind: str,
                json_mode: bool = True, max_tokens: int = 400) -> tuple[str, dict]:
    client = tokenrouter_client()
    t0 = time.perf_counter()
    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.2 if kind == "triage" else 0.7,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        resp = client.chat.completions.create(**kwargs)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    cost = float(getattr(usage, "cost", 0.0) or getattr(usage, "total_cost", 0.0) or 0.0)
    if cost == 0.0:
        cost = (usage.prompt_tokens * 3.0 + usage.completion_tokens * 15.0) / 1_000_000
    log_call(model, resp.model or model, kind, latency_ms,
             usage.prompt_tokens, usage.completion_tokens, cost)
    return text, {"latency_ms": latency_ms, "cost": cost, "model_used": resp.model or model}

def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)

# ────────────────────────────────────────────────────────────────────────────
# Triage
# ────────────────────────────────────────────────────────────────────────────
def _build_triage_system(ctx: dict) -> str:
    name = ctx["name"]
    one_liner = ctx["one_liner"]
    products = "; ".join(ctx["key_products"][:3])
    return f"""You are Pulse, a triage agent for B2B brand monitoring. You see a public mention possibly related to {name} ({one_liner}). Key products: {products}. Decide:

- IGNORE: unrelated to {name} the company, spam, or already-resolved. Watch for false positives — generic words that match the brand keyword but mean something else.
- ENGAGE: clear authentic opportunity — someone asking about {name}'s problem space, comparing to {name}, or expressing pain {name} solves.
- ESCALATE: complaint, accusation, bug report, viral negative, or any PR risk against {name}.

Conservative: prefer ESCALATE over ENGAGE when uncertain. Prefer IGNORE over ENGAGE for noise.

Return strict JSON: {{"bucket": "...", "confidence": 0.0-1.0, "reasoning": "1-2 sentences", "urgency": "LOW|MED|HIGH", "signal_type": "positive_review|customer_question|competitor_mention|pain_point|complaint|bug_report|news|irrelevant"}}

Format examples (these use FluxA — apply the same logic to {name}):

Mention: "Just spent 3 hours dialing in flux core welding settings on my Lincoln, what a pain."
Output: {{"bucket":"IGNORE","confidence":0.98,"reasoning":"Welding terminology — 'flux core' is a wire type, no relation to the brand.","urgency":"LOW","signal_type":"irrelevant"}}

Mention: "Building an MCP server for code review, want to charge per call but Stripe metering is brutal. Anything purpose-built for monetizing MCP tools?"
Output: {{"bucket":"ENGAGE","confidence":0.93,"reasoning":"Direct ICP signal: builder asking about the exact problem the brand solves.","urgency":"MED","signal_type":"customer_question"}}

Mention: "@FluxA your USDC settlement just bricked our prod agent for 40 min. Ticket #2811 — radio silence for 6 hours. unacceptable."
Output: {{"bucket":"ESCALATE","confidence":0.99,"reasoning":"Public revenue-impacting outage complaint with silence — high PR + churn risk.","urgency":"HIGH","signal_type":"complaint"}}

Mention: "saw a thing called FluxA somewhere, sounded interesting, idk what it does though"
Output: {{"bucket":"IGNORE","confidence":0.7,"reasoning":"Vague tangential mention with no actionable signal.","urgency":"LOW","signal_type":"irrelevant"}}
"""


def triage_mention(m: Mention) -> Decision:
    ctx = load_brand_context(m.brand)
    system = _build_triage_system(ctx)
    user = f"Brand under monitoring: {m.brand}\nMention from r/{m.subreddit} by u/{m.author}:\n\n{m.text}"
    text, _ = _completion(TRIAGE_MODEL, system, user, kind="triage", max_tokens=300)
    try:
        data = _parse_json(text)
        return Decision(**data)
    except Exception as e:
        return Decision(
            bucket="IGNORE", confidence=0.5,
            reasoning=f"parse-fallback: {type(e).__name__}",
            urgency="LOW", signal_type="irrelevant",
        )

# ────────────────────────────────────────────────────────────────────────────
# Drafter
# ────────────────────────────────────────────────────────────────────────────
def _build_draft_system(ctx: dict) -> str:
    products = "\n".join(f"  - {p}" for p in ctx["key_products"])
    partners = "\n".join(f"  - {k}: {v}" for k, v in ctx["ecosystem_partners"].items())
    voice = "\n".join(f'  - "{s}"' for s in ctx["voice_samples"])
    banned = ", ".join(ctx["banned_phrases"])
    preferred = ", ".join(ctx["preferred_phrases"])
    never = "\n".join(f"  - {n}" for n in ctx["what_to_never_claim"])
    return f"""You draft a Reddit reply for {ctx['name']}. Below is {ctx['name']}'s brand context, ecosystem position, voice samples, and rules. Use this context to draft a reply that sounds authentically like {ctx['name']} — short, technical, builder-focused, no corporate-speak.

ONE-LINER: {ctx['one_liner']}

KEY PRODUCTS:
{products}

ECOSYSTEM PARTNERS:
{partners}

TONE: {ctx['tone']}

VOICE SAMPLES (mimic this cadence):
{voice}

PREFERRED PHRASES: {preferred}
BANNED PHRASES (never use): {banned}

NEVER CLAIM:
{never}

Rules:
- Helpful first, promotional last. Mention {ctx['name']} only if it genuinely solves the person's problem.
- 1-3 sentences max. Reddit voice — conversational, not formal.
- If the question touches on inference / LLM / model routing, you may mention that {ctx['name']} agents commonly use TokenRouter as their LLM layer (since they're ecosystem partners). Don't oversell it.
- Never invent product facts. Use only what's in the brand context above.
- In rationale, cite 1-2 voice_samples or preferred_phrases you anchored on, verbatim.
- Populate voice_anchors with those same 1-2 quoted strings.

Return JSON: {{"draft_text": "...", "rationale": "...", "risk_flags": ["..."], "voice_anchors": ["...", "..."]}}"""


def draft_response(m: Mention, d: Decision) -> Draft:
    ctx = load_brand_context(m.brand)
    system = _build_draft_system(ctx)
    user = (
        f"Subreddit: r/{m.subreddit}\nAuthor: u/{m.author}\n"
        f"Mention: {m.text}\n\nTriage: {d.bucket} ({d.signal_type}, {d.urgency})\n"
        f"Reasoning: {d.reasoning}\n\nDraft a Reddit reply."
    )
    text, _ = _completion(DRAFT_MODEL, system, user, kind="draft", max_tokens=400)
    try:
        return Draft(**_parse_json(text))
    except Exception:
        return Draft(
            draft_text=text.strip()[:400],
            rationale="raw model output (json parse failed)",
            risk_flags=["unparsed_output"],
            voice_anchors=[],
        )

# ────────────────────────────────────────────────────────────────────────────
# Slack push
# ────────────────────────────────────────────────────────────────────────────
def send_to_slack(m: Mention, d: Decision) -> tuple[bool, str]:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    payload = {
        "text": f"🚨 Pulse Escalation · {m.brand} · r/{m.subreddit} ({d.urgency}/{d.signal_type})",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"🚨 Pulse Escalation · {m.brand}"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Urgency*\n`{d.urgency}`"},
                {"type": "mrkdwn", "text": f"*Signal*\n`{d.signal_type}`"},
                {"type": "mrkdwn", "text": f"*Subreddit*\nr/{m.subreddit}"},
                {"type": "mrkdwn", "text": f"*Author*\nu/{m.author}"},
            ]},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f">{m.text[:480].replace(chr(10), ' ')}"}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"_Pulse triage: {d.reasoning}_"}
            ]},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "View on Reddit"},
                 "url": m.url, "style": "danger"}
            ]},
        ],
    }
    if not webhook:
        return True, "demo-mode (no SLACK_WEBHOOK_URL set)"
    try:
        req = urllib.request.Request(
            webhook, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200, f"http {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"http {e.code}: {e.reason}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:100]}"

# ────────────────────────────────────────────────────────────────────────────
# Reddit ingest
# ────────────────────────────────────────────────────────────────────────────
def fetch_reddit_mentions(brand_keywords: list[str], brand_name: str = DEFAULT_BRAND) -> list[Mention]:
    """Fetches Reddit mentions; tags each mention with the brand it matched."""
    import praw
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "pulse/0.1"),
    )
    out: list[Mention] = []
    seen: set[str] = set()
    for sub in SUBREDDITS:
        sr = reddit.subreddit(sub)
        for kw in brand_keywords:
            try:
                for s in sr.search(kw, sort="new", limit=15):
                    if s.id in seen:
                        continue
                    seen.add(s.id)
                    body = s.selftext or s.title
                    out.append(Mention(
                        id=s.id, source="reddit", brand=brand_name,
                        author=str(s.author) if s.author else "[deleted]",
                        text=f"{s.title}\n\n{body}".strip()[:1200],
                        url=f"https://reddit.com{s.permalink}",
                        posted_at=datetime.fromtimestamp(s.created_utc, tz=timezone.utc),
                        subreddit=sub,
                    ))
            except Exception:
                continue
    out.sort(key=lambda x: x.posted_at, reverse=True)
    return out[:30]


def fetch_reddit_mentions_multi(active_brands: list[str]) -> list[Mention]:
    """Fan out across multiple brands using each brand's own search_keywords."""
    out: list[Mention] = []
    for name in active_brands:
        ctx = load_brand_context(name)
        out.extend(fetch_reddit_mentions(ctx.get("search_keywords", [name]), brand_name=name))
    out.sort(key=lambda x: x.posted_at, reverse=True)
    return out[:30]

# ────────────────────────────────────────────────────────────────────────────
# Demo mock data
# ────────────────────────────────────────────────────────────────────────────
def demo_mentions(active_brands: list[str] | None = None) -> list[Mention]:
    """Mock mentions across all four hackathon brands. Filtered to active_brands."""
    now = datetime.now(timezone.utc)
    raw = [
        # FluxA — engage, engage, escalate, ignore
        ("dm_f1", "FluxA", "saas_builder_22", "SaaS",
         "Built an MCP server that does competitor scraping, want to charge $0.005/call. Stripe usage-based billing is overkill. Anything purpose-built for MCP tools?"),
        ("dm_f2", "FluxA", "agentdev_lin", "LocalLLaMA",
         "Has anyone tried FluxA for paying out to agent wallets in USDC? Need something that doesn't require KYC for every $0.10 micro-transaction."),
        ("dm_f3", "FluxA", "burned_user_91", "startups",
         "@FluxA your AEP2 settlement bricked our prod for 25 min last night and we lost ~$800 in agent payouts. Ticket #4471 — ZERO response."),
        ("dm_f4", "FluxA", "shop_class_dad", "all",
         "Picked up a flux core welder for the garage, anyone running 0.030 wire?"),
        # TokenRouter — engage, engage, escalate
        ("dm_t1", "TokenRouter", "infra_pat", "MachineLearning",
         "Tired of writing my own model fallback layer when Anthropic 503s. Anyone using TokenRouter or OpenRouter for prod inference? Looking for p50/p99 numbers."),
        ("dm_t2", "TokenRouter", "indie_lab", "LocalLLaMA",
         "Is there a router that auto-picks gpt-4o-mini vs sonnet based on task difficulty? Don't want to write a classifier."),
        ("dm_t3", "TokenRouter", "frustrated_dev", "SaaS",
         "TokenRouter just billed me 3x what their dashboard showed for last week. Support hasn't replied in 4 days. Anyone else seeing this?"),
        # AgentHansa — engage, escalate
        ("dm_a1", "AgentHansa", "agent_builder_x", "startups",
         "Built a B2B research agent. Where do people actually list these for real paid quests? Heard about AgentHansa, anyone using it?"),
        ("dm_a2", "AgentHansa", "ripped_off", "MachineLearning",
         "Listed my agent on AgentHansa, got assigned a quest, completed it — and the customer disputed the payout 2 weeks later. No appeal. Out $400."),
        # BotLearn — engage, ignore
        ("dm_b1", "BotLearn", "ml_lurker", "MachineLearning",
         "My agent keeps hallucinating SQL joins. Is there a 'teach your agent SQL' course anywhere? Saw something called BotLearn."),
        ("dm_b2", "BotLearn", "random_dad", "all",
         "My kid wants to learn Python, any decent free courses? Heard of BotLearn but isn't that for AI agents?"),
    ]
    out = [
        Mention(
            id=mid, source="reddit", brand=brand, author=author,
            text=text, url=f"https://reddit.com/r/{sub}/comments/{mid}",
            posted_at=now, subreddit=sub,
        )
        for mid, brand, author, sub, text in raw
    ]
    if active_brands:
        active = set(active_brands)
        out = [m for m in out if m.brand in active]
    return out

# ────────────────────────────────────────────────────────────────────────────
# Session state
# ────────────────────────────────────────────────────────────────────────────
ss = st.session_state
ss.setdefault("results", [])  # list[(Mention, Decision, Draft|None)]
ss.setdefault("wallet", 47.32)
ss.setdefault("draft_edits", {})
ss.setdefault("rejected", set())
ss.setdefault("approved", set())
ss.setdefault("toast_queue", [])
ss.setdefault("slack_sent", set())

# ────────────────────────────────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Pulse Controls")
    demo_mode = st.toggle("Demo Mode", value=True, help="Replay hardcoded mentions instead of hitting Reddit live.")
    active_brands = st.multiselect(
        "Monitored brands",
        options=brand_names(),
        default=brand_names(),
        help="Each brand uses its own keyword list, voice library, and accent color.",
    )
    if not active_brands:
        active_brands = [DEFAULT_BRAND]
    slack_configured = bool(os.environ.get("SLACK_WEBHOOK_URL", "").strip())
    st.markdown(
        f"<div style='font-size:0.78rem;color:{MUTED};margin-top:0.4rem'>"
        f"Slack: <span style='color:{GREEN if slack_configured else MUTED}'>"
        f"{'● connected' if slack_configured else '○ demo-mode'}</span></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown("### 💰 FluxA Agent Wallet")
    st.markdown(
        f"""
        <div class="wallet-card">
            <div class="wallet-label">Balance · Mainnet</div>
            <div class="wallet-balance">{ss.wallet:.2f} USDC</div>
            <span class="powered-by">⚡ Powered by FluxA</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Settles 0.12 USDC per approved engagement via AEP2.")
    st.divider()

    st.markdown("### 📡 TokenRouter Live")
    cheap, strong, total = routing_split()
    if total:
        cheap_pct = round(cheap / total * 100)
        strong_pct = 100 - cheap_pct
        st.markdown(
            f"<div style='font-family:monospace;font-size:0.78rem;color:{MUTED};margin-bottom:0.4rem'>"
            f"Auto-routed: <span style='color:{GREEN}'>{cheap_pct}% cheap</span> / "
            f"<span style='color:{ACCENT}'>{strong_pct}% strong</span></div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<div style='font-family:monospace;color:{TEXT};font-size:0.95rem;margin-bottom:0.4rem'>"
        f"Today: <b style='color:{ACCENT}'>${cost_today():.4f}</b></div>",
        unsafe_allow_html=True,
    )
    rows_html = "".join(
        f"<div class='tr-row'>"
        f"<span>{ts.split('T')[1] if 'T' in ts else ts}</span>"
        f"<span>{(model_used or model_req).split('/')[-1][:18]}</span>"
        f"<span>{kind[:5]}</span>"
        f"<span>{lat}ms</span>"
        f"<span style='color:{ACCENT}'>${cost:.4f}</span>"
        f"</div>"
        for ts, model_req, model_used, kind, lat, cost in recent_calls(10)
    )
    empty_row = "<div class='tr-row' style='justify-content:center'>no calls yet</div>"
    body_html = rows_html or empty_row
    st.markdown(
        f"<div style='background:{PANEL};border:1px solid {BORDER};border-radius:10px;padding:6px 4px;'>"
        f"{body_html}"
        f"</div>",
        unsafe_allow_html=True,
    )

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
AGENTHANSA_LISTING_URL = os.environ.get("AGENTHANSA_LISTING_URL", "https://agenthansa.com/agents/pulse")

hcol1, hcol2 = st.columns([3, 2])
with hcol1:
    st.markdown('<h1 class="pulse-wordmark">💓 Pulse</h1>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pulse-tagline">The heartbeat of your brand, everywhere it\'s mentioned. '
        f'<a href="{AGENTHANSA_LISTING_URL}" target="_blank" '
        'style="background:rgba(61,220,132,0.12);color:#3ddc84;border:1px solid rgba(61,220,132,0.4);'
        'padding:2px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;letter-spacing:0.05em;'
        'text-transform:uppercase;text-decoration:none;margin-left:0.6rem;display:inline-block;">'
        '● Live on AgentHansa</a></div>',
        unsafe_allow_html=True,
    )
with hcol2:
    st.markdown('<div class="run-button">', unsafe_allow_html=True)
    run_clicked = st.button("🔴 RUN PULSE NOW", use_container_width=True, type="primary")
    st.markdown('</div>', unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# Brand banner — one tile per active brand, color-coded with its own pulsing dot
# ────────────────────────────────────────────────────────────────────────────
def _brand_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for m, _, _ in ss.results:
        counts[m.brand] = counts.get(m.brand, 0) + 1
    return counts

per_brand_counts = _brand_counts()

brand_tiles_html = ""
for name in active_brands:
    ctx = load_brand_context(name)
    color = ctx.get("accent_color", ACCENT)
    emoji = ctx.get("emoji", "●")
    count = per_brand_counts.get(name, 0)
    brand_tiles_html += f"""
    <div style="
        flex:1; min-width:220px;
        background: linear-gradient(135deg, {color}22 0%, {color}05 100%);
        border: 1px solid {color}66;
        border-radius: 12px; padding: 0.85rem 1rem;
        display:flex; align-items:center; gap:0.7rem;
    ">
        <span class="pulse-dot" style="background:{color};
            box-shadow: 0 0 0 0 {color}b0; animation: pulse 1.4s infinite;"></span>
        <div style="flex:1; min-width:0;">
            <div style="font-weight:700; color:#fff; font-size:1.05rem;">{emoji} {name}</div>
            <div style="color:{MUTED}; font-size:0.72rem; line-height:1.25;">
                {ctx['one_liner'][:80]}{'…' if len(ctx['one_liner']) > 80 else ''}
            </div>
        </div>
        <div style="text-align:right;">
            <div style="font-size:1.3rem;font-weight:700;color:{color};font-family:monospace;line-height:1">{count}</div>
            <div style="color:{MUTED};font-size:0.65rem;text-transform:uppercase;letter-spacing:0.08em;">mentions</div>
        </div>
    </div>
    """

st.markdown(
    f"""
    <div style="display:flex; flex-wrap:wrap; gap:0.7rem; margin: 1.2rem 0;">
        {brand_tiles_html}
    </div>
    """,
    unsafe_allow_html=True,
)

# ────────────────────────────────────────────────────────────────────────────
# Metrics
# ────────────────────────────────────────────────────────────────────────────
buckets = [d.bucket for _, d, _ in ss.results]
n_engage    = buckets.count("ENGAGE")
n_escalate  = buckets.count("ESCALATE")
n_today     = len(ss.results)
spend_today = cost_today()

mc1, mc2, mc3, mc4 = st.columns(4)
for col, (label, val) in zip(
    (mc1, mc2, mc3, mc4),
    [
        ("Mentions Today", str(n_today)),
        ("Engage Opportunities", str(n_engage)),
        ("Escalations", str(n_escalate)),
        ("TokenRouter Spend Today", f"${spend_today:.4f}"),
    ],
):
    with col:
        mono_cls = " mono" if "$" in val else ""
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">{label}</div>'
            f'<div class="metric-value{mono_cls}">{val}</div></div>',
            unsafe_allow_html=True,
        )

st.write("")

# ────────────────────────────────────────────────────────────────────────────
# Run flow
# ────────────────────────────────────────────────────────────────────────────
if run_clicked:
    ss.results = []
    ss.draft_edits = {}
    ss.approved = set()
    ss.rejected = set()

    with st.status("🔴 Pulse is live — fetching, triaging, drafting…", expanded=True) as status:
        st.write(f"🎯 Brands: {', '.join(active_brands)}")
        if demo_mode:
            st.write(f"🎬 Demo mode: replaying mentions for {len(active_brands)} brand(s)")
            mentions = demo_mentions(active_brands=active_brands)
        else:
            st.write(f"📡 Fetching from r/{', r/'.join(SUBREDDITS)}…")
            try:
                mentions = fetch_reddit_mentions_multi(active_brands)
                st.write(f"✓ Fetched {len(mentions)} unique mentions across {len(active_brands)} brand(s)")
            except Exception as e:
                st.error(f"Reddit fetch failed: {e}. Falling back to demo.")
                mentions = demo_mentions(active_brands=active_brands)

        prog = st.progress(0.0, text="Triaging…")
        results: list[tuple[Mention, Decision, Draft | None]] = []
        for i, m in enumerate(mentions, 1):
            prog.progress(i / max(len(mentions), 1), text=f"Triaging {i}/{len(mentions)} · r/{m.subreddit}")
            d = triage_mention(m)
            draft = None
            if d.bucket == "ENGAGE":
                draft = draft_response(m, d)
            results.append((m, d, draft))

        ss.results = results
        status.update(label=f"✓ Pulse complete · {len(results)} mentions processed", state="complete")
    st.rerun()

# ────────────────────────────────────────────────────────────────────────────
# Three-column dashboard
# ────────────────────────────────────────────────────────────────────────────
def pill(text: str, kind: str) -> str:
    cls = {"LOW": "pill-low", "MED": "pill-med", "HIGH": "pill-high"}.get(text, "pill-signal")
    return f'<span class="pill {cls}">{text}</span>'

def signal_pill(text: str) -> str:
    return f'<span class="pill pill-signal">{text}</span>'

def render_card(m: Mention, d: Decision, css_class: str) -> str:
    ctx = load_brand_context(m.brand)
    brand_color = ctx.get("accent_color", ACCENT)
    brand_emoji = ctx.get("emoji", "●")
    brand_tag = (
        f'<span class="pill" style="background:{brand_color}1f;color:{brand_color};'
        f'border:1px solid {brand_color}55">{brand_emoji} {m.brand}</span>'
    )
    return (
        f'<div class="mention-card {css_class}">'
        f'<div class="mention-meta">r/{m.subreddit} · u/{m.author} · {m.posted_at.strftime("%H:%M:%SZ")}</div>'
        f'<div class="mention-text">{m.text[:280]}{"…" if len(m.text) > 280 else ""}</div>'
        f'<div style="margin-top:0.6rem">{brand_tag}{pill(d.urgency, d.urgency)}{signal_pill(d.signal_type)}</div>'
        f'<div class="mention-reasoning">{d.reasoning}</div>'
        f'</div>'
    )

c_esc, c_eng, c_mon = st.columns(3, gap="medium")

with c_esc:
    st.markdown('<div class="col-header escalate">⚠️ Escalations</div>', unsafe_allow_html=True)
    items = [(m, d) for m, d, _ in ss.results if d.bucket == "ESCALATE"]
    if not items:
        st.caption("No escalations. All quiet.")
    for m, d in items:
        st.markdown(render_card(m, d, "escalate"), unsafe_allow_html=True)
        sent = m.id in ss.slack_sent
        bcol1, bcol2 = st.columns([2, 1])
        with bcol1:
            label = "✓ Sent to Slack" if sent else "🚨 Send to Slack"
            if st.button(label, key=f"slk_{m.id}", use_container_width=True, disabled=sent):
                ok, info = send_to_slack(m, d)
                if ok:
                    ss.slack_sent.add(m.id)
                    st.toast(f"📨 Posted to #brand-alerts · {info}", icon="🚨")
                    st.rerun()
                else:
                    st.toast(f"Slack failed: {info}", icon="⚠️")
        with bcol2:
            st.markdown(f"<a href='{m.url}' target='_blank' style='color:{MUTED};font-size:0.8rem'>→ Reddit</a>",
                        unsafe_allow_html=True)

with c_eng:
    st.markdown('<div class="col-header engage">✨ Engage Queue</div>', unsafe_allow_html=True)
    items = [(m, d, dr) for m, d, dr in ss.results if d.bucket == "ENGAGE"]
    if not items:
        st.caption("No engage opportunities yet. Hit RUN PULSE.")
    for m, d, draft in items:
        if m.id in ss.rejected:
            continue
        st.markdown(render_card(m, d, "engage"), unsafe_allow_html=True)
        default_text = ss.draft_edits.get(m.id, draft.draft_text if draft else "")
        edited = st.text_area(
            "Draft reply", value=default_text, key=f"draft_{m.id}",
            height=110, label_visibility="collapsed",
        )
        ss.draft_edits[m.id] = edited
        if draft:
            with st.expander("🎨 Brand voice applied"):
                if draft.voice_anchors:
                    st.markdown("**Anchored on:**")
                    for v in draft.voice_anchors:
                        st.markdown(f"> _{v}_")
                else:
                    st.caption("No explicit anchors returned by drafter.")
                st.markdown(f"**Rationale:** {draft.rationale}")
                ctx = load_brand_context(m.brand)
                st.caption(
                    f"Voice library: {len(ctx['voice_samples'])} samples · "
                    f"{len(ctx['preferred_phrases'])} preferred phrases · "
                    f"{len(ctx['banned_phrases'])} banned"
                )
        if draft and draft.risk_flags:
            st.caption(f"⚠️ risk: {', '.join(draft.risk_flags)}")
        b1, b2, b3 = st.columns(3)
        if b1.button("✅ Approve & Copy", key=f"ap_{m.id}", use_container_width=True):
            ss.approved.add(m.id)
            ss.wallet = round(ss.wallet - 0.12, 2)
            st.toast("✓ 0.12 USDC settled via FluxA AEP2.", icon="💸")
            st.code(edited, language=None)
        if b2.button("✏️ Regenerate", key=f"rg_{m.id}", use_container_width=True):
            with st.spinner("Regenerating…"):
                new_draft = draft_response(m, d)
            ss.draft_edits[m.id] = new_draft.draft_text
            st.rerun()
        if b3.button("❌ Reject", key=f"rj_{m.id}", use_container_width=True):
            ss.rejected.add(m.id)
            st.rerun()
        st.markdown(f"[→ View on Reddit]({m.url})")

with c_mon:
    st.markdown('<div class="col-header">👁 Monitored (Ignored)</div>', unsafe_allow_html=True)
    items = [(m, d) for m, d, _ in ss.results if d.bucket == "IGNORE"]
    if not items:
        st.caption("No ignored items.")
    for m, d in items:
        st.markdown(render_card(m, d, ""), unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown(
    f"<div style='text-align:center;color:{MUTED};font-size:0.85rem;'>"
    f"💓 <b style='color:{TEXT}'>Pulse is hireable on "
    f"<a href='{AGENTHANSA_LISTING_URL}' target='_blank' style='color:{GREEN}'>AgentHansa</a></b>. "
    f"Triage cycle: <span style='font-family:monospace;color:{GREEN}'>$0.50 USDC</span> via "
    f"<span style='color:{ACCENT}'>FluxA</span>. "
    f"Inference: <span style='color:{ACCENT}'>TokenRouter</span>."
    f"</div>",
    unsafe_allow_html=True,
)
