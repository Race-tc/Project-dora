"""
backend/ai_defs.py — Shared AI prompt and tool definition used by the proxy.
Mirrors ecu_tuner/ai/tuning_agent.py so the backend is self-contained.
"""

_MAP_INFO = {
    "Boost":         {"unit": "bar",  "min": 0.0,  "max": 1.8},
    "Throttle":      {"unit": "%",    "min": 0.0,  "max": 100.0},
    "MAF":           {"unit": "g/s",  "min": 0.0,  "max": 200.0},
    "Short Term FT": {"unit": "%",    "min": -25.0, "max": 25.0},
    "Long Term FT":  {"unit": "%",    "min": -25.0, "max": 25.0},
}

_RPM_AXIS  = [800, 1200, 1600, 2000, 2500, 3000, 3500, 4000,
              4500, 5000, 5500, 6000, 6500, 7000]
_LOAD_AXIS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 140, 160, 180, 200]

RECOMMENDATION_TOOL = {
    "name": "submit_tuning_recommendation",
    "description": (
        "Submit structured ECU calibration recommendations after analysing "
        "the engine log data. Always call this tool — do not respond with plain text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "adjustments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "map_name":  {"type": "string", "enum": list(_MAP_INFO.keys())},
                        "row":       {"type": "integer", "minimum": 0, "maximum": 13},
                        "col":       {"type": "integer", "minimum": 0, "maximum": 15},
                        "delta_pct": {"type": "number",  "minimum": -3.0, "maximum": 3.0},
                        "reason":    {"type": "string"},
                    },
                    "required": ["map_name", "row", "col", "delta_pct", "reason"],
                },
            },
            "warnings":   {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["summary", "adjustments", "confidence"],
    },
}

SYSTEM_PROMPT = f"""
You are an expert automotive ECU tuning engineer with 20+ years experience
on turbocharged and naturally aspirated engines. You analyse data logs and
recommend conservative, safe calibration adjustments.

AVAILABLE MAPS AND SAFE LIMITS
{chr(10).join(
    f"  {name}: unit={info['unit']}, safe range {info['min']} to {info['max']}"
    for name, info in _MAP_INFO.items()
)}

MAP AXIS REFERENCE
  RPM rows (0-13): {_RPM_AXIS}
  Load cols (0-15): {_LOAD_AXIS}

RULES YOU MUST FOLLOW
- All changes must be conservative (max ±3% per cell per session)
- Never recommend WOT AFR leaner than 11.5:1
- Never recommend ignition advance beyond 35° BTDC
- Never set Boost above 1.8 bar
- Flag any signs of knock, lean conditions, or overheating
- You MUST call the submit_tuning_recommendation tool.
"""
