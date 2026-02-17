"""
Column normalization: snake_case conversion, alias mapping, type coercion.

Also handles:
  - Coefficient row-2 headers (handled in sheets_client)
  - Duplicate column deduplication
  - HubSpot User ID -> Rep Name mapping (built from Meetings tab)
  - Meeting deduplication ([Gong], Google Meet:, blank-name merging)
"""

import re
import logging
from collections import defaultdict
from datetime import datetime

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# -- snake_case helper ---------------------------------------------------

def to_snake_case(name: str) -> str:
    s = re.sub(r"[\s\-\.\/\(\)]+", "_", str(name).strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"_+", "_", s).lower().strip("_")
    return s


# -- Column alias map ----------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    # Deals
    "create_date": "created_date",
    "associated_company_name": "company_name",
    "hub_spot_team": "hubspot_team",
    "opp_owner": "hubspot_owner_name",
    "opp_type_no_blanks": "opp_type",
    "is_deal_closed?": "is_deal_closed",
    "close_status": "close_status",
    # Meetings
    "activity_assigned_to": "activity_assigned_to",
    "activity_created_by": "activity_created_by",
    "body_preview_truncated": "body_preview",
    # Tasks
    "created_at": "created_date",
    "completed_at": "completed_at",
    "last_modified_at": "last_modified_date",
    "notes_preview": "notes_preview",
    # Calls
    "last_modified_date": "last_modified_date",
    # Emails
    "email_id": "email_id",
    "email_from_address": "email_from_address",
    "email_to_address": "email_to_address",
    "number_of_email_opens": "email_opens",
    "number_of_email_clicks": "email_clicks",
    "number_of_email_replies": "email_replies",
    "email_open_rate": "email_open_rate",
    "email_click_rate": "email_click_rate",
    "email_reply_rate": "email_reply_rate",
    "email_cc_address": "email_cc_address",
    "first_name_activity_assigned_to": "owner_first_name",
    "last_name_activity_assigned_to": "owner_last_name",
    "created_by_user_id": "created_by_user_id",
    "hub_spot_team": "hubspot_team",
    "updated_by_user_id": "updated_by_user_id",
    # Notes
    "note_id": "note_id",
    "note_body": "note_body",
    "deal_name": "deal_name",
    # Tickets
    "first_name_ticket_owner": "ticket_owner_first_name",
}

DATE_COLUMNS = {
    "created_date", "close_date", "activity_date", "meeting_start_time",
    "meeting_end_time", "completed_at", "due_date", "last_modified_date",
    "create_date", "last_activity_date", "next_activity_date",
}

NUMERIC_COLUMNS = {
    "amount", "deal_id", "company_id", "call_duration", "ticket_id",
    "opp_age", "forecast_probability", "call_id",
}


# -- HubSpot User ID -> Rep Name mapping ---------------------------------

# Hardcoded confirmed mapping (from the Meetings Rosetta Stone)
HUBSPOT_UID_TO_NAME: dict[str, str] = {
    "56564763": "Alex Gonzalez",
    "56562506": "Brad Sherman",
    "119721604": "Dave Borkowski",
    "56564944": "Jake Lynch",
    "79617483": "Lance Mitton",
    "85412002": "Owen Labombard",
}


def _clean_uid(val) -> str:
    """Clean a HubSpot User ID value — handle float, int, string forms."""
    if pd.isna(val) or val == "" or val is None:
        return ""
    s = str(val).strip()
    # Strip .0 suffix from float representation
    if s.endswith(".0"):
        s = s[:-2]
    return s


def build_uid_map_from_meetings(meetings_df: pd.DataFrame) -> dict[str, str]:
    """
    Build User ID -> Name mapping from the Meetings tab.
    Falls back to hardcoded map if meetings data is insufficient.
    """
    from src.parsing.filters import REPS_IN_SCOPE

    uid_map = dict(HUBSPOT_UID_TO_NAME)  # start with known mapping

    if meetings_df.empty:
        return uid_map

    # Try to enrich from the actual meetings data
    first_col = "first_name" if "first_name" in meetings_df.columns else None
    last_col = "last_name" if "last_name" in meetings_df.columns else None
    uid_col = "activity_assigned_to" if "activity_assigned_to" in meetings_df.columns else None

    if first_col and last_col and uid_col:
        for _, row in meetings_df.iterrows():
            first = str(row.get(first_col, "")).strip()
            last = str(row.get(last_col, "")).strip()
            name = f"{first} {last}".strip()
            if name in REPS_IN_SCOPE:
                uid = _clean_uid(row.get(uid_col))
                if uid:
                    uid_map[uid] = name

    logger.info("UID map built with %d entries: %s", len(uid_map), uid_map)
    return uid_map


