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
    """
    time_meta = structured_data.get("time_meta", {})
    used_time = time_meta.get("used") or structured_data.get("time_range")
    metric_raw = structured_data.get("metric", "data")
    metric = metric_raw.replace("_", " ")
    val = structured_data.get("value")
    
    # 1. Build Summary
    if time_meta.get("fallback_occurred"):
        req = time_meta.get("requested")
        summary = f"SUMMARY No data found for {req}. Showing latest available data from **{used_time}**."
    elif val is not None and not structured_data.get("group_by"):
        # Single value result
        unit = structured_data.get("metric_units", "")
        summary = f"SUMMARY The {metric} for {used_time} is **{val:,}** {unit}."
    elif not df.empty:
        # Grouped result - find top performer using explicit mapping
        try:
            group_cols = structured_data.get("group_by")
            if isinstance(group_cols, str):
                group_cols = [group_cols]
            
            val_col = df.columns[-1] # Usually the aggregated metric
            temp_df = df.copy()
            temp_df[val_col] = pd.to_numeric(temp_df[val_col].astype(str).str.replace(',', ''), errors='coerce')
            top_idx = temp_df[val_col].idxmax()
            top_row = df.loc[top_idx]
            
            if group_cols and len(df) > 1:
                top_entity = ", ".join(str(top_row[col]).title() for col in group_cols if col in df.columns)
                top_val = top_row[val_col]
                summary = f"SUMMARY Found {len(df)} records for {metric} in {used_time}. The highest is **{top_entity}** with **{top_val}**."
            elif len(df) == 1:
                top_val = top_row[val_col]
                if group_cols:
                    top_entity = ", ".join(str(top_row[col]).title() for col in group_cols if col in df.columns)
                    summary = f"SUMMARY The {metric} for **{top_entity}** in {used_time} is **{top_val}**."
                else:
                    summary = f"SUMMARY The total {metric} for {used_time} is **{top_val}**."
            else:
                top_val = top_row[val_col]
                summary = f"SUMMARY Found {len(df)} records for {metric} in {used_time}."
        except Exception:
            summary = f"SUMMARY Found {len(df)} records for {metric} in {used_time}."
    else:
        summary = f"SUMMARY No data records found for {metric} in {used_time}."

    # 2. Build Data Table
    if df.empty:
        return f"{summary}\n\nNo data available for this selection."

    headers = [str(col).replace("_", " ").title() for col in df.columns]
    rows = []
    for _, row in df.iterrows():
        formatted_row = []
        for item in row:
            if isinstance(item, (int, float)):
                formatted_row.append(f"{item:,}")
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
    
    # Get all valid numbers from the dataframe
    valid_numbers = set()
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
        # Ignore common small numbers in list formatting if they are just 1, 2, 3
        if num in ["1", "2", "3", "4", "5"] and len(found_numbers) > 2:
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
    if metric != "alerts" and metric.upper() not in sql_upper:
        logger.error(f"SQL Validation Failed: Metric column {metric} missing from query")
        return False
        
    # 3. Aggregation Check
    agg = intent["aggregation"]
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
        
    # 4. Grouping Check
    group_by = intent["group_by"]
    if group_by and "GROUP BY" not in sql_upper:
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
    for phrase, col in GROUP_BY_SYNONYMS.items():
        if phrase in query_lower:
            group_columns.append(col)
    if not group_columns:
        return None
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

    month_year_match = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\b", query_lower)
    if month_year_match:
        month_name, year = month_year_match.groups()
        return {"type": "month", "month": MONTHS[month_name], "year": int(year), "requested": f"{month_name.title()} {year}"}

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
    candidate_columns = ["plant", "department", "model", "issue_type", "status"]

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
    expr = None
    requested = time_range.get("requested")
    if time_range["type"] == "month":
        expr = (
            f"EXTRACT(month FROM CAST({date_col} AS DATE)) = {time_range['month']} AND "
            f"EXTRACT(year FROM CAST({date_col} AS DATE)) = {time_range['year']}"
        )
    elif time_range["type"] == "quarter":
        expr = (
            f"LOWER(quarter) = 'q{time_range['quarter']}' AND "
            f"EXTRACT(year FROM CAST({date_col} AS DATE)) = {time_range['year']}"
        )
    elif time_range["type"] == "week":
        expr = (
            f"LOWER(week) = 'w{time_range['week']:02d}' AND "
            f"EXTRACT(year FROM CAST({date_col} AS DATE)) = {time_range['year']}"
        )
    elif time_range["type"] == "year":
        expr = f"EXTRACT(year FROM CAST({date_col} AS DATE)) = {time_range['year']}"
    else:
        return None, {"used": requested, "requested": requested}

    data_svc = get_data_service()
    count_sql = f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE {expr}"
    row_count = data_svc.execute_query(count_sql).iloc[0, 0]
    if row_count > 0:
        return expr, {"used": requested, "requested": requested, "available_rows": int(row_count)}

    latest_sql = f"SELECT MAX(CAST({date_col} AS DATE)) AS latest_date FROM {table_name}"
    latest_row = data_svc.execute_query(latest_sql)
    if latest_row.empty or latest_row.iloc[0, 0] is None:
        return expr, {"used": requested, "requested": requested, "available_rows": 0}

    latest_date = latest_row.iloc[0, 0]
    used_month = int(latest_date.strftime("%m"))
    used_year = int(latest_date.strftime("%Y"))
    used = latest_date.strftime("%B %Y")
    fallback_expr = (
        f"EXTRACT(month FROM CAST({date_col} AS DATE)) = {used_month} AND "
        f"EXTRACT(year FROM CAST({date_col} AS DATE)) = {used_year}"
    )
    return fallback_expr, {
        "requested": requested,
        "used": used,
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

    if aggregation is None:
        if "average" in query_lower or "avg" in query_lower or "mean" in query_lower:
            aggregation = "avg"
        elif "total" in query_lower or "sum" in query_lower or "overall" in query_lower:
            aggregation = "sum"
        elif "count" in query_lower or "how many" in query_lower:
            aggregation = "count"
        elif "maximum" in query_lower or "highest" in query_lower or "biggest" in query_lower:
            aggregation = "max"
        elif "minimum" in query_lower or "lowest" in query_lower or "smallest" in query_lower:
            aggregation = "min"
        elif any(token in query_lower for token in ["show", "list", "display", "what is", "what are", "which", "give me", "all", "more", "most"]):
            # Default to 'sum' (which our builder will handle as a list for tasks or sum for metrics)
            aggregation = "sum"

    if metric is None or aggregation is None:
        return None

    if aggregation not in AGGREGATION_MAP:
        return None

    table_name = _choose_table(metric)
    filters = _parse_filters(query_lower, table_name)
    time_range = _parse_time_range(query)
    return {
        "metric": metric,
        "aggregation": aggregation,
        "group_by": group_by,
        "filters": filters,
        "time_range": time_range,
        "table_name": table_name,
        "raw_query": query,
        "query_type": classify_query_type(query),
    }


def _build_sql_for_intent(intent: dict) -> tuple[str, dict, str] | None:
    metric = intent["metric"]
    aggregation = intent["aggregation"]
    group_by = intent["group_by"]
    filters = intent["filters"]
    table_name = intent["table_name"]
    raw_query = intent.get("raw_query", "")

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
             # "Total alerts" should still be a count of records, not a sum of units
             select_clauses.append("COUNT(*) AS total_alerts")
             alias = "total_alerts"
        elif aggregation == "avg":
             # Average alerts per something (handled by group_by)
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
        select_clauses.append(f"MAX({metric_expr}) AS max_{col_label}")
        alias = f"max_{col_label}"
    elif aggregation == "min":
        select_clauses.append(f"MIN({metric_expr}) AS min_{col_label}")
        alias = f"min_{col_label}"
    else:
        select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
        alias = f"total_{col_label}"

    data_svc = get_data_service()
    table_cols = [c["name"] for c in data_svc.get_table_schemas().get(table_name, [])]
    
    group_key = None
    if group_by:
        if isinstance(group_by, str):
            group_by = [group_by]
        
        # Only keep columns that exist in the table
        valid_groups = [g for g in group_by if g in table_cols]
        
        if valid_groups:
            group_key = ", ".join(valid_groups)
            select_clauses = valid_groups + select_clauses
            group_clause = f"GROUP BY {group_key}"
        else:
            group_key = None

    if filters:
        for key, value in filters.items():
            if isinstance(value, list):
                quoted_vals = []
                for v in value:
                    safe_v = str(v).replace("'", "''")
                    quoted_vals.append(f"LOWER('{safe_v}')")
                vals_str = ", ".join(quoted_vals)
                where_clauses.append(f"LOWER({key}) IN ({vals_str})")
            else:
                safe = str(value).replace("'", "''")
                where_clauses.append(f"LOWER({key}) = LOWER('{safe}')")

    time_expr, time_meta = _choose_time_clause(table_name, intent["time_range"])
    if time_expr:
        where_clauses.append(time_expr)

    # Special handling for Tasks: if no aggregation specified, just show the tasks
    if table_name == "tasks_schedule" and aggregation == "sum" and "total" not in raw_query:
        where_stmt = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"SELECT * FROM tasks_schedule {where_stmt} LIMIT 10".strip()
        return sql, time_meta, where_stmt

    if aggregation in {"sum", "max"} and alias is not None and group_by:
        order_clause = f"ORDER BY {alias} DESC LIMIT 5"
    elif group_clause and not order_clause and group_key:
        order_clause = f"ORDER BY {group_key}"

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"SELECT {', '.join(select_clauses)} FROM {table_name} {where_clause} {group_clause} {order_clause}".strip()
    return sql, time_meta, where_clause


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
    return json.dumps(structured, indent=2)


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


def detect_structured_query(query: str) -> str | None:
    """Detect whether the question can be answered with a structured data query."""
    query_lower = query.lower()

    if "plant" in query_lower and any(k in query_lower for k in ["highest", "most", "max", "top"]) and any(k in query_lower for k in ["issue", "issues", "alert", "alerts"]):
        return "highest_issues_by_plant"

    return None


def execute_structured_query(query: str) -> str | None:
    """Run a safe structured query for supported data-first requests."""
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
            f"SUMMARY The plant with the highest number of active issues is **{top['plant']}**, with **{int(top['active_issues'])}** active issue(s) and **{int(top['total_issues'])}** total issue(s).",
            "",
            "### Quality issues by plant",
            table_md,
            time_context_msg,
            "",
            "Key Takeaways:",
            f"- **{top['plant']}** has the most active issues in the period: {time_meta.get('used') or 'All Time'}.",
            "- This answer is based directly on the actual dataset and not on invented values.",
        ]
        return "\n".join(response)

    structured_intent = _parse_structured_intent(query)
    if structured_intent is None:
        return None

    signals = compute_cross_dataset_signals()
    execution = _execute_structured_intent(structured_intent, signals=signals)
    
    if execution["status"] == "NO_DATA":
        # Hard stop / Python response for empty data
        return (
            f"SUMMARY No records were found for {execution['time_meta'].get('requested', 'the requested period')}. "
            "The dataset does not contain any matching rows for that selection."
        )
    
    if execution["status"] != "OK":
        return None

    # --- DETERMINISTIC LAYER (Python) ---
    df = execution["results_df"]
    structured_data = json.loads(execution["structured_context"])
    
    python_part = build_deterministic_response(df, structured_data)

    # --- SAFE INSIGHTS LAYER (LLM with Retry Logic) ---
    # Safe Context: Remove raw results to prevent re-aggregation hallucinations
    safe_context = {
        "metric": structured_data["metric"],
        "summary": structured_data["summary"],
        "insights": structured_data["computed_insights"],
        "time_range": structured_data["time_range"]
    }
    
    final_insights = ""
    for attempt in range(2):
        insights_response = llm_service.generate_explanation(
            user_query=query,
            result_context=json.dumps(safe_context, indent=2),
            data_context="", # Strictly no schema
        )
        
        # Structure Check
        has_structure = "INSIGHTS" in insights_response and "KEY TAKEAWAYS" in insights_response
        # Numeric Check
        is_valid = validate_numbers_enforce(insights_response, df)
        
        if has_structure and is_valid:
            # Clean up and finalize
            final_insights = insights_response
            if "SUMMARY" in final_insights:
                final_insights = final_insights.split("SUMMARY")[-1].split("\n\n", 1)[-1]
            break
        else:
            logger.warning(f"LLM validation failed on attempt {attempt+1}. Regenerating...")

    if not final_insights:
        final_insights = (
            "### Insights\n"
            "- Advanced insights are unavailable for this specific data slice due to validation constraints.\n\n"
            "### Key Takeaways\n"
            "- Please refer to the deterministic Data Breakdown table above for accurate figures."
        )

    return f"{python_part}\n\n{final_insights}"


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


async def process_query(
    query: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Full pipeline: Intent → Data → LLM → Response (non-streaming).
    """
    intent = detect_intent(query)
    logger.info(f"Query: '{query[:60]}...' → Intent: {intent}")

    structured_response = execute_structured_query(query)
    if structured_response is not None:
        logger.info("Returning structured response for supported query")
        return structured_response

    data_context = build_data_context(
        intent=intent, 
        query=query, 
        signals=compute_cross_dataset_signals()
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
    intent = detect_intent(query)
    logger.info(f"Streaming query: '{query[:60]}...' → Intent: {intent}")

    structured_response = execute_structured_query(query)
    if structured_response is not None:
        logger.info("Returning structured response for supported stream query")
        yield structured_response
        return

    data_context = build_data_context(
        intent=intent, 
        query=query, 
        signals=compute_cross_dataset_signals()
    )

    async for token in llm_service.stream_response(
        user_query=query,
        data_context=data_context,
        conversation_history=conversation_history,
    ):
        yield token
