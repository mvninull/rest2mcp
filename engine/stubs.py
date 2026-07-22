import json
from typing import Any


TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def _resolve_ref(ref: str, spec: dict) -> dict:
    parts = ref.lstrip("#/").split("/")
    current = spec
    for p in parts:
        current = current.get(p, {})
    return current


def _json_type_to_python(schema: dict, spec: dict, depth: int = 0) -> str:
    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], spec)
        return _json_type_to_python(resolved, spec, depth)

    schema_type = schema.get("type", "string")

    if schema_type == "array":
        items = schema.get("items", {})
        inner = _json_type_to_python(items, spec, depth)
        return f"list[{inner}]"

    if schema_type == "object":
        if depth > 2:
            return "dict"
        props = schema.get("properties", {})
        if not props:
            return "dict"
        fields = []
        for pname, pschema in props.items():
            ptype = _json_type_to_python(pschema, spec, depth + 1)
            required_list = schema.get("required", [])
            if pname not in required_list:
                ptype = f"Optional[{ptype}]"
            fields.append(f"{pname}: {ptype}")
        return f"dict"  # keep it simple for nested objects

    return TYPE_MAP.get(schema_type, "Any")


def _get_default(schema: dict) -> str | None:
    if "default" in schema:
        val = schema["default"]
        if isinstance(val, str):
            return f'"{val}"'
        return str(val)
    return None


def generate_stub(tool_name: str, input_schema: dict, description: str = "") -> str:
    lines = []
    # async def: as tools reais correm via IPC (rede/processo externo), e o
    # padrão de orquestração que queremos suportar (paralelizar N chamadas
    # com asyncio.gather) só funciona se cada stub for realmente awaitable.
    # Um `def` síncrono aqui bloquearia a sandbox chamada a chamada, mesmo
    # que o LLM escreva `asyncio.gather(*[tool(x) for x in items])`.
    lines.append(f"async def {tool_name}(")

    params = []
    props = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    for pname, pschema in props.items():
        py_type = _json_type_to_python(pschema, input_schema)
        default = _get_default(pschema)
        if pname in required:
            if default:
                params.append(f"    {pname}: {py_type} = {default}")
            else:
                params.append(f"    {pname}: {py_type}")
        else:
            if default:
                params.append(f"    {pname}: {py_type} = {default}")
            else:
                params.append(f"    {pname}: Optional[{py_type}] = None")

    # Bug corrigido: a versão anterior fazia
    #   params.append("    **kwargs") if not params else params
    # o que só adicionava **kwargs quando NÃO havia parâmetros nomeados —
    # quando havia parâmetros, o ramo "else params" era avaliado e descartado
    # (no-op), então **kwargs nunca aparecia junto de parâmetros nomeados.
    params.append("    **kwargs")
    indented_params = ",\n".join(params)
    lines.append(indented_params)
    lines.append(") -> Any:")

    if description:
        desc_clean = description.strip().replace("\n", "\n    ")
        lines.append(f'    """{desc_clean}\n\n    Nota: chamar com `await`. Para correr várias em paralelo,')
        lines.append(f'    usar `await asyncio.gather(*[...])`.')
        lines.append(f'    """')
    else:
        lines.append(f'    """{tool_name} tool. Chamar com `await`."""')

    lines.append("    ...")
    lines.append("")

    return "\n".join(lines)


def generate_stubs_from_tools(tools: list[dict]) -> str:
    result = (
        "# Ferramentas disponiveis para o teu codigo (todas assincronas).\n"
        "# Define `async def run_workflow(): ...` e usa `await`.\n"
        "# Para paralelizar chamadas independentes:\n"
        "#   import asyncio\n"
        "#   resultados = await asyncio.gather(*[tool(x) for x in items])\n\n"
    )
    for tool in tools:
        name = tool.get("name", "unknown")
        desc = tool.get("description", "")
        input_schema = tool.get("input_schema", tool.get("parameters", {}))
        stub = generate_stub(name, input_schema, desc)
        result += stub + "\n"
    return result