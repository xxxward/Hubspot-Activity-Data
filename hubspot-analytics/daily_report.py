"""
Daily Activity Report — 5:00 PM MST
Standalone script for scheduled execution via GitHub Actions.

Summarizes TODAY's activity for each rep, highlights positives,
provides encouragement, and emails the team.
"""

import argparse
import json
import logging
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import anthropic
import numpy as np
import pandas as pd

# ── Path setup (so we can import src.* when running from repo root) ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.logging import setup_logging
from src.sheets.sheets_client_standalone import read_all_tabs_standalone
from src.parsing.normalize import (
    normalize_dataframe, build_uid_map_from_meetings,
    apply_owner_mapping, deduplicate_meetings, deduplicate_emails,
    convert_calls_to_meetings_and_dedupe,
)
from src.parsing.filters import (
    apply_deal_filters, apply_activity_filters, REPS_IN_SCOPE,
)
from src.gong.gong_client import fetch_gong_enrichment, map_gong_to_rep

logger = logging.getLogger(__name__)

MST = ZoneInfo("America/Denver")

# ── Rep email addresses ──────────────────────────────────────────────
REP_EMAILS: dict[str, str] = {
    "Jake Lynch": "jlynch@calyxcontainers.com",
    "Owen Labombard": "olabombard@calyxcontainers.com",
    "Lance Mitton": "lmitton@calyxcontainers.com",
    "Dave Borkowski": "dborkowski@calyxcontainers.com",
    "Brad Sherman": "bsherman@calyxcontainers.com",
}

CC_EMAILS: list[str] = ["xward@calyxcontainers.com", "kbissell@calyxcontainers.com"]

REP_ROLES: dict[str, str] = {
    "Owen Labombard": "sdr",
    "Lance Mitton": "acquisition",
    "Brad Sherman": "acquisition",
    "Jake Lynch": "am",
    "Dave Borkowski": "am",
    "Alex Gonzalez": "ceo",
}

ROLE_LABELS: dict[str, str] = {
    "sdr": "SDR",
    "acquisition": "Acquisition",
    "am": "Account Manager",
    "ceo": "CEO",
}


# ═══════════════════════════════════════════════════════════════════════
# DATA LOADING (reuse full pipeline, no Streamlit)
# ═══════════════════════════════════════════════════════════════════════

def load_data():
    """Run the full data pipeline (same as main.py but with standalone sheets client)."""
    logger.info("Reading Google Sheets (standalone)...")
    raw = read_all_tabs_standalone()

    logger.info("Normalizing...")
    norm = {k: normalize_dataframe(v) for k, v in raw.items()}

    logger.info("Building HubSpot UID -> Name mapping...")
    uid_map = build_uid_map_from_meetings(norm.get("meetings", pd.DataFrame()))

    logger.info("Applying owner mappings...")
    for tab_type in ("deals", "meetings", "calls", "tasks", "tickets", "emails", "notes", "new_pipeline"):
        if tab_type in norm and not norm[tab_type].empty:
            norm[tab_type] = apply_owner_mapping(norm[tab_type], uid_map, tab_type)

    logger.info("Deduplicating...")
    if not norm.get("meetings", pd.DataFrame()).empty:
        norm["meetings"] = deduplicate_meetings(norm["meetings"])
    if not norm.get("calls", pd.DataFrame()).empty or not norm.get("meetings", pd.DataFrame()).empty:
        norm["calls"], norm["meetings"] = convert_calls_to_meetings_and_dedupe(
            norm.get("calls", pd.DataFrame()),
            norm.get("meetings", pd.DataFrame()),
        )
    if not norm.get("meetings", pd.DataFrame()).empty:
        norm["meetings"] = deduplicate_meetings(norm["meetings"])
    if not norm.get("emails", pd.DataFrame()).empty:
        norm["emails"] = deduplicate_emails(norm["emails"])

    logger.info("Filtering...")
    return {
        "deals": apply_deal_filters(norm.get("deals", pd.DataFrame())),
        "meetings": apply_activity_filters(norm.get("meetings", pd.DataFrame())),
        "calls": apply_activity_filters(norm.get("calls", pd.DataFrame())),
        "tasks": apply_activity_filters(norm.get("tasks", pd.DataFrame())),
        "emails": apply_activity_filters(norm.get("emails", pd.DataFrame())),
        "notes": apply_activity_filters(norm.get("notes", pd.DataFrame())),
        "tickets": apply_activity_filters(norm.get("tickets", pd.DataFrame())),
    }


