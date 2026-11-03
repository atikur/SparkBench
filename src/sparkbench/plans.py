"""The generator's entire language: bounded LED/OLED data, never source code."""
import hashlib
import json
import re

APPROVED_PINS = (25, 26)
MAX_STEPS = 8
DWELL_MS = 3000
LABEL = re.compile(r"^[A-Z0-9][A-Z0-9 -]{0,15}$")
PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "mapping", "steps"],
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "mapping": {"type": "object", "additionalProperties": False,
                    "required": ["red", "green"], "properties": {
                        c: {"type": "integer", "enum": list(APPROVED_PINS)} for c in ("red", "green")}},
        "steps": {"type": "array", "minItems": 1, "maxItems": MAX_STEPS,
                  "items": {"type": "object", "additionalProperties": False,
                            "required": ["red", "green", "text"], "properties": {
                                "red": {"type": "boolean"}, "green": {"type": "boolean"},
                                "text": {"type": "string", "pattern": LABEL.pattern}}}}
    }}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def plan_hash(plan):
    validate_plan(plan)
    return hashlib.sha256(canonical(plan)).hexdigest()


def validate_mapping(mapping):
    if (not isinstance(mapping, dict) or set(mapping) != {"red", "green"}
            or any(type(v) is not int for v in mapping.values())
            or set(mapping.values()) != set(APPROVED_PINS)):
        raise ValueError("Mapping must assign red/green one-to-one to approved GPIO25/26 only")


def validate_plan(plan):
    if (not isinstance(plan, dict) or set(plan) != {"schema_version", "mapping", "steps"}
            or type(plan["schema_version"]) is not int or plan["schema_version"] != 1):
        raise ValueError("Plan must contain only schema_version=1, mapping and steps")
    validate_mapping(plan["mapping"])
    steps = plan["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError("Plan needs 1–8 bounded steps")
    for step in steps:
        if (not isinstance(step, dict) or set(step) != {"red", "green", "text"}
                or type(step["red"]) is not bool or type(step["green"]) is not bool
                or not isinstance(step["text"], str) or not LABEL.fullmatch(step["text"])):
            raise ValueError("Steps require boolean LEDs and 1–16 uppercase ASCII label characters")
    return plan


def expected_plan(spec, mapping):
    """Translate independent expectations into the restricted data language."""
    from .vision import validate_expected
    validate_mapping(mapping)
    if spec.get("servo_actuation") is not False:
        raise ValueError("Only an explicitly servo-free specification is supported")
    validate_expected(spec.get("steps"))
    if [s["step"] for s in spec["steps"]] != list(range(1, len(spec["steps"]) + 1)):
        raise ValueError("Runtime requires consecutive step IDs from one")
    if spec.get("nominal_step_duration_ms") != DWELL_MS:
        raise ValueError("Runtime dwell is fixed at 3000 ms")
    plan = {"schema_version": 1, "mapping": mapping,
            "steps": [{"red": s["red"], "green": s["green"], "text": s["oled_text"]}
                      for s in spec["steps"]]}
    return validate_plan(plan)


def validate_against_spec(plan, spec, mapping):
    validate_plan(plan)
    if plan != expected_plan(spec, mapping):
        raise ValueError("Generated plan differs from independent behavior specification or supplied mapping")
    return plan


def render_header(plan):
    """All syntax is trusted; validated labels cannot inject C++ or paths."""
    validate_plan(plan)
    rows = []
    for step in plan["steps"]:
        states = {plan["mapping"][c]: step[c] for c in ("red", "green")}
        rows.append('  {%s, %s, "%s"},' %
                    (str(states[25]).lower(), str(states[26]).lower(), step["text"]))
    return ('// Rendered data only. Do not accept generated C++ as input.\n'
            '#pragma once\n#include "engine.h"\n'
            'static constexpr char kPlanHash[] = "%s";\n' % plan_hash(plan)
            + 'static constexpr sparkbench::Step kPlan[] = {\n' + '\n'.join(rows) + '\n};\n')
