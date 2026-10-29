#!/usr/bin/env python3
"""Report CI observations without changing gate results or persisting raw metadata."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


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
        result = subprocess.run(
            ["docker", "buildx", "history", "inspect", "--format", "json", ref],
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


def cache_observations(needs: dict) -> dict:
    pnpm = {}
    for job in ("frontend-quality", "frontend-e2e"):
        value = needs.get(job, {}).get("outputs", {}).get("pnpm_cache_hit")
        pnpm[job] = {"true": "hit", "false": "miss"}.get(value, "unavailable")
    outputs = needs.get("frontend-image-verify", {}).get("outputs", {})
    try:
        cached, total = int(outputs["cached_steps"]), int(outputs["total_steps"])
        if not 0 <= cached <= total or total == 0:
            raise ValueError("Invalid counters")
    except (KeyError, TypeError, ValueError):
        cached = total = None
    known = [value for value in pnpm.values() if value != "unavailable"]
    return {
        "pnpm": pnpm,
        "pnpm_hit_percent": round(100 * known.count("hit") / len(known), 2)
        if known
        else None,
        "docker": {
            "cached_steps": cached,
            "total_steps": total,
            "cached_step_percent": round(100 * cached / total, 2) if total else None,
        },
    }


def observations(jobs: list[dict]) -> list[dict]:
    return [
        {
            "name": job["name"],
            "status": job["status"],
            "conclusion": job.get("conclusion"),
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
        "| Job | Result | Duration |",
        "| --- | --- | --- |",
    ]
    if report["timing_status"] != "available":
        lines.append("| Timing API unavailable | unavailable | unavailable |")
    for job in report["jobs"]:
        lines.append(
            f"| {cell(job['name'])} | {cell(job['conclusion'] or job['status'])} | "
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
    lines += ["", "### Frontend caches", "", "| Cache | Observation |", "| --- | --- |"]
    for job, value in caches["pnpm"].items():
        lines.append(f"| pnpm store / {job} | {value} |")
    percent = caches["pnpm_hit_percent"]
    percent_text = f"{percent}%" if percent is not None else "unavailable"
    lines.append(
        f"| pnpm exact-key hit rate (known observations only) | {percent_text} |"
    )
    docker = caches["docker"]
    value = (
        f"{docker['cached_steps']}/{docker['total_steps']} ({docker['cached_step_percent']}%)"
        if docker["total_steps"]
        else "unavailable"
    )
    lines += [
        f"| Docker cached build steps | {value} |",
        "",
        "pnpm records exact-key store restoration, not node_modules reuse. "
        "Docker measures BuildKit cached steps, not GHA cache-download success. "
        "Missing observations are unavailable, never counted as misses.",
    ]
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
    report = {
        "run_id": run_id,
        "attempt": attempt,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_to_report_seconds": None,
        "timing_status": "unavailable",
        "jobs": [],
        "caches": cache_observations(json.loads(os.getenv("CI_NEEDS_JSON", "{}"))),
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