# ═══════════════════════════════════════════════════════════════════════
# DATE FILTERING
# ═══════════════════════════════════════════════════════════════════════

def _filter_by_date(df: pd.DataFrame, date_col: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return pd.DataFrame()
    dt = pd.to_datetime(df[date_col], errors="coerce")
    if dt.dt.tz is not None:
        dt = dt.dt.tz_localize(None)
    return df[(dt >= start) & (dt <= end + pd.Timedelta(days=1))]


def _filter_rep(df: pd.DataFrame, rep_name: str) -> pd.DataFrame:
    if df.empty or "hubspot_owner_name" not in df.columns:
        return pd.DataFrame()
    return df[df["hubspot_owner_name"] == rep_name]


def _safe_num(val, default=0):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return val if not pd.isna(val) else default
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════════════
# BUILD CONTEXT FOR EACH REP
# ═══════════════════════════════════════════════════════════════════════

def build_rep_context(datasets: dict, rep_name: str, today_ts: pd.Timestamp,
                      gong_df: pd.DataFrame | None = None) -> dict:
    """
    Build activity context for one rep for TODAY.
    Returns a dict with counts and context string for the AI.
    """
    week_start = today_ts - pd.Timedelta(days=6)
    prev_week_start = week_start - pd.Timedelta(days=7)
    prev_week_end = week_start - pd.Timedelta(days=1)

    rep_meetings = _filter_rep(datasets["meetings"], rep_name)
    rep_calls = _filter_rep(datasets["calls"], rep_name)
    rep_emails = _filter_rep(datasets["emails"], rep_name)
    rep_tasks = _filter_rep(datasets["tasks"], rep_name)
    rep_deals = _filter_rep(datasets["deals"], rep_name)
    rep_tickets = _filter_rep(datasets.get("tickets", pd.DataFrame()), rep_name)
    rep_notes = _filter_rep(datasets.get("notes", pd.DataFrame()), rep_name)

    # Today's activity
    today_meetings = _filter_by_date(rep_meetings, "meeting_start_time", today_ts, today_ts)
    today_calls = _filter_by_date(rep_calls, "activity_date", today_ts, today_ts)
    today_emails = _filter_by_date(rep_emails, "activity_date", today_ts, today_ts)
    today_tasks = _filter_by_date(rep_tasks, "created_date", today_ts, today_ts)
    today_tickets = _filter_by_date(rep_tickets, "created_date", today_ts, today_ts)
    today_notes = _filter_by_date(rep_notes, "created_date", today_ts, today_ts)

    # This week's activity (rolling 7 days)
    week_meetings = _filter_by_date(rep_meetings, "meeting_start_time", week_start, today_ts)
    week_calls = _filter_by_date(rep_calls, "activity_date", week_start, today_ts)
    week_emails = _filter_by_date(rep_emails, "activity_date", week_start, today_ts)
    week_tasks = _filter_by_date(rep_tasks, "created_date", week_start, today_ts)
    week_tickets = _filter_by_date(rep_tickets, "created_date", week_start, today_ts)
    week_notes = _filter_by_date(rep_notes, "created_date", week_start, today_ts)

    # Previous week
    prev_meetings = _filter_by_date(rep_meetings, "meeting_start_time", prev_week_start, prev_week_end)
    prev_calls = _filter_by_date(rep_calls, "activity_date", prev_week_start, prev_week_end)
    prev_emails = _filter_by_date(rep_emails, "activity_date", prev_week_start, prev_week_end)
    prev_tasks = _filter_by_date(rep_tasks, "created_date", prev_week_start, prev_week_end)
    prev_tickets = _filter_by_date(rep_tickets, "created_date", prev_week_start, prev_week_end)
    prev_notes = _filter_by_date(rep_notes, "created_date", prev_week_start, prev_week_end)

    # Companies touched today
    today_activity = pd.concat([today_meetings, today_calls, today_emails, today_tasks, today_tickets, today_notes], ignore_index=True)
    today_companies = set()
    if not today_activity.empty and "company_name" in today_activity.columns:
        today_companies = set(today_activity["company_name"].dropna().str.strip()) - {"", "nan"}

    # Active deals for those companies
    active_deals = pd.DataFrame()
    if today_companies and not rep_deals.empty and "company_name" in rep_deals.columns:
        active_deals = rep_deals[
            rep_deals["company_name"].str.strip().isin(today_companies)
        ]
        if "is_terminal" in active_deals.columns:
            active_deals = active_deals[~active_deals["is_terminal"]]

    # Meeting details for today
    meeting_details = []
    if not today_meetings.empty:
        for _, m in today_meetings.iterrows():
            name = m.get("meeting_name", "Meeting")
            company = m.get("company_name", "")
            outcome = m.get("meeting_outcome", "")
            meeting_details.append(f"{name} ({company}) — {outcome}")

    # Build context string
    today_total = len(today_calls) + len(today_meetings) + len(today_emails) + len(today_tasks) + len(today_tickets) + len(today_notes)
    week_total = len(week_calls) + len(week_meetings) + len(week_emails) + len(week_tasks) + len(week_tickets) + len(week_notes)

    role = REP_ROLES.get(rep_name, "acquisition")
    role_label = ROLE_LABELS.get(role, "Sales")

    context = f"DAILY END-OF-DAY REPORT\n"
    context += f"Date: {today_ts.strftime('%A, %B %d, %Y')}\n"
    context += f"Rep: {rep_name} ({role_label})\n\n"

    context += f"TODAY'S ACTIVITY:\n"
    context += f"  Meetings: {len(today_meetings)}\n"
    context += f"  Calls: {len(today_calls)}\n"
    context += f"  Emails: {len(today_emails)}\n"
    context += f"  Tasks: {len(today_tasks)}\n"
    context += f"  Tickets: {len(today_tickets)}\n"
    context += f"  Notes: {len(today_notes)}\n"
    context += f"  Total touchpoints: {today_total}\n\n"

    if meeting_details:
        context += f"TODAY'S MEETINGS:\n"
        for md in meeting_details:
            context += f"  • {md}\n"
        context += "\n"

    if today_companies:
        context += f"COMPANIES ENGAGED TODAY: {', '.join(sorted(today_companies))}\n\n"

    context += f"ROLLING 7-DAY CONTEXT:\n"
    context += f"  This week: {len(week_meetings)} mtgs, {len(week_calls)} calls, {len(week_emails)} emails, {len(week_tasks)} tasks, {len(week_tickets)} tickets, {len(week_notes)} notes (total: {week_total})\n"
    context += f"  Prev week: {len(prev_meetings)} mtgs, {len(prev_calls)} calls, {len(prev_emails)} emails, {len(prev_tasks)} tasks, {len(prev_tickets)} tickets, {len(prev_notes)} notes\n\n"

    if not active_deals.empty:
        context += f"DEALS CONNECTED TO TODAY'S ACTIVITY:\n"
        for _, deal in active_deals.head(6).iterrows():
            context += f"  • {deal.get('deal_name', 'Unknown')} ({deal.get('company_name', '')}) — "
            context += f"${_safe_num(deal.get('amount', 0)):,.0f} — {deal.get('deal_stage', '')}\n"
        context += "\n"

    # Gong call intelligence enrichment
    gong_calls: list[dict] = []
    if gong_df is not None and not gong_df.empty:
        rep_gong = gong_df[gong_df["hubspot_owner_name"] == rep_name]
        if not rep_gong.empty:
            context += f"GONG CALL INTELLIGENCE ({len(rep_gong)} calls recorded):\n"
            for _, gc in rep_gong.iterrows():
                title = gc.get("call_title", "Call")
                company = gc.get("company_name", "")
                duration_s = gc.get("call_duration_seconds", 0)
                duration_min = round(duration_s / 60, 1) if duration_s else 0
                talk_ratio = gc.get("talk_ratio")
                topics = gc.get("topics", "")
                questions = gc.get("question_count", 0)
                direction = gc.get("call_direction", "")

                context += f"  • {title}"
                if company:
                    context += f" ({company})"
                context += f" — {duration_min} min"
                if direction:
                    context += f", {direction}"
                if talk_ratio is not None:
                    context += f", talk ratio: {talk_ratio:.0%}"
                if questions:
                    context += f", {questions} questions asked"
                context += "\n"
                if topics:
                    context += f"    Topics: {topics}\n"

                # Store for email display
                gong_calls.append({
                    "title": title,
                    "company": company,
                    "duration_min": duration_min,
                    "talk_ratio": talk_ratio,
                    "topics": topics,
                    "question_count": questions,
                    "direction": direction,
                    "transcript_preview": gc.get("transcript_preview", ""),
                })
            context += "\n"

    return {
        "context": context,
        "today_total": today_total,
        "today_meetings": len(today_meetings),
        "today_calls": len(today_calls),
        "today_emails": len(today_emails),
        "today_tasks": len(today_tasks),
        "today_tickets": len(today_tickets),
        "today_notes": len(today_notes),
        "week_total": week_total,
        "companies_touched": len(today_companies),
        "meeting_details": meeting_details,
        "gong_calls": gong_calls,
    }


# ═══════════════════════════════════════════════════════════════════════
# AI ENCOURAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def generate_encouragement(client: anthropic.Anthropic, rep_name: str, context: str) -> str:
    """Generate a positive, encouraging daily summary for one rep."""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=f"""You are writing an end-of-day activity summary email for {rep_name}, a sales rep at Calyx Containers (cannabis packaging).

YOUR GOAL: Highlight positives, provide encouragement, and offer one small helpful insight. This is NOT a big-brother report — it's a daily win tracker and momentum builder.

RULES:
- PAY ATTENTION TO THE DATE in the report. The day of the week matters — do NOT say things like "great close to the week" unless it's actually Thursday or Friday. If it's Monday, reference the start of the week. If it's mid-week, reference mid-week momentum. Match your language to the actual day.
- Lead with what went WELL today. Find the wins, no matter how small.
- If activity was high, celebrate it. If it was low, note what WAS done and encourage tomorrow.
- Mention specific companies or meetings by name when available — it shows you're paying attention.
- Give ONE brief forward-looking insight or suggestion (not a lecture).
- Keep it warm, human, and concise — like a supportive team lead checking in at end of day.
- Tone: encouraging coach, not surveillance software.
- No markdown formatting, no bullet points, no headers — just flowing conversational paragraphs.
- Under 150 words.
- Do NOT start with "Hey" or "Hi" — just dive in.
- If there's literally zero activity, don't shame — just say "Quiet day on the board" and pivot to tomorrow.""",
        messages=[{"role": "user", "content": context}],
    )
    return resp.content[0].text


