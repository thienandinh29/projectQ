"""Sequential, resumable P4 verification. Run with python -m app.content.verify_batch."""

import argparse
import asyncio
import json
import os
import random
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.content.artifacts import load_topic
from app.content.gateway import ModelReply, P3Gateway, independent
from app.content.models import Item, cited_chunks, digest, item_hash
from app.guardrails.answerability import (
    PROMPT_VERSION,
    blind_request,
    is_currently_verified,
    verify_item,
)
from app.llm.gateway import (
    Adapter,
    Attempt,
    Gateway,
    Message,
    ProviderError,
    ProviderReply,
    Route,
    gateway_scope,
)
from app.llm.providers import default_gateway


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class Capture(P3Gateway):
    reply: ModelReply | None = None

    async def generate(self, **kwargs: Any) -> ModelReply:
        self.reply = await super().generate(**kwargs)
        return self.reply


class Replay:
    def __init__(self, reply: ModelReply, payload_hash: str) -> None:
        self.reply, self.payload_hash = reply, payload_hash

    async def generate(self, **kwargs: Any) -> ModelReply:
        if digest(kwargs["payload"]) != self.payload_hash:
            raise ValueError("Replay requires identical blind input")
        return self.reply


class ClassifiedAdapter:
    def __init__(self, adapter: Adapter, errors: list[dict[str, Any]]) -> None:
        self.adapter, self.errors = adapter, errors

    async def generate(
        self,
        route: Route,
        system: str,
        messages: Sequence[Message],
        schema: type[BaseModel] | None,
    ) -> ProviderReply:
        try:
            return await self.adapter.generate(route, system, messages, schema)
        except ProviderError as exc:
            self.errors.append(
                {
                    "kind": getattr(
                        exc, "failure_kind", "transient" if exc.retryable else "configuration"
                    ),
                    "code": str(exc),
                    "retry_after": getattr(exc, "retry_after", None),
                    "delay_source": getattr(exc, "delay_source", None),
                    "quota_violations": getattr(exc, "quota_violations", []),
                    "http": getattr(exc, "http_diagnostic", None),
                    "transport": getattr(exc, "transport_diagnostic", None),
                }
            )
            raise


