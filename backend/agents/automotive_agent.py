"""
VOXA Backend — Automotive Agent (Layer 6: AI Agent Layer)
Orchestrates: Intent Detection → Data Retrieval → LLM Response Generation

This is the brain of the assistant. It:
1. Detects user intent from the query
2. Pulls relevant data from DuckDB
3. Builds context for the LLM
4. Generates rich markdown responses with tables, summaries, and insights
"""

import logging
from typing import AsyncGenerator
from datetime import datetime

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


def detect_structured_query(query: str) -> str | None:
    """Detect whether the question can be answered with a structured data query."""
    query_lower = query.lower()

    if "plant" in query_lower and any(k in query_lower for k in ["highest", "most", "max", "top"]) and any(k in query_lower for k in ["issue", "issues", "alert", "alerts"]):
        return "highest_issues_by_plant"

    return None


def execute_structured_query(query: str) -> str | None:
    """Run a safe structured query for supported data-first requests."""
    intent = detect_structured_query(query)
    if intent is None:
        return None

    data_svc = get_data_service()

    if intent == "highest_issues_by_plant":
        sql = """
            SELECT plant,
                   SUM(CASE WHEN LOWER(status) = 'active' THEN 1 ELSE 0 END) AS active_issues,
                   COUNT(*) AS total_issues
            FROM alerts_quality
            GROUP BY plant
            ORDER BY active_issues DESC, total_issues DESC
        """
        df = data_svc.execute_query(sql)
        if df.empty:
            return None

        top = df.iloc[0]

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
            "",
            "Key Takeaways:",
            f"- **{top['plant']}** has the most active issues in the `alerts_quality` dataset.",
            "- This answer is based directly on the actual dataset and not on invented values.",
        ]
        return "\n".join(response)

    return None


def build_data_context(intent: str, query: str) -> str:
    """
    Build the data context string based on detected intent.
    Pulls relevant data from DuckDB and formats it for the LLM.
    """
    data_svc = get_data_service()
    context_parts = []

    try:
        # Always include table schemas so LLM knows what data is available
        context_parts.append("## Data Schema")
        context_parts.append(data_svc.get_table_schemas_text())

        # For small datasets, include ALL data so LLM can do precise analysis
        context_parts.append("\n## Full Dataset")
        context_parts.append(data_svc.get_full_data_dump())

        # Add current date context for time-relative queries
        now = datetime.now()
        context_parts.append(f"\n## Time Context")
        context_parts.append(f"- Current date: {now.strftime('%Y-%m-%d (%A)')}")
        context_parts.append(f"- Current week: Week {now.isocalendar()[1]} of {now.year}")
        context_parts.append(f"- Current quarter: Q{(now.month - 1) // 3 + 1} {now.year}")
        context_parts.append(f"- Previous quarter: Q{((now.month - 4) // 3 + 1) if now.month > 3 else 4} {now.year if now.month > 3 else now.year - 1}")

        # Add intent-specific instructions
        context_parts.append(f"\n## Detected Intent: {intent}")
        if intent in INTENTS:
            context_parts.append(f"Description: {INTENTS[intent]['description']}")

        if intent == "weekly_schedule":
            context_parts.append("""
### Response Instructions:
- Present the weekly schedule as a TABLE with columns: Day, Status, Models Planned, Target Units, Notes
- Group data by days of the week (Monday through Friday)
- If exact weekly schedule data isn't available, derive a realistic schedule from the sales/production data
- Show shift information if available
- Include a summary of total planned production for the week
""")
        elif intent == "quarter_comparison":
            context_parts.append("""
                    ### Response Instructions:
                    - Create a comparison TABLE showing current quarter vs previous quarter
                    - Include metrics: Total Sales, Revenue, Units Produced, Top Model, Growth %
                    - Calculate percentage changes between quarters
                    - Highlight positive/negative trends with ↑/↓ arrows
                    - Add a brief analysis of what drove the changes
                    """)
        elif intent == "week_broadcast":
            context_parts.append("""
                    ### Response Instructions:
                    - Create a week-over-week comparison TABLE
                    - Show next week's projected data vs previous week's actual data
                    - Include: Production targets, Sales forecast, Key models, any alerts
                    - Highlight significant changes (>10% variance)
                    - Add broadcast-style announcements for the plant floor
                    """)

    except Exception as e:
        logger.error(f"Error building data context: {e}")
        context_parts.append(f"\n⚠️ Error loading data: {str(e)}")

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

    data_context = build_data_context(intent, query)

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

    data_context = build_data_context(intent, query)

    async for token in llm_service.stream_response(
        user_query=query,
        data_context=data_context,
        conversation_history=conversation_history,
    ):
        yield token
