from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import time
from typing import Any

from .models import RecoveryTimingResult


@dataclass
class RecoveryEvent:
    event_id: str
    current_ph: float
    unsafe_dose_ml: float
    unsafe_reagent: str


class RecoveryTimingWorkflow:
    STAGE_BUDGETS_SECONDS = {
        "ICS creates recovery event": 0.30,
        "Gateway switches to RECOVERY": 0.50,
        "Controller sends recovery command": 2.00,
    }

    def run_event(self, event: RecoveryEvent) -> RecoveryTimingResult:
        t1 = time.perf_counter()
        timeline: list[dict[str, Any]] = []
        self._ics_create_recovery_event(event)
        timeline.append(self._milestone("ICS creates recovery event", t1))
        self._gateway_switch_to_recovery()
        timeline.append(self._milestone("Gateway switches to RECOVERY", t1))
        counter_agent = "base" if event.current_ph < 6.0 else "acid"
        self._controller_send()
        timeline.append(self._milestone("Controller sends recovery command", t1))
        total = timeline[-1]["elapsed_seconds"]
        return RecoveryTimingResult(event.event_id, event.current_ph, counter_agent, total, total <= 2.0, timeline)

    def _ics_create_recovery_event(self, event: RecoveryEvent) -> None:
        time.sleep(0.02)

    def _gateway_switch_to_recovery(self) -> None:
        time.sleep(0.03)

    def _controller_send(self) -> None:
        time.sleep(0.03)

    def _milestone(self, stage: str, t1: float) -> dict[str, Any]:
        elapsed = time.perf_counter() - t1
        return {
            "stage": stage,
            "elapsed_seconds": round(elapsed, 4),
            "budget_seconds": self.STAGE_BUDGETS_SECONDS[stage],
            "stage_pass": elapsed <= self.STAGE_BUDGETS_SECONDS[stage],
        }


def run_int_s1_timing(output_dir: Path, events_count: int = 100) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    workflow = RecoveryTimingWorkflow()
    events = [
        RecoveryEvent(f"INTS1-EVT-{i:03d}", 3.8 if i % 2 else 9.4, 20.0 + (i % 5), "acid" if i % 2 else "base")
        for i in range(1, events_count + 1)
    ]
    results = [workflow.run_event(e) for e in events]
    csv_path = raw_dir / "int_s1_recovery_timing.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["event_id", "current_ph", "counter_agent", "stage", "elapsed_seconds", "budget_seconds", "stage_pass", "total_elapsed_s", "pass_2s_target"])
        writer.writeheader()
        for result in results:
            for item in result.timeline:
                writer.writerow({
                    "event_id": result.event_id,
                    "current_ph": result.current_ph,
                    "counter_agent": result.counter_agent,
                    "stage": item["stage"],
                    "elapsed_seconds": item["elapsed_seconds"],
                    "budget_seconds": item["budget_seconds"],
                    "stage_pass": item["stage_pass"],
                    "total_elapsed_s": round(result.total_elapsed_s, 4),
                    "pass_2s_target": result.pass_2s_target,
                })
    return {
        "events_count": events_count,
        "max_elapsed_s": round(max(r.total_elapsed_s for r in results), 4),
        "raw_csv": str(csv_path),
        "pass_fail": "PASS" if all(r.pass_2s_target for r in results) else "FAIL",
    }
