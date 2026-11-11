#!/usr/bin/env python3
"""Report CI observations without changing gate results or persisting raw metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

PYTHON_JOBS = (
    "backend-quality",
    "backend-migrations",
    "backend-coverage",
    "hermes-quality",
    "hermes-contract",
)
DOCKER_JOBS = (
    "frontend-image-verify",
    "backend-image-verify",
    "backend-dev-image-verify",
    "ci-tools",
)


def phase_observations(needs: dict) -> dict:
    phases = {}
    for job in PYTHON_JOBS:
        try:
            records = json.loads(needs[job]["outputs"]["phases"])
            if not isinstance(records, list):
                raise ValueError("Invalid phase list")
            safe = []
            for item in records:
                duration = item["duration_seconds"]
                if (
                    not re.fullmatch(r"[a-z][a-z0-9-]*", item["phase"])
                    or item["category"]
                    not in (
                        "environment",
                        "dependencies",
                        "quality",
                        "migration",
                        "contract",
                        "tests",
                        "coverage",
                    )
                    or type(duration) not in (int, float)
                    or not math.isfinite(duration)
                    or duration < 0
                    or type(item["exit_code"]) is not int
                ):
                    raise ValueError("Invalid phase observation")
                safe.append(
                    {
                        key: item[key]
                        for key in (
                            "phase",
                            "category",
                            "duration_seconds",
                            "exit_code",
                        )
                    }
                )
            phases[job] = {"status": "available", "records": safe}
        except (KeyError, ValueError, TypeError):
            phases[job] = {"status": "unavailable", "records": []}
    return phases


def seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    elapsed = (
        datetime.fromisoformat(end.replace("Z", "+00:00"))
        - datetime.fromisoformat(start.replace("Z", "+00:00"))
    ).total_seconds()
    return round(elapsed, 3) if elapsed >= 0 else None


def build_cache(metadata: str) -> dict[str, int | None]:
    """Only export counters; build arguments, logs and provenance stay private."""
    unknown = {"cached_steps": None, "total_steps": None}
    try:
        ref = json.loads(metadata).get("buildx.build.ref")
        if not isinstance(ref, str) or not ref or ref.startswith("-"):
            return unknown
        # build-push-action emits builder/node/record; history expects a record ID
        # on the selected builder, not the composite metadata reference.
        parts = ref.split("/")
        if len(parts) not in (1, 3) or any(
            not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part) for part in parts
        ):
            return unknown
        command = ["docker", "buildx"]
        if len(parts) == 3:
            command += ["--builder", parts[0]]
        command += ["history", "inspect", "--format", "json", parts[-1]]
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        record = json.loads(result.stdout)
        cached, total = record.get("NumCachedSteps"), record.get("NumTotalSteps")
        if (
            record.get("Status") != "completed"
            or type(cached) is not int
            or type(total) is not int
            or not 0 <= cached <= total
            or total == 0
        ):
            return unknown
        return {"cached_steps": cached, "total_steps": total}
    except (ValueError, AttributeError, OSError, subprocess.SubprocessError):
        return unknown


def api_json(path: str) -> dict:
    request = Request(
        f"{os.environ.get('GITHUB_API_URL', 'https://api.github.com')}{path}",
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def collect_jobs(repository: str, run_id: str, attempt: str) -> list[dict]:
    # Attempt-specific API prevents an earlier successful retry from being mixed in.
    jobs = []
    page = 1
    while True:
        payload = api_json(
            f"/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs"
            f"?per_page=100&page={page}"
        )
        batch = payload["jobs"]
        jobs.extend(batch)
        if len(batch) < 100:
            return jobs
        page += 1


def shard_cache_status(job: dict, label: str) -> str:
    # Matrix job outputs can overwrite one another. Read each shard's step.
    statuses = {f"{label} true": "hit", f"{label} false": "miss"}
    return next(
        (
            statuses[step["name"]]
            for step in job["steps"]
            if step["conclusion"] == "success" and step["name"] in statuses
        ),
        "unavailable",
    )


def docker_cache_observation(outputs: dict) -> dict:
    try:
        cached, total = int(outputs["cached_steps"]), int(outputs["total_steps"])
        if not 0 <= cached <= total or total == 0:
            raise ValueError("Invalid counters")
    except (KeyError, TypeError, ValueError):
        cached = total = None
    return {
        "cached_steps": cached,
        "total_steps": total,
        "cached_step_percent": round(100 * cached / total, 2) if total else None,
    }


def cache_observations(needs: dict, jobs: list[dict] | None = None) -> dict:
    status = {"true": "hit", "false": "miss"}
    pnpm = {}
    for job in ("frontend-quality", "frontend-build", "frontend-coverage"):
        value = needs.get(job, {}).get("outputs", {}).get("pnpm_cache_hit")
        pnpm[job] = status.get(value, "unavailable")
    docker_images = {
        job: docker_cache_observation(needs.get(job, {}).get("outputs", {}))
        for job in DOCKER_JOBS
    }
    uv = {
        job: status.get(
            needs.get(job, {}).get("outputs", {}).get("uv_cache_hit"), "unavailable"
        )
        for job in PYTHON_JOBS
    }
    for job in jobs or []:
        name = job["name"]
        if name.startswith(("Frontend Unit (", "Stable Frontend E2E (")):
            pnpm[name] = shard_cache_status(job, "pnpm store cache")
        elif name.startswith("Backend Integration ("):
            uv[name] = shard_cache_status(job, "uv cache")
    known = [value for value in pnpm.values() if value != "unavailable"]
    known_uv = [value for value in uv.values() if value != "unavailable"]
    return {
        "pnpm": pnpm,
        "uv": uv,
        "uv_hit_percent": round(100 * known_uv.count("hit") / len(known_uv), 2)
        if known_uv
        else None,
        "pnpm_hit_percent": round(100 * known.count("hit") / len(known), 2)
        if known
        else None,
        "docker": docker_images["frontend-image-verify"],
        "docker_images": docker_images,
    }


def observations(jobs: list[dict]) -> list[dict]:
    return [
        {
            "name": job["name"],
            "status": job["status"],
            "conclusion": job.get("conclusion"),
            "queued_seconds": (
                seconds(job.get("created_at"), job.get("started_at"))
                if job.get("conclusion") != "skipped"
                else None
            ),
            "duration_seconds": (
                seconds(job.get("started_at"), job.get("completed_at"))
                if job.get("conclusion") != "skipped"
                else None
            ),
            "steps": [
                {
                    "name": step["name"],
                    "conclusion": step.get("conclusion"),
                    "duration_seconds": (
                        seconds(step.get("started_at"), step.get("completed_at"))
                        if step.get("conclusion") != "skipped"
                        else None
                    ),
                }
                for step in job.get("steps") or []
            ],
        }
        for job in jobs
    ]


def cell(value: object) -> str:
    return (
        str(value)
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("<", "&lt;")
    )


def duration(value: float | None) -> str:
    return f"{value:.1f}s" if value is not None else "unavailable"


def render_summary(report: dict) -> str:
    lines = [
        "## CI timing and cache observations",
        "",
        f"Run {report['run_id']}, attempt {report['attempt']}. "
        f"Elapsed to report: {duration(report['elapsed_to_report_seconds'])}.",
        "This is a snapshot before CI Gate finishes, not final workflow duration. "
        "Job durations include setup/cleanup; parallel durations must not be summed as wall time.",
        "",
        "| Job | Result | Queued | Duration |",
        "| --- | --- | --- | --- |",
    ]
    if report["timing_status"] != "available":
        lines.append(
            "| Timing API unavailable | unavailable | unavailable | unavailable |"
        )
    for job in report["jobs"]:
        lines.append(
            f"| {cell(job['name'])} | {cell(job['conclusion'] or job['status'])} | "
            f"{duration(job['queued_seconds'])} | "
            f"{duration(job['duration_seconds'])} |"
        )
    lines += [
        "",
        "### Slowest completed steps (up to 15)",
        "",
        "| Job / step | Result | Duration |",
        "| --- | --- | --- |",
    ]
    steps = [
        (job["name"], step)
        for job in report["jobs"]
        for step in job["steps"]
        if step["duration_seconds"] is not None
    ]
    for job, step in sorted(
        steps, key=lambda item: item[1]["duration_seconds"], reverse=True
    )[:15]:
        lines.append(
            f"| {cell(job)} / {cell(step['name'])} | {cell(step['conclusion'])} | "
            f"{duration(step['duration_seconds'])} |"
        )
    caches = report["caches"]
    lines += [
        "",
        "### Frontend and Docker caches",
        "",
        "| Cache | Observation |",
        "| --- | --- |",
    ]
    for job, value in caches["pnpm"].items():
        lines.append(f"| pnpm store / {job} | {value} |")
    percent = caches["pnpm_hit_percent"]
    percent_text = f"{percent}%" if percent is not None else "unavailable"
    lines.append(
        f"| pnpm exact-key hit rate (known observations only) | {percent_text} |"
    )
    for job, docker in caches["docker_images"].items():
        value = (
            f"{docker['cached_steps']}/{docker['total_steps']} ({docker['cached_step_percent']}%)"
            if docker["total_steps"]
            else "unavailable"
        )
        lines.append(f"| Docker cached build steps / {job} | {value} |")
    lines += [
        "",
        "pnpm records exact-key store restoration, not node_modules reuse. "
        "Docker measures BuildKit cached steps, not GHA cache-download success. "
        "Missing observations are unavailable, never counted as misses.",
    ]
    lines += [
        "",
        "### Python caches and phases",
        "",
        "| uv cache / job | Observation |",
        "| --- | --- |",
    ]
    for job, value in caches["uv"].items():
        lines.append(f"| {cell(job)} | {value} |")
    percent = caches["uv_hit_percent"]
    lines.append(
        f"Known uv cache hit rate: {str(percent) + '%' if percent is not None else 'unavailable'}"
    )
    lines += [
        "",
        "| Job / phase | Category | Exit code | Duration |",
        "| --- | --- | --- | --- |",
    ]
    for job, observations in report["phases"].items():
        if observations["status"] == "unavailable":
            lines.append(f"| {cell(job)} | unavailable | unavailable | unavailable |")
        for phase in observations["records"]:
            lines.append(
                f"| {cell(job)} / {cell(phase['phase'])} | {phase['category']} | "
                f"{phase['exit_code']} | {duration(phase['duration_seconds'])} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build-cache")
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build-cache":
        counters = build_cache(os.getenv("BUILD_METADATA", ""))
        if output := os.getenv("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as stream:
                for key, value in counters.items():
                    stream.write(f"{key}={value if value is not None else ''}\n")
        return 0

    repository = os.environ["GITHUB_REPOSITORY"]
    run_id, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    needs = json.loads(os.getenv("CI_NEEDS_JSON", "{}"))
    report = {
        "run_id": run_id,
        "attempt": attempt,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_to_report_seconds": None,
        "timing_status": "unavailable",
        "jobs": [],
        "phases": phase_observations(needs),
    }
    try:
        report["jobs"] = observations(collect_jobs(repository, run_id, attempt))
        run = api_json(f"/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}")
        report["elapsed_to_report_seconds"] = seconds(
            run.get("run_started_at"), report["observed_at"]
        )
        report["timing_status"] = "available"
    except (OSError, ValueError, KeyError, TypeError):
        # Never print request headers, response bodies or exception text.
        print("::warning::CI timing API unavailable; gate results are unchanged.")
    report["caches"] = cache_observations(needs, report["jobs"])
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = render_summary(report)
    print(summary)
    if summary_path := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a", encoding="utf-8") as stream:
            stream.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
