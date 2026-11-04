"""Logical requirements retained across a bounded firmware mapping repair.

The requirements come from an operator-reviewed proposal. They are independent of
subsequent pin-mapping candidates, not an independent interpretation of the user's
natural-language instruction.
"""
from .plans import DWELL_MS, validate_plan


def logical_contract(plan):
    """Return the exact camera-test specification, deliberately excluding pins."""
    validate_plan(plan)
    return {
        "schema_version": 1,
        "servo_actuation": False,
        "nominal_step_duration_ms": DWELL_MS,
        "scope": "Physical comparison against the original operator-reviewed behavior; not an independent test of natural-language intent",
        "expectation_provenance": "Frozen at original review; logical colors, OLED labels and timing cannot change during a mapping repair",
        "steps": [
            {"step": index + 1, "red": step["red"], "green": step["green"], "oled_text": step["text"]}
            for index, step in enumerate(plan["steps"])
        ],
    }