# ═══════════════════════════════════════════════════════════════════════
# TEAM SUMMARY (manager view)
# ═══════════════════════════════════════════════════════════════════════

def generate_team_summary(client: anthropic.Anthropic, all_rep_data: dict[str, dict], today_str: str) -> str:
    """Generate a brief team-level summary for managers."""
    team_context = f"TEAM DAILY SUMMARY — {today_str}\n\n"
    for rep_name, rep_data in all_rep_data.items():
        role = ROLE_LABELS.get(REP_ROLES.get(rep_name, "acquisition"), "Sales")
        team_context += f"{rep_name} ({role}): "
        team_context += f"{rep_data['today_meetings']} mtgs, {rep_data['today_calls']} calls, "
        team_context += f"{rep_data['today_emails']} emails, {rep_data['today_tasks']} tasks, "
        team_context += f"{rep_data['today_tickets']} tickets, {rep_data['today_notes']} notes "
        team_context += f"({rep_data['today_total']} total)\n"

    total_team = sum(d["today_total"] for d in all_rep_data.values())
    team_context += f"\nTEAM TOTAL: {total_team} touchpoints\n"

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system="""You are writing a brief team activity summary for sales managers at Calyx Containers.

RULES:
- PAY ATTENTION TO THE DATE. Match your language to the actual day of the week — don't say "great close to the week" on a Monday or Wednesday.
- 2-3 sentences max. Highlight the team's wins and momentum.
- Call out standout performers by name.
- Keep it positive and forward-looking.
- No markdown formatting — plain conversational text.
- This goes to managers — keep it high-level.""",
        messages=[{"role": "user", "content": team_context}],
    )
    return resp.content[0].text


