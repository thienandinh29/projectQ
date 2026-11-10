"""Public failure reports derived from the existing durable research trail."""

from typing import Any


def failure_report(step_vi: str, trail: list[dict[str, Any]]) -> dict[str, Any]:
    start = max(
        (i for i, event in enumerate(trail) if event.get("code") == "research_started"),
        default=0,
    )
    events = trail[start:]
    selected = {e.get("url") for e in events if e.get("kind") == "select"}
    licensed = {e.get("url") for e in events if e.get("code") == "license_verified"}
    failed: dict[str, Any] = next((e for e in reversed(events) if e.get("outcome") == "failed"), {})
    rejected = [
        {
            "code": e.get("code", "source_rejected"),
            "url": e.get("url") or None,
            "message_vi": e["text_vi"],
        }
        for e in events
        if (
            e.get("outcome") == "rejected"
            or str(e.get("text_vi", "")).startswith(("Bỏ qua nguồn:", "Nguồn chưa được xác nhận"))
        )
        and (not e.get("url") or e.get("url") not in selected)
        and not (e.get("code") == "license_missing" and e.get("url") in licensed)
    ]
    return {
        "stage": failed.get("stage", "unknown"),
        "code": failed.get("code", "legacy_failure"),
        "message_vi": failed.get("text_vi", step_vi),
        "action_vi": failed.get("action_vi")
        or "Xem các nguồn bị loại và nhật ký research; dùng mã job để đối chiếu log backend.",
        "rejected_sources": rejected[-24:],
    }
