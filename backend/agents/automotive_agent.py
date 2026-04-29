"""
VOXA Backend — Automotive Agent (Layer 6: AI Agent Layer)
Orchestrates: Intent Detection → Data Retrieval → LLM Response Generation

This is the brain of the assistant. It:
1. Detects user intent from the query
2. Pulls relevant data from DuckDB
3. Builds context for the LLM
4. Generates rich markdown responses with tables, summaries, and insights
"""

import json
import logging
import re
from typing import AsyncGenerator, Dict, Any
from datetime import datetime, date, timedelta

import pandas as pd

from services.data_service import get_data_service
from services import llm_service

logger = logging.getLogger("voxa.agent")

# ── Intent Categories ──
INTENTS = {
    "weekly_schedule": {
        "keywords": ["schedule", "this week", "weekly", "week's schedule", "production schedule",
                      "what's happening", "planned", "upcoming"],
        "description": "Plant schedule for the current/upcoming week",
    },
    "quarter_comparison": {
        "keywords": ["quarter", "quarterly", "q1", "q2", "q3", "q4", "compared to last quarter",
                      "qoq", "quarter over quarter", "this quarter", "last quarter", "previous quarter"],
        "description": "Quarter-over-quarter performance comparison",
    },
    "week_broadcast": {
        "keywords": ["broadcast", "next week", "previous week", "week over week", "wow",
                      "compared to last week", "week comparison", "weekly comparison", "weekly trend"],
        "description": "Week-over-week data comparison and broadcast",
    },
    "sales_by_model": {
        "keywords": ["model", "vehicle", "car", "top selling", "best seller", "worst",
                      "which model", "suv", "sedan", "hatchback", "variant"],
        "description": "Vehicle model-specific sales analysis",
    },
    "sales_by_plant": {
        "keywords": ["plant", "factory", "location", "facility", "which plant",
                      "plant performance", "production", "output", "capacity"],
        "description": "Plant-level production and sales data",
    },
    "sales_by_region": {
        "keywords": ["region", "country", "india", "usa", "europe", "city", "geography",
                      "where", "market", "territory"],
        "description": "Regional sales breakdown",
    },
    "revenue_analysis": {
        "keywords": ["revenue", "income", "profit", "earnings", "money", "financial",
                      "total sales", "turnover", "growth"],
        "description": "Revenue and financial analysis",
    },
    "trend_analysis": {
        "keywords": ["trend", "over time", "growth", "decline", "pattern", "forecast",
                      "prediction", "projection", "historically"],
        "description": "Trend analysis and patterns",
    },
    "comparison": {
        "keywords": ["compare", "versus", "vs", "difference", "better", "worse",
                      "against", "benchmark"],
        "description": "Comparative analysis between entities",
    },
    "general": {
        "keywords": [],
        "description": "General automotive/plant question",
    },
}

METRIC_SYNONYMS = {
    "forecasted production": "forecast_units",
    "forecast production": "forecast_units",
    "forecasted revenue": "forecast_revenue",
    "forecast revenue": "forecast_revenue",
    "quality issues": "alerts",
    "affected units": "affected_units",
    "units affected": "affected_units",
    "units were affected": "affected_units",
    "affected_units": "affected_units",
    "generated more revenue": "revenue",
    "more revenue": "revenue",
    "production": "units",
    "revenue": "revenue",
    "output": "units",
    "alerts": "alerts",
    "issues": "alerts",
    "sales": "revenue",
    "units": "units",
    "unit": "units",
    "tasks": "tasks",
    "task": "tasks",
}

AGGREGATION_SYNONYMS = {
    "average": "avg",
    "avg": "avg",
    "mean": "avg",
    "total": "sum",
    "sum": "sum",
    "count": "count",
    "number": "count",
    "maximum": "max",
    "max": "max",
    "minimum": "min",
    "min": "min",
    "highest": "max",
    "lowest": "min",
    "trend": "trend",
    "change": "change",
    "difference": "change",
}

AGGREGATION_MAP = {
    "avg": "AVG",
    "sum": "SUM",
    "count": "COUNT",
    "max": "MAX",
    "min": "MIN",
}

GROUP_BY_SYNONYMS = {
    "plant": "plant",
    "department": "department",
    "model": "model",
    "issue type": "issue_type",
    "status": "status",
    "week": "week",
    "quarter": "quarter",
    "month": "month",
    "date": "date",
}

DATE_COLUMNS = {
    "production_data": "date",
    "alerts_quality": "date",
    "forecast_data": "date",
}

METRIC_UNITS = {
    "units": "units",
    "forecast_units": "units",
    "revenue": "USD",
    "forecast_revenue": "USD",
    "alerts": "alert records",
    "affected_units": "affected units",
    "tasks": "tasks",
}

METRIC_DEFINITIONS = {
    "alerts": "Total alert records in alerts_quality. Active alerts are those where status='active'.",
    "affected_units": "Total affected units tied to alerts in the alerts_quality dataset.",
    "revenue": "Revenue figures in production_data, expressed in absolute USD.",
    "forecast_revenue": "Forecast revenue values in forecast_data, expressed in absolute USD.",
    "units": "Production units in production_data.",
    "forecast_units": "Forecast production units in forecast_data.",
    "tasks": "Scheduled tasks in tasks_schedule.",
}

