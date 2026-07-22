import json
import socket
import threading
from typing import Any, Callable


class IPCError(Exception):
    pass


class IPCClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None

    def connect(self, port: int):
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))
        self._sock.settimeout(30.0)

    def call(self, tool_name: str, args: dict) -> Any:
        if not self._sock:
            raise IPCError("Not connected to IPC server")
        request = json.dumps({"name": tool_name, "arguments": args})
        self._sock.sendall(request.encode())
        response = self._sock.recv(65536)
        result = json.loads(response.decode())
        if "error" in result:
            raise IPCError(result["error"])
        return result.get("result")

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None


class IPCServer:
    def __init__(self, tool_caller: Callable[[str, dict], Any], host: str = "127.0.0.1"):
        self._tool_caller = tool_caller
        self._host = host
        self._port: int = 0
        self._server: socket.socket | None = None
        self._ready = threading.Event()

    @property
    def port(self) -> int:
        return self._port

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.bind((self._host, 0))
        # Backlog subia de 1 para 128: com os stubs agora assíncronos,
        # `asyncio.gather(*[tool(x) for x in items])` pode abrir dezenas de
        # ligações quase simultâneas ao IPC server. Um backlog de 1 deixava
        # a maioria dessas ligações em risco de serem recusadas (ou de ficar
        # a aguardar) exatamente no cenário de paralelismo que esta correção
        # passou a permitir.
        self._server.listen(128)
        self._port = self._server.getsockname()[1]
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self._ready.wait(timeout=5.0)
        if not self._ready.is_set():
            raise IPCError("IPCServer failed to become ready within 5s")

    def _accept_loop(self):
        self._ready.set()
        while self._server:
            try:
                conn, _ = self._server.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except OSError:
                break

    def _handle_client(self, conn: socket.socket):
        try:
            data = conn.recv(65536)
            if not data:
                return
            request = json.loads(data.decode())
            tool_name = request["name"]
            args = request.get("arguments", {})

            result = self._tool_caller(tool_name, args)
            response = json.dumps({"result": result})
            conn.sendall(response.encode())
        except Exception as e:
            try:
                response = json.dumps({"error": str(e)})
                conn.sendall(response.encode())
            except Exception:
                pass
        finally:
            conn.close()

    def stop(self):
        if self._server:
            self._server.close()
            self._server = None