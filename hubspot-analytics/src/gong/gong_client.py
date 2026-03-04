"""
Gong API client — fetches call data to enrich the daily activity report.

Authentication: Basic Auth with access_key:secret_key.
Env vars:  GONG_ACCESS_KEY, GONG_SECRET_KEY, GONG_BASE_URL (optional).
"""

import base64
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger(__name__)

MST = ZoneInfo("America/Denver")

# Default base URL — override via GONG_BASE_URL env var if your instance differs
DEFAULT_BASE_URL = "https://us-9297.api.gong.io"


def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from env vars first, then Streamlit secrets as fallback."""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


def _get_auth_header() -> dict[str, str]:
    access_key = _get_secret("GONG_ACCESS_KEY")
    secret_key = _get_secret("GONG_SECRET_KEY")
    if not access_key or not secret_key:
        raise EnvironmentError("GONG_ACCESS_KEY and GONG_SECRET_KEY must be set.")
    token = base64.b64encode(f"{access_key}:{secret_key}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return _get_secret("GONG_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


# ─── List calls for a date range ────────────────────────────────────

def fetch_calls(from_dt: datetime, to_dt: datetime) -> list[dict]:
    """
    GET /v2/calls — returns call metadata for the given time window.
    Handles cursor-based pagination.
    """
    url = f"{_base_url()}/v2/calls"
    headers = _get_auth_header()
    params = {
        "fromDateTime": from_dt.isoformat(),
        "toDateTime": to_dt.isoformat(),
    }

    all_calls: list[dict] = []
    cursor = None

    while True:
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        calls = data.get("calls", [])
        all_calls.extend(calls)
        logger.info("Fetched %d calls from Gong (batch).", len(calls))

        records = data.get("records", {})
        cursor = records.get("cursor")
        if not cursor or records.get("currentPageNumber", 0) >= records.get("totalRecords", 0):
            break

    logger.info("Total Gong calls fetched: %d", len(all_calls))
    return all_calls


# ─── Get extensive call data (talk ratio, topics, trackers, etc.) ───

def fetch_calls_extensive(call_ids: list[str]) -> list[dict]:
    """
    POST /v2/calls/extensive — returns detailed call data for specific call IDs.
    Includes interaction stats, topics, trackers, and party info.
    """
    if not call_ids:
        return []

    url = f"{_base_url()}/v2/calls/extensive"
    headers = _get_auth_header()

    body = {
        "filter": {
            "callIds": call_ids,
        },
        "contentSelector": {
            "exposedFields": {
                "content": {
                    "pointsOfInterest": True,
                    "topics": True,
                    "trackers": True,
                },
                "interaction": {
                    "personInteractionStats": True,
                    "questions": True,
                    "speakers": True,
                },
                "parties": True,
            }
        },
    }

    all_calls: list[dict] = []
    cursor = None

    while True:
        if cursor:
            body["cursor"] = cursor

        resp = requests.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        calls = data.get("calls", [])
        all_calls.extend(calls)

        records = data.get("records", {})
        cursor = records.get("cursor")
        if not cursor:
            break

    logger.info("Fetched extensive data for %d calls.", len(all_calls))
    return all_calls


# ─── Get call transcripts ───────────────────────────────────────────

def fetch_call_transcripts(call_ids: list[str]) -> dict[str, list[dict]]:
    """
    POST /v2/calls/transcript — returns transcripts keyed by call ID.
    """
    if not call_ids:
        return {}

    url = f"{_base_url()}/v2/calls/transcript"
    headers = _get_auth_header()

    body = {
        "filter": {
            "callIds": call_ids,
        },
    }

    transcripts: dict[str, list[dict]] = {}
    cursor = None

    while True:
        if cursor:
            body["cursor"] = cursor

        resp = requests.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        for ct in data.get("callTranscripts", []):
            cid = ct.get("callId", "")
            transcripts[cid] = ct.get("transcript", [])

        records = data.get("records", {})
        cursor = records.get("cursor")
        if not cursor:
            break

    logger.info("Fetched transcripts for %d calls.", len(transcripts))
    return transcripts


# ─── Build enriched DataFrame ───────────────────────────────────────

def fetch_gong_enrichment(today: datetime | None = None) -> pd.DataFrame:
    """
    Fetch today's Gong call data and return a DataFrame with enrichment fields.

    Returns columns:
        gong_call_id, call_title, call_start, call_duration_seconds,
        gong_user_id, gong_user_name, company_name,
        talk_ratio, question_count, topics, trackers,
        transcript_preview
    """
    if today is None:
        today = datetime.now(MST)

    # Fetch calls from today (start of day to end of day MST)
    day_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = today.replace(hour=23, minute=59, second=59, microsecond=0)

    try:
        calls = fetch_calls(day_start, day_end)
    except Exception as e:
        logger.warning("Failed to fetch Gong calls: %s", e)
        return pd.DataFrame()

    if not calls:
        logger.info("No Gong calls found for %s.", today.date())
        return pd.DataFrame()

    call_ids = [c["id"] for c in calls if "id" in c]

    # Fetch extensive data and transcripts in parallel-ready fashion
    try:
        extensive = fetch_calls_extensive(call_ids)
    except Exception as e:
        logger.warning("Failed to fetch extensive Gong data: %s", e)
        extensive = []

    try:
        transcripts = fetch_call_transcripts(call_ids)
    except Exception as e:
        logger.warning("Failed to fetch Gong transcripts: %s", e)
        transcripts = {}

    # Build lookup for extensive data
    extensive_map = {}
    for ec in extensive:
        meta = ec.get("metaData", {})
        cid = meta.get("id", "")
        if cid:
            extensive_map[cid] = ec

    # Build rows
    rows = []
    for call in calls:
        cid = call.get("id", "")
        title = call.get("title", "")
        started = call.get("started", "")
        duration = call.get("duration", 0)  # seconds
        direction = call.get("direction", "")

        # Parties from base call
        parties = call.get("parties", [])
        user_name = ""
        user_id = ""
        company = ""
        for p in parties:
            if p.get("affiliation") == "Internal":
                user_name = p.get("name", user_name)
                user_id = p.get("userId", user_id)
            elif p.get("affiliation") == "External":
                company = p.get("company", company) or p.get("name", "")

        # Extensive enrichment
        ext = extensive_map.get(cid, {})
        interaction = ext.get("interaction", {})
        content = ext.get("content", {})

        # Talk ratio from person interaction stats
        talk_ratio = None
        person_stats = interaction.get("personInteractionStats", [])
        for ps in person_stats:
            if ps.get("userId") == user_id or ps.get("affiliation") == "Internal":
                talk_ratio = ps.get("talkRatio")
                break

        # Questions asked
        questions = interaction.get("questions", [])
        question_count = len(questions)

        # Topics
        topics = [t.get("name", "") for t in content.get("topics", []) if t.get("name")]

        # Trackers
        trackers = [t.get("name", "") for t in content.get("trackers", []) if t.get("name")]

        # Transcript preview (first 500 chars)
        transcript_preview = ""
        if cid in transcripts:
            parts = []
            for turn in transcripts[cid][:10]:
                speaker = turn.get("speakerName", "")
                text = " ".join(s.get("text", "") for s in turn.get("sentences", []))
                if text:
                    parts.append(f"{speaker}: {text}")
            transcript_preview = "\n".join(parts)[:500]

        rows.append({
            "gong_call_id": cid,
            "call_title": title,
            "call_start": started,
            "call_duration_seconds": duration,
            "call_direction": direction,
            "gong_user_id": user_id,
            "gong_user_name": user_name,
            "company_name": company,
            "talk_ratio": talk_ratio,
            "question_count": question_count,
            "topics": ", ".join(topics) if topics else "",
            "trackers": ", ".join(trackers) if trackers else "",
            "transcript_preview": transcript_preview,
        })

    df = pd.DataFrame(rows)
    logger.info("Built Gong enrichment DataFrame: %d rows x %d cols.", len(df), len(df.columns))
    return df


# ─── Map Gong users to HubSpot rep names ────────────────────────────

# Gong user names may differ slightly from HubSpot — this map handles it.
# Add entries here if Gong names don't match REPS_IN_SCOPE exactly.
GONG_TO_REP_NAME: dict[str, str] = {
    # "Gong Display Name": "HubSpot Rep Name"
    # Most should match automatically — only add overrides here.
}


def map_gong_to_rep(gong_name: str) -> str:
    """Map a Gong user display name to a HubSpot rep name."""
    if gong_name in GONG_TO_REP_NAME:
        return GONG_TO_REP_NAME[gong_name]
    return gong_name  # assume names match


def is_gong_configured() -> bool:
    """Check whether Gong API credentials are available."""
    return bool(_get_secret("GONG_ACCESS_KEY") and _get_secret("GONG_SECRET_KEY"))