TIME_KEYWORDS = {
    "this month": "this_month",
    "last month": "last_month",
    "this quarter": "this_quarter",
    "last quarter": "last_quarter",
    "this week": "this_week",
    "last week": "last_week",
    "this year": "this_year",
    "last year": "last_year",
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# ── Determinism Helpers ──

def build_deterministic_response(df: pd.DataFrame, structured_data: dict) -> str:
    """
    Generate high-quality SUMMARY and DATA TABLE sections in Python.
    Summary is rendered as bullet points for readability.
    """
    def format_val(val, metric_name):
        if val is None: return "0"
        try:
            f_val = float(str(val).replace(',', ''))
            if "revenue" in metric_name.lower() or "sales" in metric_name.lower():
                return f"${f_val:,.0f}"
            return f"{f_val:,.0f}"
        except:
            return str(val)

    time_meta = structured_data.get("time_meta", {})
    used_time = time_meta.get("used") or structured_data.get("time_range")
    if isinstance(used_time, list):
        used_time = " or ".join(filter(None, [str(t) for t in used_time]))
    if not used_time:
        used_time = "the selected period"

    metric_raw = structured_data.get("metric", "data")
    metric = metric_raw.replace("_", " ").title()
    val = structured_data.get("value")
    filters_used = structured_data.get("filters_applied", "")
    aggregation = structured_data.get("aggregation", "sum")

    # ── Build Summary as 3-4 line prose ──
    if time_meta.get("fallback_occurred"):
        req = time_meta.get("requested")
        summary_text = (
            f"No data was found for the requested period **{req}**. "
            f"The figures below reflect the latest available data from **{used_time}**. "
            f"Please verify the time range or check if data ingestion is up to date."
        )
    elif val is not None and not structured_data.get("group_by"):
        unit = structured_data.get("metric_units", "")
        formatted_val = format_val(val, metric_raw)
        val_str = formatted_val if "$" in formatted_val else f"{formatted_val} {unit}".strip()
        filter_note = f" The results are filtered to **{filters_used}**." if filters_used else ""
        summary_text = (
            f"For **{used_time}**, the total **{metric}** recorded is **{val_str}**.{filter_note} "
            f"This figure is aggregated across all matching records in the dataset and reflects the complete result for the selected period."
        )
    elif not df.empty:
        try:
            group_cols = structured_data.get("group_by")
            if isinstance(group_cols, str):
                group_cols = [group_cols]

            val_col = df.columns[-1]
            temp_df = df.copy()
            temp_df[val_col] = pd.to_numeric(
                temp_df[val_col].astype(str).str.replace(',', '').str.replace('$', ''), errors='coerce'
            )
            top_idx = temp_df[val_col].idxmax()
            top_row = df.loc[top_idx]
            total_sum = temp_df[val_col].sum()

            if group_cols and len(df) > 1:
                top_entity = ", ".join(str(top_row[col]).title() for col in group_cols if col in df.columns)
                top_val = format_val(top_row[val_col], metric_raw)
                total_fmt = format_val(total_sum, metric_raw)
                contribution = round((float(top_row[val_col]) / float(total_sum)) * 100, 1) if total_sum > 0 else 0
                filter_note = f" Results are filtered to **{filters_used}**." if filters_used else ""
                summary_text = (
                    f"The analysis for **{used_time}** covers **{len(df)} {group_cols[0]}(s)** with a combined total {metric.lower()} of **{total_fmt}**.{filter_note} "
                    f"The top performer is **{top_entity}**, contributing **{top_val}** — which accounts for **{contribution}%** of the overall total. "
                    f"The data breakdown below shows the full distribution across all {group_cols[0]}s."
                )
                # Add deterministic insight
                if total_sum > 0:
                    structured_data.setdefault("computed_insights", []).append(
                        f"**{top_entity}** leads all {group_cols[0]}s with a **{contribution}%** share of total {metric.lower()} ({total_fmt}) for {used_time}."
                    )
            elif len(df) == 1:
                top_val = format_val(top_row[val_col], metric_raw)
                if group_cols:
                    top_entity = ", ".join(str(top_row[col]).title() for col in group_cols if col in df.columns)
                    filter_note = f" Results are filtered to **{filters_used}**." if filters_used else ""
                    summary_text = (
                        f"For **{used_time}**, the **{metric.lower()}** recorded for **{top_entity}** is **{top_val}**.{filter_note} "
                        f"This represents the complete aggregated result for this {group_cols[0]} during the selected period."
                    )
                else:
                    summary_text = (
                        f"For **{used_time}**, the total **{metric.lower()}** is **{top_val}**. "
                        f"This is the complete aggregated result for the selected period across all matching records in the dataset."
                    )
            else:
                summary_text = (
                    f"**{len(df)} record(s)** were found for **{metric.lower()}** in **{used_time}**. "
                    f"Refer to the data breakdown table below for the full details."
                )
        except Exception:
            summary_text = f"Data retrieved for **{metric.lower()}** in **{used_time}**. Refer to the breakdown table below."
    else:
        summary_text = (
            f"No records were found for **{metric.lower()}** in **{used_time}**. "
            f"The dataset does not contain any matching entries for this selection. "
            f"Try adjusting the time range or filter criteria."
        )

    summary = f"### Summary\n{summary_text}"

    # ── Build Data Table ──
    if df.empty:
        return f"{summary}\n\nNo data available for this selection."

    headers = [str(col).replace("_", " ").title() for col in df.columns]
    rows = []
    for _, row in df.iterrows():
        formatted_row = []
        for i, item in enumerate(row):
            col_name = df.columns[i]
            if isinstance(item, (int, float)) or (isinstance(item, str) and item.replace('.','',1).isdigit()):
                formatted_row.append(format_val(item, col_name))
            else:
                formatted_row.append(str(item))
        rows.append("| " + " | ".join(formatted_row) + " |")

    table_md = "| " + " | ".join(headers) + " |" + "\n" + "|" + "---|" * len(headers) + "\n" + "\n".join(rows)

    return f"{summary}\n\n### Data Breakdown\n{table_md}"


def validate_numbers_enforce(text: str, df: pd.DataFrame) -> bool:
    """
    STRICT numeric integrity. Returns True if valid, False if ANY hallucination detected.
    """
    import re
    # Extract all numbers from the LLM text
    found_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", text)
    if not found_numbers:
        return True
        
    # Get all valid numbers from the dataframe
    valid_numbers = set()
    # Also include columns themselves if they are numeric
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
             for val in df[col].dropna():
                 valid_numbers.add(str(val).replace(',', ''))
    
    for val in df.values.flatten():
        if pd.notnull(val):
            v_str = str(val).replace(',', '')
            valid_numbers.add(v_str)
            try:
                f_val = float(v_str)
                # Add various formats the LLM might use
                valid_numbers.add(str(int(f_val)))
                valid_numbers.add(f"{int(f_val):,}")
                valid_numbers.add(str(round(f_val, 1)))
                valid_numbers.add(str(round(f_val, 2)))
            except ValueError:
                pass

    # Strict check: if it's not in the source, it's fake.
    for num in found_numbers:
        # Refined bypass: only ignore 1-5 if they appear to be list ordinals (followed by '.' or ')')
        # or if they are extremely common and likely not the 'metric' being hallucinated.
        # However, for metric safety, we only bypass if the number is in a list context in the text.
        is_ordinal = any(re.search(rf"{num}[\.\)]\s", text) for num in ["1", "2", "3", "4", "5"])
        if num in ["1", "2", "3", "4", "5"] and is_ordinal:
            continue
            
        if num not in valid_numbers:
             logger.warning(f"Validation FAILED: LLM invented '{num}'")
             return False
    
    return True


def validate_sql(intent: dict, sql: str) -> bool:
    """
    Pre-execution SQL validation layer.
    """
    sql_upper = sql.upper()
    metric = intent["metric"]
    table = intent["table_name"]
    
    # 1. Correct Table Check
    if table.upper() not in sql_upper:
        logger.error(f"SQL Validation Failed: Table {table} missing from query")
        return False
        
    # 2. Metric Presence
    if metric == "alerts":
        # For alerts, we MUST be querying alerts_quality table
        if table != "alerts_quality":
            logger.error(f"SQL Validation Failed: metric 'alerts' requested but table is {table}")
            return False
        # If it's alerts, we usually expect COUNT(*) or SUM(affected_units)
        # But we must check that the table is correct.
    elif metric.upper() not in sql_upper:
        logger.error(f"SQL Validation Failed: Metric column {metric} missing from query")
        return False
        
    # 3. Aggregation Check
    agg = intent["aggregation"]
    group_by = intent["group_by"]
    if agg == "count" and "COUNT" not in sql_upper:
        logger.error(f"SQL Validation Failed: Expected COUNT aggregation")
        return False
    if agg == "sum":
        if metric == "alerts":
             if "COUNT" not in sql_upper and "SUM" not in sql_upper:
                 logger.error(f"SQL Validation Failed: Expected COUNT or SUM aggregation for alerts")
                 return False
        elif table == "tasks_schedule":
             # Tasks special handling (SELECT *) is valid
             if "*" not in sql and "SUM" not in sql_upper and "COUNT" not in sql_upper:
                 logger.error(f"SQL Validation Failed: Expected *, SUM or COUNT for tasks")
                 return False
        elif "SUM" not in sql_upper:
            logger.error(f"SQL Validation Failed: Expected SUM aggregation")
            return False
    # trend/change produce SUM + GROUP BY — accept as long as SUM is present
    if agg in {"trend", "change"} and "SUM" not in sql_upper:
        logger.error(f"SQL Validation Failed: Expected SUM for trend aggregation")
        return False
    # max/min with group_by uses SUM+ORDER BY internally, so accept SUM or MAX/MIN
    if agg in {"max", "min"} and group_by:
        if "SUM" not in sql_upper and "MAX" not in sql_upper and "MIN" not in sql_upper:
            logger.error(f"SQL Validation Failed: Expected SUM/MAX/MIN aggregation for {agg} intent")
            return False
        
    # 4. Grouping Check
    if group_by:
        group_by_cols = [group_by] if isinstance(group_by, str) else group_by
        sql_has_group = "GROUP BY" in sql_upper
        # Only fail if group_by was requested AND the columns actually exist in the target table
        # (they might have been filtered out if they don't exist)
        any_col_in_sql = any(col.upper() in sql_upper for col in group_by_cols)
        if any_col_in_sql and not sql_has_group:
            logger.error("SQL Validation Failed: Missing GROUP BY clause")
            return False
        
    return True


def detect_intent(query: str) -> str:
    """
    Simple keyword-based intent detection.
    Returns the best matching intent category.
    """
    query_lower = query.lower()
    scores = {}

    for intent_name, intent_data in INTENTS.items():
        if intent_name == "general":
            continue
        score = sum(1 for kw in intent_data["keywords"] if kw in query_lower)
        if score > 0:
            scores[intent_name] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


def _normalize_text(query: str) -> str:
    return re.sub(r"[^a-z0-9\s-]", " ", query.lower())


def _parse_group_by(query: str) -> str | list[str] | None:
    query_lower = query.lower()
    group_columns = []
    
    # Sort by length descending to match longest phrases first
    sorted_groups = sorted(GROUP_BY_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)
    
    # Check if we have "by", "per", "across", etc. OR "which X" / "what X" to confirm it's a grouping request
    # e.g. "which model had highest" => group by model
    # e.g. "what plant generated" => group by plant
    has_grouping_signal = any(f"{signal} " in query_lower for signal in ["by", "per", "across", "break down", "breakdown"])
    
    # Also detect "which <entity>" and "what <entity>" as implicit group-by
    implicit_group_match = re.search(
        r"\b(?:which|what)\s+(vehicle\s+)?(model|plant|factory|region|department|week|quarter|month)\b",
        query_lower
    )
    if implicit_group_match:
        has_grouping_signal = True

    if not has_grouping_signal:
        return None

    matched_phrases = []
    
    # If we detected an implicit "which/what <entity>", ensure that entity is first in the group
    if implicit_group_match:
        raw_entity = implicit_group_match.group(2).lower()  # e.g. "model", "plant"
        mapped = GROUP_BY_SYNONYMS.get(raw_entity)
        if mapped and mapped not in group_columns:
            group_columns.append(mapped)
            matched_phrases.append(raw_entity)

    for phrase, col in sorted_groups:
        if phrase in query_lower:
            # Avoid overlapping matches (e.g. if we already matched 'plant location', don't match 'plant')
            if any(phrase in existing for existing in matched_phrases):
                continue
            group_columns.append(col)
            matched_phrases.append(phrase)
            
    if not group_columns:
        return None
        
    # Deduplicate time grains: if multiple time grains are matched, keep only the most specific one
    # e.g. if 'week' and 'month' are both in query, but query is 'by week', don't group by month too.
    time_grains = {"week", "month", "quarter", "date"}
    found_grains = [g for g in group_columns if g in time_grains]
    if len(found_grains) > 1:
        # Keep only the first one found (which corresponds to the longest phrase matching)
        non_time = [g for g in group_columns if g not in time_grains]
        group_columns = non_time + [found_grains[0]]

    if len(group_columns) == 1:
        return group_columns[0]
    return group_columns


def _is_per_day_query(query: str) -> bool:
    query_lower = query.lower()
    return any(k in query_lower for k in ["per day", "daily average", "average per day"])


def _get_date_column(table_name: str) -> str:
    return DATE_COLUMNS.get(table_name, "date")


def _get_metric_units(metric: str) -> str:
    return METRIC_UNITS.get(metric, "value")


def _get_metric_definition(metric: str) -> str:
    return METRIC_DEFINITIONS.get(metric, f"Metric '{metric}' from the selected dataset.")


def _extract_computed_change(intent: dict, df) -> dict:
    if df is None or df.empty:
        return {}

    time_columns = [c for c in df.columns if c in {"week", "date", "quarter", "month"}]
    if not time_columns or df.shape[0] < 2:
        return {}

    value_columns = [
        c for c in df.columns
        if c not in {"week", "date", "quarter", "month", "plant", "department", "model", "status"}
    ]
    if not value_columns:
        return {}

    primary = value_columns[-1]
    try:
        latest = float(df.iloc[-1][primary])
        previous = float(df.iloc[-2][primary])
    except Exception:
        return {}

    if previous == 0:
        return {}

    pct_change = round((latest - previous) / previous * 100, 2)
    direction = "higher" if pct_change > 0 else "lower" if pct_change < 0 else "unchanged"
    return {
        "primary_metric": primary,
        "latest_value": latest,
        "previous_value": previous,
        "percent_change": pct_change,
        "direction": direction,
    }


def _build_data_insights(intent: dict, df, computed_change: dict) -> list[str]:
    insights = []
    if computed_change:
        metric_label = computed_change["primary_metric"].replace("_", " ")
        direction = computed_change["direction"]
        pct = abs(computed_change["percent_change"])
        insights.append(
            f"The latest {metric_label} is {direction} by {pct}% compared to the previous period."
        )

    if intent["metric"] == "alerts" and df is not None and "status" in df.columns:
        active_count = df[df["status"].astype(str).str.lower() == "active"].shape[0]
        total_count = df.shape[0]
        insights.append(
            f"Active alerts represent {active_count}/{total_count} alert records in the current result set."
        )

    return insights


def _extract_all_time_ranges(query: str) -> list[dict]:
    """Extract multiple time ranges from a query (handling 'OR' cases)."""
    query_lower = query.lower()
    
    # Try splitting by 'or' first
    parts = re.split(r'\s+or\s+', query_lower)
    all_ranges = []
    
    for part in parts:
        # For each part, check if it contains 'and' but isn't a date range
        # If it's something like "May and June", split it.
        sub_parts = re.split(r'\s+and\s+', part)
        for sp in sub_parts:
            # Propagate year context if one part has it and others don't
            year_match = re.search(r"\b(20\d{2})\b", part)
            if year_match and not re.search(r"\b(20\d{2})\b", sp):
                sp = f"{sp} {year_match.group(1)}"
            
            tr = _parse_time_range(sp)
            if tr:
                all_ranges.append(tr)
            
    # Deduplicate ranges
    unique_ranges = []
    seen = set()
    for r in all_ranges:
        key = f"{r.get('type')}_{r.get('month')}_{r.get('week')}_{r.get('quarter')}_{r.get('year')}"
        if key not in seen:
            unique_ranges.append(r)
            seen.add(key)
            
    return unique_ranges

def _parse_time_range(query: str) -> dict | None:
    query_lower = query.lower()
    now = datetime.now()

    for phrase, token in TIME_KEYWORDS.items():
        if phrase in query_lower:
            if token == "this_month":
                return {"type": "month", "month": now.month, "year": now.year, "requested": "this month"}
            if token == "last_month":
                last_month = (now.replace(day=1) - timedelta(days=1))
                return {"type": "month", "month": last_month.month, "year": last_month.year, "requested": "last month"}
            if token == "this_quarter":
                quarter = (now.month - 1) // 3 + 1
                return {"type": "quarter", "quarter": quarter, "year": now.year, "requested": "this quarter"}
            if token == "last_quarter":
                quarter = (now.month - 1) // 3
                year = now.year
                if quarter == 0:
                    quarter = 4
                    year -= 1
                return {"type": "quarter", "quarter": quarter, "year": year, "requested": "last quarter"}
            if token == "this_week":
                return {"type": "week", "week": now.isocalendar()[1], "year": now.year, "requested": "this week"}
            if token == "last_week":
                last_week_date = now - timedelta(days=7)
                return {"type": "week", "week": last_week_date.isocalendar()[1], "year": last_week_date.year, "requested": "last week"}
            if token == "this_year":
                return {"type": "year", "year": now.year, "requested": "this year"}
            if token == "last_year":
                return {"type": "year", "year": now.year - 1, "requested": "last year"}

    # Month parsing
    for m_name, m_num in MONTHS.items():
        if re.search(rf"\b{m_name}\b", query_lower):
            year_match = re.search(r"\b(20\d{2})\b", query_lower)
            year = int(year_match.group(1)) if year_match else now.year
            return {"type": "month", "month": m_num, "year": year, "requested": f"{m_name.title()} {year}"}

    # Bare week number: "week 12", "week 12 of 2026", "week 12 2026"
    week_match = re.search(r"\bweek\s+(\d{1,2})(?:\s+(?:of\s+)?(\d{4}))?\b", query_lower)
    if week_match:
        week_num = int(week_match.group(1))
        year = int(week_match.group(2)) if week_match.group(2) else now.year
        return {"type": "week", "week": week_num, "year": year, "requested": f"Week {week_num} {year}"}

    quarter_match = re.search(r"\bq([1-4])(?:\s+(\d{4}))?\b", query_lower)
    if quarter_match:
        quarter = int(quarter_match.group(1))
        year = int(quarter_match.group(2) or now.year)
        return {"type": "quarter", "quarter": quarter, "year": year, "requested": f"Q{quarter} {year}"}

    year_match = re.search(r"\b(20\d{2})\b", query_lower)
    if year_match:
        year = int(year_match.group(1))
        return {"type": "year", "year": year, "requested": str(year)}

    return None


def classify_query_type(query: str) -> str:
    query_lower = query.lower()
    if any(token in query_lower for token in ["why", "cause", "because", "reason", "how come"]):
        return "diagnostic"
    if any(token in query_lower for token in ["compare", "versus", " vs ", "difference", "better", "worse"]):
        return "comparative"
    if any(token in query_lower for token in ["show", "list", "display", "what are", "which are", "give me"]):
        return "listing"
    return "analytical"


def _parse_filters(query: str, table_name: str) -> dict:
    query_lower = query.lower()
    filters = {}
    data_svc = get_data_service()
    candidate_columns = ["plant", "department", "model", "issue_type", "status", "severity"]

    for column in candidate_columns:
        try:
            values = data_svc.get_column_values(table_name, column)
        except Exception:
            continue
        for value in values:
            if value is None:
                continue
            value_text = str(value).lower()
            if value_text and value_text in query_lower:
                # Skip filtering on generic terms that match column values but are used generally
                if value_text in ["quality issue", "alert", "issue"] and column == "issue_type":
                    # Only filter if the query has it as a distinct specific term, not a plural/general
                    if f" {value_text} " not in f" {query_lower} ":
                        continue

                if column not in filters:
                    filters[column] = []
                if value not in filters[column]:
                    filters[column].append(value)
    
    # Flatten single-value filters back to scalar for compatibility, 
    # but keep as list if multiple found.
    for col, vals in filters.items():
        if len(vals) == 1:
            filters[col] = vals[0]
            
    return filters


def _choose_time_clause(table_name: str, time_range: dict | None) -> tuple[str | None, dict]:
    if time_range is None:
        return None, {"used": None, "requested": None}

    date_col = _get_date_column(table_name)
    # Ensure date_col is valid for the specific table
    if table_name == "alerts_quality":
        # Check if column is actually 'date' or 'Date' (some CSVs vary)
        data_svc = get_data_service()
        cols = [c["name"].lower() for c in data_svc.get_table_schemas().get(table_name, [])]
        if "date" not in cols and "date" in cols: # Should be lowercase already
             pass 
    
    # Use a more robust date casting that handles YYYY-MM-DD explicitly
    date_expr = f"strptime({date_col}, '%Y-%m-%d')" if table_name == "alerts_quality" else f"TRY_CAST({date_col} AS DATE)"
    expr = None
    requested = time_range.get("requested")
    if time_range["type"] == "month":
        expr = (
            f"EXTRACT(month FROM {date_expr}) = {time_range['month']} AND "
            f"EXTRACT(year FROM {date_expr}) = {time_range['year']}"
        )
    elif time_range["type"] == "quarter":
        q = time_range["quarter"]
        yr = time_range["year"]
        q_start = (q - 1) * 3 + 1
        q_end = q * 3
        expr = (
            f"EXTRACT(month FROM {date_expr}) BETWEEN {q_start} AND {q_end} AND "
            f"EXTRACT(year FROM {date_expr}) = {yr}"
        )
    elif time_range["type"] == "week":
        w = time_range["week"]
        yr = time_range["year"]
        # Prioritize the manual 'week' column if it exists in the table.
        # This prevents double-counting when manual labels don't match ISO calendar weeks.
        data_svc = get_data_service()
        table_cols = [c["name"] for c in data_svc.get_table_schemas().get(table_name, [])]
        
        if "week" in table_cols:
            expr = (
                f"LOWER(CAST(week AS VARCHAR)) IN ('w{w:02d}', 'w{w}', '{w:02d}', '{w}', 'week {w}', 'week {w:02d}') "
                f"AND EXTRACT(year FROM {date_expr}) = {yr}"
            )
        else:
            expr = (
                f"EXTRACT(week FROM {date_expr}) = {w} AND "
                f"EXTRACT(year FROM {date_expr}) = {yr}"
            )
    elif time_range["type"] == "year":
        expr = f"EXTRACT(year FROM {date_expr}) = {time_range['year']}"
    else:
        return None, {"used": requested, "requested": requested}

    data_svc = get_data_service()
    count_sql = f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE {expr}"
    row_count = data_svc.execute_query(count_sql).iloc[0, 0]
    if row_count > 0:
        return expr, {"used": requested, "requested": requested, "available_rows": int(row_count)}

    latest_sql = f"SELECT MAX({date_expr}) AS latest_date FROM {table_name}"
    latest_row = data_svc.execute_query(latest_sql)
    if latest_row.empty or latest_row.iloc[0, 0] is None:
        return expr, {"used": requested, "requested": requested, "available_rows": 0}

    latest_date = latest_row.iloc[0, 0]
    
    # Robust Fallback: respect the original time grain
    if time_range["type"] == "week":
        used_week = latest_date.isocalendar()[1]
        used_year = latest_date.year
        used = f"Week {used_week} {used_year}"
        fallback_expr = (
            f"("
            f"  LOWER(CAST(week AS VARCHAR)) IN ('w{used_week:02d}', 'w{used_week}', '{used_week:02d}', '{used_week}', 'week {used_week}', 'week {used_week:02d}') "
            f"  OR EXTRACT(week FROM {date_expr}) = {used_week}"
            f") AND EXTRACT(year FROM {date_expr}) = {used_year}"
        )
    elif time_range["type"] == "quarter":
        used_quarter = (latest_date.month - 1) // 3 + 1
        used_year = latest_date.year
        used = f"Q{used_quarter} {used_year}"
        fq_start = (used_quarter - 1) * 3 + 1
        fq_end = used_quarter * 3
        fallback_expr = (
            f"EXTRACT(month FROM {date_expr}) BETWEEN {fq_start} AND {fq_end} AND "
            f"EXTRACT(year FROM {date_expr}) = {used_year}"
        )
    else:
        # Default to month
        used_month = int(latest_date.strftime("%m"))
        used_year = int(latest_date.strftime("%Y"))
        used = latest_date.strftime("%B %Y")
        fallback_expr = (
            f"EXTRACT(month FROM {date_expr}) = {used_month} AND "
            f"EXTRACT(year FROM {date_expr}) = {used_year}"
        )
        
    return fallback_expr, {
        "requested": requested,
        "used": used,
        "fallback_occurred": True,
        "available_rows": int(
            data_svc.execute_query(
                f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE {fallback_expr}"
            ).iloc[0, 0]
        ),
    }


def _choose_table(metric: str) -> str:
    if metric in {"forecast_units", "forecast_revenue"}:
        return "forecast_data"
    if metric in {"alerts", "affected_units"}:
        return "alerts_quality"
    if metric == "tasks":
        return "tasks_schedule"
    return "production_data"


def _parse_structured_intent(query: str) -> dict | None:
    query_lower = query.lower()
    raw = _normalize_text(query_lower)
    metric = None
    aggregation = None
    group_by = _parse_group_by(query)

    # Sort by length descending to match longest phrases first (e.g. "affected units" before "units")
    sorted_synonyms = sorted(METRIC_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)
    
    for phrase, field in sorted_synonyms:
        if phrase in query_lower:
            metric = field
            break

    for phrase, agg in AGGREGATION_SYNONYMS.items():
        if phrase in query_lower:
            aggregation = agg
            break

    if metric is None:
        if any(token in query_lower for token in ["alert", "issue"]):
            metric = "alerts"
        elif any(token in query_lower for token in ["revenue", "sales"]):
            metric = "revenue"
        elif any(token in query_lower for token in ["unit", "production", "output"]):
            metric = "units"
        elif "tasks" in query_lower or "schedule" in query_lower:
            metric = "tasks"

    if aggregation is None:
        if "average" in query_lower or "avg" in query_lower or "mean" in query_lower:
            aggregation = "avg"
        elif "total" in query_lower or "sum" in query_lower or "overall" in query_lower:
            aggregation = "sum"
        elif "count" in query_lower or "how many" in query_lower:
            # "how many units/revenue were produced" → SUM the metric, not COUNT rows
            if metric in {"units", "revenue", "forecast_units", "forecast_revenue", "affected_units"}:
                aggregation = "sum"
            else:
                aggregation = "count"
        elif "maximum" in query_lower or "highest" in query_lower or "biggest" in query_lower:
            aggregation = "max"
        elif "minimum" in query_lower or "lowest" in query_lower or "smallest" in query_lower:
            aggregation = "min"
        else:
            # Sane Defaults
            if metric == "alerts":
                aggregation = "count"
            elif metric in ["revenue", "units"]:
                aggregation = "sum"
            else:
                aggregation = "sum"

    if metric is None:
        return None

    table_name = _choose_table(metric)
    filters = _parse_filters(query_lower, table_name)
    
    # Handle multiple time ranges (OR queries)
    time_ranges = _extract_all_time_ranges(query)
    time_range = time_ranges[0] if time_ranges else None
    
    # Confidence Score for intent
    confidence_score = 1.0
    # Penalty if we relied on the generic keyword fallback for the metric
    rely_on_metric_fallback = not any(phrase in query_lower for phrase, _ in sorted_synonyms)
    if rely_on_metric_fallback:
        confidence_score -= 0.3 # Vague metric
        
    # Penalty if we guessed the aggregation
    rely_on_agg_fallback = not any(phrase in query_lower for phrase, _ in AGGREGATION_SYNONYMS.items())
    if rely_on_agg_fallback:
        confidence_score -= 0.2 # Guessed aggregation
        
    return {
        "metric": metric,
        "aggregation": aggregation,
        "group_by": group_by,
        "filters": filters,
        "time_range": time_range,
        "all_time_ranges": time_ranges, # Store for multi-time logic
        "table_name": table_name,
        "raw_query": query,
        "query_type": classify_query_type(query),
        "intent_confidence": confidence_score
    }


def _build_sql_for_intent(intent: dict) -> tuple[str, dict, str] | None:
    metric = intent["metric"]
    aggregation = intent["aggregation"]
    group_by = intent["group_by"]
    filters = intent["filters"]
    table_name = intent["table_name"]
    raw_query = intent.get("raw_query", "")
    all_time_ranges = intent.get("all_time_ranges", [])

    # Check for JOIN requirement (e.g. "impact of alerts on production")
    is_join = any(k in raw_query.lower() for k in ["impact", "correlation", "relation", "versus", " vs ", "against"]) and \
              any(k in raw_query.lower() for k in ["alert", "issue"]) and \
              any(k in raw_query.lower() for k in ["production", "units", "output", "revenue"])

    if is_join:
        # Specialized JOIN query
        time_range = all_time_ranges[0] if all_time_ranges else None
        time_expr, time_meta = _choose_time_clause("production_data", time_range)
        where_clause = f"WHERE {time_expr}" if time_expr else ""
        
        sql = f"""
            SELECT p.week, 
                   COALESCE(SUM(p.units), 0) AS total_units, 
                   COALESCE(SUM(p.revenue), 0) AS total_revenue,
                   COUNT(a.id) AS alert_count,
                   COALESCE(SUM(a.affected_units), 0) AS affected_units
            FROM production_data p
            LEFT JOIN alerts_quality a ON p.week = a.week AND p.plant = a.plant
            {where_clause}
            GROUP BY p.week
            ORDER BY p.week
        """.strip()
        return sql, time_meta, where_clause

    select_clauses = []
    group_clause = ""
    order_clause = ""
    where_clauses = []

    if metric == "alerts":
        metric_expr = "*"
        col_label = "issue_records"
    elif metric == "affected_units":
        metric_expr = "affected_units"
        col_label = "affected_units"
    else:
        metric_expr = metric
        col_label = metric

    derived_per_day = aggregation == "avg" and _is_per_day_query(raw_query)
    alias = None

    if metric == "alerts":
        if aggregation == "sum":
             select_clauses.append("COUNT(*) AS total_alerts")
             alias = "total_alerts"
        elif aggregation == "avg":
             select_clauses.append("COUNT(*) AS alert_count")
             alias = "alert_count"
        else:
            select_clauses.append("COUNT(*) AS total_alerts")
            alias = "total_alerts"
    elif aggregation == "avg" and derived_per_day:
        select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
        select_clauses.append(f"COUNT(DISTINCT CAST({_get_date_column(table_name)} AS DATE)) AS record_days")
        select_clauses.append(f"ROUND(SUM({metric_expr}) / NULLIF(COUNT(DISTINCT CAST({_get_date_column(table_name)} AS DATE)), 0), 2) AS average_{col_label}")
        alias = f"average_{col_label}"
    elif aggregation == "avg":
        select_clauses.append(f"ROUND(AVG({metric_expr}), 2) AS average_{col_label}")
        alias = f"average_{col_label}"
    elif aggregation == "sum":
        select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
        alias = f"total_{col_label}"
    elif aggregation == "count":
        select_clauses.append(f"COUNT(*) AS total_{col_label}")
        alias = f"total_{col_label}"
    elif aggregation == "max":
        # For alerts, 'max' means we want the group with the highest COUNT.
        if metric == "alerts":
            # Select clause already added in the metric=='alerts' block
            pass
        elif group_by:
            select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
            alias = f"total_{col_label}"
        else:
            select_clauses.append(f"MAX({metric_expr}) AS max_{col_label}")
            alias = f"max_{col_label}"
    elif aggregation == "min":
        if metric == "alerts":
            pass
        elif group_by:
            select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
            alias = f"total_{col_label}"
        else:
            select_clauses.append(f"MIN({metric_expr}) AS min_{col_label}")
            alias = f"min_{col_label}"
    elif aggregation in {"trend", "change"}:
        # Produce a time-series: SUM per week so the LLM sees the trajectory
        select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
        alias = f"total_{col_label}"
        # Force group by week for trend queries unless already grouped
        if not group_by:
            if "week" in table_cols:
                select_clauses = ["week"] + select_clauses
                group_clause = "GROUP BY week"
                group_key = "week"
                order_clause = "ORDER BY week"
            else:
                date_col = _get_date_column(table_name)
                grain_expr = f"EXTRACT(week FROM CAST({date_col} AS DATE)) AS week_number"
                select_clauses = [grain_expr] + select_clauses
                group_clause = "GROUP BY week_number"
                group_key = "week_number"
                order_clause = "ORDER BY week_number"

    data_svc = get_data_service()
    table_schemas = data_svc.get_table_schemas()
    table_cols = [c["name"] for c in table_schemas.get(table_name, [])]
    
    group_key = None
    if group_by:
        if isinstance(group_by, str):
            group_by_list = [group_by]
        else:
            group_by_list = group_by
            
        valid_groups = [g for g in group_by_list if g in table_cols]
        if valid_groups:
            group_key = ", ".join(valid_groups)
            select_clauses = valid_groups + select_clauses
            group_clause = f"GROUP BY {group_key}"
        else:
            group_key = None

    if filters:
        for key, value in filters.items():
            if key not in table_cols: continue
            if isinstance(value, list):
                quoted_vals = [f"LOWER('{str(v).replace(chr(39), chr(39)+chr(39))}')" for v in value]
                where_clauses.append(f"LOWER({key}) IN ({', '.join(quoted_vals)})")
            else:
                safe = str(value).replace("'", "''")
                where_clauses.append(f"LOWER({key}) = LOWER('{safe}')")

    # Multi-time range handling
    time_exprs = []
    final_time_meta = {"used": [], "requested": [], "available_rows": 0}
    
    if all_time_ranges:
        # If multiple distinct time ranges are requested (e.g. "Jan AND Feb", "this week vs last week"),
        # we must GROUP BY the time grain so each period gets its own row, not one collapsed total.
        needs_group_by_time = len(all_time_ranges) > 1

        for tr in all_time_ranges:
            expr, meta = _choose_time_clause(table_name, tr)
            if expr:
                time_exprs.append(f"({expr})")
                final_time_meta["used"].append(meta.get("used"))
                final_time_meta["requested"].append(meta.get("requested"))
                final_time_meta["available_rows"] += meta.get("available_rows", 0)

        if time_exprs:
            where_clauses.append("(" + " OR ".join(time_exprs) + ")")
            final_time_meta["used"] = " vs ".join(filter(None, [str(t) for t in final_time_meta["used"]]))
            final_time_meta["requested"] = " vs ".join(filter(None, [str(t) for t in final_time_meta["requested"]]))

            # Inject time-grain GROUP BY so each period appears as a separate row
            if needs_group_by_time and not group_key:
                time_grain = all_time_ranges[0].get("type")  # "month", "week", "quarter"
                grain_col_map = {"week": "week", "month": "month", "quarter": "quarter", "year": "year"}
                grain_col = grain_col_map.get(time_grain)
                if grain_col and grain_col in table_cols:
                    select_clauses = [grain_col] + select_clauses
                    group_clause = f"GROUP BY {grain_col}"
                    group_key = grain_col
                    order_clause = f"ORDER BY {grain_col}"
                elif time_grain in {"week", "month"}:
                    # Fall back to extracting from the date column
                    date_col = _get_date_column(table_name)
                    if time_grain == "week":
                        grain_expr = f"EXTRACT(week FROM CAST({date_col} AS DATE)) AS week_number"
                        order_col = "week_number"
                    else:
                        grain_expr = f"EXTRACT(month FROM CAST({date_col} AS DATE)) AS month_number"
                        order_col = "month_number"
                    select_clauses = [grain_expr] + select_clauses
                    group_clause = f"GROUP BY {order_col}"
                    group_key = order_col
                    order_clause = f"ORDER BY {order_col}"
    else:
        # Default latest if no time range
        final_time_meta = {"used": None, "requested": None, "available_rows": 0}

    if not time_exprs:
         final_time_meta = {"used": None, "requested": None, "available_rows": 0}

    if table_name == "tasks_schedule" and aggregation == "sum" and "total" not in raw_query:
        where_stmt = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"SELECT * FROM tasks_schedule {where_stmt} LIMIT 10".strip()
        return sql, final_time_meta, where_stmt

    if aggregation in {"sum", "max", "min"} and alias is not None and group_by:
        query_lower_raw = raw_query.lower()
        is_single_best = any(k in query_lower_raw for k in ["highest", "lowest", "which", "what", "best", "worst", "leading"])
        is_top_list = any(k in query_lower_raw for k in ["top", "bottom"])
        if is_single_best and not is_top_list:
            # "Which model had highest" → Order by the metric so the summary logic picks the top one
            sort_dir = "ASC" if aggregation == "min" or any(k in query_lower_raw for k in ["lowest", "worst", "minimum", "fewest"]) else "DESC"
            order_clause = f"ORDER BY {alias} {sort_dir}"
        elif is_top_list:
            order_clause = f"ORDER BY {alias} DESC LIMIT 5"
        else:
            order_clause = f"ORDER BY {alias} DESC"
    elif group_clause and not order_clause and group_key:
        order_clause = f"ORDER BY {group_key}"

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"SELECT {', '.join(select_clauses)} FROM {table_name} {where_clause} {group_clause} {order_clause}".strip()
    return sql, final_time_meta, where_clause


def _build_structured_context(intent: dict, df, sql: str, time_meta: dict, row_count: int, signals: dict | None = None) -> str:
    value = None
    if df is not None and not df.empty:
        if df.shape[0] == 1 and df.shape[1] >= 1:
            value = df.iloc[0, -1]
    summary = {}
    trend_label = None
    if df is not None and not df.empty:
        if "total_units" in df.columns:
            summary["total_units"] = int(df.iloc[0]["total_units"])
        if "record_days" in df.columns:
            summary["days"] = int(df.iloc[0]["record_days"])
        if "average_units" in df.columns:
            summary["average_units"] = float(df.iloc[0]["average_units"])
        if "average_affected_units" in df.columns:
            summary["average_affected_units"] = float(df.iloc[0]["average_affected_units"])
        if "max_units" in df.columns:
            summary["max_units"] = float(df.iloc[0]["max_units"])

        if df.shape[0] > 1 and "total_units" in df.columns:
            first = df.iloc[0]["total_units"]
            last = df.iloc[-1]["total_units"]
            if last > first:
                trend_label = "increasing"
            elif last < first:
                trend_label = "decreasing"
            else:
                trend_label = "flat"

    if trend_label:
        summary["trend"] = trend_label

    # Enhanced Confidence Scoring
    if row_count > 100:
        confidence = "high"
    elif row_count > 20:
        confidence = "medium"
    else:
        confidence = "low"

    # Calculate advanced metrics
    computed_change = _extract_computed_change(intent, df)
    computed_insights = _build_data_insights(intent, df, computed_change)
    allow_trend = bool(computed_change)

    # Add advanced insights (ratios/anomalies) using Cross-Dataset Signals
    if signals and intent["metric"] == "alerts":
        latest_stats = signals.get("latest_stats", {})
        total_prod = latest_stats.get("production_units", 0)
        affected = summary.get("average_affected_units", 0) * row_count if "average_affected_units" in summary else 0
        
        if total_prod > 0 and affected > 0:
            impact_ratio = round((affected / total_prod) * 100, 2)
            if impact_ratio > 5:
                computed_insights.append(f"EXECUTIVE ALERT: Quality issues are affecting {impact_ratio}% of current production output.")

    structured = {
        "metric": intent["metric"],
        "metric_definition": _get_metric_definition(intent["metric"]),
        "metric_units": _get_metric_units(intent["metric"]),
        "aggregation": intent["aggregation"],
        "group_by": intent["group_by"],
        "query_type": intent.get("query_type", "analytical"),
        "time_range": time_meta.get("used") or time_meta.get("requested"),
        "time_meta": {
            "requested": time_meta.get("requested"),
            "used": time_meta.get("used"),
            "fallback_occurred": time_meta.get("requested") != time_meta.get("used") and time_meta.get("used") is not None
        },
        "confidence": confidence,
        "confidence_reason": f"Based on {row_count} records",
        "allow_trend": allow_trend,
        "display_unit": "auto",
        "notes": f"Based on {row_count} record(s) in the selected time range.",
        "sql": sql,
        "value": value,
        "summary": summary,
        "computed_change": computed_change,
        "computed_insights": computed_insights,
        "computed_results": df.to_dict(orient="records") if df is not None else [],
    }
    class _SafeEncoder(json.JSONEncoder):
        def default(self, obj):
            import numpy as np
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if hasattr(obj, 'item'):
                return obj.item()
            return super().default(obj)
    return json.dumps(structured, indent=2, cls=_SafeEncoder)


def _execute_structured_intent(intent: dict, signals: dict | None = None) -> dict:
    data_svc = get_data_service()
    sql, time_meta, where_clause = _build_sql_for_intent(intent)
    if sql is None:
        return {"status": "UNSUPPORTED"}

    # SQL Validation Step
    if not validate_sql(intent, sql):
        return {"status": "SQL_VALIDATION_FAILED"}

    row_count = data_svc.execute_query(f"SELECT COUNT(*) AS cnt FROM {intent['table_name']} {where_clause}").iloc[0, 0]
    if row_count == 0:
        logger.info({
            "query": intent["raw_query"],
            "intent": intent,
            "sql": sql,
            "status": "NO_DATA",
            "row_count": int(row_count),
        })
        return {
            "status": "NO_DATA",
            "message": (
                f"No data found for {time_meta.get('requested', 'the requested time range')}. "
                f"Showing latest available data: {time_meta.get('used', 'unknown')}"
            ),
            "sql": sql,
            "time_meta": time_meta,
            "row_count": int(row_count),
        }

    df = data_svc.execute_query(sql)
    logger.info({
        "query": intent["raw_query"],
        "intent": intent,
        "sql": sql,
        "status": "OK",
        "row_count": int(row_count),
    })
    return {
        "status": "OK",
        "sql": sql,
        "time_meta": time_meta,
        "row_count": int(row_count),
        "structured_context": _build_structured_context(intent, df, sql, time_meta, int(row_count), signals),
        "results_df": df,
    }


def _is_dashboard_query(query: str) -> bool:
    """
    True only when the user wants a high-level global overview with NO specific entity filter.
    
    Key rules:
    - Unambiguous dashboard words (dashboard, overview, full report, etc.) always trigger,
      UNLESS a specific entity (plant name, model, etc.) is also present.
    - "summary" alone is too broad: only triggers if there's no "for/of/at <entity>" qualifier,
      because "Summary for Dearborn" is a filtered query, not a global dashboard.
    """
    q = query.lower()

    # Hard dashboard keywords — unambiguous intent
    hard_keywords = [
        "dashboard", "overview", "all metrics",
        "how are we doing", "status report", "weekly report",
        "show me everything", "full report",
    ]
    has_hard = any(k in q for k in hard_keywords)

    # "summary" and "overall" are soft — only count them when no entity qualifier follows
    if not has_hard:
        soft_keywords = ["summary", "overall", "plant status"]
        if any(k in q for k in soft_keywords):
            # If query contains "for/of/at/in <word>", treat it as a filtered query, not a dashboard
            has_entity_qualifier = bool(re.search(r'\b(for|of|at|in)\s+\w+', q))
            has_hard = not has_entity_qualifier

    if not has_hard:
        return False

    # Even for hard keywords: if a specific filterable entity (plant name, model name) is
    # mentioned, let the structured path handle it so filters are respected.
    try:
        data_svc = get_data_service()
        for column in ["plant", "model", "department"]:
            try:
                values = data_svc.get_column_values("production_data", column)
            except Exception:
                continue
            for value in values:
                if value and str(value).lower() in q:
                    return False  # Specific entity → not a global dashboard
    except Exception:
        pass  # If data service unavailable, proceed with dashboard

    return True


def _is_actual_vs_forecast_query(query: str) -> bool:
    """True when the user wants to compare actuals against forecast."""
    q = query.lower()
    has_compare = any(k in q for k in ["compare", "versus", " vs ", "against", "difference", "actual vs", "vs forecast", "forecast vs"])
    has_actual = any(k in q for k in ["actual", "production", "units", "revenue"])
    has_forecast = any(k in q for k in ["forecast", "predicted", "projection", "target"])
    return (has_compare and has_forecast) or (has_actual and has_forecast)


def execute_dashboard_query(query: str) -> str:
    """
    Build a full dashboard: production + revenue + alerts, aggregated for the requested period.
    Respects plant/model/department filters if present in the query.
    """
    data_svc = get_data_service()
    time_range = _parse_time_range(query)

    # Parse any entity filters (plant, model, etc.) so a "dashboard for Dearborn" is scoped correctly
    prod_filters = _parse_filters(query, "production_data")
    alert_filters = _parse_filters(query, "alerts_quality")
    fcast_filters = _parse_filters(query, "forecast_data")

    def _build_filter_clause(filters: dict, table_cols: list[str]) -> str:
        """Build WHERE filter fragment from a filters dict, skipping unknown columns."""
        clauses = []
        for key, value in filters.items():
            if key not in table_cols:
                continue
            if isinstance(value, list):
                quoted = [f"LOWER('{str(v).replace(chr(39), chr(39)+chr(39))}')" for v in value]
                clauses.append(f"LOWER({key}) IN ({', '.join(quoted)})")
            else:
                safe = str(value).replace("'", "''")
                clauses.append(f"LOWER({key}) = LOWER('{safe}')")
        return " AND ".join(clauses)

    # --- Production & Revenue ---
    time_expr_prod, time_meta = _choose_time_clause("production_data", time_range)
    prod_table_cols = [c["name"] for c in data_svc.get_table_schemas().get("production_data", [])]
    prod_filter_sql = _build_filter_clause(prod_filters, prod_table_cols)
    prod_where_parts = [p for p in [time_expr_prod, prod_filter_sql] if p]
    prod_where = f"WHERE {' AND '.join(prod_where_parts)}" if prod_where_parts else ""
    try:
        prod_df = data_svc.execute_query(
            f"SELECT SUM(units) AS total_units, SUM(revenue) AS total_revenue FROM production_data {prod_where}"
        )
        total_units = int(prod_df.iloc[0]["total_units"] or 0)
        total_revenue = float(prod_df.iloc[0]["total_revenue"] or 0)
    except Exception:
        total_units, total_revenue = 0, 0

    # --- Forecast ---
    time_expr_fcast, _ = _choose_time_clause("forecast_data", time_range)
    fcast_table_cols = [c["name"] for c in data_svc.get_table_schemas().get("forecast_data", [])]
    fcast_filter_sql = _build_filter_clause(fcast_filters, fcast_table_cols)
    fcast_where_parts = [p for p in [time_expr_fcast, fcast_filter_sql] if p]
    fcast_where = f"WHERE {' AND '.join(fcast_where_parts)}" if fcast_where_parts else ""
    try:
        fcast_df = data_svc.execute_query(
            f"SELECT SUM(forecast_units) AS forecast_units, SUM(forecast_revenue) AS forecast_revenue FROM forecast_data {fcast_where}"
        )
        forecast_units = int(fcast_df.iloc[0]["forecast_units"] or 0)
        forecast_revenue = float(fcast_df.iloc[0]["forecast_revenue"] or 0)
    except Exception:
        forecast_units, forecast_revenue = 0, 0

    # --- Alerts ---
    time_expr_alerts, _ = _choose_time_clause("alerts_quality", time_range)
    alert_table_cols = [c["name"] for c in data_svc.get_table_schemas().get("alerts_quality", [])]
    alert_filter_sql = _build_filter_clause(alert_filters, alert_table_cols)
    alert_where_parts = [p for p in [time_expr_alerts, alert_filter_sql] if p]
    alert_where = f"WHERE {' AND '.join(alert_where_parts)}" if alert_where_parts else ""
    try:
        alert_df = data_svc.execute_query(
            f"SELECT COUNT(*) AS total_alerts, "
            f"SUM(CASE WHEN LOWER(status)='active' THEN 1 ELSE 0 END) AS active_alerts, "
            f"SUM(affected_units) AS affected_units "
            f"FROM alerts_quality {alert_where}"
        )
        total_alerts = int(alert_df.iloc[0]["total_alerts"] or 0)
        active_alerts = int(alert_df.iloc[0]["active_alerts"] or 0)
        affected_units = int(alert_df.iloc[0]["affected_units"] or 0)
    except Exception:
        total_alerts, active_alerts, affected_units = 0, 0, 0

    period = time_meta.get("used") or "All Available Data"
    fallback_note = ""
    if time_meta.get("fallback_occurred"):
        fallback_note = f"\n\n> ⚠️ No data for **{time_meta['requested']}**. Showing latest available: **{period}**."

    # Build a scope label if entity filters were applied (e.g. "Dearborn plant")
    scope_parts = []
    for col, val in prod_filters.items():
        if col in ("plant", "model", "department"):
            scope_parts.append(str(val).title() if isinstance(val, str) else ", ".join(str(v).title() for v in val))
    scope_label = f" — **{', '.join(scope_parts)}**" if scope_parts else ""

    # Variance calculations
    units_var = total_units - forecast_units
    rev_var = total_revenue - forecast_revenue
    units_var_str = f"+{units_var:,}" if units_var >= 0 else f"{units_var:,}"
    rev_var_str = f"+${rev_var:,.0f}" if rev_var >= 0 else f"-${abs(rev_var):,.0f}"

    summary = (
        f"### Summary\n"
        f"For **{period}**{scope_label}, production reached **{total_units:,} units** (forecast: {forecast_units:,}, variance: {units_var_str}) "
        f"with revenue of **${total_revenue:,.0f}** (forecast: ${forecast_revenue:,.0f}, variance: {rev_var_str}). "
        f"There are **{active_alerts} active alerts** out of {total_alerts} total, affecting **{affected_units:,} units**."
        f"{fallback_note}"
    )

    table = (
        f"### Dashboard Overview{scope_label}\n"
        "| Metric | Actual | Forecast | Variance |\n"
        "|--------|--------|----------|----------|\n"
        f"| Production Units | {total_units:,} | {forecast_units:,} | {units_var_str} |\n"
        f"| Revenue | ${total_revenue:,.0f} | ${forecast_revenue:,.0f} | {rev_var_str} |\n"
        f"| Total Alerts | {total_alerts:,} | — | — |\n"
        f"| Active Alerts | {active_alerts:,} | — | — |\n"
        f"| Affected Units | {affected_units:,} | — | — |"
    )

    takeaways = ["### Key Takeaways"]
    if units_var < 0:
        takeaways.append(f"- ⚠️ Production is **{abs(units_var):,} units below forecast** for {period}.")
    else:
        takeaways.append(f"- ✅ Production is **{units_var_str} units above forecast** for {period}.")
    if active_alerts > 0:
        pct = round(affected_units / total_units * 100, 1) if total_units > 0 else 0
        takeaways.append(f"- **{active_alerts} active quality alerts** are affecting **{pct}%** of produced units.")

    return "\n\n".join([summary, table, "\n".join(takeaways)])


def execute_actual_vs_forecast_query(query: str) -> str:
    """
    Cross-table comparison: production_data (actuals) JOIN forecast_data, grouped by week.
    """
    data_svc = get_data_service()
    time_range = _parse_time_range(query)
    time_expr, time_meta = _choose_time_clause("production_data", time_range)
    where_clause = f"WHERE p.{time_expr.replace('date', 'date')}" if time_expr else ""

    # Determine which metrics the user wants
    q = query.lower()
    want_units = any(k in q for k in ["unit", "production", "output"])
    want_revenue = any(k in q for k in ["revenue", "sales", "income"])
    if not want_units and not want_revenue:
        want_units = want_revenue = True  # Default: show both

    select_parts = ["p.week"]
    if want_units:
        select_parts += ["COALESCE(SUM(p.units), 0) AS actual_units", "COALESCE(SUM(f.forecast_units), 0) AS forecast_units",
                         "COALESCE(SUM(p.units), 0) - COALESCE(SUM(f.forecast_units), 0) AS units_variance"]
    if want_revenue:
        select_parts += ["COALESCE(SUM(p.revenue), 0) AS actual_revenue", "COALESCE(SUM(f.forecast_revenue), 0) AS forecast_revenue",
                         "COALESCE(SUM(p.revenue), 0) - COALESCE(SUM(f.forecast_revenue), 0) AS revenue_variance"]

    # Build time filter applicable to both tables
    if time_expr:
        fcast_time_expr, _ = _choose_time_clause("forecast_data", time_range)
        join_where = f"WHERE ({time_expr}) OR ({fcast_time_expr})" if fcast_time_expr else f"WHERE {time_expr}"
        # Simpler: just filter production side and LEFT JOIN forecast
        p_where = f"WHERE {time_expr}"
    else:
        p_where = ""

    sql = f"""
        SELECT {', '.join(select_parts)}
        FROM production_data p
        LEFT JOIN forecast_data f ON p.week = f.week AND p.plant = f.plant
        {p_where}
        GROUP BY p.week
        ORDER BY p.week
    """.strip()

    try:
        df = data_svc.execute_query(sql)
    except Exception as e:
        logger.error(f"Actual vs forecast query failed: {e}")
        return None

    if df.empty:
        return (
            f"### Summary\nNo data found for {time_meta.get('requested', 'the requested period')}. "
            "Try adjusting the time range."
        )

    period = time_meta.get("used") or "All Available Data"
    fallback_note = ""
    if time_meta.get("fallback_occurred"):
        fallback_note = f"\n> ⚠️ No data for **{time_meta['requested']}**. Showing latest available: **{period}**."

    # Summary stats
    summary_lines = [f"### Summary", f"Actual vs Forecast comparison for **{period}**:{fallback_note}"]
    if want_units and "actual_units" in df.columns:
        total_actual = int(df["actual_units"].sum())
        total_forecast = int(df["forecast_units"].sum())
        variance = total_actual - total_forecast
        var_str = f"+{variance:,}" if variance >= 0 else f"{variance:,}"
        summary_lines.append(
            f"Total actual production: **{total_actual:,} units** vs forecast **{total_forecast:,} units** (variance: **{var_str}**)."
        )
    if want_revenue and "actual_revenue" in df.columns:
        total_rev = float(df["actual_revenue"].sum())
        total_frev = float(df["forecast_revenue"].sum())
        rev_var = total_rev - total_frev
        rev_var_str = f"+${rev_var:,.0f}" if rev_var >= 0 else f"-${abs(rev_var):,.0f}"
        summary_lines.append(
            f"Total actual revenue: **${total_rev:,.0f}** vs forecast **${total_frev:,.0f}** (variance: **{rev_var_str}**)."
        )

    # Table
    headers = [c.replace("_", " ").title() for c in df.columns]
    table_lines = ["### Actual vs Forecast by Week",
                   "| " + " | ".join(headers) + " |",
                   "|" + "---|" * len(headers)]
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            v = row[col]
            if "revenue" in col:
                cells.append(f"${float(v):,.0f}")
            elif isinstance(v, (int, float)):
                cells.append(f"{float(v):,.0f}")
            else:
                cells.append(str(v))
        table_lines.append("| " + " | ".join(cells) + " |")

    # Key takeaways
    takeaways = ["### Key Takeaways"]
    if want_units and "units_variance" in df.columns:
        below_weeks = df[df["units_variance"] < 0]
        if not below_weeks.empty:
            takeaways.append(f"- Production fell short of forecast in **{len(below_weeks)} week(s)** — review capacity constraints.")
        else:
            takeaways.append("- ✅ Actual production met or exceeded forecast every week in this period.")
    if want_revenue and "revenue_variance" in df.columns:
        below_rev = df[df["revenue_variance"] < 0]
        if not below_rev.empty:
            takeaways.append(f"- Revenue underperformed forecast in **{len(below_rev)} week(s)**.")

    return "\n\n".join(["\n".join(summary_lines), "\n".join(table_lines), "\n".join(takeaways)])



def detect_structured_query(query: str) -> str | None:
    """Detect whether the question can be answered with a structured data query."""
    query_lower = query.lower()

    if "plant" in query_lower and any(k in query_lower for k in ["highest", "most", "max", "top"]) and any(k in query_lower for k in ["issue", "issues", "alert", "alerts"]):
        return "highest_issues_by_plant"

    return None


def _is_filtered_dashboard_query(query: str) -> bool:
    """
    True when the user wants a summary/overview scoped to a specific entity
    (plant, model, department) — e.g. "summary for Dearborn", "Dearborn week 10 overview".

    These were intentionally excluded from _is_dashboard_query (which handles global
    dashboards only), but they must NOT fall through to the LLM without data.
    execute_dashboard_query already supports filters, so we route them there.
    """
    q = query.lower()

    # Must have a summary/overview signal
    summary_signals = ["summary", "overview", "report", "dashboard", "how is", "how are", "status"]
    if not any(s in q for s in summary_signals):
        return False

    # Must mention at least one known entity value from the data
    try:
        data_svc = get_data_service()
        for column in ["plant", "model", "department"]:
            try:
                values = data_svc.get_column_values("production_data", column)
            except Exception:
                continue
            for value in values:
                if value and str(value).lower() in q:
                    return True
    except Exception:
        pass

    return False


def execute_structured_query(query: str) -> str | None:
    """Run a safe structured query for supported data-first requests."""
    # ── Global dashboard / summary intent ──
    if _is_dashboard_query(query):
        logger.info("Routing to global dashboard handler")
        return execute_dashboard_query(query)

    # ── Filtered dashboard: "summary for Dearborn", "Dearborn week 10 report", etc. ──
    if _is_filtered_dashboard_query(query):
        logger.info("Routing to filtered dashboard handler")
        return execute_dashboard_query(query)

    # ── Actual vs Forecast cross-table comparison ──
    if _is_actual_vs_forecast_query(query):
        logger.info("Routing to actual-vs-forecast handler")
        result = execute_actual_vs_forecast_query(query)
        if result:
            return result

    intent_key = detect_structured_query(query)
    if intent_key == "highest_issues_by_plant":
        data_svc = get_data_service()
        time_range = _parse_time_range(query)
        time_expr, time_meta = _choose_time_clause("alerts_quality", time_range)
        
        where_clause = f"WHERE {time_expr}" if time_expr else ""
        
        sql = f"""
            WITH all_plants AS (
                SELECT DISTINCT plant FROM production_data
                UNION
                SELECT DISTINCT plant FROM alerts_quality
            ),
            plant_issues AS (
                SELECT plant,
                       SUM(CASE WHEN LOWER(status) = 'active' THEN 1 ELSE 0 END) AS active_issues,
                       COUNT(*) AS total_issues
                FROM alerts_quality
                {where_clause}
                GROUP BY plant
            )
            SELECT a.plant, 
                   COALESCE(p.active_issues, 0) AS active_issues, 
                   COALESCE(p.total_issues, 0) AS total_issues
            FROM all_plants a
            LEFT JOIN plant_issues p ON a.plant = p.plant
            ORDER BY active_issues DESC, total_issues DESC
        """
        df = data_svc.execute_query(sql)
        if df.empty:
            return f"SUMMARY No data available for {time_meta.get('requested', 'the requested period')}."

        top = df.iloc[0]
        
        # Format for fallback explanation
        time_context_msg = ""
        if time_meta.get("requested") != time_meta.get("used") and time_meta.get("used"):
            time_context_msg = f"\n\n(Note: No data for {time_meta['requested']}, showing latest available: {time_meta['used']})"

        headers = [str(col) for col in df.columns]
        rows = df.values.tolist()
        table_lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        for row in rows:
            table_lines.append("| " + " | ".join(str(item) for item in row) + " |")
        table_md = "\n".join(table_lines)

        response = [
            f"### Summary",
            f"The plant with the highest number of active issues during **{time_meta.get('used') or 'All Time'}** is **{top['plant']}**, "
            f"recording **{int(top['active_issues'])}** active issue(s) out of **{int(top['total_issues'])}** total issues logged. "
            f"This indicates elevated quality risk at this facility and warrants immediate operational review.",
            "",
            "### Quality Issues by Plant",
            table_md,
            time_context_msg,
            "",
            "### Key Takeaways",
            f"- **{top['plant']}** leads all plants in active quality issues for the period **{time_meta.get('used') or 'All Time'}**, "
            f"with **{int(top['active_issues'])}** active and **{int(top['total_issues'])}** total issues recorded.",
            "- Active issues represent unresolved quality alerts that may be impacting production output.",
            "- Consider prioritising corrective action plans for the departments driving the highest alert volumes at this plant.",
        ]
        return "\n".join(response)

    python_part = ""
    final_insights = ""
    explain_block = ""

    structured_intent = _parse_structured_intent(query)
    if structured_intent is None:
        return None

    signals = compute_cross_dataset_signals()
    execution = _execute_structured_intent(structured_intent, signals=signals)
    
    if execution["status"] == "NO_DATA":
        req = execution["time_meta"].get("requested", "the requested period")
        return (
            f"### Summary\n"
            f"No records were found for **{req}**. "
            f"The dataset does not contain any matching entries for this selection. "
            f"Try adjusting the time range or filter criteria."
        )
    
    if execution["status"] != "OK":
        return None

    # --- DETERMINISTIC LAYER (Python) ---
    df = execution["results_df"]
    structured_data = json.loads(execution["structured_context"])
    
    try:
        python_part = build_deterministic_response(df, structured_data)
    except Exception as e:
        logger.error(f"Deterministic response failed: {e}")
        python_part = "SUMMARY Data retrieved but formatting failed."

    # --- SAFE INSIGHTS LAYER (LLM with Retry Logic) ---
    # Build a grounded plain-English result for the LLM.
    # We pass the actual computed figures so it doesn't hallucinate "no data".
    metric_label = structured_data["metric"].replace("_", " ")
    time_label = structured_data.get("time_range") or "the selected period"
    filters_applied = structured_intent.get("filters", {})

    result_lines = []
    if not df.empty:
        if df.shape[0] == 1:
            # Single row result: Include all columns so LLM knows which entity (model/plant) it is
            row = df.iloc[0]
            parts = []
            for col in df.columns:
                v = row[col]
                try:
                    v_fmt = f"${float(v):,.0f}" if "revenue" in col.lower() else (f"{float(v):,.0f}" if isinstance(v, (int, float)) else str(v))
                except Exception:
                    v_fmt = str(v)
                parts.append(f"{col.replace('_',' ').title()}: {v_fmt}")
            result_lines.append("- " + ", ".join(parts))
            
            if filters_applied:
                result_lines.append(f"- Filters applied: {filters_applied}")
        else:
            for _, row in df.iterrows():
                parts = []
                for col in df.columns:
                    v = row[col]
                    try:
                        v_fmt = f"${float(v):,.0f}" if "revenue" in col.lower() else (f"{float(v):,.0f}" if isinstance(v, (int, float)) else str(v))
                    except Exception:
                        v_fmt = str(v)
                    parts.append(f"{col.replace('_',' ').title()}: {v_fmt}")
                result_lines.append("- " + ", ".join(parts))

    safe_context = {
        "metric": metric_label,
        "time_range": time_label,
        "filters": str(filters_applied) if filters_applied else "none",
        "computed_results": "\n".join(result_lines) if result_lines else "No data.",
        "insights": structured_data.get("computed_insights", []),
    }
    
    # Prompt instruction injected into result_context so LLM writes richer, formatted output
    insights_prompt = (
        "You are a senior manufacturing data analyst. Write a concise executive report using ONLY the computed_results provided.\n\n"
        "RULES (strictly enforced):\n"
        "1. Every point MUST be a bullet point starting with a dash (-).\n"
        "2. Every bullet MUST contain a specific figure or entity from computed_results — no generic sentences.\n"
        "3. Explain what the numbers MEAN for operations (e.g., impact on capacity, risk level), don't just repeat them.\n"
        "4. Do NOT write a 'Summary' or 'Introduction' section.\n"
        "5. Bold all entity names and numeric values.\n\n"
        "FORMAT (use exactly these two markdown headings):\n\n"
        "### Insights\n"
        "- [3 specific bullets with bolded figures]\n\n"
        "### Key Takeaways\n"
        "- [2-3 actionable bullets with bolded figures]"
    )
    safe_context["instructions"] = insights_prompt

    for attempt in range(2):
        insights_response = llm_service.generate_explanation(
            user_query=query,
            result_context=json.dumps(safe_context, indent=2),
            data_context="",
        )
        
        # Case-insensitive structure check
        response_upper = insights_response.upper()
        has_structure = ("INSIGHTS" in response_upper) and ("TAKEAWAY" in response_upper)
        has_bullets = insights_response.count("\n- ") >= 3 or insights_response.count("\n* ") >= 3 or insights_response.startswith("- ")

        if has_structure and has_bullets:
            final_insights = insights_response
            
            # 1. Strip everything before the first section heading
            for section in ["### Insights", "## Insights", "Insights", "### Insights\n", "INSIGHTS"]:
                if section in final_insights:
                    final_insights = final_insights.split(section, 1)[-1]
                    final_insights = "### Insights\n" + final_insights
                    break
            
            # 2. Normalise Takeaways heading
            for section in ["### Key Takeaways", "## Key Takeaways", "Key Takeaways", "KEY TAKEAWAYS", "### Key Takeaway"]:
                if section in final_insights and section != "### Key Takeaways":
                    final_insights = final_insights.replace(section, "### Key Takeaways")
                    break
            
            # 3. Ensure bullet consistency (replace * with -)
            final_insights = final_insights.replace("\n* ", "\n- ")
            if final_insights.startswith("* "):
                final_insights = "- " + final_insights[2:]

            # Strip any SUMMARY section the LLM may have prepended
            for marker in ["## Summary", "### Summary", "SUMMARY\n", "SUMMARY "]:
                if marker in final_insights:
                    remainder = final_insights.split(marker, 1)[-1]
                    if "\n\n" in remainder:
                        final_insights = remainder.split("\n\n", 1)[-1]
                    break
            
            # If LLM returned no markdown headings at all, wrap it
            if not any(h in final_insights for h in ["### Insights", "## Insights", "### Key"]):
                final_insights = "### Insights & Key Takeaways\n\n" + final_insights.strip()
            break
        else:
            logger.warning(f"LLM structure check failed on attempt {attempt+1}. Regenerating...")

    if not final_insights:
        final_insights = (
            "### Insights\n"
            "- Detailed insights could not be generated for this data slice. "
            "The figures in the Data Breakdown table above are accurate and deterministically computed.\n\n"
            "### Key Takeaways\n"
            "- Refer to the **Data Breakdown** table for the authoritative figures.\n"
            "- If you need deeper analysis, try a more specific query such as filtering by plant, model, or time period."
        )

    # --- EXPLAINABILITY LAYER ---
    from config import DEBUG_MODE
    explain_block = ""
    if DEBUG_MODE:
        explain_block = (
            f"\n\n---\n**Debug Info**\n"
            f"- **SQL Query**: `{execution['sql']}`\n"
            f"- **Filters Applied**: {structured_intent['filters']}\n"
            f"- **Rows Scanned**: {execution['row_count']}\n"
            f"- **Confidence Score**: {structured_intent.get('intent_confidence', 1.0)}\n"
        )

    return f"{python_part}\n\n{final_insights}\n{explain_block}"


def compute_cross_dataset_signals() -> dict:
    data_svc = get_data_service()
    signals = {
        "alerts_spike": False,
        "production_drop": False,
        "affected_departments": [],
        "correlation_summary": "No clear cross-dataset relationship found.",
    }

    try:
        production = data_svc.execute_query(
            "SELECT week, SUM(units) AS total_units, SUM(revenue) AS total_revenue FROM production_data GROUP BY week ORDER BY week"
        )
        alerts = data_svc.execute_query(
            "SELECT week, COUNT(*) AS issue_count, SUM(affected_units) AS affected_units FROM alerts_quality GROUP BY week ORDER BY week"
        )
    except Exception:
        return signals

    if production.empty or alerts.empty or len(production) < 4 or len(alerts) < 4:
        return signals

    latest_prod = production.iloc[-1]
    latest_alert = alerts.iloc[-1]
    recent_prod = production.tail(3)["total_units"].mean()
    prior_prod = production.head(3)["total_units"].mean() if len(production) >= 6 else production.iloc[:3]["total_units"].mean()
    recent_alert = alerts.tail(3)["issue_count"].mean()
    prior_alert = alerts.iloc[-6:-3]["issue_count"].mean() if len(alerts) >= 6 else alerts.iloc[:3]["issue_count"].mean()

    if prior_alert > 0:
        signals["alerts_spike"] = recent_alert >= prior_alert * 1.2
    if prior_prod > 0:
        signals["production_drop"] = recent_prod <= prior_prod * 0.9

    dept_rows = data_svc.execute_query(
        "SELECT department, SUM(CASE WHEN LOWER(status) = 'active' THEN 1 ELSE 0 END) AS active_issues "
        "FROM alerts_quality GROUP BY department ORDER BY active_issues DESC LIMIT 3"
    )
    signals["affected_departments"] = [str(row["department"]) for _, row in dept_rows.iterrows() if row["active_issues"] > 0]

    signals["latest_stats"] = {
        "week": str(latest_prod['week']),
        "production_units": int(latest_prod['total_units']),
        "revenue": float(latest_prod['total_revenue']),
        "alert_count": int(latest_alert['issue_count']),
        "affected_units": int(latest_alert['affected_units'])
    }

    if signals["alerts_spike"] and signals["production_drop"]:
        signals["correlation_summary"] = (
            f"Recent data shows alerts increasing while production fell. "
            f"The latest week ({latest_prod['week']}) had {int(latest_alert['issue_count'])} issues and {int(latest_prod['total_units'])} production units, "
            "suggesting a potential link between quality/alerts and output."
        )

    return signals


def build_data_context(intent: str, query: str, computed_results: str | None = None, signals: dict | None = None) -> str:
    """
    Build the data context string based on detected intent.
    Pulls relevant data from DuckDB and formats it for the LLM.
    """
    data_svc = get_data_service()
    context_parts = []

    try:
        context_parts.append("## Data Schema")
        context_parts.append(data_svc.get_table_schemas_text())
        now = datetime.now()
        context_parts.append(f"\n## Time Context")
        context_parts.append(f"- Current date: {now.strftime('%Y-%m-%d (%A)')}")
        context_parts.append(f"- Current week: Week {now.isocalendar()[1]} of {now.year}")
        context_parts.append(f"- Current quarter: Q{(now.month - 1) // 3 + 1} {now.year}")
        context_parts.append(f"- Previous quarter: Q{((now.month - 4) // 3 + 1) if now.month > 3 else 4} {now.year if now.month > 3 else now.year - 1}")
        context_parts.append(f"\n## Detected Intent: {intent}")
        if intent in INTENTS:
            context_parts.append(f"Description: {INTENTS[intent]['description']}")
        context_parts.append("\n## Metric Definitions")
        context_parts.append("- alerts: total alert records in alerts_quality. Active alerts are rows where status='active'.")
        context_parts.append("- affected_units: total affected units from alert events in alerts_quality.")
        context_parts.append("- revenue / forecast_revenue: absolute USD values in production_data and forecast_data.")
        context_parts.append("- units / forecast_units: physical production units.")
        if computed_results:
            context_parts.append("\n## Computed Results")
            context_parts.append(computed_results)
        if signals:
            context_parts.append("\n## Cross-Dataset Signals")
            context_parts.append("- alerts_spike: {}".format(signals.get("alerts_spike", False)))
            context_parts.append("- production_drop: {}".format(signals.get("production_drop", False)))
            context_parts.append("- affected_departments: {}".format(signals.get("affected_departments", [])))
            context_parts.append(f"- correlation_summary: {signals.get('correlation_summary', '')}")


    except Exception as e:
        logger.error(f"Error building data context: {e}")
        context_parts.append(f"\n⚠️ Error loading data context: {str(e)}")

    return "\n".join(context_parts)



def _is_conversational_query(query: str) -> bool:
    """
    Returns True when the message is clearly conversational / small-talk and
    should bypass all data-query logic entirely.
    """
    q = query.strip().lower()
    words = q.split()

    greetings = {
        "hi", "hello", "hey", "howdy", "hiya", "greetings", "sup", "yo",
        "good morning", "good afternoon", "good evening", "good night",
        "thanks", "thank you", "thankyou", "cheers", "bye", "goodbye",
        "ok", "okay", "cool", "great", "nice", "awesome", "sure", "got it",
    }
    if any(q == g or q.startswith(g + " ") or q.startswith(g + ",") for g in greetings):
        return True

    assistant_meta = [
        "who are you", "what are you", "what can you do", "what do you do",
        "how do you work", "what is voxa", "tell me about yourself",
        "are you an ai", "are you a bot",
    ]
    if any(m in q for m in assistant_meta):
        return True

    # Short message (<=4 words) with no data-domain vocabulary
    data_domain_words = {
        "production", "revenue", "alert", "forecast", "units", "plant",
        "model", "week", "quarter", "month", "sales", "output", "department",
    }
    if len(words) <= 4 and not any(w in data_domain_words for w in words):
        return True

    return False


async def process_query(
    query: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Full pipeline: Intent → Data → LLM → Response (non-streaming).
    """
    # ── Conversational short-circuit: bypass all data logic for greetings/small-talk ──
    if _is_conversational_query(query):
        logger.info(f"Conversational query, bypassing data pipeline: '{query[:40]}'")
        return llm_service.generate_response(
            user_query=query,
            data_context="",
            conversation_history=conversation_history,
        )

    intent = detect_intent(query)
    logger.info(f"Query: '{query[:60]}...' → Intent: {intent}")

    # 1. Check for Dashboard/Summary Queries (Multi-metric)
    if _is_dashboard_query(query) or _is_filtered_dashboard_query(query):
        logger.info("Routing to dashboard handler")
        structured_response = execute_dashboard_query(query)
        if structured_response:
            return structured_response

    # 2. Check for Structured Data Queries (Single-metric)
    structured_intent = _parse_structured_intent(query)
    if structured_intent and structured_intent.get("intent_confidence", 1.0) > 0.6:
        structured_response = execute_structured_query(query)
        if structured_response:
            logger.info("Returning structured response for supported query")
            return structured_response
    elif structured_intent and structured_intent.get("intent_confidence", 1.0) <= 0.6:
        # Ambiguous data query - ask for clarification instead of hallucinating
        return (
            "I'm not entirely sure which metric or location you're referring to. "
            "Could you please specify if you want to see **production units**, **revenue**, or **quality alerts**? "
            "And for which plant or time period?"
        )

    # 2. Fallback to LLM but ONLY for general/diagnostic queries
    data_context = build_data_context(
        intent=intent, 
        query=query, 
        signals=compute_cross_dataset_signals()
    )

    # Detect if query sounds like a data question that failed structured parsing
    data_keywords = ["how many", "total", "what is the revenue", "production of", "units", "alerts in"]
    if any(k in query.lower() for k in data_keywords) and "why" not in query.lower():
         return (
             "I couldn't find a direct way to calculate that value from the current dataset. "
             "Could you rephrase your question? For example: 'Show me production by plant for Q1'."
         )

    response = llm_service.generate_response(
        user_query=query,
        data_context=data_context,
        conversation_history=conversation_history,
    )

    return response


async def stream_query(
    query: str,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Full pipeline: Intent → Data → LLM → Streaming Response.
    Yields tokens as they arrive from the LLM.
    """
    # ── Conversational short-circuit ──
    if _is_conversational_query(query):
        logger.info(f"Conversational stream query, bypassing data pipeline: '{query[:40]}'")
        async for token in llm_service.stream_response(
            user_query=query,
            data_context="",
            conversation_history=conversation_history,
        ):
            yield token
        return

    intent = detect_intent(query)
    logger.info(f"Streaming query: '{query[:60]}...' → Intent: {intent}")

    # 1. Check for Dashboard/Summary Queries (Multi-metric)
    if _is_dashboard_query(query) or _is_filtered_dashboard_query(query):
        logger.info("Routing to dashboard handler (stream)")
        structured_response = execute_dashboard_query(query)
        if structured_response:
            yield structured_response
            return

    # 2. Check for Structured Data Queries (Single-metric)
    structured_intent = _parse_structured_intent(query)
    if structured_intent and structured_intent.get("intent_confidence", 1.0) > 0.6:
        structured_response = execute_structured_query(query)
        if structured_response:
            logger.info("Returning structured response for supported stream query")
            yield structured_response
            return
    elif structured_intent and structured_intent.get("intent_confidence", 1.0) <= 0.6:
        yield "I'm not entirely sure which metric or location you're referring to. Could you please specify if you want to see **production units**, **revenue**, or **quality alerts**?"
        return

    # 2. Fallback to LLM but ONLY for general/diagnostic queries
    data_context = build_data_context(
        intent=intent, 
        query=query, 
        signals=compute_cross_dataset_signals()
    )

    # Detect if query sounds like a data question that failed structured parsing
    data_keywords = ["how many", "total", "what is the revenue", "production of", "units", "alerts in"]
    if any(k in query.lower() for k in data_keywords) and "why" not in query.lower():
         yield "I couldn't find a direct way to calculate that value from the current dataset. Could you rephrase your question? For example: 'Show me production by plant for Q1'."
         return

    async for token in llm_service.stream_response(
        user_query=query,
        data_context=data_context,
        conversation_history=conversation_history,
    ):
        yield token