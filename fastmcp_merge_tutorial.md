# Tutorial: Merge de Servidores MCP — 1 Remoto + 2 Internos com Namespace

---

## 🧰 Ferramentas que Vamos Usar

### 1. `FastMCP` — O servidor em si

```python
from fastmcp import FastMCP
server = FastMCP("Nome do Servidor")
```

Cria um servidor MCP. Cada servidor pode ter as suas próprias tools, resources e prompts.

---

### 2. `@server.tool` — Decorator para criar ferramentas

```python
@server.tool
def minha_ferramenta(param: str) -> str:
    return f"Resultado: {param}"
```

Registra uma função como uma ferramenta (tool) acessível pelo LLM.

---

### 3. `Client` — Para conectar a servidores remotos

```python
from fastmcp import Client

async with Client("http://localhost:8001/mcp") as client:
    await client.ping()
```

Usado para testar se o servidor remoto está vivo **antes** de fazer o merge.

---

### 4. `FastMCP.as_proxy()` — Cria um proxy de servidor remoto

```python
proxy = FastMCP.as_proxy(Client("http://localhost:8001/mcp"))
```

Transforma a conexão com um servidor remoto num objeto `FastMCP` local, que pode ser passado ao `mount()`.

---

### 5. `server.mount()` — Faz o merge

```python
main.mount(outro_servidor, namespace="weather")
```

Monta as tools de outro servidor no servidor principal. O `namespace` é definido **uma vez** e aplica-se automaticamente a **todas** as ferramentas do servidor montado.

---

## 📐 Arquitectura do Exemplo

```
┌─────────────────────────────────────────────────┐
│           MAIN SERVER (servidor principal)       │
│                                                  │
│  [weather_*]  ←── Servidor Interno 1 (weather)  │
│  [utils_*]    ←── Servidor Interno 2 (utils)    │
│  [news_*]     ←── Servidor REMOTO (news API)    │
└─────────────────────────────────────────────────┘
```

---

## 📝 Código Passo a Passo

### Passo 1 — Criar os dois servidores internos

```python
from fastmcp import FastMCP

# ── Servidor interno 1: Weather ──────────────────────────
weather_server = FastMCP("Weather Server")

@weather_server.tool
def get_weather(city: str) -> str:
    """Retorna o tempo actual de uma cidade"""
    return f"Tempo em {city}: 25°C, Ensolarado"

@weather_server.tool
def get_forecast(city: str, days: int) -> str:
    """Retorna a previsão para os próximos dias"""
    return f"Previsão de {days} dias para {city}: Estável"


# ── Servidor interno 2: Utils ─────────────────────────────
utils_server = FastMCP("Utils Server")

@utils_server.tool
def celsius_to_fahrenheit(celsius: float) -> float:
    """Converte Celsius para Fahrenheit"""
    return (celsius * 9 / 5) + 32

@utils_server.tool
def word_count(text: str) -> int:
    """Conta as palavras num texto"""
    return len(text.split())
```

---

### Passo 2 — Testar a conexão com o servidor remoto

Antes de fazer o `mount()`, testamos sempre a conexão:

```python
import asyncio
import logging
from fastmcp import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_remote_connection(url: str) -> bool:
    """
    Testa se o servidor remoto está disponível.
    Retorna True se OK, False se falhou.
    """
    try:
        logger.info(f"🔍 A testar conexão com: {url}")

        async with Client(url) as client:
            alive = await client.ping()

            if not alive:
                logger.error("❌ Ping falhou")
                return False

            tools = await client.list_tools()
            logger.info(f"✅ Conexão OK — {len(tools)} ferramentas encontradas")
            for tool in tools:
                logger.info(f"   - {tool.name}")

            return True

    except Exception as e:
        logger.error(f"❌ Erro na conexão: {e}")
        return False
```

---

### Passo 3 — Construir o servidor principal com mount()

