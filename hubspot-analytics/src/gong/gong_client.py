"""
Gong API client — fetches call data to enrich the daily activity report
and powers the Product Intelligence transcript analysis.

Authentication: Basic Auth with access_key:secret_key.
Env vars:  GONG_ACCESS_KEY, GONG_SECRET_KEY, GONG_BASE_URL (optional).
"""

import base64
import logging
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger(__name__)

MST = ZoneInfo("America/Denver")

# Default base URL — override via GONG_BASE_URL env var if your instance differs
DEFAULT_BASE_URL = "https://us-9297.api.gong.io"

# How many call IDs to send per API batch (Gong max is 100)
BATCH_SIZE = 100

# ─── Product tracker column names (as they appear in the CSV export) ─
PRODUCT_TRACKER_COLS = {
    "Calyx Cure":        "Calyx Cure - # Occurrences",
    "Flexible Packaging": "Flexible Packaging - # Occurrences",
    "Calyx Drams":       "Calyx Drams - # Occurrences",
    "Bundle Pitch":      "Bundle Pitch - # Occurrences",
    "Competitors":       "Calyx Container Competitors - # Occurrences",
}

PRICING_TRACKER_COL   = "Pricing (tracker) - # Occurrences"
STAGE_WON_COL         = "CRM - Account 1 Deal 1 Stage Won (Now)"
STAGE_CLOSED_COL      = "CRM - Account 1 Deal 1 Stage Closed (Now)"
CALL_ID_COL           = "Gong Internal Call ID"
DEAL_VALUE_COL        = "CRM - Account 1 Deal 1 Deal Value (Now)"
ACCOUNT_NAME_COL      = "CRM - Account 1 Name"
HOST_COL              = "Host"
RECORDED_DATE_COL     = "Recorded Date"


# ─── Auth / config helpers ───────────────────────────────────────────

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


def is_gong_configured() -> bool:
    """Check whether Gong API credentials are available."""
    return bool(_get_secret("GONG_ACCESS_KEY") and _get_secret("GONG_SECRET_KEY"))