# ═══════════════════════════════════════════════════════════════════════
# EMAIL BUILDING
# ═══════════════════════════════════════════════════════════════════════

def build_email_html(rep_name: str, rep_data: dict, ai_text: str, today_str: str) -> str:
    """Build the HTML email for one rep's daily summary."""
    # Activity stat cards
    stats = [
        ("Meetings", rep_data["today_meetings"], "#f472b6"),
        ("Calls", rep_data["today_calls"], "#818cf8"),
        ("Emails", rep_data["today_emails"], "#c084fc"),
        ("Tasks", rep_data["today_tasks"], "#fbbf24"),
        ("Tickets", rep_data["today_tickets"], "#34d399"),
        ("Notes", rep_data["today_notes"], "#fb923c"),
    ]

    stat_cards = ""
    for label, count, color in stats:
        stat_cards += f"""
        <td style="text-align:center; padding:12px 8px;">
            <div style="font-size:28px; font-weight:800; color:{color}; line-height:1;">{count}</div>
            <div style="font-size:11px; color:#9b93b7; text-transform:uppercase; letter-spacing:1px; margin-top:4px;">{label}</div>
        </td>"""

    # AI summary paragraphs
    paragraphs = [p.strip() for p in ai_text.split("\n\n") if p.strip()]
    ai_html = "".join(f'<p style="margin:0 0 12px 0; color:#ede9fc; font-size:15px; line-height:1.7;">{p}</p>' for p in paragraphs)

    # Companies touched
    companies_section = ""
    if rep_data["companies_touched"] > 0:
        companies_section = f"""
        <div style="margin-top:20px; padding:12px 16px; background:rgba(129,140,248,0.1); border-radius:10px; border-left:3px solid #818cf8;">
            <span style="font-size:12px; color:#818cf8; text-transform:uppercase; letter-spacing:1px; font-weight:600;">Companies Engaged Today</span>
            <span style="font-size:20px; font-weight:700; color:#ede9fc; margin-left:12px;">{rep_data['companies_touched']}</span>
        </div>"""

    # Gong call intelligence section
    gong_section = ""
    gong_calls = rep_data.get("gong_calls", [])
    if gong_calls:
        gong_rows = ""
        for gc in gong_calls:
            talk_pct = f"{gc['talk_ratio']:.0%}" if gc.get("talk_ratio") is not None else "—"
            topics_str = gc.get("topics", "") or "—"
            gong_rows += f"""
            <tr style="border-bottom:1px solid #2d2750;">
                <td style="padding:8px 10px; color:#ede9fc; font-size:13px;">{gc['title']}<br><span style="font-size:11px; color:#6a6283;">{gc.get('company', '')}</span></td>
                <td style="padding:8px 6px; text-align:center; color:#818cf8; font-size:13px;">{gc['duration_min']}m</td>
                <td style="padding:8px 6px; text-align:center; color:#34d399; font-size:13px;">{talk_pct}</td>
                <td style="padding:8px 6px; text-align:center; color:#fbbf24; font-size:13px;">{gc.get('question_count', 0)}</td>
            </tr>"""
            if topics_str != "—":
                gong_rows += f"""
            <tr style="border-bottom:1px solid #1e1a35;">
                <td colspan="4" style="padding:4px 10px 8px; font-size:11px; color:#9b93b7;">Topics: {topics_str}</td>
            </tr>"""

        gong_section = f"""
    <!-- Gong Call Intelligence -->
    <div style="padding:0 24px 24px;">
        <div style="background:#1e1a35; border-radius:12px; overflow:hidden; border:1px solid #2d2750;">
            <div style="padding:12px 16px; background:rgba(52,211,153,0.1); border-bottom:1px solid #2d2750;">
                <span style="font-size:12px; color:#34d399; text-transform:uppercase; letter-spacing:1px; font-weight:700;">Gong Call Intelligence</span>
                <span style="font-size:11px; color:#6a6283; margin-left:8px;">{len(gong_calls)} calls recorded</span>
            </div>
            <table width="100%" cellpadding="0" cellspacing="0">
            <tr style="background:#0c0a1a;">
                <th style="padding:8px 10px; text-align:left; color:#6a6283; font-size:10px; text-transform:uppercase;">Call</th>
                <th style="padding:8px 6px; text-align:center; color:#6a6283; font-size:10px; text-transform:uppercase;">Dur</th>
                <th style="padding:8px 6px; text-align:center; color:#6a6283; font-size:10px; text-transform:uppercase;">Talk%</th>
                <th style="padding:8px 6px; text-align:center; color:#6a6283; font-size:10px; text-transform:uppercase;">Q's</th>
            </tr>
            {gong_rows}
            </table>
        </div>
    </div>"""

    # Week context
    week_note = f"Rolling 7-day total: {rep_data['week_total']} touchpoints"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:20px; font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; background:#0c0a1a;">
