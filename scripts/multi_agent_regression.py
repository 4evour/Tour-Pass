"""Run multi-agent smoke regression across supported cities.

This script posts prompts to /agent/plan-sync and writes a Markdown report.
It intentionally uses only the Python standard library so it can run in CI
without extra dependencies.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


CITY_DIR_MAP = {
    "广州": "guangzhou",
    "北京": "beijing",
    "上海": "shanghai",
    "深圳": "shenzhen",
    "成都": "chengdu",
    "重庆": "chongqing",
    "杭州": "hangzhou",
    "武汉": "wuhan",
    "南京": "nanjing",
    "西安": "xian",
    "长沙": "changsha",
    "昆明": "kunming",
    "大理": "dali",
    "丽江": "lijiang",
    "三亚": "sanya",
    "桂林": "guilin",
    "厦门": "xiamen",
    "青岛": "qingdao",
    "哈尔滨": "harbin",
    "苏州": "suzhou",
    "张家界": "zhangjiajie",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--agent-path", default="/agent/plan-sync")
    parser.add_argument("--out", default="docs/multi_agent_regression_report.md")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--city", action="append", default=[])
    parser.add_argument("--skip-image-head", action="store_true")
    return parser.parse_args()


def load_must_visit(city: str) -> str:
    city_dir = CITY_DIR_MAP.get(city, city)
    pois_path = Path("data") / city_dir / "pois.json"
    if not pois_path.exists():
        return ""
    pois = json.loads(pois_path.read_text(encoding="utf-8"))
    for poi in pois:
        if poi.get("type") == "attraction" and poi.get("name"):
            return poi["name"]
    return ""


def post_plan(base_url: str, agent_path: str, message: str, timeout: int) -> tuple[bool, dict | str]:
    body = json.dumps({"message": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + agent_path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return True, json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, str(exc)


def image_url_safe(url: str) -> bool:
    if not url:
        return True
    return url.startswith(("http://", "https://", "/data/", "/images/", "images/"))


def head_ok(url: str, timeout: int) -> bool:
    if not url.startswith(("http://", "https://")):
        return True
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 400
    except Exception:
        return False


def validate_itinerary(payload: dict, must_visit: str, skip_image_head: bool, timeout: int) -> list[str]:
    errors: list[str] = []
    if not payload.get("success"):
        return [f"success=false: {payload.get('error', '')}"]

    itinerary = payload.get("itinerary") or {}
    days = itinerary.get("days") or []
    hotel = itinerary.get("hotel")
    if not hotel:
        errors.append("missing hotel")
    if not days:
        errors.append("missing days")

    planned_names: list[str] = []
    image_urls: list[str] = []
    for day in days:
        stops = day.get("stops") or []
        if not stops:
            errors.append(f"day {day.get('day', '?')} has no stops")
        for stop in stops:
            name = stop.get("poi_name") or ""
            planned_names.append(name)
            image_url = stop.get("image_url") or ""
            if image_url:
                image_urls.append(image_url)
            if not image_url_safe(image_url):
                errors.append(f"unsafe image url: {image_url}")

    if must_visit and not any(must_visit in name or name in must_visit for name in planned_names):
        errors.append(f"must visit not covered: {must_visit}")

    if not skip_image_head:
        for url in image_urls[:3]:
            if not head_ok(url, timeout=min(timeout, 20)):
                errors.append(f"image HEAD failed: {url}")

    return errors


def main() -> int:
    args = parse_args()
    cities = args.city or list(CITY_DIR_MAP.keys())
    rows = []

    for city in cities:
        must_visit = load_must_visit(city)
        prompts = [
            (f"{city}3天轻松游，偏经典景点和本地美食", ""),
            (f"{city}3天行程，必须安排{must_visit}，节奏不要太赶", must_visit),
        ]
        for message, must in prompts:
            start = time.time()
            ok, payload = post_plan(args.base_url, args.agent_path, message, args.timeout)
            elapsed = round(time.time() - start, 1)
            if ok and isinstance(payload, dict):
                errors = validate_itinerary(payload, must, args.skip_image_head, args.timeout)
            else:
                errors = [str(payload)]
            rows.append({
                "city": city,
                "prompt": message,
                "seconds": elapsed,
                "status": "PASS" if not errors else "FAIL",
                "errors": errors,
            })
            print(f"{city}: {rows[-1]['status']} ({elapsed}s)")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Multi-Agent Regression Report",
        "",
        f"- Base URL: `{args.base_url}`",
        f"- Endpoint: `{args.agent_path}`",
        f"- Cities: {len(cities)}",
        "",
        "| City | Status | Seconds | Errors | Prompt |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        errors = "<br>".join(row["errors"]) if row["errors"] else "-"
        lines.append(
            f"| {row['city']} | {row['status']} | {row['seconds']} | {errors} | {row['prompt']} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    failures = sum(1 for row in rows if row["status"] != "PASS")
    print(f"Wrote {out_path}; failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
