"""One bounded request per process: profiles and DB snapshots cannot leak across requests."""

import hashlib
import os
import signal
import subprocess
import threading
from pathlib import Path

from ..artifacts import encoded, strict_json
from ..contracts import request_check, validate

MAX_LINE = 65536


class AgentFailure(ValueError):
    def __init__(self, code, diagnostics=None):
        super().__init__(code)
        self.code = code
        self.diagnostics = diagnostics or {}


def terminate(process):
    """Terminate only the process tree started for this request."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def exchange(command, request, *, cwd, timeout, protocol="agent/v1"):
    """Exchange one explicitly selected protocol; never infer it from request fields."""
    if protocol == "agent/v1":
        request_check(request)
    elif protocol == "agent/v2":
        from ..contracts.semalign import request_check as v2_request_check

        v2_request_check(request)
    else:
        raise ValueError("unsupported_agent_protocol")
    data = (encoded(request) + "\n").encode("utf-8")
    if len(data) - 1 > MAX_LINE:
        raise AgentFailure("request_too_large")
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    )
    try:
        process = subprocess.Popen(
            command,
            cwd=Path(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **options,
        )
    except OSError:
        raise AgentFailure("agent_start_failed") from None
    output = bytearray()
    stderr_hash = hashlib.sha256()
    stderr_count = 0
    overflow = threading.Event()

    def read_output():
        while chunk := process.stdout.read(4096):
            room = MAX_LINE + 2 - len(output)
            output.extend(chunk[: max(room, 0)])
            if len(chunk) > room:
                overflow.set()
                # Stop the parent promptly; the main thread owns process-tree termination.
                return

    def read_errors():
        nonlocal stderr_count
        while chunk := process.stderr.read(4096):
            stderr_count += len(chunk)
            stderr_hash.update(chunk)

    def send():
        try:
            process.stdin.write(data)
            process.stdin.close()
        except (OSError, ValueError):
            pass

    threads = [threading.Thread(target=f, daemon=True) for f in (read_output, read_errors, send)]
    for thread in threads:
        thread.start()
    import time

    deadline = time.monotonic() + timeout
    failure = None
    try:
        while process.poll() is None:
            if overflow.is_set():
                failure = "response_too_large"
                break
            if time.monotonic() >= deadline:
                failure = "agent_timeout"
                break
            try:
                process.wait(timeout=min(0.05, max(0.001, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
    finally:
        if process.poll() is None:
            terminate(process)
        for thread in threads:
            thread.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            if not any(t.is_alive() for t in threads):
                stream.close()
    diagnostics = {
        "exit_code": process.returncode,
        "stderr_bytes": stderr_count,
        "stderr_sha256": stderr_hash.hexdigest(),
    }
    if failure or overflow.is_set():
        raise AgentFailure(failure or "response_too_large", diagnostics)
    if any(t.is_alive() for t in threads):
        raise AgentFailure("agent_unclosed_stream", diagnostics)
    try:
        raw = bytes(output)
        # Permit one LF/CRLF or one EOF-terminated record, never extra blank lines.
        if raw.endswith(b"\r\n"):
            raw = raw[:-2]
        elif raw.endswith(b"\n"):
            raw = raw[:-1]
        if not raw or b"\n" in raw or b"\r" in raw or len(raw) > MAX_LINE:
            raise ValueError
        response = strict_json(raw.decode("utf-8"))
        validate(protocol + "/response", response)
        if response["request_id"] != request["request_id"]:
            raise ValueError
        if protocol == "agent/v2":
            from ..contracts.semalign import response_check

            response_check(response, request)
    except (ValueError, UnicodeError, RecursionError):
        raise AgentFailure("invalid_agent_response", diagnostics) from None
    if response["status"] == "error":
        raise AgentFailure(response["error"]["code"], diagnostics)
    if process.returncode != 0:
        raise AgentFailure("agent_exit_failed", diagnostics)
    if (
        protocol == "agent/v1"
        and response["observation"]["reported_values"][0]["period"] != request["period"]
    ):
        raise AgentFailure("response_period_mismatch", diagnostics)
    return response["observation"], diagnostics