<div style="max-width:600px; margin:0 auto; background:#151228; border-radius:16px; overflow:hidden; border:1px solid #2d2750;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg, #818cf8 0%, #c084fc 50%, #f472b6 100%); padding:28px 24px; text-align:center;">
        <div style="font-size:24px; font-weight:800; color:#fff; letter-spacing:-0.5px;">Daily Wins</div>
        <div style="font-size:13px; color:rgba(255,255,255,0.85); margin-top:6px;">{rep_name} &middot; {today_str}</div>
    </div>

    <!-- Stats Row -->
    <div style="padding:20px 16px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#1e1a35; border-radius:12px;">
        <tr>{stat_cards}</tr>
        </table>
        <div style="text-align:center; margin-top:8px; font-size:11px; color:#6a6283;">{week_note}</div>
    </div>

    <!-- AI Summary -->
    <div style="padding:24px;">
        <div style="background:#1e1a35; border-radius:12px; padding:20px; border:1px solid #2d2750;">
            {ai_html}
        </div>
        {companies_section}
    </div>

    {gong_section}

    <!-- Footer -->
    <div style="padding:16px 24px; text-align:center; border-top:1px solid #2d2750;">
        <div style="font-size:11px; color:#6a6283;">Calyx Activity Hub &middot; End-of-Day Summary</div>
    </div>

