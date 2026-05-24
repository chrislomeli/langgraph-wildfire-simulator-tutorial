"""evals.framework.stores — ExperimentStore implementations with NO DB dependency.

    InMemoryStore — keeps runs in process; enough to run an eval and read a
                    baseline within one session.
    JsonStore     — writes one JSON file per run to a directory, so baselines and
                    regression survive across processes.

A Postgres-backed store (writing eval_runs / eval_results) implements the same
``ExperimentStore`` Protocol, but it lives OUTSIDE this isolated package because
it depends on the DB layer. Both stores here expose ``latest_report()`` as a
convenience for fetching a baseline.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.framework.core import CaseExecution, Report, RunId, Score


@dataclass
class _RunRecord:
    run_id: RunId
    dataset_version: str
    task_label: str
    prompt_version: str
    started_at: str
    meta: dict[str, Any]
    case_scores: dict[str, list[dict]] = field(default_factory=dict)
    finished_at: str | None = None
    report: dict | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _report_to_dict(r: Report) -> dict:
    return {
        "run_id": r.run_id,
        "metrics": r.metrics,
        "passed_cases": r.passed_cases,
        "total_cases": r.total_cases,
        "regressions": r.regressions,
    }


def _report_from_dict(d: dict) -> Report:
    return Report(
        run_id=d["run_id"],
        metrics=d["metrics"],
        passed_cases=d["passed_cases"],
        total_cases=d["total_cases"],
        regressions=d.get("regressions", []),
    )


class InMemoryStore:
    """ExperimentStore kept in process memory."""

    def __init__(self) -> None:
        self._runs: dict[RunId, _RunRecord] = {}
        self._next = 1

    def start_run(self, *, dataset_version, task_label, prompt_version, meta) -> RunId:
        run_id = self._next
        self._next += 1
        self._runs[run_id] = _RunRecord(
            run_id=run_id,
            dataset_version=dataset_version,
            task_label=task_label,
            prompt_version=prompt_version,
            started_at=_now(),
            meta=dict(meta),
        )
        return run_id

    def record(self, run_id, case_id, scores: list[Score], execution: CaseExecution) -> None:
        self._runs[run_id].case_scores[case_id] = [asdict(s) for s in scores]

    def finish_run(self, run_id, report: Report) -> None:
        rec = self._runs[run_id]
        rec.finished_at = _now()
        rec.report = _report_to_dict(report)

    def latest_report(self) -> Report | None:
        finished = [r for r in self._runs.values() if r.report is not None]
        if not finished:
            return None
        return _report_from_dict(max(finished, key=lambda r: r.run_id).report)


class JsonStore:
    """ExperimentStore that writes one ``run-<id>.json`` file under ``root``."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._open: dict[RunId, _RunRecord] = {}
        self._next = self._max_existing_id() + 1

    def _max_existing_id(self) -> int:
        ids = [self._id_of(p) for p in self._root.glob("run-*.json")]
        return max(ids, default=0)

    @staticmethod
    def _id_of(path: Path) -> int:
        return int(path.stem.split("-", 1)[1])

    def start_run(self, *, dataset_version, task_label, prompt_version, meta) -> RunId:
        run_id = self._next
        self._next += 1
        self._open[run_id] = _RunRecord(
            run_id=run_id,
            dataset_version=dataset_version,
            task_label=task_label,
            prompt_version=prompt_version,
            started_at=_now(),
            meta=dict(meta),
        )
        return run_id

    def record(self, run_id, case_id, scores: list[Score], execution: CaseExecution) -> None:
        self._open[run_id].case_scores[case_id] = [asdict(s) for s in scores]

    def finish_run(self, run_id, report: Report) -> None:
        rec = self._open.pop(run_id)
        rec.finished_at = _now()
        rec.report = _report_to_dict(report)
        (self._root / f"run-{run_id}.json").write_text(json.dumps(asdict(rec), indent=2))

    def latest_report(self) -> Report | None:
        runs = list(self._root.glob("run-*.json"))
        if not runs:
            return None
        data = json.loads(max(runs, key=self._id_of).read_text())
        return _report_from_dict(data["report"]) if data.get("report") else None
