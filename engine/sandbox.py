import ast
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
from pathlib import Path
from typing import Any, Callable


FORBIDDEN_NAMES = {"exec", "eval", "compile", "__import__", "open", "breakpoint", "input"}
# "asyncio" adicionado: o código do utilizador pode agora legitimamente
# escrever `import asyncio` para usar `asyncio.gather(...)` explicitamente,
# tal como no exemplo de referência da Anthropic para Programmatic Tool
# Calling. Sem isto, validate_code() rejeitava o próprio padrão de
# paralelismo que os stubs async foram desenhados para suportar.
ALLOWED_IMPORTS = {"json", "math", "datetime", "re", "typing", "asyncio"}


SANDBOX_WRAPPER = """\
import sys, json, time, traceback, asyncio, inspect, threading

_ipc_lock = threading.Lock()
_ipc_id = 0

def _ipc_call_sync(name, args_dict):
    global _ipc_id
    with _ipc_lock:
        _ipc_id += 1
        req_id = _ipc_id
        payload = json.dumps({{"type": "call", "id": req_id, "name": name, "arguments": args_dict}})
        sys.stdout.write(payload + "\\n")
        sys.stdout.flush()
        line = sys.stdin.readline()
    if not line:
        raise RuntimeError("IPC: stdin closed unexpectedly")
    response = json.loads(line)
    if "error" in response:
        raise RuntimeError(response["error"])
    return response.get("result")

async def _ipc_call(name, args_dict):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _ipc_call_sync, name, args_dict)

{proxy_defs}

# User workflow
{user_code}

async def _main():
    if "run_workflow" not in globals():
        return None
    fn = globals()["run_workflow"]
    if inspect.iscoroutinefunction(fn):
        return await fn()
    return fn()

_output_buf = []
_tools_result = None
try:
    _tools_result = asyncio.run(_main())
except Exception as _exc:
    _output_buf.append(traceback.format_exc())
finally:
    _final = json.dumps({{"type": "done", "output": "".join(_output_buf), "result": _tools_result}})
    sys.stdout.write(_final + "\\n")
    sys.stdout.flush()
"""


class ValidationError(Exception):
    pass


class ExecutionError(Exception):
    pass


def validate_code(code: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValidationError(f"Erro de sintaxe: {e}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_IMPORTS:
                    raise ValidationError(f"Import nao permitido: {alias.name}")
        if isinstance(node, ast.ImportFrom):
            if node.module not in ALLOWED_IMPORTS:
                raise ValidationError(f"Import nao permitido: {node.module}")
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_NAMES:
                raise ValidationError(f"Chamada nao permitida: {fn.id}()")
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                if fn.attr in FORBIDDEN_NAMES:
                    raise ValidationError(f"Chamada nao permitida: {fn.attr}()")
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id.startswith("__"):
                raise ValidationError("Acesso a dunders nao permitido")

    return code


# Limite de memória virtual do processo filho: 256MB. Sem isto, um workflow
# gerado pela LLM que aloque memória sem controlo (ex: lista que cresce sem
# parar) pode esgotar a RAM do host inteiro antes do timeout disparar — em
# produção (ex: Fly.io com pouca RAM disponível), isso pode arrastar o
# próprio processo do servidor FastAPI com ele via OOM killer do SO.
# preexec_fn corre no processo filho, depois do fork() e antes do exec(),
# por isso só afeta a sandbox — nunca o processo pai (o servidor).
def _set_child_resource_limits():
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    except (ImportError, AttributeError):
        pass


def _start_memory_monitor(proc: subprocess.Popen, limit_bytes: int) -> threading.Timer | None:
    """Monitoriza a memória do processo filho numa thread daemon.
    Mata o processo se exceder o limite. Usado no Windows onde
    resource.setrlimit não está disponível. Se psutil não estiver
    instalado, a monitorização é silenciosamente ignorada."""
    try:
        import psutil
    except ImportError:
        return None

    def _check():
        if proc.poll() is not None:
            return
        try:
            p = psutil.Process(proc.pid)
            mem = p.memory_info().rss
            if mem > limit_bytes:
                proc.kill()
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        # Re-agenda a verificação a cada 500ms enquanto o processo corre
        t = threading.Timer(0.5, _check)
        t.daemon = True
        t.start()

    t = threading.Timer(0.5, _check)
    t.daemon = True
    t.start()
    return t


import sys as _sys


class Sandbox:
    def __init__(self, tool_map: dict[str, dict], timeout: int = 15):
        print("SANDBOX_V2_INIT", file=_sys.stderr, flush=True)
        self._tool_map = tool_map
        self._timeout = timeout

    def _generate_proxy_defs(self) -> str:
        lines = []
        seen = set()
        for tool_key, info in self._tool_map.items():
            name = info.get("name", "unknown")
            # Sanitizar: nomes de ferramentas podem ter /, -, etc. que não
            # são válidos como identificadores Python (ex: get_/api/v1/produtos)
            name = (
                name.replace("/", "_")
                .replace("-", "_")
                .replace(" ", "_")
                .replace(".", "_")
                .replace("{", "_")
                .replace("}", "_")
            )
            if name in seen:
                name = f"{name}_{info.get('_server_id', 'unknown')}"
            seen.add(name)
            # async + await: tem de corresponder ao _ipc_call assíncrono do
            # wrapper. Um proxy síncrono aqui quebraria em runtime assim que
            # o código do utilizador tentasse `await tool(...)`.
            lines.append(f'''
async def {name}(**kwargs):
    return await _ipc_call("{tool_key}", kwargs)
''')
        return "\n".join(lines)

    def execute(self, code: str, caller: Callable) -> dict:
        validate_code(code)

        tmpdir = Path(tempfile.mkdtemp(prefix="r2mcp_sandbox_"))

        try:
            proxy_defs = self._generate_proxy_defs()
            wrapper_code = SANDBOX_WRAPPER.format(
                proxy_defs=proxy_defs,
                user_code=textwrap.dedent(code),
            )

            wrapper_path = tmpdir / "_run.py"
            wrapper_path.write_text(wrapper_code, encoding="utf-8")

            env = os.environ.copy()
            env.update(
                {
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                }
            )
            for k in list(env.keys()):
                if k.startswith(("SUPABASE_", "STRIPE_", "PAYPAL_", "SECRET", "TOKEN", "KEY")):
                    del env[k]

            popen_kwargs = dict(
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(tmpdir),
                text=True,
            )
            if sys.platform != "win32":
                popen_kwargs["preexec_fn"] = _set_child_resource_limits

            proc = subprocess.Popen(
                [sys.executable, "-u", str(wrapper_path)],
                **popen_kwargs,
            )

            _mem_killer = None
            if sys.platform == "win32":
                _mem_killer = _start_memory_monitor(proc, 256 * 1024 * 1024)

            stderr_lines = []

            def _read_stderr():
                for line in iter(proc.stderr.readline, ""):
                    stderr_lines.append(line)

            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            try:
                from .proxy import run_stdio_ipc

                result = run_stdio_ipc(proc, caller)
            finally:
                if _mem_killer is not None:
                    _mem_killer.cancel()

            try:
                proc.wait(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                return {"error": f"Timeout de {self._timeout}s excedido", "output": "", "result": None}

            stderr_output = "".join(stderr_lines)

            if result is None:
                return {"error": "IPC: processo terminou sem resposta", "output": stderr_output, "result": None}

            if proc.returncode != 0:
                result.setdefault("output", "")
                result["output"] += f"\n[stderr]\n{stderr_output}"

            return result

        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