```python
async def build_main_server() -> FastMCP:
    """
    Constrói o servidor principal fazendo merge de:
    - 2 servidores internos (weather, utils)
    - 1 servidor remoto (news), apenas se a conexão for OK
    """

    main = FastMCP(
        name="Main Merged Server",
        instructions="Servidor principal que agrega weather, utils e news."
    )

    # ── MOUNT dos servidores INTERNOS ─────────────────────
    # Não precisam de teste de conexão — estão no mesmo processo

    logger.info("🔗 A montar servidor interno: weather")
    main.mount(weather_server, namespace="weather")
    # Ferramentas disponíveis: weather_get_weather, weather_get_forecast

    logger.info("🔗 A montar servidor interno: utils")
    main.mount(utils_server, namespace="utils")
    # Ferramentas disponíveis: utils_celsius_to_fahrenheit, utils_word_count


    # ── MOUNT do servidor REMOTO ──────────────────────────
    # Primeiro testa a conexão, só depois faz o mount

    REMOTE_URL = "http://localhost:8003/mcp"

    logger.info(f"\n📡 A verificar servidor remoto: {REMOTE_URL}")
    connection_ok = await test_remote_connection(REMOTE_URL)

    if connection_ok:
        # Cria o proxy do servidor remoto e monta
        remote_client = Client(REMOTE_URL)
        news_proxy = FastMCP.as_proxy(remote_client, name="News Proxy")

        main.mount(news_proxy, namespace="news")
        logger.info("✅ Servidor remoto montado com namespace 'news'")
        # Ferramentas disponíveis: news_get_headlines, news_search, etc.
    else:
        logger.warning("⚠️  Servidor remoto não disponível — ignorado no merge")

    return main
```

---

### Passo 4 — Ver todas as ferramentas resultantes

```python
async def show_merged_tools(main: FastMCP):
    """Lista todas as ferramentas disponíveis no servidor merged"""

    tools = await main.list_tools()

    print(f"\n📋 Total de ferramentas no servidor merged: {len(tools)}\n")

    namespaces = {}
    for tool in tools:
        ns = tool.name.split("_")[0] if "_" in tool.name else "local"
        namespaces.setdefault(ns, []).append(tool.name)

    for ns, names in sorted(namespaces.items()):
        print(f"  [{ns.upper()}]")
        for name in names:
            print(f"    - {name}")
```

---

### Passo 5 — Ponto de entrada completo

```python
async def main():
    server = await build_main_server()
    await show_merged_tools(server)

    # Para correr como servidor HTTP:
    # await server.run_http_async(host="0.0.0.0", port=9000)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🖥️ Output Esperado

```
INFO  🔗 A montar servidor interno: weather
INFO  🔗 A montar servidor interno: utils
INFO  📡 A verificar servidor remoto: http://localhost:8003/mcp
INFO  🔍 A testar conexão com: http://localhost:8003/mcp
INFO  ✅ Conexão OK — 2 ferramentas encontradas
INFO     - get_headlines
INFO     - search_news
INFO  ✅ Servidor remoto montado com namespace 'news'

📋 Total de ferramentas no servidor merged: 6

  [NEWS]
    - news_get_headlines
    - news_search_news
  [UTILS]
    - utils_celsius_to_fahrenheit
    - utils_word_count
  [WEATHER]
    - weather_get_forecast
    - weather_get_weather
```

---

## 📌 Resumo dos Conceitos

| O quê | Como | Porquê |
|---|---|---|
| Servidores internos | `mount(server, namespace="x")` | Não precisam de teste — estão no mesmo processo |
| Servidor remoto | Testa com `Client.ping()` primeiro | Pode estar offline |
| Proxy remoto | `FastMCP.as_proxy(Client(url))` | Transforma conexão remota em objecto local para o `mount()` |
| Namespace | Definido **uma vez** no `mount()` | Aplica-se automaticamente a **todas** as tools do servidor |