def apply_owner_mapping(df: pd.DataFrame, uid_map: dict[str, str], tab_type: str) -> pd.DataFrame:
    """
    Apply the correct owner mapping strategy per tab type.

    - meetings: First name + Last name = rep name
    - calls: Activity assigned to (UID) -> name via uid_map
    - tasks: full_name is already the rep name
    - tickets: First name + Last name = rep name
    - deals: hubspot_owner_name already mapped from Opp Owner
    """
    if df.empty:
        return df
    df = df.copy()

    if tab_type == "meetings":
        # Build rep name from first + last
        first = df.get("first_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        last = df.get("last_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        df["hubspot_owner_name"] = (first + " " + last).str.strip()

    elif tab_type == "calls":
        # Map UID to name
        uid_col = "activity_assigned_to" if "activity_assigned_to" in df.columns else "hubspot_owner_name"
        df["hubspot_owner_name"] = df[uid_col].apply(lambda x: uid_map.get(_clean_uid(x), ""))

    elif tab_type == "tasks":
        # full_name is the rep
        if "full_name" in df.columns:
            df["hubspot_owner_name"] = df["full_name"]

    elif tab_type == "emails":
        # Emails have first_name/last_name (Activity assigned to) and activity_assigned_to (UID)
        # Build name from first + last name columns, or map UID
        REP_LAST_NAMES = {"Sherman", "Labombard", "Lynch", "Borkowski", "Gonzalez", "Mitton"}

        logger.info("Emails columns before owner mapping: %s", list(df.columns))

        # Try owner_first_name + owner_last_name first (from "First name (Activity assigned to)" etc)
        first_col = "owner_first_name" if "owner_first_name" in df.columns else ("first_name" if "first_name" in df.columns else None)
        last_col = "owner_last_name" if "owner_last_name" in df.columns else ("last_name" if "last_name" in df.columns else None)

        if first_col and last_col:
            first = df[first_col].fillna("").astype(str).str.strip()
            last = df[last_col].fillna("").astype(str).str.strip()
            df["hubspot_owner_name"] = (first + " " + last).str.strip()
            # Filter to only our reps by last name
            logger.info("Emails: unique last names: %s", df[last_col].unique()[:20].tolist())
            df = df[df[last_col].astype(str).str.strip().isin(REP_LAST_NAMES)].copy()
        elif "activity_assigned_to" in df.columns:
            df["hubspot_owner_name"] = df["activity_assigned_to"].apply(lambda x: uid_map.get(_clean_uid(x), ""))
            df = df[df["hubspot_owner_name"] != ""].copy()
        else:
            logger.warning("Emails: no owner columns found. Available: %s", list(df.columns))
        logger.info("Emails owner mapping: %d rows after filtering to reps.", len(df))

    elif tab_type == "notes":
        # Notes have activity_assigned_to (UID) — map via uid_map
        if "activity_assigned_to" in df.columns:
            df["hubspot_owner_name"] = df["activity_assigned_to"].apply(lambda x: uid_map.get(_clean_uid(x), ""))
            df = df[df["hubspot_owner_name"] != ""].copy()
        logger.info("Notes owner mapping: %d rows after filtering to reps.", len(df))

    elif tab_type == "tickets":
        first = df.get("first_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        last = df.get("last_name", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
        df["hubspot_owner_name"] = (first + " " + last).str.strip()

    elif tab_type == "new_pipeline":
        # New Pipeline has First name/Last name columns for deal owner
        first_col = "first_name" if "first_name" in df.columns else None
        last_col = "last_name" if "last_name" in df.columns else None
        
        if first_col and last_col:
            first = df[first_col].fillna("").astype(str).str.strip()
            last = df[last_col].fillna("").astype(str).str.strip()
            df["hubspot_owner_name"] = (first + " " + last).str.strip()
        elif "deal_owner_email" in df.columns:
            # Fallback to mapping by email if needed
            rep_emails = {
                "olabombard@calyxcontainers.com": "Owen Labombard",
                "bsherman@calyxcontainers.com": "Brad Sherman", 
                "dborkowski@calyxcontainers.com": "Dave Borkowski",
                "jlynch@calyxcontainers.com": "Jake Lynch",
                "lmitton@calyxcontainers.com": "Lance Mitton",
                "alex@calyxcontainers.com": "Alex Gonzalez"
            }
            df["hubspot_owner_name"] = df["deal_owner_email"].map(rep_emails).fillna("")
        logger.info("New Pipeline owner mapping: %d rows after processing.", len(df))

    # deals: hubspot_owner_name already set from Opp Owner alias
    return df


# -- Meeting Deduplication ------------------------------------------------

# Meeting outcomes that COUNT as actual meetings that HAPPENED (only completed count)
VALID_MEETING_OUTCOMES = {
    "Completed"  # Only completed meetings count as meetings that actually happened
    # Note: "Scheduled" = future meeting, "No Show" = didn't happen, "Canceled" = didn't happen
}

OUTCOME_PRIORITY = {
    "Completed": 5, "No Show": 4, "Rescheduled": 2, "Scheduled": 1, 
    "Canceled": 0,  # Canceled gets lowest priority and filtered out
    "": 0
}


def _norm_meeting_name(name: str) -> str:
    """Strip [Gong] and Google Meet: prefixes, and handle <NA> values."""
    n = str(name).strip() if pd.notna(name) else ""
    
    # Convert <NA> to empty string
    if n == "<NA>":
        return ""
        
    for prefix in ["[Gong] ", "[Gong]", "Google Meet: ", "Google Meet:"]:
        if n.startswith(prefix):
            n = n[len(prefix):]
    return n.strip()


def _safe_str(val) -> str:
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()


def _best_value(values: list[str]) -> str:
    """Return the longest non-empty string from a list."""
    non_empty = [v for v in values if v]
    return max(non_empty, key=len) if non_empty else ""


def _merge_meeting_group(group_df: pd.DataFrame, name_col: str, outcome_col: str, company_col: str) -> dict:
    """
    Merge a group of duplicate meetings into a single representative record.
    Prioritizes the record with the most complete/rich data, especially Gong records.
    Then pulls the BEST data from ALL records in the group.
    """
    if group_df.empty:
        return {}
    
    # Score each record by how much data it has (prefer records with more fields filled)
    def _score_record(row):
        score = 0
        
        # HEAVILY prioritize Gong records - they have the most reliable data
        meeting_name = str(row.get(name_col, "")).strip()
        if meeting_name.startswith("[Gong]"):
            score += 10  # Big bonus for Gong records
            
        # Penalize records with no outcome
        outcome = str(row.get(outcome_col, "")).strip()
        if outcome and outcome not in ['', 'nan', '<NA>', 'None']:
            if outcome in ['Completed', 'Scheduled', 'No Show', 'Rescheduled']:
                score += 5  # Good outcomes get big bonus
            # Don't penalize canceled here - they should be filtered out already
        else:
            score -= 3  # Penalize missing outcome
        
        # More points for having actual values vs null/empty
        important_fields = [name_col, company_col, 'call_and_meeting_type', 'meeting_type', 'body_preview']
        for field in important_fields:
            if field in row.index:
                val = str(row[field]).strip()
                if val and val not in ['', 'nan', '<NA>', 'None']:
                    score += 1
            
        # Extra points for having call_and_meeting_type filled  
        if 'call_and_meeting_type' in row.index and str(row['call_and_meeting_type']).strip() not in ['', 'nan', '<NA>', 'None']:
            score += 2
            
        # Penalize "Meeting sync" sources (they're usually less complete)
        source = str(row.get('meeting_source', "")).strip()
        if 'sync' in source.lower():
            score -= 2
            
        return score
    
    # Score all records and pick the one with highest score (most data)
    group_df = group_df.copy()
    group_df['_data_score'] = group_df.apply(_score_record, axis=1)
    
    # Sort by score (descending) and take the richest record as base
    group_df = group_df.sort_values('_data_score', ascending=False)
    best_record = group_df.iloc[0]
    merged = best_record.to_dict()
    
    # NOW MERGE THE BEST DATA FROM ALL RECORDS
    # For each field, take the best non-empty value across ALL duplicates
    
    # Meeting name - prefer Gong names, then longest names
    if name_col in group_df.columns:
        names = [_safe_str(val) for val in group_df[name_col] if _safe_str(val)]
        gong_names = [name for name in names if name.startswith("[Gong]")]
        if gong_names:
            merged[name_col] = max(gong_names, key=len)  # Longest Gong name
        elif names:
            merged[name_col] = max(names, key=len)  # Longest name overall
    
    # Company name - take the longest/most complete
    if company_col in group_df.columns:
        companies = [_safe_str(val) for val in group_df[company_col] if _safe_str(val)]
        if companies:
            merged[company_col] = max(companies, key=len)
    
    # Meeting outcome - take the best priority, but prefer "Completed" over "Scheduled"
    if outcome_col in group_df.columns:
        outcomes = [str(val).strip() for val in group_df[outcome_col] if str(val).strip() not in ['', 'nan', '<NA>', 'None']]
        if outcomes:
            # Custom priority that prefers "Completed" over "Scheduled"
            def outcome_priority(outcome):
                if outcome == "Completed": return 10
                elif outcome == "No Show": return 9  
                elif outcome == "Rescheduled": return 8
                elif outcome == "Scheduled": return 7  # Lower than completed
                else: return 0
            
            best_outcome = max(outcomes, key=outcome_priority)
            merged[outcome_col] = best_outcome
    
    # Call and meeting type - take the best non-empty value
    if 'call_and_meeting_type' in group_df.columns:
        call_types = [_safe_str(val) for val in group_df['call_and_meeting_type'] if _safe_str(val)]
        if call_types:
            # Prefer more specific types over generic ones
            specific_types = [ct for ct in call_types if ct.lower() not in ['call', 'meeting']]
            merged['call_and_meeting_type'] = specific_types[0] if specific_types else call_types[0]
    
    # Meeting type - take the best non-empty value  
    if 'meeting_type' in group_df.columns:
        meeting_types = [_safe_str(val) for val in group_df['meeting_type'] if _safe_str(val)]
        if meeting_types:
            merged['meeting_type'] = meeting_types[0]
    
    # Body preview - take the longest one (most detail)
    if 'body_preview' in group_df.columns:
        previews = [_safe_str(val) for val in group_df['body_preview'] if _safe_str(val)]
        if previews:
            merged['body_preview'] = max(previews, key=len)
    
    # Meeting source - prefer CRM UI over sync
    if 'meeting_source' in group_df.columns:
        sources = [_safe_str(val) for val in group_df['meeting_source'] if _safe_str(val)]
        if sources:
            crm_sources = [s for s in sources if 'CRM UI' in s]
            merged['meeting_source'] = crm_sources[0] if crm_sources else sources[0]
    
    # Remove the scoring column
    if '_data_score' in merged:
        del merged['_data_score']
    
    return merged


def deduplicate_meetings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate meetings using the three-pattern algorithm:
    1. [Gong] prefix duplicates
    2. Google Meet: prefix duplicates  
    3. Blank-name CRM entries matching by date+rep+company
    4. Filter out canceled meetings (they don't count)
    5. Include internal meetings about clients

    Groups are merged keeping the richest data.
    """
    if df.empty:
        return df

    # Ensure we have the needed columns
    name_col = "meeting_name" if "meeting_name" in df.columns else None
    date_col = "meeting_start_time" if "meeting_start_time" in df.columns else "activity_date"
    rep_col = "hubspot_owner_name"
    company_col = "company_name"
    outcome_col = "meeting_outcome"

    if not name_col:
        logger.warning("No meeting_name column found for deduplication.")
        return df

    pre_count = len(df)
    df = df.copy()

    # Add normalized meeting names and date (DATE only, not datetime)
    df["_norm_name"] = df[name_col].apply(_norm_meeting_name)
    df["_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date  # DATE only, ignore time
    df["_rep"] = df.get(rep_col, "").fillna("").astype(str)
    df["_company"] = df.get(company_col, "").fillna("").astype(str)
    df["_outcome"] = df.get(outcome_col, "").fillna("").astype(str)

    # DEBUG: Check for INSA meetings specifically
    insa_meetings = df[df["_company"] == "INSA"]
    if not insa_meetings.empty:
        logger.info(f"DEBUG: Found {len(insa_meetings)} INSA meetings before dedup:")
        for idx, row in insa_meetings.iterrows():
            logger.info(f"  {idx}: {row['_norm_name'][:50]} | {row['_date']} | {row['_rep']} | {row['_company']}")

    # Group meetings for deduplication
    groups = []
    processed_indices = set()

    for idx, row in df.iterrows():
        if idx in processed_indices:
            continue

        # Find all potential duplicates for this meeting
        candidates = []
        norm_name = row["_norm_name"]
        date_val = row["_date"]
        rep_val = row["_rep"]
        company_val = row["_company"]

        # DEBUG: Log INSA meeting processing
        if company_val == "INSA":
            logger.info(f"DEBUG: Processing INSA meeting {idx}: '{norm_name}' on {date_val}")

        for idx2, row2 in df.iterrows():
            if idx2 in processed_indices or idx2 == idx:
                continue

            # Pattern 1: Same normalized name, date, rep (regardless of company)
            if (norm_name and norm_name == row2["_norm_name"] and 
                date_val == row2["_date"] and rep_val == row2["_rep"]):
                candidates.append(idx2)
                processed_indices.add(idx2)
                if company_val == "INSA" or row2["_company"] == "INSA":
                    logger.info(f"  DEBUG: Pattern 1 match - {idx2}")

            # Pattern 2: Both have blank names but same date/rep/company
            elif (not norm_name and not row2["_norm_name"] and
                  date_val == row2["_date"] and rep_val == row2["_rep"] and
                  company_val and company_val == row2["_company"]):
                candidates.append(idx2)
                processed_indices.add(idx2)
                if company_val == "INSA":
                    logger.info(f"  DEBUG: Pattern 2 match - {idx2}")
                
            # Pattern 3: One has name, other is blank, but same date/rep/company
            elif ((norm_name and not row2["_norm_name"]) or (not norm_name and row2["_norm_name"])) and \
                 date_val == row2["_date"] and rep_val == row2["_rep"] and \
                 company_val and company_val == row2["_company"]:
                candidates.append(idx2)
                processed_indices.add(idx2)
                if company_val == "INSA":
                    logger.info(f"  DEBUG: Pattern 3 match - {idx2}: '{row2['_norm_name']}'")
            
            # DETAILED DEBUGGING for INSA meetings that should match but don't
            elif company_val == "INSA" and row2["_company"] == "INSA":
                logger.info(f"  DEBUG: INSA {idx} vs {idx2} - checking conditions:")
                logger.info(f"    norm_name1='{norm_name}' norm_name2='{row2['_norm_name']}'")
                logger.info(f"    date1={date_val} date2={row2['_date']} match={date_val == row2['_date']}")
                logger.info(f"    rep1='{rep_val}' rep2='{row2['_rep']}' match={rep_val == row2['_rep']}")
                logger.info(f"    company1='{company_val}' company2='{row2['_company']}' match={company_val == row2['_company']}")
                name_condition = (norm_name and not row2["_norm_name"]) or (not norm_name and row2["_norm_name"])
                logger.info(f"    name_condition={name_condition}")
                logger.info(f"    SHOULD MATCH: {name_condition and date_val == row2['_date'] and rep_val == row2['_rep'] and company_val == row2['_company']}")

        # Include the original row
        candidates.append(idx)
        processed_indices.add(idx)

        # DEBUG: Log INSA candidates
        if company_val == "INSA":
            logger.info(f"  DEBUG: INSA meeting {idx} has {len(candidates)} candidates: {candidates}")

        # Merge the group
        group_rows = df.loc[candidates]
        merged = _merge_meeting_group(group_rows, name_col, outcome_col, company_col)
        groups.append(merged)

    # Reconstruct DataFrame
    result = pd.DataFrame(groups)

    # FILTER OUT CANCELED MEETINGS - they don't count as meetings
    if outcome_col in result.columns:
        before_cancel_filter = len(result)
        result = result[result[outcome_col] != "Canceled"].copy()
        canceled_removed = before_cancel_filter - len(result)
        if canceled_removed > 0:
            logger.info(f"Filtered out {canceled_removed} canceled meetings")

    # ADD FLAG for dashboard filtering - only "Completed" meetings count as meetings that happened
    if outcome_col in result.columns:
        result["_counts_as_meeting"] = result[outcome_col] == "Completed"
        completed_meetings = result["_counts_as_meeting"].sum()
        total_meetings = len(result)
        logger.info(f"Meeting counting: {completed_meetings} completed out of {total_meetings} total meetings")
    else:
        result["_counts_as_meeting"] = True  # If no outcome column, assume all count

    # DEBUG: Check INSA meetings after dedup
    insa_after = result[result.get(company_col, "") == "INSA"]
    if not insa_after.empty:
        logger.info(f"DEBUG: Found {len(insa_after)} INSA meetings after dedup:")
        for idx, row in insa_after.iterrows():
            meeting_name = row.get(name_col, "")
            logger.info(f"  {meeting_name[:50]} | {row.get(company_col, '')}")

    # Clean up temp columns
    result = result.drop(columns=[c for c in result.columns if c.startswith("_")], errors="ignore")

    logger.info("Meeting dedup: %d -> %d rows (removed %d duplicates).", 
                pre_count, len(result), pre_count - len(result))
    return result

    if name_col is None or date_col not in df.columns:
        logger.warning("Cannot deduplicate meetings — missing columns.")
        return df

    # Parse dates to just date part for grouping
    df = df.copy()
    df["_start_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    # Normalize meeting names
    df["_norm_name"] = df[name_col].apply(_norm_meeting_name)

    # Check for Gong prefix
    raw_name = df[name_col].fillna("").astype(str)
    df["has_gong"] = raw_name.str.startswith("[Gong]")

    # Step 1 & 2: Group named meetings
    named_groups: dict[tuple, list[int]] = defaultdict(list)
    blank_indices: list[int] = []

    for idx in df.index:
        norm = df.at[idx, "_norm_name"]
        if norm:
            key = (
                norm,
                df.at[idx, "_start_date"],
                _safe_str(df.at[idx, rep_col]) if rep_col in df.columns else "",
            )
            named_groups[key].append(idx)
        else:
            blank_indices.append(idx)

    # Step 3: Match blanks to named groups by date+rep+company
    named_lookup: dict[tuple, tuple] = {}
    for key, indices in named_groups.items():
        for idx in indices:
            comp = _safe_str(df.at[idx, company_col]) if company_col in df.columns else ""
            if comp:
                lookup_key = (key[1], key[2], comp)  # date, rep, company
                named_lookup[lookup_key] = key

    for idx in blank_indices:
        rep = _safe_str(df.at[idx, rep_col]) if rep_col in df.columns else ""
        comp = _safe_str(df.at[idx, company_col]) if company_col in df.columns else ""
        date_val = df.at[idx, "_start_date"]
        lookup_key = (date_val, rep, comp)
        if lookup_key in named_lookup:
            named_groups[named_lookup[lookup_key]].append(idx)
        else:
            # Standalone blank — keep as its own group
            named_groups[("_blank", date_val, rep)].append(idx)

    # Step 4: Merge each group
    merged_rows = []
    merge_cols = [c for c in df.columns if not c.startswith("_")]

    for key, indices in named_groups.items():
        if len(indices) == 1:
            merged_rows.append(df.loc[indices[0], merge_cols].to_dict())
            continue

        group = df.loc[indices]
        merged = {}

        for col in merge_cols:
            if col == outcome_col:
                # Use highest priority outcome
                outcomes = group[col].fillna("").astype(str).tolist()
                best_outcome = max(outcomes, key=lambda o: OUTCOME_PRIORITY.get(o.strip(), 0))
                merged[col] = best_outcome
            elif col == "has_gong":
                merged[col] = group[col].any()
            elif col == name_col:
                # Use the normalized name (without prefixes)
                merged[col] = key[0] if key[0] != "_blank" else ""
            else:
                # Keep longest non-empty value
                vals = group[col].fillna("").astype(str).tolist()
                merged[col] = _best_value(vals)

        merged_rows.append(merged)

    result = pd.DataFrame(merged_rows)

    # Fix mixed types from merge — re-parse datetime columns
    for col in result.columns:
        if col in DATE_COLUMNS or col.endswith("_date") or col.endswith("_time") or col.endswith("_at"):
            result[col] = pd.to_datetime(result[col], errors="coerce")

    logger.info("Meeting dedup: %d -> %d rows (removed %d duplicates).",
                len(df), len(result), len(df) - len(result))
    return result


def deduplicate_emails(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove duplicate emails and collapse threads.
    
    Two-phase dedup:
      Phase 1: Remove Gong duplicates ([Gong Out]/[Gong In] copies of same email)
      Phase 2: Collapse email threads into single activity records.
               "Re: Re: Re: Subject" and "Re: Subject" on the same company = 1 thread.
               Keep the MOST RECENT email in the thread as the representative record.
               Store thread depth and all subjects for AI analysis.
    """
    if df.empty:
        return df

    pre = len(df)
    df = df.copy()

    subject_col = "email_subject" if "email_subject" in df.columns else None
    if subject_col is None:
        logger.warning("No email_subject column — skipping email dedup.")
        return df

    date_col = "activity_date" if "activity_date" in df.columns else "create_date"
    if date_col not in df.columns:
        logger.warning("No date column for email dedup.")
        return df

    # ── Phase 1: Remove Gong duplicates ──
    raw_subject = df[subject_col].fillna("").astype(str)
    df["_is_gong"] = raw_subject.str.contains(r'^\[Gong (Out|In)\]', regex=True)
    df["_clean_subject"] = raw_subject.str.replace(r'^\[Gong (Out|In)\]\s*', '', regex=True).str.strip()

    df["_email_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    co_col = "company_name" if "company_name" in df.columns else None
    df["_co"] = df[co_col].fillna("").astype(str).str.strip().str.lower() if co_col else ""
    from_col = "email_from_address" if "email_from_address" in df.columns else None
    df["_from"] = df[from_col].fillna("").astype(str).str.strip().str.lower() if from_col else ""

    has_subject = df["_clean_subject"].str.strip() != ""
    with_subject = df[has_subject].copy()
    without_subject = df[~has_subject].copy()

    if not with_subject.empty:
        with_subject = with_subject.sort_values("_is_gong", ascending=True)
        gong_group = ["_clean_subject", "_email_date", "_co", "_from"]
        with_subject = with_subject.drop_duplicates(subset=[c for c in gong_group if c in with_subject.columns], keep="first")

    df = pd.concat([with_subject, without_subject], ignore_index=True)
    after_gong = len(df)

    # ── Phase 2: Collapse email threads ──
    # Strip Re:/Fwd:/FW: prefixes to get root subject (the original thread topic)
    df["_thread_subject"] = (
        df["_clean_subject"]
        .str.replace(r'^(Re:\s*|Fwd:\s*|FW:\s*|Fw:\s*)+', '', regex=True)
        .str.strip()
        .str.lower()
    )

    # Group by thread subject + company (threads span multiple days)
    df["_dt"] = pd.to_datetime(df[date_col], errors="coerce")

    # Only collapse threads where we have a thread subject
    has_thread = df["_thread_subject"] != ""
    threadable = df[has_thread].copy()
    non_threadable = df[~has_thread].copy()

    if not threadable.empty:
        thread_group = ["_thread_subject", "_co"]
        # Sort by date desc so first record is the most recent
        threadable = threadable.sort_values("_dt", ascending=False)

        # For each thread group, keep the most recent email and annotate with thread info
        thread_records = []
        for key, group in threadable.groupby([c for c in thread_group if c in threadable.columns]):
            # Keep the most recent email as the representative
            rep_row = group.iloc[0].to_dict()
            thread_depth = len(group)
            rep_row["thread_depth"] = thread_depth

            # Build thread summary for AI analysis (all subjects + dates)
            if thread_depth > 1:
                thread_parts = []
                for _, msg in group.iterrows():
                    dt_str = msg["_dt"].strftime("%m/%d") if pd.notna(msg["_dt"]) else "?"
                    direction = msg.get("email_direction", "")
                    subj = msg.get("_clean_subject", "")[:80]
                    thread_parts.append(f"{dt_str} [{direction}] {subj}")
                rep_row["thread_summary"] = " | ".join(thread_parts)
            else:
                rep_row["thread_summary"] = ""

            thread_records.append(rep_row)

        collapsed = pd.DataFrame(thread_records)
    else:
        collapsed = threadable
        if "thread_depth" not in collapsed.columns:
            collapsed["thread_depth"] = 1
            collapsed["thread_summary"] = ""

    result = pd.concat([collapsed, non_threadable], ignore_index=True)

    # Add thread_depth to non-threadable
    if "thread_depth" not in result.columns:
        result["thread_depth"] = 1
    if "thread_summary" not in result.columns:
        result["thread_summary"] = ""
    result["thread_depth"] = result["thread_depth"].fillna(1).astype(int)

    # Clean up temp columns
    drop_cols = ["_is_gong", "_clean_subject", "_email_date", "_co", "_from",
                 "_thread_subject", "_dt"]
    result = result.drop(columns=[c for c in drop_cols if c in result.columns], errors="ignore")

    logger.info("Email dedup: %d -> %d after Gong dedup -> %d after thread collapse (removed %d total).",
                pre, after_gong, len(result), pre - len(result))
    return result


def convert_calls_to_meetings_and_dedupe(calls_df: pd.DataFrame, meetings_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    1. Convert calls with call_and_meeting_type filled out to meetings
    2. Cross-deduplicate calls and meetings to eliminate duplicates
    3. Return cleaned (calls_df, meetings_df)
    """
    if calls_df.empty and meetings_df.empty:
        return calls_df, meetings_df
    
    calls_df = calls_df.copy() if not calls_df.empty else pd.DataFrame()
    meetings_df = meetings_df.copy() if not meetings_df.empty else pd.DataFrame()
    
    # Step 1: Convert calls with call_and_meeting_type filled to meetings
    meeting_type_calls = pd.DataFrame()
    if not calls_df.empty and "call_and_meeting_type" in calls_df.columns:
        # Look for ANY filled call_and_meeting_type (not just "negotiation meeting")
        meeting_type_mask = (
            calls_df["call_and_meeting_type"].notna() & 
            (calls_df["call_and_meeting_type"].astype(str).str.strip() != "") &
            (~calls_df["call_and_meeting_type"].astype(str).str.strip().isin(['nan', 'None', '<NA>']))
        )
        
        meeting_type_calls = calls_df[meeting_type_mask].copy()
        calls_df = calls_df[~meeting_type_mask].copy()  # Remove from calls
        
        if not meeting_type_calls.empty:
            logger.info(f"DEBUG: Found {len(meeting_type_calls)} calls with call_and_meeting_type filled:")
            for _, row in meeting_type_calls.iterrows():
                logger.info(f"  {row.get('call_title', 'No title')} - Type: {row['call_and_meeting_type']}")
            
            # Convert call fields to meeting fields
            meeting_type_calls["meeting_name"] = meeting_type_calls.get("call_title", "Meeting from Call")
            meeting_type_calls["meeting_start_time"] = meeting_type_calls["activity_date"]
            meeting_type_calls["meeting_outcome"] = "Completed"  # Assume completed since it was a logged call
            meeting_type_calls["meeting_type"] = meeting_type_calls["call_and_meeting_type"]
            
            # Add to meetings
            meetings_df = pd.concat([meetings_df, meeting_type_calls], ignore_index=True)
            logger.info(f"Converted {len(meeting_type_calls)} calls with meeting types to meetings")
    
    # Step 2: Cross-deduplicate calls and meetings
    # Remove calls that match meetings by date/time + rep + company
    if not calls_df.empty and not meetings_df.empty:
        calls_to_remove = []
        
        for call_idx, call_row in calls_df.iterrows():
            call_date = pd.to_datetime(call_row.get("activity_date"), errors="coerce")
            call_rep = str(call_row.get("hubspot_owner_name", ""))
            call_company = str(call_row.get("company_name", ""))
            
            if pd.isna(call_date):
                continue
                
            # Look for matching meetings within 2 hours (more lenient)
            for _, meeting_row in meetings_df.iterrows():
                meeting_date = pd.to_datetime(meeting_row.get("meeting_start_time"), errors="coerce")
                meeting_rep = str(meeting_row.get("hubspot_owner_name", ""))
                meeting_company = str(meeting_row.get("company_name", ""))
                
                if pd.isna(meeting_date):
                    continue
                
                # Match if same rep, company, and within 2 hours
                if (call_rep == meeting_rep and 
                    call_company == meeting_company and
                    abs((call_date - meeting_date).total_seconds()) <= 7200):  # 2 hours = 7200 seconds
                    calls_to_remove.append(call_idx)
                    logger.info(f"DEBUG: Removing call that duplicates meeting - {call_company} on {call_date.date()}")
                    break
        
        if calls_to_remove:
            calls_df = calls_df.drop(calls_to_remove)
            logger.info(f"Removed {len(calls_to_remove)} calls that duplicate meetings")
    
    return calls_df, meetings_df


# -- Column dedup & normalization pipeline --------------------------------

def _deduplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Append _2, _3 etc. to duplicate column names."""
    cols = list(df.columns)
    seen: dict[str, int] = {}
    new_cols = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 1
            new_cols.append(c)
    df.columns = new_cols
    return df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [to_snake_case(c) for c in df.columns]
    df = _deduplicate_columns(df)
    df = df.rename(columns=COLUMN_ALIASES)
    df = df.loc[:, [bool(str(c).strip()) and not str(c).startswith("unnamed") for c in df.columns]]
    return df


def coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for col in df.columns:
        if col in DATE_COLUMNS or col.endswith("_date") or col.endswith("_time") or col.endswith("_at"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for col in df.columns:
        if col in NUMERIC_COLUMNS or col.endswith("_amount") or col.endswith("_duration"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for col in df.columns:
        if df[col].dtype != object:
            continue
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        series = series.astype(str).str.strip()
        # Special handling for sequence_id - keep empty as empty string, not np.nan
        if col == "sequence_id":
            series = series.replace({"nan": "", "None": "", "none": ""})
        else:
            series = series.replace({"nan": np.nan, "": np.nan, "None": np.nan, "none": np.nan})
        df[col] = series
    return df


def safe_column(df: pd.DataFrame, col: str, default=np.nan) -> pd.Series:
    if col in df.columns:
        result = df[col]
        if isinstance(result, pd.DataFrame):
            result = result.iloc[:, 0]
        return result
    return pd.Series(default, index=df.index, name=col)


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Full normalization: snake_case -> dedup cols -> alias -> whitespace -> dates -> numerics."""
    if df.empty:
        return df
    df = normalize_columns(df)
    df = strip_whitespace(df)
    df = coerce_dates(df)
    df = coerce_numerics(df)
    logger.info("Normalized: %d rows x %d cols.", len(df), len(df.columns))
    return df
