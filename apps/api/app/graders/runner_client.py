"""Client for the code runner service (`runner/`): one POST /run per submission."""

from typing import Any

import httpx

from app.graders.code import RunOutcome

TIMEOUT_SECONDS = 15.0  # the sandbox stops a run at 5 s; this covers container start and transfer


class RunnerUnavailable(RuntimeError):
    """The runner could not be reached, refused the request, or was busy."""


class RunnerClient:
    def __init__(
        self,
        base_url: str,
        token: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self.url = base_url.rstrip("/") + "/run"
        self.headers = {"X-Runner-Token": token} if token else {}
        self.transport = transport
        self.timeout = timeout

    async def run(self, body: dict[str, object]) -> RunOutcome:
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
                response = await client.post(self.url, json=body, headers=self.headers)
        except httpx.HTTPError as exc:
            raise RunnerUnavailable(f"runner unreachable: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise RunnerUnavailable(f"runner answered {response.status_code}")
        return parse_outcome(response.json())


def parse_outcome(data: Any) -> RunOutcome:
    if not isinstance(data, dict) or data.get("status") not in {
        "ok", "load_error", "timeout", "memory", "output_limit", "crashed",
    }:  # fmt: skip
        raise RunnerUnavailable("runner returned an unexpected body")
    results = data.get("results") or []
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        raise RunnerUnavailable("runner returned malformed results")
    load_error = data.get("load_error")
    return RunOutcome(
        status=data["status"],
        results=tuple({str(k): str(v) for k, v in r.items()} for r in results),
        load_error={str(k): str(v) for k, v in load_error.items()}
        if isinstance(load_error, dict)
        else None,
        output=str(data.get("output") or "")[:8000],
        duration_ms=int(data.get("duration_ms") or 0),
    )
