import json
import threading
from typing import Any, Callable


class StdioIPCError(Exception):
    pass


def run_stdio_ipc(proc, caller: Callable[[str, dict], Any]) -> dict | None:
    result = None
    write_lock = threading.Lock()

    def write_response(response: str):
        with write_lock:
            proc.stdin.write(response + "\n")
            proc.stdin.flush()

    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type")

        if msg_type == "call":
            name = msg.get("name", "")
            args = msg.get("arguments", {})
            req_id = msg.get("id", 0)

            try:
                call_result = caller(name, args)
                response = json.dumps({"type": "result", "id": req_id, "result": call_result})
                write_response(response)
            except Exception as e:
                response = json.dumps({"type": "result", "id": req_id, "error": str(e)})
                write_response(response)

        elif msg_type == "done":
            result = {k: v for k, v in msg.items() if k != "type"}
            break

    return result
