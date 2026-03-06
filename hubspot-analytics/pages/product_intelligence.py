"""
Product Intelligence — Pricing Deep Dive

How it works:
  1. User uploads the latest Gong CSV export (or we pull via API date range)
  2. User picks a product + outcome filter
  3. App pulls transcripts for the highest-signal calls
  4. Claude reads every transcript and extracts concrete pricing intelligence
  5. Results surface in a structured table + summary

Requires: gong_client.py in src/gong/
"""

import json
import time

import anthropic
import pandas as pd
import streamlit as st

from src.gong import gong_client as gc

# ─── Page config ────────────────────────────────────────────────────

st.title("Product Intelligence — Pricing Deep Dive")
st.caption(
    "Upload the Gong CSV export, pick a product, and get concrete pricing "
    "intelligence extracted directly from call transcripts."
)

# ─── Sidebar controls ───────────────────────────────────────────────

with st.sidebar:
    st.header("Data Source")
    data_source = st.radio(
        "Load calls from:",
        ["Upload CSV", "API date range"],
        index=0,
    )

    st.divider()
    st.header("Model & Cost")

    MODEL_OPTIONS = {
        "Haiku (fastest, cheapest)": "claude-haiku-4-5-20251001",
        "Sonnet (balanced)": "claude-sonnet-4-20250514",
    }
    model_label = st.selectbox(
        "Claude model",
        options=list(MODEL_OPTIONS.keys()),
        index=0,
        help="Haiku is ~10x cheaper and much less likely to hit rate limits.",
    )
    selected_model = MODEL_OPTIONS[model_label]

    max_transcript_chars = st.slider(
        "Max transcript chars per call",
        min_value=1000, max_value=20000, value=6000, step=1000,
        help="Truncate long transcripts to reduce token usage and avoid rate limits.",
    )

    st.divider()
    st.header("Analysis Filters")

    product = st.selectbox(
        "Product",
        options=list(gc.PRODUCT_TRACKER_COLS.keys()),
        index=0,
    )

    outcome = st.selectbox(
        "Outcome filter",
        options=["lost", "won", "closed", "all"],
        index=0,
        help="'lost' = closed lost · 'won' = closed won · 'closed' = both · 'all' = every call",
    )

    min_pricing = st.slider(
        "Min pricing mentions",
        min_value=1, max_value=10, value=2,
        help="Only include calls where pricing came up at least this many times",
    )

    max_calls = st.slider(
        "Max calls to analyze",
        min_value=10, max_value=200, value=75,
        help="Higher = more thorough but slower. 75 is a good starting point.",
    )

    st.divider()
    st.caption(
        f"API configured: {'✅' if gc.is_gong_configured() else '❌ missing GONG_ACCESS_KEY / GONG_SECRET_KEY'}"
    )

# ─── Load data ──────────────────────────────────────────────────────

df: pd.DataFrame | None = None

if data_source == "Upload CSV":
    uploaded = st.file_uploader(
        "Upload Gong CSV export",
        type=["csv"],
        help="Export from Gong → Analytics → Calls. Include the 'Extensive' template.",
    )
    if uploaded:
        with st.spinner("Loading CSV..."):
            df = gc.load_gong_csv(uploaded)
        st.success(f"Loaded {len(df):,} calls.")
else:
    col1, col2 = st.columns(2)
    from_date = col1.date_input("From date")
    to_date   = col2.date_input("To date")

    if st.button("Pull calls from Gong API"):
        if not gc.is_gong_configured():
            st.error("Gong API credentials not configured. Set GONG_ACCESS_KEY and GONG_SECRET_KEY.")
        else:
            with st.spinner("Fetching call list from Gong..."):
                from datetime import datetime
                from zoneinfo import ZoneInfo

                MST = ZoneInfo("America/Denver")
                from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=MST)
                to_dt   = datetime(to_date.year,   to_date.month,   to_date.day, 23, 59, 59, tzinfo=MST)
                calls = gc.fetch_calls(from_dt, to_dt)

            st.info(
                f"Found {len(calls)} calls in range. "
                "Note: API date-range pulls return call metadata only — "
                "upload the CSV export to get pricing tracker pre-filtering."
            )


