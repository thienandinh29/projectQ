"""Runs inside the sandbox container. Untrusted learner code is executed here and nowhere else.

stdin: one JSON object {"nonce": str, "code": str, "calls": [str, ...]}.
stdout: whatever the learner prints (captured and capped), then one line "<nonce> " + JSON:
        {"load_error": {...}} or {"results": [{"repr": ...} or {"error": ..., "message": ...}]}.

The harness never sees expected values: it only reports what each call produced. The comparison
happens on the host, so printing a fake result line cannot turn a failure into a pass.
"""

import contextlib
import io
import json
import sys

MAX_REPR = 2000
MAX_MESSAGE = 500
MAX_CAPTURE = 8000


class CappedText(io.TextIOBase):
    """Keeps the first MAX_CAPTURE characters a learner prints and drops the rest, so a print
    loop cannot fill the memory limit; the wall-clock limit ends the loop itself."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if self.size < MAX_CAPTURE:
            keep = s[: MAX_CAPTURE - self.size]
            self.parts.append(keep)
            self.size += len(keep)
        return len(s)

    def getvalue(self) -> str:
        return "".join(self.parts)


def main() -> None:
    request = json.loads(sys.stdin.read())
    nonce, code, calls = request["nonce"], request["code"], request["calls"]
    real_stdout = sys.stdout
    captured = CappedText()
    namespace: dict[str, object] = {"__name__": "learner"}
    report: dict[str, object]
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        try:
            exec(compile(code, "learner.py", "exec"), namespace)
        except BaseException as exc:
            report = {
                "load_error": {"error": type(exc).__name__, "message": str(exc)[:MAX_MESSAGE]}
            }
        else:
            results = []
            for call in calls:
                try:
                    value = eval(call, namespace)
                    results.append({"repr": repr(value)[:MAX_REPR]})
                except BaseException as exc:
                    results.append({"error": type(exc).__name__, "message": str(exc)[:MAX_MESSAGE]})
            report = {"results": results}
    real_stdout.write(captured.getvalue()[:MAX_CAPTURE])
    real_stdout.write("\n" + nonce + " " + json.dumps(report) + "\n")
    real_stdout.flush()


if __name__ == "__main__":
    main()
