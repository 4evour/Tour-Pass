"""Bounded, logged product comparison; raw artifacts stay in ignored artifacts/."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

CASES = [
    {
        "id": "guangzhou-three-days",
        "city": "广州",
        "message": "请规划广州3天行程，第一次去，喜欢老城和本地美食，不要太赶，公共交通为主。日期、抵返时间和酒店尚未确定。请给出每天的路线、餐饮、住宿区域、交通策略、预算边界和需要预约的事项。不要追问；明确说明假设，不要虚构实时票价、库存或已经核验的信息。",
    },
    {
        "id": "chongqing-required-stops",
        "city": "重庆",
        "message": "请规划重庆1天行程，住解放碑住宿区，必去李子坝和洪崖洞，10:00到21:00，公共交通为主，同行2位成人，其中一位膝盖不太好，少走路，不吃辣。没有指定出发日期。请给出路线、三餐、通勤和返回住宿的安排，以及体力风险和预约待办。不要追问，不要虚构实时票价、库存或已经核验的信息。",
    },
]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def run_codex(case: dict, output: Path, timeout: float) -> dict:
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("Codex CLI executable not found")
    # Keep the benchmark agent out of the repository and away from its .env.
    with tempfile.TemporaryDirectory(
        prefix="tour-pass-codex-benchmark-", ignore_cleanup_errors=True
    ) as cwd:
        command = [
            executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            cwd,
            "-c",
            'web_search="disabled"',
            "-o",
            str(output / "answer.md"),
            "-",
        ]
        prompt = (
            "这是旅行规划产品的无工具基线测试。不要读取文件、执行命令、使用搜索或任何工具；"
            "直接根据已有知识用中文交付可读方案。不要写入文件，最终回复就是结果。\n\n"
            + case["message"]
        )
        write_json(output / "invocation.json", {"command": command, "prompt": prompt})
        started = time.perf_counter()
        with (
            (output / "events.jsonl").open("w", encoding="utf-8") as stdout,
            (output / "stderr.log").open("w", encoding="utf-8") as stderr,
        ):
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=stdout,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                process.communicate(prompt, timeout=timeout)
                exit_code = process.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                        timeout=15,
                    )
                else:
                    process.kill()
                process.communicate(timeout=15)
                exit_code = process.returncode
                timed_out = True
        answer_path = output / "answer.md"
        answer = answer_path.read_text(encoding="utf-8") if answer_path.exists() else ""
        events = []
        for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        tools = [
            event
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type")
            not in {"agent_message", "reasoning", "plan"}
        ]
        usage = next(
            (
                event.get("usage")
                for event in events
                if event.get("type") == "turn.completed"
            ),
            None,
        )
        return {
            "delivered": exit_code == 0 and bool(answer.strip()),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "output_chars": len(answer),
            "usage": usage,
            "tool_item_count": len(tools),
            "evidence_mode": "knowledge_only_no_live_verification",
        }


class RecordedSkeletonLLM:
    """Controlled ablation, not a request-matched ReplayLLM or a live model run."""

    model = "recorded-skeleton"
    reasoning_effort = "not_run"
    wire_api = "not_run"
    hedge_delay_seconds = 0.0

    def __init__(self, path: Path, case: dict) -> None:
        request = json.loads((path.parent / "request.json").read_text(encoding="utf-8"))
        if request != case:
            raise ValueError("Recorded skeleton must come from the identical test case")
        recording = json.loads(path.read_text(encoding="utf-8"))
        responses = [
            call["response"] for call in recording["llm"] if call.get("response")
        ]
        if len(responses) != 1:
            raise ValueError("Expected exactly one successful recorded skeleton")
        self.content = responses[0]["content"]
        json.loads(self.content)

    async def ainvoke(self, messages: list, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            content=self.content, tool_calls=[], metrics={"replayed_skeleton": True}
        )

    async def close(self) -> None:
        return None


async def run_tour_pass(
    case: dict,
    output: Path,
    timeout: float,
    recorded_skeleton: Path | None = None,
    llm_timeout: float | None = None,
) -> dict:
    from dotenv import load_dotenv

    from trip_agent.cache import ProviderCache
    from trip_agent.context import MemoryPolicy
    from trip_agent.evaluate import (
        RecordingAmap,
        RecordingLLM,
        RecordingWeather,
        _summarize,
    )
    from trip_agent.llm import OpenAICompatibleLLM
    from trip_agent.loop import TripAgent
    from trip_agent.observability import close_logging, configure_logging
    from trip_agent.providers.amap import AmapProvider
    from trip_agent.providers.weather import WeatherProvider
    from trip_agent.store import TripStore

    load_dotenv(ROOT / ".env", override=False)
    configure_logging(output / "planning.jsonl")
    cache = ProviderCache(output / "provider-cache.sqlite")
    amap = RecordingAmap(AmapProvider(cache))
    weather = RecordingWeather(WeatherProvider(cache, amap=amap.inner))
    llm = RecordingLLM(
        RecordedSkeletonLLM(recorded_skeleton, case)
        if recorded_skeleton
        else OpenAICompatibleLLM()
    )
    if llm_timeout is not None:
        llm.inner.timeout_seconds = llm_timeout
    store = TripStore(f"sqlite:///{(output / 'trips.sqlite').as_posix()}")
    agent = TripAgent(
        llm=llm,
        amap=amap,
        weather=weather,
        store=store,
        memory_policy=MemoryPolicy(),
        max_provider_calls=int(os.environ.get("TRIP_AGENT_MAX_PROVIDER_CALLS", "18")),
    )
    write_json(
        output / "configuration.json",
        {
            "model": llm.model,
            "reasoning_effort": llm.reasoning_effort,
            "wire_api": llm.wire_api,
            "max_provider_calls": agent.max_provider_calls,
            "memory_policy": agent.memory_policy.as_dict(),
            "cache_mode": "fresh_per_run",
            "rail": "not_exercised_in_single_city_cases",
            "hedge_delay_seconds": llm.hedge_delay_seconds,
            "llm_timeout_seconds": getattr(llm, "timeout_seconds", None),
            "timeout_override_experiment": llm_timeout is not None,
            "model_mode": "recorded_skeleton_live_providers"
            if recorded_skeleton
            else "live",
            "skeleton_source": str(recorded_skeleton) if recorded_skeleton else None,
        },
    )
    response = None
    error = None
    events = []
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            agent.run(case["message"], on_event=events.append), timeout=timeout
        )
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        await agent.close()
        await llm.close()
        store.close()
        close_logging()
    recording = {"llm": llm.calls, "amap": amap.calls, "weather": weather.calls}
    write_json(output / "recording.json", recording)
    write_json(output / "events.json", events)
    if response is None:
        write_json(output / "error.json", error)
        return {"delivered": False, "elapsed_ms": elapsed_ms, "error": error}
    write_json(output / "response.json", response.model_dump(mode="json"))
    summary = _summarize(response, recording, elapsed_ms)
    plan = response.plan or {}
    transfers = [
        item for day in plan.get("days", []) for item in day.get("transfers", [])
    ]
    return {
        "delivered": bool(response.plan),
        **summary,
        "route_count": len(transfers),
        "verified_route_count": sum(item.get("source") == "amap" for item in transfers),
        "evidence_mode": "provider_enriched_validation_with_explicit_fallbacks",
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=["codex", "tour-pass"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--case", choices=[case["id"] for case in CASES])
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--recorded-skeleton", type=Path)
    parser.add_argument("--llm-timeout", type=float)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 3:
        parser.error("rounds must be between 1 and 3")
    if not 15 <= args.timeout <= 900:
        parser.error("timeout must be between 15 and 900 seconds")
    if args.recorded_skeleton and (args.system != "tour-pass" or not args.case):
        parser.error("--recorded-skeleton requires --system tour-pass and one --case")
    if args.llm_timeout is not None and (
        args.system != "tour-pass"
        or args.recorded_skeleton
        or not 15 <= args.llm_timeout <= args.timeout
    ):
        parser.error(
            "--llm-timeout requires live Tour Pass and 15 <= value <= --timeout"
        )
    output_root = args.output.resolve() / args.system
    output_root.mkdir(parents=True, exist_ok=True)
    cases = [case for case in CASES if not args.case or case["id"] == args.case]
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "system": args.system,
        "rounds": args.rounds,
        "timeout_seconds": args.timeout,
        "comparison": "configured_products_not_same_model_or_equal_tools",
        "llm_timeout_override_seconds": args.llm_timeout,
        "model_mode": "recorded_skeleton_live_providers"
        if args.recorded_skeleton
        else "live",
        "skeleton_source_sha256": hashlib.sha256(
            args.recorded_skeleton.read_bytes()
        ).hexdigest()
        if args.recorded_skeleton
        else None,
        "cases": cases,
        "source_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "trip_agent").rglob("*.py"))
        },
    }
    write_json(output_root / "manifest.json", manifest)
    if args.system == "codex":
        config_path = (
            Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
        )
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        write_json(
            output_root / "configuration.json",
            {
                key: config.get(key)
                for key in ("model", "model_reasoning_effort", "model_provider")
            },
        )
    summaries = []
    for round_number in range(1, args.rounds + 1):
        for case in cases:
            output = output_root / f"round-{round_number}" / case["id"]
            output.mkdir(parents=True, exist_ok=False)
            write_json(output / "request.json", case)
            summary = (
                await asyncio.to_thread(run_codex, case, output, args.timeout)
                if args.system == "codex"
                else await run_tour_pass(
                    case, output, args.timeout, args.recorded_skeleton, args.llm_timeout
                )
            )
            summary.update(case=case["id"], round=round_number, system=args.system)
            write_json(output / "summary.json", summary)
            summaries.append(summary)
            write_json(output_root / "summaries.json", summaries)
            print(
                json.dumps(
                    {
                        key: summary.get(key)
                        for key in (
                            "case",
                            "round",
                            "system",
                            "delivered",
                            "elapsed_ms",
                            "exit_code",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(main())
