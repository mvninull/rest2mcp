import locale
import os
import sys

_translations = {
    "pt": {
        "app.help": "CLI para gestao de servidores MCP via rest2mcp gateway",
        "app.config_help": "Gerir configuracao local",
        "app.servers_help": "Gerir servidores MCP",
        "app.tools_help": "Interagir com ferramentas MCP",
        "app.link_help": "Ligar servidor a editor IA",
        "app.logs_help": "Ver logs de servidores",

        "field": "Campo",
        "value": "Valor",
        "error": "Erro",
        "token_invalid": "Token invalido",
        "error_connection": "Erro de conexao",
        "not_auth": "Nao autenticado",
        "get_token_at": "Obtem um token em [bold]https://rest2mcp.pages.dev/[/bold] e corre [bold]r2mcp login[/bold]",
        "get_new_token_at": "Obtem um token novo em [bold]https://rest2mcp.pages.dev/[/bold]",

        "auth.login_header": "r2mcp login",
        "auth.login_sub": "Autenticar com o gateway rest2mcp",
        "auth.token_prompt": "Introduz o teu JWT do Supabase\nhttps://rest2mcp.pages.dev/",
        "auth.token_expired": "Token expirado.\nFaz [bold]r2mcp logout[/bold], obtém um novo em\nhttps://rest2mcp.pages.dev/ e faz login novamente.",
        "auth.already_auth": "Ja estas autenticado.\nFaz [bold]r2mcp logout[/bold] primeiro se quiseres mudar de conta.",
        "auth.testing": "A testar conexao...",
        "auth.error_auth": "Erro na autenticacao: {detail}\nObtém um token em https://rest2mcp.pages.dev/",
        "auth.error_connection": "Erro de conexao: {error}\nObtém um token em https://rest2mcp.pages.dev/",
        "auth.success": "Autenticado com sucesso!",
        "auth.not_auth": "Nao estás autenticado.",
        "auth.removed": "Token removido.",

        "me.fetching": "A obter informacoes do utilizador...",
        "me.not_auth": "Nao autenticado.\nCorre [bold]r2mcp login[/bold] primeiro.",
        "me.email": "Email",
        "me.plan": "Plano",
        "me.servers": "Servidores",
        "me.name": "Nome",
        "me.status": "Status",

        "config.title": "Configuracao",
        "config.env": "Ambiente",
        "config.prod": "producao",
        "config.local": "local",
        "config.custom": "custom",
        "config.token_set": "configurado",
        "config.token_none": "nenhum",
        "config.env_help": "Ambiente: local ou prod",
        "config.env_invalid": "Ambiente '{env}' invalido. Usa 'local' ou 'prod'.",
        "config.env_changed": "Ambiente alterado para [bold]{env}[/bold]: {url}",
        "config.base_help": "URL base da API",
        "config.base_changed": "URL base alterada para: [bold]{url}[/bold]",

        "servers.creating": "A criar servidor '{name}'...",
        "servers.spec_invalid": "URL de spec invalida: '{url}'. Deve ser http:// ou https://",
        "servers.using_env": "A usar ambiente {env} ({url})",
        "servers.created": "Servidor criado",
        "servers.name": "Nome",
        "servers.transport": "Transporte",
        "servers.url_mcp": "URL MCP",
        "servers.api_key": "API Key",
        "servers.create_help_name": "Nome do servidor",
        "servers.create_help_spec": "URL do spec OpenAPI",
        "servers.create_help_transport": "Transporte (sse ou http)",
        "servers.listing": "A listar servidores...",
        "servers.count": "{count} servidor(es)",
        "servers.none": "Nenhum servidor encontrado.",
        "servers.delete_confirm": "Tens a certeza que queres apagar o servidor '{id}'?",
        "servers.delete_cancel": "Operacao cancelada.",
        "servers.deleting": "A apagar servidor '{id}'...",
        "servers.deleted": "Servidor '{id}' apagado.",
        "servers.pausing": "A pausar servidor '{id}'...",
        "servers.paused": "Servidor '{id}' pausado.",
        "servers.resuming": "A retomar servidor '{id}'...",
        "servers.resumed": "Servidor '{id}' retomado.",
        "servers.id_help": "ID do servidor",
        "servers.creds_help": "Par chave=valor (ex: -s username=admin -s password=123456)",
        "servers.creds_invalid": "Formato invalido: '{kv}'. Use chave=valor.",
        "servers.creds_saved": "Credenciais salvas para '{id}'.",
        "servers.creds_yes": "Servidor '{id}' tem credenciais configuradas.",
        "servers.creds_no": "Servidor '{id}' nao tem credenciais configuradas.",
        "servers.login_no_auth": "Este servidor nao requer autenticacao.",
        "servers.login_already": "Servidor ja esta autenticado.",
        "servers.login_header": "Login no servidor [cyan]{id}[/cyan]",
        "servers.login_fields": "Campos necessarios: {fields}",
        "servers.login_auth": "Autenticacao",
        "servers.login_ok": "Autenticado com sucesso!",
        "servers.login_unexpected": "Resposta inesperada do servidor.",
        "servers.login_api_down": "API do servidor nao esta acessivel ou recusou o login.\nVerifica se a API esta online.",
        "servers.login_error": "Erro no login: {detail}",

        "tools.listing": "A listar tools do servidor '{id}'...",
        "tools.count": "{count} tool(s)",
        "tools.none": "Nenhuma tool encontrada.",
        "tools.name": "Nome",
        "tools.desc": "Descricao",
        "tools.call_help_name": "Nome da tool",
        "tools.call_help_args": "JSON string de argumentos",
        "tools.call_help_kv": "Argumentos key=value (pode usar multiplas vezes)",
        "tools.calling": "A chamar tool '{name}'...",
        "tools.json_invalid": "JSON invalido em --args: {error}",
        "tools.kv_invalid": "Formato invalido: '{kv}'. Esperado key=value.",
        "tools.call_error": "A tool retornou um erro:",
        "tools.result": "Resultado",
        "tools.result_json": "Resultado (JSON)",
        "tools.list_help": "ID do servidor",

        "link.unsupported": "Editor '{editor}' nao suportado\nOpcoes: [bold]{supported}[/bold]",
        "link.no_path": "Nao foi possivel determinar o caminho de configuracao para '{editor}'.",
        "link.not_found": "Servidor '{id}' nao encontrado.",
        "link.needs_auth": "Servidor precisa de autenticacao.\nFaz o login primeiro com [bold]r2mcp servers login[/bold].",
        "link.connected": "Servidor ligado!",
        "link.editor": "Editor",
        "link.server": "Servidor",
        "link.file": "Ficheiro",
        "link.claude_note": "O Claude Code usa 'mcp-remote' como bridge.\nCertifica-te de que o Node.js esta instalado e disponivel no PATH para correr npx.",
        "link.restart": "Reinicia o {editor} para aplicar as alteracoes.",
        "link.editor_help": "Editor: claude-code, cursor, vscode, opencode",
        "link.server_help": "ID do servidor",

        "logs.fetching": "A obter logs do servidor '{id}'...",
        "logs.none": "Nenhum log encontrado.",
        "logs.count": "{count} log(s)",
        "logs.method": "Metodo",
        "logs.duration": "Duracao (ms)",
        "logs.server_help": "ID do servidor",
        "logs.limit_help": "Numero de logs a mostrar",
    },
    "en": {
        "app.help": "CLI for managing MCP servers via rest2mcp gateway",
        "app.config_help": "Manage local configuration",
        "app.servers_help": "Manage MCP servers",
        "app.tools_help": "Interact with MCP tools",
        "app.link_help": "Link server to AI editor",
        "app.logs_help": "View server logs",

        "field": "Field",
        "value": "Value",
        "error": "Error",
        "token_invalid": "Invalid token",
        "error_connection": "Connection error",
        "not_auth": "Not authenticated",
        "get_token_at": "Get a token at [bold]https://rest2mcp.pages.dev/[/bold] and run [bold]r2mcp login[/bold]",
        "get_new_token_at": "Get a new token at [bold]https://rest2mcp.pages.dev/[/bold]",

        "auth.login_header": "r2mcp login",
        "auth.login_sub": "Authenticate with the rest2mcp gateway",
        "auth.token_prompt": "Enter your Supabase JWT\nhttps://rest2mcp.pages.dev/",
        "auth.token_expired": "Token expired.\nRun [bold]r2mcp logout[/bold], get a new one at\nhttps://rest2mcp.pages.dev/ and login again.",
        "auth.already_auth": "Already authenticated.\nRun [bold]r2mcp logout[/bold] first if you want to switch accounts.",
        "auth.testing": "Testing connection...",
        "auth.error_auth": "Authentication error: {detail}\nGet a token at https://rest2mcp.pages.dev/",
        "auth.error_connection": "Connection error: {error}\nGet a token at https://rest2mcp.pages.dev/",
        "auth.success": "Authenticated successfully!",
        "auth.not_auth": "Not authenticated.",
        "auth.removed": "Token removed.",

        "me.fetching": "Fetching user info...",
        "me.not_auth": "Not authenticated.\nRun [bold]r2mcp login[/bold] first.",
        "me.email": "Email",
        "me.plan": "Plan",
        "me.servers": "Servers",
        "me.name": "Name",
        "me.status": "Status",

        "config.title": "Configuration",
        "config.env": "Environment",
        "config.prod": "production",
        "config.local": "local",
        "config.custom": "custom",
        "config.token_set": "set",
        "config.token_none": "none",
        "config.env_help": "Environment: local or prod",
        "config.env_invalid": "Invalid environment '{env}'. Use 'local' or 'prod'.",
        "config.env_changed": "Environment changed to [bold]{env}[/bold]: {url}",
        "config.base_help": "API base URL",
        "config.base_changed": "Base URL changed to: [bold]{url}[/bold]",

        "servers.creating": "Creating server '{name}'...",
        "servers.spec_invalid": "Invalid spec URL: '{url}'. Must be http:// or https://",
        "servers.using_env": "Using {env} environment ({url})",
        "servers.created": "Server created",
        "servers.name": "Name",
        "servers.transport": "Transport",
        "servers.url_mcp": "MCP URL",
        "servers.api_key": "API Key",
        "servers.create_help_name": "Server name",
        "servers.create_help_spec": "OpenAPI spec URL",
        "servers.create_help_transport": "Transport (sse or http)",
        "servers.listing": "Listing servers...",
        "servers.count": "{count} server(s)",
        "servers.none": "No servers found.",
        "servers.delete_confirm": "Are you sure you want to delete server '{id}'?",
        "servers.delete_cancel": "Operation cancelled.",
        "servers.deleting": "Deleting server '{id}'...",
        "servers.deleted": "Server '{id}' deleted.",
        "servers.pausing": "Pausing server '{id}'...",
        "servers.paused": "Server '{id}' paused.",
        "servers.resuming": "Resuming server '{id}'...",
        "servers.resumed": "Server '{id}' resumed.",
        "servers.id_help": "Server ID",
        "servers.creds_help": "Key=value pair (e.g. -s username=admin -s password=123456)",
        "servers.creds_invalid": "Invalid format: '{kv}'. Use key=value.",
        "servers.creds_saved": "Credentials saved for '{id}'.",
        "servers.creds_yes": "Server '{id}' has credentials configured.",
        "servers.creds_no": "Server '{id}' has no credentials configured.",
        "servers.login_no_auth": "This server does not require authentication.",
        "servers.login_already": "Server is already authenticated.",
        "servers.login_header": "Login to server [cyan]{id}[/cyan]",
        "servers.login_fields": "Required fields: {fields}",
        "servers.login_auth": "Authentication",
        "servers.login_ok": "Authenticated successfully!",
        "servers.login_unexpected": "Unexpected server response.",
        "servers.login_api_down": "Server API is unreachable or refused login.\nVerify the API is online.",
        "servers.login_error": "Login error: {detail}",

        "tools.listing": "Listing tools for server '{id}'...",
        "tools.count": "{count} tool(s)",
        "tools.none": "No tools found.",
        "tools.name": "Name",
        "tools.desc": "Description",
        "tools.call_help_name": "Tool name",
        "tools.call_help_args": "JSON arguments string",
        "tools.call_help_kv": "Key=value arguments (can be used multiple times)",
        "tools.calling": "Calling tool '{name}'...",
        "tools.json_invalid": "Invalid JSON in --args: {error}",
        "tools.kv_invalid": "Invalid format: '{kv}'. Expected key=value.",
        "tools.call_error": "The tool returned an error:",
        "tools.result": "Result",
        "tools.result_json": "Result (JSON)",
        "tools.list_help": "Server ID",

        "link.unsupported": "Editor '{editor}' not supported\nOptions: [bold]{supported}[/bold]",
        "link.no_path": "Could not determine config path for '{editor}'.",
        "link.not_found": "Server '{id}' not found.",
        "link.needs_auth": "Server requires authentication.\nLogin first with [bold]r2mcp servers login[/bold].",
        "link.connected": "Server linked!",
        "link.editor": "Editor",
        "link.server": "Server",
        "link.file": "File",
        "link.claude_note": "Claude Code uses 'mcp-remote' as a bridge.\nEnsure Node.js is installed and available in PATH to run npx.",
        "link.restart": "Restart {editor} to apply changes.",
        "link.editor_help": "Editor: claude-code, cursor, vscode, opencode",
        "link.server_help": "Server ID",

        "logs.fetching": "Fetching logs for server '{id}'...",
        "logs.none": "No logs found.",
        "logs.count": "{count} log(s)",
        "logs.method": "Method",
        "logs.duration": "Duration (ms)",
        "logs.server_help": "Server ID",
        "logs.limit_help": "Number of logs to show",
    },
}


def _detect_lang() -> str:
    env = os.environ.get("R2MCP_LANG", "").strip().lower()
    if env in ("pt", "en"):
        return env

    if sys.platform == "win32":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if lang_id & 0xFF == 0x16:
                return "pt"
            return "en"
        except Exception:
            pass
    else:
        try:
            system_locale = locale.getdefaultlocale()[0] or ""
            if system_locale.startswith("pt"):
                return "pt"
        except Exception:
            pass
    return "en"


_lang = _detect_lang()


def t(key: str, **kwargs) -> str:
    msg = _translations.get(_lang, _translations["en"]).get(key, key)
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, IndexError):
            return msg
    return msg