</div>
</body>
</html>"""


def build_manager_email_html(team_summary: str, all_rep_data: dict[str, dict], today_str: str) -> str:
    """Build the HTML email for the manager team summary."""
    # Rep rows
    rep_rows = ""
    for rep_name, rd in all_rep_data.items():
        role = ROLE_LABELS.get(REP_ROLES.get(rep_name, "acquisition"), "Sales")
        total_color = "#34d399" if rd["today_total"] >= 5 else ("#fbbf24" if rd["today_total"] >= 2 else "#6a6283")
        rep_rows += f"""
        <tr style="border-bottom:1px solid #2d2750;">
            <td style="padding:10px 12px; color:#ede9fc; font-weight:600; font-size:14px;">{rep_name}<br><span style="font-size:11px; color:#6a6283; font-weight:400;">{role}</span></td>
            <td style="padding:10px 8px; text-align:center; color:#f472b6; font-weight:600;">{rd['today_meetings']}</td>
            <td style="padding:10px 8px; text-align:center; color:#818cf8; font-weight:600;">{rd['today_calls']}</td>
            <td style="padding:10px 8px; text-align:center; color:#c084fc; font-weight:600;">{rd['today_emails']}</td>
            <td style="padding:10px 8px; text-align:center; color:#fbbf24; font-weight:600;">{rd['today_tasks']}</td>
            <td style="padding:10px 8px; text-align:center; color:#34d399; font-weight:600;">{rd['today_tickets']}</td>
            <td style="padding:10px 8px; text-align:center; color:#fb923c; font-weight:600;">{rd['today_notes']}</td>
            <td style="padding:10px 8px; text-align:center; color:{total_color}; font-weight:700; font-size:16px;">{rd['today_total']}</td>
        </tr>"""

    team_total = sum(d["today_total"] for d in all_rep_data.values())

    summary_paragraphs = [p.strip() for p in team_summary.split("\n\n") if p.strip()]
    summary_html = "".join(f'<p style="margin:0 0 10px 0; color:#ede9fc; font-size:14px; line-height:1.6;">{p}</p>' for p in summary_paragraphs)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:20px; font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; background:#0c0a1a;">
<div style="max-width:640px; margin:0 auto; background:#151228; border-radius:16px; overflow:hidden; border:1px solid #2d2750;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg, #34d399 0%, #818cf8 50%, #c084fc 100%); padding:28px 24px; text-align:center;">
        <div style="font-size:24px; font-weight:800; color:#fff; letter-spacing:-0.5px;">Team Daily Wins</div>
        <div style="font-size:13px; color:rgba(255,255,255,0.85); margin-top:6px;">{today_str} &middot; {team_total} total touchpoints</div>
    </div>

    <!-- AI Summary -->
    <div style="padding:20px 24px 0;">
        <div style="background:#1e1a35; border-radius:12px; padding:16px; border:1px solid #2d2750;">
            {summary_html}
        </div>
    </div>

    <!-- Team Table -->
    <div style="padding:20px 24px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#1e1a35; border-radius:12px; overflow:hidden;">
        <tr style="background:#0c0a1a;">
            <th style="padding:10px 12px; text-align:left; color:#6a6283; font-size:11px; text-transform:uppercase; letter-spacing:1px;">Rep</th>
            <th style="padding:10px 8px; text-align:center; color:#f472b6; font-size:11px; text-transform:uppercase;">Mtgs</th>
            <th style="padding:10px 8px; text-align:center; color:#818cf8; font-size:11px; text-transform:uppercase;">Calls</th>
            <th style="padding:10px 8px; text-align:center; color:#c084fc; font-size:11px; text-transform:uppercase;">Emails</th>
            <th style="padding:10px 8px; text-align:center; color:#fbbf24; font-size:11px; text-transform:uppercase;">Tasks</th>
            <th style="padding:10px 8px; text-align:center; color:#34d399; font-size:11px; text-transform:uppercase;">Tickets</th>
            <th style="padding:10px 8px; text-align:center; color:#fb923c; font-size:11px; text-transform:uppercase;">Notes</th>
            <th style="padding:10px 8px; text-align:center; color:#6a6283; font-size:11px; text-transform:uppercase;">Total</th>
        </tr>
        {rep_rows}
        </table>
    </div>

    <!-- Footer -->
    <div style="padding:16px 24px; text-align:center; border-top:1px solid #2d2750;">
        <div style="font-size:11px; color:#6a6283;">Calyx Activity Hub &middot; Manager Daily Summary</div>
    </div>

</div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════
# EMAIL SENDING
# ═══════════════════════════════════════════════════════════════════════

def send_email(to: str, subject: str, html_body: str, cc: list[str] | None = None) -> None:
    """Send one email via SMTP.

    If the TEST_EMAIL_OVERRIDE env var is set, ALL emails are redirected to
    that address (CC is cleared).  This lets you review every report yourself
    before going live.
    """
    override = os.environ.get("TEST_EMAIL_OVERRIDE", "").strip()
    if override:
        logger.info("TEST_EMAIL_OVERRIDE active — redirecting %s → %s", to, override)
        subject = f"[TEST → {to}] {subject}"
        to = override
        cc = None

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        logger.warning("SMTP credentials not set — skipping email to %s", to)
        return

    msg = MIMEMultipart()
    msg["From"] = smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.attach(MIMEText(html_body, "html"))

    recipients = [to] + (cc or [])

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, recipients, msg.as_string())

    logger.info("Email sent to %s (cc: %s)", to, cc or [])


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Daily Activity Report")
    parser.add_argument(
        "--test",
        metavar="REP_NAME",
        help="Test mode: generate report for one rep and send only to xward@calyxcontainers.com (no CC, no manager email)",
    )
    args = parser.parse_args()

    setup_logging()

    # Today in MST
    now_mst = datetime.now(MST)
    today = now_mst.date()
    today_ts = pd.Timestamp(today)
    today_str = today.strftime("%A, %B %d, %Y")

    test_mode = args.test is not None
    test_rep = args.test

    if test_mode:
        logger.info("=== TEST MODE: Report for %s → xward@calyxcontainers.com ===", test_rep)
    logger.info("=== Daily Report for %s (MST) ===", today_str)

    # 1. Load data
    logger.info("Loading HubSpot data...")
    datasets = load_data()

    # 1b. Fetch Gong call intelligence (optional — skipped if creds not set)
    gong_df = pd.DataFrame()
    if os.environ.get("GONG_ACCESS_KEY") and os.environ.get("GONG_SECRET_KEY"):
        logger.info("Fetching Gong call data...")
        try:
            gong_df = fetch_gong_enrichment(now_mst)
            if not gong_df.empty:
                # Map Gong user names to HubSpot rep names
                gong_df["hubspot_owner_name"] = gong_df["gong_user_name"].apply(map_gong_to_rep)
                logger.info("Gong enrichment: %d calls loaded.", len(gong_df))
        except Exception as e:
            logger.warning("Gong fetch failed (continuing without): %s", e)
            gong_df = pd.DataFrame()
    else:
        logger.info("Gong credentials not set — skipping call intelligence.")

    # 2. Build context for each rep (skip CEO — Alex)
    if test_mode:
        reps_to_report = [test_rep]
    else:
        reps_to_report = [r for r in REPS_IN_SCOPE if r in REP_EMAILS]
    all_rep_data: dict[str, dict] = {}

    for rep in reps_to_report:
        logger.info("Building context for %s...", rep)
        all_rep_data[rep] = build_rep_context(
            datasets, rep, today_ts,
            gong_df=gong_df if not gong_df.empty else None,
        )

    # 3. Generate AI encouragement for each rep
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot generate AI summaries.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    rep_summaries: dict[str, str] = {}
    for rep in reps_to_report:
        logger.info("Generating encouragement for %s...", rep)
        rep_summaries[rep] = generate_encouragement(
            client, rep, all_rep_data[rep]["context"]
        )

    # 4. Generate team summary for managers (skip in test mode)
    if not test_mode:
        logger.info("Generating team summary...")
        team_summary = generate_team_summary(client, all_rep_data, today_str)

    # 5. Send individual rep emails
    for rep in reps_to_report:
        subject = f"Your Daily Wins — {today.strftime('%A, %b %d')}"
        if test_mode:
            subject = f"[TEST] {subject}"
        html = build_email_html(rep, all_rep_data[rep], rep_summaries[rep], today_str)

        if test_mode:
            send_email(to="xward@calyxcontainers.com", subject=subject, html_body=html)
        else:
            send_email(to=REP_EMAILS[rep], subject=subject, html_body=html)

    # 6. Send manager summary (skip in test mode)
    if not test_mode:
        manager_subject = f"Team Daily Wins — {today.strftime('%A, %b %d')}"
        manager_html = build_manager_email_html(team_summary, all_rep_data, today_str)
        for manager_email in CC_EMAILS:
            send_email(to=manager_email, subject=manager_subject, html_body=manager_html)

    logger.info("=== Daily Report Complete ===")


if __name__ == "__main__":
    main()
