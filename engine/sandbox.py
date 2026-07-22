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


# Wrapper convertido para asyncio: antes, _ipc_call usava um socket bloqueante
# (socket.connect/sendall/recv), o que tornava os stubs gerados em stubs.py
# inúteis para o caso de uso principal de Programmatic Tool Calling —
# `asyncio.gather(*[tool(x) for x in items])` — porque cada chamada
# bloqueava a thread inteira em vez de ceder controlo ao event loop.
# Agora _ipc_call é uma coroutine (asyncio.open_connection), por isso várias
# chamadas dentro de um `asyncio.gather` correm concorrentemente de verdade.
SANDBOX_WRAPPER = """\
import sys, json, time, traceback, asyncio, inspect

_ipc_port = {ipc_port}

async def _ipc_call(name, args_dict):
    reader = writer = None
    for _ in range(10):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", _ipc_port)
            break
        except ConnectionRefusedError:
            await asyncio.sleep(0.1)
    else:
        raise ConnectionRefusedError("IPC server not reachable after 10 retries")
    try:
        payload = json.dumps({{"name": name, "arguments": args_dict}}).encode()
        writer.write(payload)
        await writer.drain()
        data = await reader.read(65536)
        result = json.loads(data.decode())
        if "error" in result:
            raise RuntimeError(result["error"])
        return result.get("result")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

{proxy_defs}

# User workflow
{user_code}

async def _main():
    # globals() em vez de dir(): dentro desta função aninhada, dir() sem
    # argumentos só devolve o escopo LOCAL de _main(), nunca encontraria
    # run_workflow (definido ao nível do módulo). globals() vê sempre o
    # escopo do módulo, independentemente de onde é chamado.
    if "run_workflow" not in globals():
        return None
    fn = globals()["run_workflow"]
    # Aceita tanto `async def run_workflow()` (caminho recomendado, permite
    # await/gather) como `def run_workflow()` síncrono, por compatibilidade
    # com workflows antigos gerados antes desta correção.
    if inspect.iscoroutinefunction(fn):
        return await fn()
    return fn()

# Capture result
_output_buf = []
_tools_result = None
try:
    _tools_result = asyncio.run(_main())
except Exception as _exc:
    _output_buf.append(traceback.format_exc())
finally:
    sys.stdout.write(json.dumps({{"output": "".join(_output_buf), "result": _tools_result}}))
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
    resource.setrlimit não está disponível."""
    import psutil

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


class Sandbox:
    def __init__(self, tool_map: dict[str, dict], timeout: int = 15):
        self._tool_map = tool_map
        self._timeout = timeout

    def _generate_proxy_defs(self) -> str:
        lines = []
        seen = set()
        for tool_key, info in self._tool_map.items():
            name = info.get("name", "unknown")
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

        from .proxy import IPCServer

        ipc_server = IPCServer(caller)
        ipc_server.start()
        ipc_port = ipc_server.port

        tmpdir = Path(tempfile.mkdtemp(prefix="r2mcp_sandbox_"))

        try:
            proxy_defs = self._generate_proxy_defs()
            wrapper_code = SANDBOX_WRAPPER.format(
                ipc_port=ipc_port,
                proxy_defs=proxy_defs,
                user_code=textwrap.dedent(code),
            )

            wrapper_path = tmpdir / "_run.py"
            wrapper_path.write_text(wrapper_code, encoding="utf-8")

            # Ambiente limpo, SEM PYTHONPATH do host: a versão anterior fazia
            # env["PYTHONPATH"] = str(Path.cwd()), que é o cwd do processo do
            # servidor FastAPI. Isso deixava o código gerado pela LLM fazer
            # `import cloud_models` ou `import config` e aceder diretamente
            # a segredos do backend (ex: chaves Supabase/Stripe). A sandbox
            # não precisa de importar nada do projeto principal — só do que
            # está definido no próprio wrapper (json, math, datetime, re,
            # typing, asyncio, mais os proxies das tools).
            env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            }
            if sys.platform == "win32":
                # WinError 10106: o Winsock precisa de SYSTEMROOT para
                # carregar o provedor de serviços (dll de socket). Sem
                # isto, asyncio (importado no wrapper) crasha ao tentar
                # importar _overlapped no processo filho.
                env.setdefault("SYSTEMROOT", os.environ.get("SYSTEMROOT", r"C:\Windows"))

            popen_kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(tmpdir),
                text=True,
            )
            if sys.platform != "win32":
                popen_kwargs["preexec_fn"] = _set_child_resource_limits

            proc = subprocess.Popen(
                [sys.executable, "-I", "-u", str(wrapper_path)],
                **popen_kwargs,
            )

            # No Windows, o resource.setrlimit não existe, por isso
            # monitorizamos a memória do processo filho via psutil numa
            # thread separada. No Linux, o setrlimit via preexec_fn já
            # faz esta proteção ao nível do SO antes de qualquer código
            # correr, por isso não precisamos da thread adicional.
            _mem_killer = None
            if sys.platform == "win32":
                _mem_killer = _start_memory_monitor(proc, 256 * 1024 * 1024)

            try:
                stdout, stderr = proc.communicate(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                return {"error": f"Timeout de {self._timeout}s excedido", "output": "", "result": None}
            finally:
                if _mem_killer is not None:
                    _mem_killer.cancel()

            if proc.returncode != 0:
                return {"error": f"Processo terminou com codigo {proc.returncode}", "output": stderr, "result": None}

            if stdout.strip():
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError:
                    return {"output": stdout.strip(), "result": None}

            return {"output": stderr, "result": None}

        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
            ipc_server.stop()
