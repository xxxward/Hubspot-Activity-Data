# HubSpot Sales Analytics Dashboard

Production analytics repository that reads HubSpot CRM data from Google Sheets (synced via Coefficient) and powers a Streamlit dashboard.

## Architecture

```
Google Sheets (Coefficient → HubSpot) → Python (pandas) → Streamlit Dashboard
```

- **Source of truth**: Google Sheets — "Hubspot Activity Data"
- **No database, no CSV files, no HubSpot API calls**
- **Tabs**: Deals, Meetings, Tasks, Tickets, Calls

## Quick Start

### 1. Service Account

Place your Google service account JSON in the project root (or anywhere — just point the env var at it).

The service account email must have **Viewer** access to the spreadsheet.

### 2. Environment

```bash
cp .env.example .env
# Edit .env with your paths
```

### 3. Install

```bash
pip install -r requirements.txt
```

### 4. Run

```bash
# Dashboard
streamlit run streamlit_app.py

# CLI summary (no Streamlit)
python main.py
```

## Repository Structure

```
src/
  sheets/
    sheets_client.py        # gspread auth + tab reading
  parsing/
    normalize.py            # snake_case, type coercion, column mapping
    filters.py              # rep / pipeline / stage filters, terminal tagging
  metrics/
    activity.py             # calls, meetings, completed/overdue tasks by rep
    pipeline.py             # active pipeline value, stage counts, win rate
    terminal.py             # closed won/lost, NCR, sales order, cycle length
    scoring.py              # composite activity score per rep
  utils/
    dates.py                # period bucketing, quarter ranges
    logging.py              # centralized logging config
main.py                     # orchestrates load → normalize → filter → metrics
streamlit_app.py            # dashboard with 3 tabs + sidebar filters
```

## Business Rules

| Rule | Detail |
|------|--------|
| **Reps in scope** | Brad Sherman, Lance Mitton, Dave Borkowski, Jake Lynch, Alex Gonzalez, Owen Labombard |
| **Pipelines** | Growth Pipeline (Upsell/Cross-sell), Acquisition (New Customer), Retention (Existing Product), Calyx Distribution |
| **Terminal stages** | Closed Won, Closed Lost, NCR, Sales Order Created in NS |
| **Active pipeline** | All deals NOT in a terminal stage |
| **Activity score** | `meetings×5 + calls×3 + completed_tasks×2 + overdue_tasks×(−2)` |

## Column Mapping

The code maps your actual Coefficient column names to internal names:

| Sheet Column | Internal Name |
|---|---|
| Deal ID | deal_id |
| Deal Name | deal_name |
| Opp Owner | hubspot_owner_name |
| Deal Stage | deal_stage |
| Amount | amount |
| Create Date | created_date |
| Close Date | close_date |
| Associated Company Name | company_name |
| Activity assigned to | hubspot_owner_name (activities) |
| Activity date | activity_date |
| Meeting start time | activity_date (meetings) |
| Completed at / Due date | used for task status logic |

See `src/parsing/normalize.py` → `COLUMN_ALIASES` for the full mapping.
