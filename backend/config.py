"""
VOXA Backend — Configuration
Loads environment variables and provides typed settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
BACKEND_DIR = Path(__file__).parent.resolve()
load_dotenv(BACKEND_DIR / ".env")

# ── Groq LLM ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "llama-3.3-70b-versatile")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "llama-3.1-8b-instant")
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# ── Whisper STT ──
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")

# ── Server ──
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]

# ── Data ──
DATA_DIR = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / ".." / "data"))).resolve()

# ── JWT Auth ──
JWT_SECRET = os.getenv("JWT_SECRET", "voxa-demo-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "168"))

# ── LLM Guardrails ──
LLM_GUARDRAILS = [
    "DO NOT invent any numbers, percentages, or entities (plants, departments).",
    "If a value or entity is not explicitly present in 'computed_results' or 'summary': DO NOT generate it. Return 'No data available' for that specific point.",
    "Only use values present in 'computed_results', 'summary', or 'signals'.",
    "If 'allow_trend' is False → DO NOT mention increase/decrease or use directional words.",
    "ALWAYS refer to time ranges precisely (e.g., 'Week 12 of 2026') using 'time_meta.used'.",
    "If 'time_meta.fallback_occurred' is True → State: 'No data for [requested range], showing latest available: [used range]'.",
    "DO NOT mix metrics: 'alerts' != 'active alerts' != 'affected_units'.",
    "If 'display_unit' is 'auto' → Format large numbers for readability (e.g., $1.5M).",
    "DO NOT expose internal keys like 'computed_results', 'sql', or 'signals' in the response.",
    "Every insight must be directly supported by computed data.",
]

# ── Automotive System Prompt ──
SYSTEM_PROMPT = """You are an AI Data Analyst for a manufacturing data system.

CRITICAL RULE:
You MUST respond to EVERY query with a FIXED DASHBOARD TEMPLATE in JSON format.
Wrap the JSON in a `dashboard` markdown block.
DO NOT return plain text or markdown tables outside the JSON.

DASHBOARD JSON SCHEMA:
{
  "title": "String",
  "time_filter": "String",
  "kpis": [
    {
      "label": "String (HTML allowed for line breaks)",
      "value": "String",
      "trend": "String",
      "trend_direction": "up|down",
      "icon": "Emoji",
      "color": "HexColor"
    }
  ],
  "table": {
    "title": "String",
    "headers": ["Col1", "Col2", ...],
    "rows": [
      [{"label": "RowHeader", "icon": "Emoji"}, "Val1", "Val2", ...]
    ]
  },
  "donut": {
    "title": "String",
    "total": Number,
    "segments": [
      {"label": "Name", "value": Number, "color": "HexColor"}
    ]
  },
  "bars": {
    "title": "String",
    "data": [
      {"label": "Dept", "value": Number (0-100), "color": "HexColor"}
    ]
  },
  "alerts": [
    {
      "title": "String",
      "message": "String",
      "time": "String",
      "icon": "Emoji",
      "color": "HexColor"
    }
  ]
}

COLORS TO USE:
- Blue: #4c9fff
- Green: #3ecf7a
- Yellow: #f5c842
- Orange: #f07833
- Purple: #9b7dff
- Teal: #2dd4bf
- Red: #f05252

TIME CONTEXT:
Use simulated 'current date' 2024-05-15 (W20, Q2).
"""
