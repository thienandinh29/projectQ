"""Review routing offline; --live probes the agreed generator/verifier pair.

Usage: uv run python -m app.llm.smoke
       uv run python -m app.llm.smoke --live --output ../../outputs/gateway-live.json
       uv run python -m app.llm.smoke --live --provider vertex --tier free --task items
"""

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.llm.gateway import (
    Attempt,
    Gateway,
    GatewayError,
    Message,
    Routing,
    load_routing,
    verification_scope,
)
from app.llm.providers import default_gateway


class SmokeAnswer(BaseModel):
    text_vi: str = Field(min_length=1)


def configuration(routing: Routing) -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    for tier, tasks in routing.tiers.items():
        for task, routes in tasks.items():
            for route in routes:
                model = os.path.expandvars(route.model)
                rows.append(
                    {
                        "tier": tier,
                        "task": task,
                        "provider": route.provider,
                        "family": route.family,
                        "model_configured": "$" not in model
                        and route.family in model.casefold()
                        and not model.endswith(":free"),
                    }
                )
    return rows


async def probe(
    gateway: Gateway, provider: str, tier: str, task: str
) -> dict[str, str | int | float]:
    if task == "verify":
        raise ValueError("Probe a generation task; verification requires actual generator metadata")
    routes = [
        route
        for route in gateway.routing.tiers.get(tier, {}).get(task, [])
        if route.provider == provider
    ]
    attempts: list[Attempt] = []
    isolated = Gateway(
        Routing(tiers={tier: {task: routes}}),
        gateway.adapters,
        attempts_per_model=1,
        total_timeout=40,
        observe_attempt=attempts.append,
    )
    result = await isolated.complete_with_metadata(
        task,
        tier,
        "Đây là kiểm tra kết nối. Trả về JSON ngắn bằng tiếng Việt.",
        [Message(role="user", content='Trả về {"text_vi":"Kết nối thành công."}')],
        SmokeAnswer,
    )
    return {
        "provider": result.route.provider,
        "family": result.route.family,
        "model": result.route.model,
        "successful_latency_ms": next(
            a.latency_ms for a in reversed(attempts) if a.status == "success"
        ),
        "status": "ok",
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }


async def probe_pair(gateway: Gateway, tier: str) -> dict[str, Any]:
    """Route smoke only; the verifier receives the source, never generated text."""
    attempts: list[Attempt] = []
    isolated = Gateway(gateway.routing, gateway.adapters, observe_attempt=attempts.append)
    report: dict[str, Any] = {"scope": "Synthetic route smoke, not canonical topic/H8 acceptance"}
    question = [
        Message(
            role="user",
            content="Nguồn: Một chương trình là chuỗi chỉ dẫn. "
            'Dựa trên nguồn, chương trình là gì? Trả JSON {"text_vi":"..."}.',
        )
    ]
    try:
        generated = await isolated.complete_with_metadata(
            "items",
            tier,
            "Chỉ trả lời từ nguồn bằng tiếng Việt.",
            question,
            SmokeAnswer,
        )
        with verification_scope(generated.route.family):
            verified = await isolated.complete_with_metadata(
                "verify",
                tier,
                "Giải độc lập chỉ từ nguồn bằng tiếng Việt.",
                question,
                SmokeAnswer,
            )
        report.update(
            status="ok",
            generator=generated.route.model_dump(),
            verifier=verified.route.model_dump(),
            generator_answer_excluded=True,
        )
    except GatewayError:
        report.update(status="failed", error_type="GatewayError")
    report["attempts"] = [{**asdict(a), "route": a.route.model_dump()} for a in attempts]
    report["successful_calls"] = [
        {"task": a.task, "route": a.route.model_dump(), "latency_ms": a.latency_ms}
        for a in attempts
        if a.status == "success"
    ]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P3 routing check; no network unless --live is set."
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["vertex", "bedrock", "openrouter", "deepseek", "gemini"],
    )
    parser.add_argument("--tier", choices=["free", "pro"], default="free")
    parser.add_argument("--task", default="items")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from app.config import get_settings

    get_settings().export_worker_environment()
    if not args.live:
        print(json.dumps({"live": False, "routes": configuration(load_routing())}, indent=2))
        return
    try:
        gateway = default_gateway()
        report = (
            asyncio.run(probe(gateway, args.provider, args.tier, args.task))
            if args.provider
            else (asyncio.run(probe_pair(gateway, args.tier)))
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps(report, ensure_ascii=False))
        if report["status"] != "ok":
            raise SystemExit(1)
    except (GatewayError, ValueError):
        print(
            json.dumps(
                {
                    "provider": args.provider,
                    "status": "failed",
                    "reason": "Check model IDs, credentials, region and account access.",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
