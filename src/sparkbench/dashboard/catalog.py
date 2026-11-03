"""Explicit run catalog; no filesystem discovery or mutable global defaults."""
from dataclasses import dataclass

BASE = "runs/live/led-oled-resume-2026-11-03-v1/"


@dataclass(frozen=True)
class Run:
    id: str
    title: str
    description: str
    directory: str
    capture: str
    report: str = "analysis/verification.json"
    spec: str = "analysis/spec.snapshot.json"
    kind: str = "led_oled"


CATALOG = (
    Run("led-oled-pass", "LED + OLED check", "Independent recorded verification",
        BASE+"latest-view-oled-fresh", BASE+"latest-view-oled-fresh/capture"),
    Run("wiring-swap", "Wiring swap test", "Intentional physical fault",
        BASE+"physical-led-swap-negative-fresh-v2", BASE+"physical-led-swap-negative-fresh-v2/capture",
        "result.json", "spec.snapshot.json", "negative"),
    Run("oled-incomplete", "Unreadable OLED", "Retained incomplete analysis",
        BASE+"latest-view-oled-verification", BASE+"restored-positive-control/capture"),
)
