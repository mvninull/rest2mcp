import httpx
from rich.console import Console

from r2mcp_cli.config import get_base_url, get_token

console = Console()


class APIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class APIClient:
    def __init__(self):
        self.base_url = get_base_url()
        self._client = httpx.Client(timeout=30.0)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        token = get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        resp = self._client.request(method, url, headers=self._headers(), **kwargs)
        if resp.status_code >= 400:
            detail = self._extract_detail(resp)
            raise APIError(resp.status_code, detail)
        return resp

    def _extract_detail(self, resp: httpx.Response) -> str:
        try:
            body = resp.json()
            if isinstance(body, dict):
                return body.get("detail", resp.text)
            return resp.text
        except Exception:
            return resp.text

    def get_me(self) -> dict:
        resp = self._request("GET", "/v1/me")
        return resp.json()

    def list_servers(self) -> list[dict]:
        resp = self._request("GET", "/v1/servers")
        return resp.json()

    def create_server(self, name: str, spec_url: str, transport: str = "sse") -> dict:
        resp = self._request("POST", "/v1/servers", json={"name": name, "spec_url": spec_url, "transport": transport})
        return resp.json()

    def update_server(self, server_id: str, data: dict) -> dict:
        resp = self._request("PATCH", f"/v1/servers/{server_id}", json=data)
        return resp.json()

    def delete_server(self, server_id: str):
        self._request("DELETE", f"/v1/servers/{server_id}")

    def list_tools(self, server_id: str) -> list[dict]:
        resp = self._request("GET", f"/v1/servers/{server_id}/tools")
        data = resp.json()
        return data.get("tools", [])

    def call_tool(self, server_id: str, tool_name: str, arguments: dict) -> dict:
        resp = self._request(
            "POST",
            f"/v1/servers/{server_id}/tools/call",
            json={"name": tool_name, "arguments": arguments},
        )
        return resp.json()

    def get_logs(self, server_id: str, limit: int = 20) -> list[dict]:
        resp = self._request("GET", f"/v1/servers/{server_id}/logs", params={"limit": limit})
        return resp.json()

    def get_auth_status(self, server_id: str) -> dict:
        resp = self._request("GET", f"/v1/servers/{server_id}/auth")
        return resp.json()

    def set_credentials(self, server_id: str, credentials: dict) -> dict:
        resp = self._request("PUT", f"/v1/servers/{server_id}/auth/credentials", json=credentials)
        return resp.json()

    def check_credentials(self, server_id: str) -> dict:
        resp = self._request("GET", f"/v1/servers/{server_id}/auth/credentials")
        return resp.json()

    def delete_credentials(self, server_id: str):
        self._request("DELETE", f"/v1/servers/{server_id}/auth/credentials")

    def close(self):
        self._client.close()