async def run(
    topic: Path,
    checkpoint: Path,
    interval: float,
    retries: int,
    max_items: int | None = None,
    timeout_seconds: float = 70,
    gateway_override: Gateway | None = None,
) -> dict[str, Any]:
    _, chunks, graph, items = load_topic(topic)
    base = gateway_override or default_gateway()
    config_hash = digest(
        {
            "routing": base.routing.model_dump(),
            "models": {
                name: value for name, value in os.environ.items() if name.endswith("_MODEL")
            },
            "prompt": PROMPT_VERSION,
        }
    )
    state: dict[str, Any] = (
        json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    )
    state.setdefault("items", {})
    state.setdefault("attempts", [])
    if state.get("resume_after_epoch", 0) > time.time() and "summary" in state:
        return state
    state["blocked"] = None
    started = time.monotonic()
    reused = 0
    processed = 0
    for item in items:
        fingerprint = item_hash(item, chunks)
        source_hash = digest(
            [c.model_dump(mode="json") for c in chunks if c.chunk_id in item.chunk_ids]
        )
        old = state["items"].get(item.id)
        if (
            old
            and old["fingerprint"] == fingerprint
            and old["config_hash"] == config_hash
            and is_currently_verified(Item.model_validate(old["result"]), chunks)
        ):
            reused += 1
            continue
        for attempt in range(retries + 1):
            events: list[Attempt] = []
            provider_errors: list[dict[str, Any]] = []
            adapters = {
                name: ClassifiedAdapter(adapter, provider_errors)
                for name, adapter in base.adapters.items()
            }
            gateway = Gateway(
                base.routing,
                adapters,
                attempts_per_model=1,
                request_timeout=timeout_seconds - 5,
                total_timeout=timeout_seconds - 2,
                observe_attempt=events.append,
            )
            capture = Capture()
            tick = time.monotonic()
            with gateway_scope(gateway):
                result = await verify_item(item, chunks, capture, timeout_seconds=timeout_seconds)
            audit = result.verification
            assert audit is not None
            infrastructure = audit.reason.startswith("verification_error:")
            record = {
                "fingerprint": fingerprint,
                "source_fingerprint": source_hash,
                "config_hash": config_hash,
                "result": result.model_dump(mode="json"),
                "reply": capture.reply.model_dump(mode="json") if capture.reply else None,
                "blind_hash": digest(blind_request(item, chunks).model_dump(mode="json")),
                "checked_at": datetime.now(UTC).isoformat(),
                "attempt": attempt + 1,
                "latency_ms": round((time.monotonic() - tick) * 1000),
                "infrastructure_error": infrastructure,
                "provider_errors": provider_errors,
            }
            state["items"][item.id] = record
            for event in events:
                state["attempts"].append(
                    {
                        "item_id": item.id,
                        "batch_attempt": attempt + 1,
                        "provider": event.route.provider,
                        "model": event.route.model,
                        "family": event.route.family,
                        "status": event.status,
                        "error": event.error_code,
                        "latency_ms": event.latency_ms,
                        "input_tokens": event.input_tokens
                        if event.status == "success" or event.input_tokens > 0
                        else None,
                        "output_tokens": event.output_tokens
                        if event.status == "success" or event.output_tokens > 0
                        else None,
                    }
                )
            atomic_json(checkpoint, state)
            print(
                json.dumps({"item": item.id, "status": result.status, "reason": audit.reason}),
                flush=True,
            )
            if not infrastructure:
                break
            # Inspect classified errors captured by the provider wrapper below.
            fatal = next(
                (e for e in provider_errors if e.get("kind") in ("quota", "configuration")), None
            )
            if fatal or attempt == retries:
                state["blocked"] = fatal or {"kind": "api_retry_exhausted"}
                if fatal and fatal.get("retry_after"):
                    state["resume_after_epoch"] = time.time() + fatal["retry_after"]
                break
            retry_after = max((e.get("retry_after") or 0 for e in provider_errors), default=0)
            await asyncio.sleep(max(interval, retry_after, 2**attempt * 5 + random.random()))
        if state["blocked"]:
            break
        processed += 1
        if max_items is not None and processed >= max_items:
            break
        await asyncio.sleep(interval)
    valid = [
        state["items"][i.id]
        for i in items
        if i.id in state["items"]
        and state["items"][i.id]["config_hash"] == config_hash
        and state["items"][i.id]["fingerprint"] == item_hash(i, chunks)
    ]
    concepts = sorted(
        {r["result"]["concept"] for r in valid if r["result"]["status"] == "verified"}
    )
    state["summary"] = {
        "verified": sum(r["result"]["status"] == "verified" for r in valid),
        "concepts": concepts,
        "edges": [
            e.model_dump(mode="json", by_alias=True)
            for e in graph.edges
            if e.prerequisite in concepts and e.to in concepts
        ],
        "reused_verified": reused,
        "elapsed_seconds": time.monotonic() - started,
        "cost_usd": None,
        "requests": len(state["attempts"]),
        "human_review": "pending",
        "successful_requests": sum(e["status"] == "success" for e in state["attempts"]),
        "retry_requests": sum(e.get("batch_attempt", 1) > 1 for e in state["attempts"]),
        "errors_by_type": dict(
            Counter(
                e["error"] or e["status"] for e in state["attempts"] if e["status"] != "success"
            )
        ),
        "input_tokens": sum(
            e["input_tokens"] for e in state["attempts"] if e["input_tokens"] is not None
        )
        if any(e["input_tokens"] is not None for e in state["attempts"])
        else None,
        "output_tokens": sum(
            e["output_tokens"] for e in state["attempts"] if e["output_tokens"] is not None
        )
        if any(e["output_tokens"] is not None for e in state["attempts"])
        else None,
    }
    # Paired evaluation reuses identical blind model inputs; never claims 20 API calls.
    cases = []
    for item in items[:10]:
        record = state["items"].get(item.id)
        for flipped in (False, True):
            candidate = (
                next(o.id for o in item.options if o.id != item.answer_id)
                if flipped
                else item.answer_id
            )
            outcome = "infrastructure_or_unfinished"
            if record in valid and record["reply"] and not record["infrastructure_error"]:
                from app.guardrails.answerability import bind_verdict, evidence_valid

                verdict = bind_verdict(
                    ModelReply.model_validate(record["reply"]), blind_request(item, chunks)
                )
                selected = next(
                    (
                        o.id
                        for i, o in enumerate(item.options)
                        if f"choice-{i}" == verdict.selected_option_id
                    ),
                    None,
                )
                supported = (
                    independent(item.generator, ModelReply.model_validate(record["reply"]).identity)
                    and evidence_valid(verdict.evidence, cited_chunks(item, chunks))
                    and verdict.supported
                    and verdict.unique_answer
                    and not verdict.ambiguous
                    and not verdict.multiple_correct
                    and not verdict.insufficient_evidence
                )
                outcome = "allowed" if selected == candidate and supported else "blocked"
            cases.append(
                {
                    "original_item": item.id,
                    "variant": "flipped" if flipped else "unchanged",
                    "expected_error": flipped,
                    "candidate_answer": candidate,
                    "outcome": outcome,
                    "reuse": "identical question/options/chunks; backend candidate differs",
                }
            )
    state["evaluation"] = cases
    state["evaluation_summary"] = {
        "wrong_blocked": sum(c["expected_error"] and c["outcome"] == "blocked" for c in cases),
        "wrong_allowed": sum(c["expected_error"] and c["outcome"] == "allowed" for c in cases),
        "correct_blocked": sum(
            not c["expected_error"] and c["outcome"] == "blocked" for c in cases
        ),
        "wrong_valid": sum(
            c["expected_error"] and c["outcome"] != "infrastructure_or_unfinished" for c in cases
        ),
        "correct_valid": sum(
            not c["expected_error"] and c["outcome"] != "infrastructure_or_unfinished"
            for c in cases
        ),
        "unfinished": sum(c["outcome"] == "infrastructure_or_unfinished" for c in cases),
        "model_result_reuses": sum(c["outcome"] != "infrastructure_or_unfinished" for c in cases),
        "labels": "expected agent labels; human confirmation pending",
    }
    atomic_json(checkpoint, state)
    return state


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[4] / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-items", type=int, help="Probe only this many unfinished items")
    args = parser.parse_args()
    if args.interval < 0 or args.retries < 0:
        parser.error("interval/retries must be nonnegative")
    if args.max_items is not None and args.max_items < 1:
        parser.error("max-items must be positive")
    print(
        json.dumps(
            asyncio.run(
                run(args.topic, args.checkpoint, args.interval, args.retries, args.max_items)
            )["summary"]
        )
    )


if __name__ == "__main__":
    main()
