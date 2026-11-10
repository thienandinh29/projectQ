"""One explicit 90s Gemini diagnostic, identical inputs on P2/P4; no batch."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from app.content import verify_batch
from app.content.artifacts import load_topic
from app.content.models import digest
from app.content.verify_batch import atomic_json
from app.guardrails.answerability import SYSTEM, Verdict, blind_request
from app.llm.gateway import Message, Route
from app.llm.providers import (
    _gemini_payload,
    _thinking_config,
    default_gateway,
    diagnostic_transport_timeout,
    http_failure,
)

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "data/guardrails/gemini-shared-request.json"


async def diagnose(output: Path) -> None:
    if output.exists():
        raise ValueError("Diagnostic output already exists; refusing another attempt")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _, chunks, _, items = load_topic(ROOT / "data/golden/python-conditions")
    payload = blind_request(items[0], chunks).model_dump(mode="json")
    route = Route(provider="gemini", family="gemini", model=manifest["model"])
    request = _gemini_payload(
        SYSTEM, [Message(role="user", content=json.dumps(payload, ensure_ascii=False))], Verdict
    )
    _thinking_config(request, route)
    fingerprint = digest(
        {"provider": "gemini", "version": "v1beta", "model": route.model, "request": request}
    )
    if (
        fingerprint != manifest["request_fingerprint"]
        or os.environ.get("GEMINI_VERIFY_MODEL") != route.model
    ):
        raise ValueError("Shared input/model differs; compare manifest before calling")
    context = {
        "request_fingerprint": fingerprint,
        "provider": "gemini",
        "model": route.model,
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/"
        + quote(route.model, safe="")
        + ":generateContent",
        "project": "credential-associated; cannot derive from API key",
        "timeout_seconds": 90,
    }
    atomic_json(output, {"diagnostic": context, "status": "model_listing_started"})
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": os.environ.get("GEMINI_API_KEY", "")},
                params={"pageSize": 1000},
            )
        if response.status_code != 200:
            atomic_json(
                output,
                {"diagnostic": context, "listing_error": http_failure(response).http_diagnostic},
            )
            return
        data = response.json()
        models = [
            {"name": m.get("name"), "methods": m.get("supportedGenerationMethods", [])}
            for m in data.get("models", [])
        ]
        context["accessible_models"] = models
        supported = any(
            m["name"] == "models/" + route.model and "generateContent" in m["methods"]
            for m in models
        )
        context["configured_operation_supported"] = supported
        if not supported:
            atomic_json(
                output,
                {
                    "diagnostic": context,
                    "status": "configured_model_not_listed_for_operation",
                    "listing_paginated": bool(data.get("nextPageToken")),
                },
            )
            return
    except (httpx.RequestError, ValueError) as exc:
        atomic_json(output, {"diagnostic": context, "listing_error_type": type(exc).__name__})
        return
    # Same routing metadata/config hash as the regular runner; only disallow
    # other adapters/fallback calls during this single explicitly bounded probe.
    base = default_gateway()
    base.adapters = {name: adapter for name, adapter in base.adapters.items() if name == "gemini"}
    with diagnostic_transport_timeout(90):
        state = await verify_batch.run(
            ROOT / "data/golden/python-conditions",
            output,
            0,
            0,
            max_items=1,
            timeout_seconds=100,
            gateway_override=base,
        )
    state["diagnostic"] = context
    atomic_json(output, state)
    print(
        json.dumps(
            {
                "request_fingerprint": fingerprint,
                "summary": state["summary"],
                "blocked": state["blocked"],
            }
        )
    )


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(diagnose(args.output))


if __name__ == "__main__":
    main()
