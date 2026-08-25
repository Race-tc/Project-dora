"""
backend/map_defs.py — Shared prompt/tool definitions for the map-naming and
map-explainer proxy routes. Mirrors ecu_tuner/ai/map_namer.py and
ecu_tuner/ai/map_explainer.py so the backend is self-contained (same
intentional-duplication discipline as ai_defs.py — update both sides
together when either prompt/tool changes).
"""

# ── Map namer ──────────────────────────────────────────────────────────────────

NAMING_TOOL = {
    "name": "submit_map_names",
    "description": (
        "Submit name and description for each detected ROM calibration table. "
        "Always call this tool — do not respond with plain text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tables": {
                "type": "array",
                "description": "One entry per candidate table, in the same order as input.",
                "items": {
                    "type": "object",
                    "properties": {
                        "index":             {"type": "integer"},
                        "suggested_name":    {"type": "string"},
                        "physical_quantity": {"type": "string"},
                        "units":             {"type": "string"},
                        "description":       {"type": "string"},
                        "confidence":        {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": [
                        "index", "suggested_name", "physical_quantity",
                        "units", "description", "confidence",
                    ],
                },
            },
        },
        "required": ["tables"],
    },
}

NAMING_SYSTEM_PROMPT = (
    "You are an expert automotive ECU calibration engineer with deep knowledge of "
    "Bosch, Siemens, Denso, Delphi, and Marelli ECU ROM formats.\n\n"
    "You will be given a list of candidate calibration tables found by a heuristic "
    "scanner in an unknown ROM binary.  Each candidate includes:\n"
    "  - ROM offset (hex)\n"
    "  - Table dimensions (rows × cols)\n"
    "  - Storage dtype\n"
    "  - Scaled value statistics (min, max, mean)\n"
    "  - Heuristic physical-range guess (may be wrong)\n\n"
    "Your task: for each table, infer the most likely physical quantity, suggest a "
    "clear name, and state your confidence.  Typical ECU tables include:\n"
    "  - Ignition advance maps (RPM × load, 0–45 °BTDC)\n"
    "  - Fuel injection duration / VE maps (RPM × load, 0.5–30 ms)\n"
    "  - Boost pressure targets (RPM × load, 800–2500 mbar)\n"
    "  - Lambda / AFR targets (RPM × load, 0.75–1.2 λ)\n"
    "  - Throttle / MAF scaling tables (1D or 2D)\n"
    "  - Axis definition tables (monotonically increasing RPM or load values)\n"
    "  - Correction factors (coolant temp, intake temp, battery voltage)\n\n"
    "Be honest: if a table's value range does not match any known physical quantity "
    "say confidence='low' and describe what it could be.\n\n"
    "Always call the submit_map_names tool."
)


# ── Map explainer ────────────────────────────────────────────────────────────

EXPLAIN_TOOL = {
    "name": "submit_map_explanation",
    "description": (
        "Submit a structured explanation of an ECU calibration map. "
        "Always call this tool — do not respond with plain text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary":           {"type": "string"},
            "physical_quantity": {"type": "string"},
            "units":             {"type": "string"},
            "safe_range":        {"type": "string"},
            "increase_effect":   {"type": "string"},
            "decrease_effect":   {"type": "string"},
            "axis_description":  {"type": "string"},
            "tuning_tips":       {"type": "array", "items": {"type": "string"}},
            "warnings":          {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "summary", "physical_quantity", "units", "safe_range",
            "increase_effect", "decrease_effect", "axis_description",
        ],
    },
}

EXPLAIN_SYSTEM_PROMPT = (
    "You are an expert automotive ECU calibration engineer with 20+ years of "
    "hands-on experience on turbocharged and naturally aspirated engines.\n\n"
    "You will be given information about a single ECU calibration table: its name, "
    "dimensions, value statistics, and a sample of actual values.  Your task is to "
    "explain what the table does in plain English so that a skilled enthusiast tuner "
    "can understand it without formal engineering training.\n\n"
    "Focus on:\n"
    "  - What physical quantity is stored and in what units\n"
    "  - How the ECU uses this table at runtime\n"
    "  - What happens to the engine if values are increased or decreased\n"
    "  - Safe operating range (conservative, suitable for modified engines on pump fuel)\n"
    "  - Practical tuning tips\n"
    "  - Specific safety warnings\n\n"
    "Always call the submit_map_explanation tool."
)