def _strip_call_id(raw_id: str) -> str:
    """
    CSV exports prefix call IDs with an underscore ('_719399...').
    The API expects the bare numeric string ('719399...').
    """
    return str(raw_id).lstrip("_").strip()


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
    Automatically batches into groups of BATCH_SIZE.
    """
    if not call_ids:
        return []

    clean_ids = [_strip_call_id(i) for i in call_ids]
    url = f"{_base_url()}/v2/calls/extensive"
    headers = _get_auth_header()
    all_calls: list[dict] = []

    for i in range(0, len(clean_ids), BATCH_SIZE):
        batch = clean_ids[i : i + BATCH_SIZE]
        body = {
            "filter": {"callIds": batch},
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

        cursor = None
        while True:
            if cursor:
                body["cursor"] = cursor

            resp = requests.post(url, headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            all_calls.extend(data.get("calls", []))
            records = data.get("records", {})
            cursor = records.get("cursor")
            if not cursor:
                break

        time.sleep(0.2)  # gentle rate-limit spacing between batches

    logger.info("Fetched extensive data for %d calls.", len(all_calls))
    return all_calls


# ─── Get call transcripts ───────────────────────────────────────────

def fetch_call_transcripts(call_ids: list[str]) -> dict[str, list[dict]]:
    """
    POST /v2/calls/transcript — returns full transcripts keyed by call ID.
    Automatically batches into groups of BATCH_SIZE.
    """
    if not call_ids:
        return {}

    clean_ids = [_strip_call_id(i) for i in call_ids]
    url = f"{_base_url()}/v2/calls/transcript"
    headers = _get_auth_header()
    transcripts: dict[str, list[dict]] = {}

    for i in range(0, len(clean_ids), BATCH_SIZE):
        batch = clean_ids[i : i + BATCH_SIZE]
        body = {"filter": {"callIds": batch}}
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

        time.sleep(0.2)

    logger.info("Fetched transcripts for %d calls.", len(transcripts))
    return transcripts


# ─── Flatten a transcript into plain text ───────────────────────────

def transcript_to_text(transcript: list[dict], max_chars: int | None = None) -> str:
    """
    Convert the Gong transcript structure into a readable plain-text string.

    Each turn looks like:
        {"speakerName": "Jake Lynch", "sentences": [{"text": "...", "start": 1234}]}
    """
    lines = []
    for turn in transcript:
        speaker = turn.get("speakerName", "Unknown")
        sentences = turn.get("sentences", [])
        text = " ".join(s.get("text", "") for s in sentences).strip()
        if text:
            lines.append(f"{speaker}: {text}")

    full = "\n".join(lines)
    if max_chars:
        full = full[:max_chars]
    return full


# ─── Product Intelligence: select high-signal calls from CSV ────────

def select_product_intelligence_calls(
    df: pd.DataFrame,
    product: str,
    outcome: str = "all",          # "won" | "lost" | "all"
    min_pricing_mentions: int = 1,
    max_calls: int = 150,
) -> pd.DataFrame:
    """
    Given the Gong CSV export DataFrame, return the subset of calls that are
    most informative for product intelligence analysis.

    Filters applied (in order):
      1. Product tracker > 0 (call mentions this product)
      2. Pricing tracker >= min_pricing_mentions
      3. outcome filter (won / lost / all closed / all)
      4. Sort by pricing mentions descending, cap at max_calls

    Returns a slim DataFrame with just the columns needed to drive the
    transcript fetch and analysis.
    """
    product_col = PRODUCT_TRACKER_COLS.get(product)
    if product_col is None:
        raise ValueError(f"Unknown product '{product}'. Options: {list(PRODUCT_TRACKER_COLS)}")

    mask = (df[product_col] > 0) & (df[PRICING_TRACKER_COL] >= min_pricing_mentions)

    if outcome == "won":
        mask &= df[STAGE_WON_COL] == "Yes"
    elif outcome == "lost":
        mask &= (df[STAGE_CLOSED_COL] == "Yes") & (df[STAGE_WON_COL] == "No")
    elif outcome == "closed":
        mask &= df[STAGE_CLOSED_COL] == "Yes"

    subset = df[mask].copy()
    subset = subset.sort_values(PRICING_TRACKER_COL, ascending=False).head(max_calls)

    keep_cols = [
        CALL_ID_COL,
        HOST_COL,
        RECORDED_DATE_COL,
        ACCOUNT_NAME_COL,
        DEAL_VALUE_COL,
        PRICING_TRACKER_COL,
        STAGE_WON_COL,
        STAGE_CLOSED_COL,
        "Call Link",
        product_col,
    ]
    keep_cols = [c for c in keep_cols if c in subset.columns]

    logger.info(
        "Selected %d %s calls for product '%s' (pricing >= %d).",
        len(subset), outcome, product, min_pricing_mentions,
    )
    return subset[keep_cols].reset_index(drop=True)


# ─── Product Intelligence: fetch transcripts for selected calls ──────

def fetch_transcripts_for_calls(call_df: pd.DataFrame) -> dict[str, str]:
    """
    Given a DataFrame produced by select_product_intelligence_calls(),
    fetch full transcripts and return a dict of {clean_call_id: plain_text}.
    """
    raw_ids = call_df[CALL_ID_COL].dropna().tolist()
    clean_ids = [_strip_call_id(i) for i in raw_ids]

    logger.info("Fetching transcripts for %d calls...", len(clean_ids))
    raw_transcripts = fetch_call_transcripts(clean_ids)

    # Convert to plain text
    return {
        cid: transcript_to_text(turns)
        for cid, turns in raw_transcripts.items()
    }


# ─── Product Intelligence: build analysis context ───────────────────

def build_analysis_payload(
    call_df: pd.DataFrame,
    transcripts: dict[str, str],
    product: str,
) -> list[dict]:
    """
    Join call metadata with transcript text into a list of dicts,
    one per call, ready to send to an LLM for pricing analysis.

    Each dict contains:
        call_id, rep, date, account, deal_value, won, pricing_mentions,
        call_link, transcript_text
    """
    rows = []
    for _, row in call_df.iterrows():
        raw_id = str(row.get(CALL_ID_COL, ""))
        clean_id = _strip_call_id(raw_id)

        transcript_text = transcripts.get(clean_id, "")
        if not transcript_text:
            continue  # skip calls where transcript wasn't returned

        rows.append({
            "call_id":          clean_id,
            "rep":              row.get(HOST_COL, ""),
            "date":             str(row.get(RECORDED_DATE_COL, "")),
            "account":          row.get(ACCOUNT_NAME_COL, ""),
            "deal_value":       row.get(DEAL_VALUE_COL, None),
            "won":              row.get(STAGE_WON_COL, ""),
            "pricing_mentions": int(row.get(PRICING_TRACKER_COL, 0)),
            "call_link":        row.get("Call Link", ""),
            "transcript_text":  transcript_text,
        })

    logger.info(
        "Built analysis payload: %d calls with transcripts for '%s'.",
        len(rows), product,
    )
    return rows


# ─── Product Intelligence: full pipeline ────────────────────────────

def run_product_intelligence(
    df: pd.DataFrame,
    product: str,
    outcome: str = "lost",
    min_pricing_mentions: int = 2,
    max_calls: int = 100,
) -> list[dict]:
    """
    End-to-end pipeline:
      1. Filter CSV for high-signal calls about this product
      2. Fetch their full transcripts from the Gong API
      3. Return a list of dicts ready for LLM pricing analysis

    Usage in Streamlit:
        payload = run_product_intelligence(df, product="Calyx Cure", outcome="lost")
        # then pass payload to your Claude/AI analysis function

    Args:
        df:                    The Gong CSV export as a pandas DataFrame
        product:               One of the keys in PRODUCT_TRACKER_COLS
        outcome:               "lost" | "won" | "closed" | "all"
        min_pricing_mentions:  Minimum pricing tracker count to include a call
        max_calls:             Cap on calls to fetch (API cost / latency guard)

    Returns:
        List of call dicts with transcript_text included.
    """
    call_df = select_product_intelligence_calls(
        df, product, outcome, min_pricing_mentions, max_calls
    )

    if call_df.empty:
        logger.warning("No calls matched filters for product '%s'.", product)
        return []

    transcripts = fetch_transcripts_for_calls(call_df)
    payload = build_analysis_payload(call_df, transcripts, product)
    return payload


# ─── Streamlit helper: load and cache CSV ───────────────────────────

def load_gong_csv(uploaded_file) -> pd.DataFrame:
    """
    Load a Gong CSV export from a Streamlit UploadedFile object.
    Handles the underscore-prefixed call IDs and mixed date formats.
    """
    df = pd.read_csv(uploaded_file, low_memory=False)

    # Normalise date column if present
    if RECORDED_DATE_COL in df.columns:
        df[RECORDED_DATE_COL] = pd.to_datetime(
            df[RECORDED_DATE_COL], format="mixed", dayfirst=True
        )

    logger.info("Loaded Gong CSV: %d rows, %d columns.", len(df), len(df.columns))
    return df


# ─── Build enriched DataFrame (existing daily activity flow) ────────

def fetch_gong_enrichment(today: datetime | None = None) -> pd.DataFrame:
    """
    Fetch today's Gong call data and return a DataFrame with enrichment fields.
    This is the original daily-report enrichment — unchanged.

    Returns columns:
        gong_call_id, call_title, call_start, call_duration_seconds,
        gong_user_id, gong_user_name, company_name,
        talk_ratio, question_count, topics, trackers,
        transcript_preview
    """
    if today is None:
        today = datetime.now(MST)

    day_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = today.replace(hour=23, minute=59, second=59, microsecond=0)

    try:
        calls = fetch_calls(day_start, day_end)
    except Exception as e:
        logger.warning("Failed to fetch Gong calls: %s", e)
        return pd.DataFrame()

    if not calls:
        logger.info("No Gong calls found for %s.", today.date())
        return pd.DataFrame()

    call_ids = [c["id"] for c in calls if "id" in c]

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

    extensive_map = {}
    for ec in extensive:
        meta = ec.get("metaData", {})
        cid = meta.get("id", "")
        if cid:
            extensive_map[cid] = ec

    rows = []
    for call in calls:
        cid      = call.get("id", "")
        title    = call.get("title", "")
        started  = call.get("started", "")
        duration = call.get("duration", 0)
        direction = call.get("direction", "")

        parties   = call.get("parties", [])
        user_name = ""
        user_id   = ""
        company   = ""
        for p in parties:
            if p.get("affiliation") == "Internal":
                user_name = p.get("name", user_name)
                user_id   = p.get("userId", user_id)
            elif p.get("affiliation") == "External":
                company = p.get("company", company) or p.get("name", "")

        ext          = extensive_map.get(cid, {})
        interaction  = ext.get("interaction", {})
        content      = ext.get("content", {})

        talk_ratio   = None
        person_stats = interaction.get("personInteractionStats", [])
        for ps in person_stats:
            if ps.get("userId") == user_id or ps.get("affiliation") == "Internal":
                talk_ratio = ps.get("talkRatio")
                break

        questions      = interaction.get("questions", [])
        question_count = len(questions)
        topics   = [t.get("name", "") for t in content.get("topics",   []) if t.get("name")]
        trackers = [t.get("name", "") for t in content.get("trackers", []) if t.get("name")]

        transcript_preview = ""
        if cid in transcripts:
            transcript_preview = transcript_to_text(transcripts[cid])[:500]

        rows.append({
            "gong_call_id":            cid,
            "call_title":              title,
            "call_start":              started,
            "call_duration_seconds":   duration,
            "call_direction":          direction,
            "gong_user_id":            user_id,
            "gong_user_name":          user_name,
            "company_name":            company,
            "talk_ratio":              talk_ratio,
            "question_count":          question_count,
            "topics":                  ", ".join(topics)   if topics   else "",
            "trackers":                ", ".join(trackers) if trackers else "",
            "transcript_preview":      transcript_preview,
        })

    df = pd.DataFrame(rows)
    logger.info("Built Gong enrichment DataFrame: %d rows x %d cols.", len(df), len(df.columns))
    return df


# ─── Map Gong users to HubSpot rep names ────────────────────────────

GONG_TO_REP_NAME: dict[str, str] = {
    # "Gong Display Name": "HubSpot Rep Name"
    # Most should match automatically — only add overrides here.
}


def map_gong_to_rep(gong_name: str) -> str:
    """Map a Gong user display name to a HubSpot rep name."""
    if gong_name in GONG_TO_REP_NAME:
        return GONG_TO_REP_NAME[gong_name]
    return gong_name
