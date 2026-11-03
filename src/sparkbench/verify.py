"""Evaluate measured step traces against an independent behavior specification.

Measurement extraction is a separate component. This module does not claim to
read a camera or independently validate the origin of supplied measurements.
"""

import math


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _check_spec(spec):
    if spec.get("schema_version") != 1:
        raise ValueError("Unsupported spec schema_version")
    tolerance = spec.get("angle_tolerance_deg")
    if not _number(tolerance) or tolerance < 0:
        raise ValueError("angle_tolerance_deg must be finite and nonnegative")
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Spec must have a nonempty steps array")
    identifiers = []
    for row in steps:
        if not isinstance(row, dict):
            raise ValueError("Each expected step must be an object")
        identifier = row.get("step")
        if type(identifier) is not int or identifier < 1:
            raise ValueError("Step identifiers must be positive integers")
        identifiers.append(identifier)
        if not _number(row.get("expected_angle")):
            raise ValueError("Each step needs a finite expected_angle")
        if type(row.get("red")) is not bool or type(row.get("green")) is not bool:
            raise ValueError("Expected LED states must be booleans")
        if not isinstance(row.get("oled_text"), str):
            raise ValueError("Expected OLED text must be a string")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate step identifier in spec")


def verify_trace(spec, trace):
    _check_spec(spec)
    if trace.get("schema_version") != 1:
        raise ValueError("Unsupported trace schema_version")
    rows = trace.get("measurements")
    if not isinstance(rows, list):
        raise ValueError("Trace must contain a measurements array")
    if any(not isinstance(row, dict) or type(row.get("step")) is not int
           for row in rows):
        raise ValueError("Each measurement needs an integer step identifier")
    ids = [row["step"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate measurement step identifier")

    # Check acquisition order as well as values: both behaviors are sequences.
    expected_ids = [row["step"] for row in spec["steps"]]
    failures = []
    unknowns = []
    if ids != expected_ids:
        failures.append("Step sequence mismatch: expected %r, observed %r"
                        % (expected_ids, ids))
    by_step = {row["step"]: row for row in rows}
    tolerance = spec["angle_tolerance_deg"]
    for expected in spec["steps"]:
        identifier = expected["step"]
        actual = by_step.get(identifier)
        if actual is None:
            unknowns.append("step %s: missing observation" % identifier)
            continue
        angle = actual.get("angle_deg")
        if not _number(angle):
            unknowns.append("step %s: angle not measured" % identifier)
        elif abs(angle - expected["expected_angle"]) > tolerance:
            failures.append("step %s: angle %.2f outside %.2f +/- %.2f deg"
                            % (identifier, angle, expected["expected_angle"], tolerance))
        for channel in ("red", "green"):
            value = actual.get(channel)
            if type(value) is not bool:
                unknowns.append("step %s: %s state not measured" % (identifier, channel))
            elif value != expected[channel]:
                failures.append("step %s: %s expected %s, observed %s"
                                % (identifier, channel, expected[channel], value))
        text = actual.get("oled_text")
        if not isinstance(text, str):
            unknowns.append("step %s: OLED text not measured" % identifier)
        elif text.strip() != expected["oled_text"].strip():
            failures.append("step %s: OLED expected %r, observed %r"
                            % (identifier, expected["oled_text"], text))

    status = "fail" if failures else ("incomplete" if unknowns else "pass")
    return {
        "status": status,
        "spec": spec.get("name", "unnamed"),
        "reported_provenance": trace.get("provenance", {"kind": "unspecified"}),
        "failures": failures,
        "unknowns": unknowns,
        "note": "Evaluates supplied measurements only; provenance is not authenticated.",
    }
