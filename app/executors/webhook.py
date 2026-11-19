"""
webhook executor.

POST a JSON body to a URL from the payload using stdlib urllib only.
URL must use https:// (enforced at execute time).
"""
import json
import urllib.error
import urllib.request

from app.executors.base import ExecutionResult, truncate


def execute(payload: dict) -> ExecutionResult:
    url: str = payload.get("url", "")
    body: dict = payload.get("body", {})
    headers: dict = payload.get("headers", {})

    if not url:
        return ExecutionResult(
            status="failure",
            result_summary="No URL specified in payload.",
            log_excerpt="payload missing 'url' key.",
        )

    if not url.startswith("https://"):
        return ExecutionResult(
            status="failure",
            result_summary="URL must use https://.",
            log_excerpt=f"Received URL: {url}",
        )

    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)

        with urllib.request.urlopen(req, timeout=15) as response:
            status_code = response.status
            response_body = truncate(response.read().decode("utf-8", errors="replace"))

        if 200 <= status_code < 300:
            return ExecutionResult(
                status="success",
                result_summary=f"HTTP {status_code}",
                log_excerpt=response_body,
            )
        else:
            return ExecutionResult(
                status="failure",
                result_summary=f"HTTP {status_code}",
                log_excerpt=response_body,
            )

    except urllib.error.HTTPError as exc:
        try:
            body_text = truncate(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            body_text = ""
        return ExecutionResult(
            status="failure",
            result_summary=f"HTTP {exc.code}",
            log_excerpt=body_text,
        )
    except urllib.error.URLError as exc:
        return ExecutionResult(
            status="failure",
            result_summary=f"URLError: {exc.reason}",
            log_excerpt=str(exc),
        )
    except Exception as exc:
        return ExecutionResult(
            status="failure",
            result_summary=f"Unexpected error: {exc}",
            log_excerpt=str(exc),
        )