# ─── Retry helper for rate limits ────────────────────────────────────

def _call_claude_with_retry(client, model, max_tokens, messages, max_retries=4):
    """Call the Anthropic API with exponential backoff on 429 rate-limit errors."""
    for attempt in range(max_retries + 1):
        try:
            return client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
        except anthropic.RateLimitError:
            if attempt == max_retries:
                raise
            wait = 2 ** (attempt + 1)  # 2, 4, 8, 16 seconds
            st.toast(f"Rate limited — waiting {wait}s before retry {attempt + 2}/{max_retries + 1}...")
            time.sleep(wait)


# ─── Claude analysis function ────────────────────────────────────────

def _run_claude_pricing_analysis(
    payload: list[dict],
    product: str,
    outcome: str,
    model: str = "claude-haiku-4-5-20251001",
    max_transcript_chars: int = 6000,
) -> dict:
    """
    Send transcript batches to Claude and extract structured pricing intelligence.

    Returns a dict with:
        summary:        str — executive summary
        raw_findings:   list[dict] — per-call findings
        product:        str
        outcome:        str
        call_count:     int
    """
    client = anthropic.Anthropic()

    # Smaller batches = fewer tokens per request = less likely to hit rate limits
    CLAUDE_BATCH = 3
    all_findings: list[dict] = []
    progress = st.progress(0, text="Analyzing transcripts...")

    for i in range(0, len(payload), CLAUDE_BATCH):
        batch = payload[i : i + CLAUDE_BATCH]

        # Build the transcript block for this batch, truncating long transcripts
        transcript_block = ""
        for call in batch:
            won_label = {"Yes": "WON", "No": "LOST"}.get(call["won"], "UNKNOWN")
            transcript_text = call["transcript_text"][:max_transcript_chars]
            if len(call["transcript_text"]) > max_transcript_chars:
                transcript_text += "\n[... transcript truncated ...]"
            transcript_block += f"""
---
CALL ID: {call['call_id']}
REP: {call['rep']}
DATE: {call['date']}
ACCOUNT: {call['account']}
DEAL VALUE: {call['deal_value']}
OUTCOME: {won_label}
PRICING MENTIONS: {call['pricing_mentions']}
CALL LINK: {call['call_link']}

TRANSCRIPT:
{transcript_text}
---
"""
        prompt = f"""You are analyzing sales call transcripts for Calyx Containers, a cannabis packaging company selling {product}.

Your job is to extract CONCRETE PRICING INTELLIGENCE — not just that pricing was mentioned, but the actual specifics of what was said.

For each call below, extract:
1. PRICE POINTS: Any specific dollar amounts mentioned (unit price, case price, per-unit, total order value, etc.)
2. PRICING OBJECTIONS: Exactly what the customer said about price being a barrier — verbatim quotes if possible
3. COMPETITOR COMPARISONS: Any mention of what competitors charge or "I can get it cheaper from X"
4. PRICING GAP: If the customer pushed back, how far apart were they from Calyx's price? (e.g. "customer said they're paying $0.18/unit, we quoted $0.25")
5. RESOLUTION: How did the rep handle it? Did they discount? Hold price? Lose the deal on price?
6. MOQ / VOLUME ISSUES: Any discussion of minimum order quantities affecting the deal

Return your findings as a JSON array. One object per call. Use this exact structure:
[
  {{
    "call_id": "...",
    "rep": "...",
    "account": "...",
    "outcome": "WON or LOST",
    "price_points_mentioned": ["$0.45/unit", "$2,400 total order", etc],
    "customer_pricing_quotes": ["exact quote from customer about price"],
    "competitor_price_comparison": "e.g. 'customer said competitor charges X vs our Y' or null",
    "pricing_gap_estimate": "e.g. '$0.08/unit too high' or 'no gap identified' or null",
    "resolution": "e.g. 'rep offered 10% discount', 'held price, customer agreed', 'lost on price'",
    "moq_issue": true or false,
    "key_insight": "one sentence summary of the pricing dynamic on this call"
  }}
]

Only include fields where you found actual evidence in the transcript. If a call has no meaningful pricing content despite the tracker firing, set all fields to null and note "No substantive pricing discussion found."

Here are the {len(batch)} call transcripts:
{transcript_block}

Return ONLY the JSON array. No preamble, no markdown fences."""

        try:
            response = _call_claude_with_retry(
                client, model, 4000,
                [{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown fences if Claude added them anyway
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            batch_findings = json.loads(raw)
            all_findings.extend(batch_findings)
        except Exception as e:
            st.warning(f"Batch {i//CLAUDE_BATCH + 1} failed: {e}")

        progress.progress(
            min((i + CLAUDE_BATCH) / len(payload), 1.0),
            text=f"Analyzed {min(i + CLAUDE_BATCH, len(payload))}/{len(payload)} calls..."
        )
        time.sleep(2)  # pace requests to avoid rate limits

    progress.empty()

    # ── Synthesize a summary across all findings ─────────────────────
    synthesis_prompt = f"""You have just analyzed {len(all_findings)} {outcome} sales calls for Calyx Containers' {product}.

Here are the per-call pricing findings:
{json.dumps(all_findings, indent=2)[:12000]}

Write a concise executive summary of the PRICING INTELLIGENCE. Focus on:
1. The most common price points being discussed
2. The most frequent pricing objections (with approximate frequency)
3. Competitor price comparisons and the typical gap
4. Whether MOQ/volume is a factor
5. What separates the WON deals from the LOST deals on pricing
6. The 2-3 most actionable recommendations for the sales team

Format as structured plain text with clear section headers. Be specific with numbers. This is for a VP of Sales."""

    try:
        summary_response = _call_claude_with_retry(
            client, model, 1500,
            [{"role": "user", "content": synthesis_prompt}],
        )
        summary_text = summary_response.content[0].text
    except Exception as e:
        summary_text = f"Summary generation failed: {e}"

    return {
        "summary": summary_text,
        "raw_findings": all_findings,
        "product": product,
        "outcome": outcome,
        "call_count": len(all_findings),
    }


# ─── Results renderer ────────────────────────────────────────────────

def _render_pricing_results(results: dict, product: str, outcome: str) -> None:
    """Display the Claude analysis results in a structured layout."""

    st.subheader(f"Pricing Intelligence — {product} ({outcome.upper()} deals)")
    st.caption(f"Based on {results['call_count']} calls with transcripts")

    # Executive summary
    st.markdown("### Executive Summary")
    st.markdown(results["summary"])
    st.divider()

    # Per-call findings table
    findings = results.get("raw_findings", [])
    if not findings:
        st.warning("No per-call findings to display.")
        return

    st.markdown("### Per-Call Findings")

    # Build a display DataFrame
    rows = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        rows.append({
            "Rep":           f.get("rep", ""),
            "Account":       f.get("account", ""),
            "Outcome":       f.get("outcome", ""),
            "Price Points":  ", ".join(f.get("price_points_mentioned") or []),
            "Gap Est.":      f.get("pricing_gap_estimate") or "",
            "Competitor":    f.get("competitor_price_comparison") or "",
            "MOQ Issue":     "Warning" if f.get("moq_issue") else "",
            "Resolution":    f.get("resolution") or "",
            "Key Insight":   f.get("key_insight") or "",
            "Call ID":       f.get("call_id", ""),
        })

    findings_df = pd.DataFrame(rows)

    # Color-code outcome
    def color_outcome(val):
        if val == "WON":
            return "background-color: #052e16; color: #4ade80"
        elif val == "LOST":
            return "background-color: #450a0a; color: #f87171"
        return ""

    styled = findings_df.style.map(color_outcome, subset=["Outcome"])
    st.dataframe(styled, use_container_width=True, height=500)

    # Download button
    csv_out = findings_df.to_csv(index=False)
    st.download_button(
        "Download findings as CSV",
        data=csv_out,
        file_name=f"pricing_intelligence_{product.lower().replace(' ', '_')}_{outcome}.csv",
        mime="text/csv",
    )

    # Filter to worst pricing objections
    with st.expander("Calls with competitor price comparisons"):
        comp_calls = [f for f in findings if f.get("competitor_price_comparison")]
        if comp_calls:
            for c in comp_calls:
                st.markdown(f"""
**{c.get('rep')} → {c.get('account')}** ({c.get('outcome')})
- Competitor: {c.get('competitor_price_comparison')}
- Gap: {c.get('pricing_gap_estimate') or 'unknown'}
- Resolution: {c.get('resolution') or 'unknown'}
""")
        else:
            st.info("No competitor price comparisons found in these calls.")

    with st.expander("Customer pricing quotes"):
        for f in findings:
            quotes = f.get("customer_pricing_quotes") or []
            if quotes:
                st.markdown(f"**{f.get('rep')} → {f.get('account')}** ({f.get('outcome')})")
                for q in quotes:
                    st.markdown(f"> _{q}_")
                st.markdown("---")


# ─── Main analysis flow ─────────────────────────────────────────────

if df is not None:
    # Show quick stats for chosen filters
    product_col = gc.PRODUCT_TRACKER_COLS[product]
    pricing_col = gc.PRICING_TRACKER_COL

    total_product_calls = (df[product_col] > 0).sum() if product_col in df.columns else 0
    eligible = df[
        (df[product_col] > 0) & (df[pricing_col] >= min_pricing)
    ] if product_col in df.columns and pricing_col in df.columns else pd.DataFrame()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total calls in CSV", f"{len(df):,}")
    col2.metric(f"Calls mentioning {product}", f"{total_product_calls:,}")
    col3.metric(f"With pricing >= {min_pricing}", f"{len(eligible):,}")
    col4.metric("Will analyze (capped)", f"{min(len(eligible), max_calls):,}")

    st.divider()

    if st.button(f"Run Pricing Analysis — {product} ({outcome})", type="primary"):
        if not gc.is_gong_configured():
            st.error("Gong API credentials required to fetch transcripts.")
            st.stop()

        # ── Step 1: Filter calls ─────────────────────────────────────
        with st.status("Step 1/3 — Selecting high-signal calls...", expanded=True) as status:
            call_df = gc.select_product_intelligence_calls(
                df, product, outcome, min_pricing, max_calls
            )
            st.write(f"Selected **{len(call_df)}** calls to analyze.")
            st.dataframe(
                call_df[[
                    gc.CALL_ID_COL, gc.HOST_COL, gc.RECORDED_DATE_COL,
                    gc.ACCOUNT_NAME_COL, gc.PRICING_TRACKER_COL,
                    gc.STAGE_WON_COL, "Call Link",
                ]].head(10),
                use_container_width=True,
            )
            status.update(label="Step 1/3 — Calls selected", state="complete")

        # ── Step 2: Fetch transcripts ────────────────────────────────
        with st.status("Step 2/3 — Fetching transcripts from Gong API...", expanded=True) as status:
            start = time.time()
            transcripts = gc.fetch_transcripts_for_calls(call_df)
            elapsed = time.time() - start
            st.write(
                f"Retrieved **{len(transcripts)}** transcripts "
                f"({len(call_df) - len(transcripts)} had no transcript available) "
                f"in {elapsed:.1f}s."
            )
            status.update(label="Step 2/3 — Transcripts fetched", state="complete")

        if not transcripts:
            st.warning("No transcripts returned from the API. Check credentials and call IDs.")
            st.stop()

        # ── Step 3: Claude pricing analysis ─────────────────────────
        with st.status("Step 3/3 — Analyzing pricing intelligence with Claude...", expanded=True) as status:
            payload = gc.build_analysis_payload(call_df, transcripts, product)
            st.write(f"Analyzing **{len(payload)}** calls with transcripts...")
            results = _run_claude_pricing_analysis(
                payload, product, outcome,
                model=selected_model,
                max_transcript_chars=max_transcript_chars,
            )
            status.update(label="Step 3/3 — Analysis complete", state="complete")

        # ── Display results ──────────────────────────────────────────
        st.divider()
        _render_pricing_results(results, product, outcome)
