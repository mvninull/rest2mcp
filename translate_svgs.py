import re
import os
import sys

# All translations: PT -> EN (ordered longest first to avoid partial matches)
TRANSLATIONS = [
    # Long descriptions
    ("Um card @run_tool contém o diagrama do script encadeado: search verifica o produto; se existir, segue à direita em ângulo reto para adicionar, send e atualizar até success; se não existir, segue à esquerda e devolve product out of stock. O resultado sai do run_tool para a LLM, que responde ao utilizador.",
     "A @run_tool card contains the chained script diagram: search checks the product; if it exists, it goes right at a right angle to add, send and update until success; if not, it goes left and returns product out of stock. The result exits run_tool to the LLM, which responds to the user."),
    ("Workflow interno do @run_tool: search, decisão de estoque, adicionar, send, atualizar, e resposta final à LLM",
     "@run_tool internal workflow: search, stock decision, add, send, update, and final response to LLM"),
    ("Um pedido de compra entra em @search_tool, que cruza com os endpoints da Store API e devolve, sem sobreposição de cartões, as ferramentas necessárias com parâmetros prontos.",
     "A purchase request enters @search_tool, which cross-references Store API endpoints and returns the necessary tools with ready parameters."),
    ("Pedido do utilizador processado pela @search_tool que devolve as ferramentas necessárias",
     "User request processed by @search_tool returning necessary tools"),
    ("Login por CLI ou dashboard web gera um token de sessão que vive só em memória, injetado nas chamadas reais da API. A LLM apenas chama tools e recebe dados, nunca vê o token.",
     "CLI or web dashboard login generates a session token that lives only in memory, injected into real API calls. The LLM only calls tools and receives data, never sees the token."),
    ("Código gerado pela IA é executado apenas na infraestrutura do rest2mcp, dentro de um temporary and isolated sandbox, com limites de tempo e memória, minimal access às ferramentas registadas e bloqueio de dangerous operations. No fim, tudo é apagado. Em caso de falha, um erro claro volta para a IA para correção e nova tentativa.",
     "AI-generated code is executed only on rest2mcp infrastructure, inside a temporary and isolated sandbox, with time and memory limits, minimal access to registered tools and blocking of dangerous operations. At the end, everything is deleted. In case of failure, a clear error returns to the AI for correction and retry."),
    # Medium descriptions
    ("Autenticação sem expor credenciais à IA", "Authentication without exposing credentials to AI"),
    ("Execução isolada na infraestrutura do rest2mcp", "Isolated execution on rest2mcp infrastructure"),
    ("não corre na tua máquina nem no teu servidor", "doesn't run on your machine or server"),
    ("Quero comprar um teclado luminoso e envia para minha casa", "I want to buy a glowing keyboard and send it to my house"),
    ("Encontrei o teu teclado luminoso!", "Found your glowing keyboard!"),
    ("Encontrei o teclado luminoso!", "Found the glowing keyboard!"),
    ("Já foi enviado para a tua casa.", "It has been sent to your house."),
    ("sandbox temporário e isolado", "temporary and isolated sandbox"),
    ("Infraestrutura do rest2mcp", "rest2mcp infrastructure"),
    ("credenciais nunca saem daqui", "credentials never leave here"),
    ("produto esgotado no stock", "product out of stock"),
    ("código gerado pela IA", "AI-generated code"),
    ("operações perigosas", "dangerous operations"),
    ("Workflow gerado pela IA", "AI-generated workflow"),
    ("o que a LLM vê", "what the LLM sees"),
    ("run_tool devolve o resultado à LLM", "run_tool returns result to LLM"),
    ("escreve o workflow", "writes the workflow"),
    ("recebe dados (json)", "receives data (json)"),
    ("Camada de execução", "Execution layer"),
    ("sandbox: chamadas internas", "sandbox: internal calls"),
    ("código temporário", "temporary code"),
    ("busca semântica", "semantic search"),
    ("recursos controlados", "controlled resources"),
    ("execução controlada", "controlled execution"),
    ("criar_inventario", "create_inventory"),
    ("chamada à API real", "real API call"),
    ("Token de sessão", "Session token"),
    ("chamada 1", "call 1"),
    ("chamada 2", "call 2"),
    ("retornado + params", "returned + params"),
    ("limite de memória", "memory limit"),
    ("acesso mínimo", "minimal access"),
    ("tools registadas", "registered tools"),
    ("+ funções JSON", "+ JSON functions"),
    ("antes de arrancar", "before starting"),
    ("executado aqui", "executed here"),
    ("limite de tempo", "time limit"),
    ("chama a tool", "calls the tool"),
    ("produto existe?", "product exists?"),
    ("produto esgotado", "product out of stock"),
    ("Loja API", "Store API"),
    ("Quero comprar um teclado luminoso", "I want to buy a glowing keyboard"),
    ("ferramentas selecionadas", "selected tools"),
    ("e envia para minha casa", "and send it to my house"),
    ("workflow encadeado", "chained workflow"),
    ("inventarios", "inventories"),
    ("resultado final", "final result"),
    ("Zona da IA", "AI Zone"),
    ("só em memória", "in memory only"),
    ("decisão de estoque", "stock decision"),
    ("execução terminada", "execution finished"),
    ("tudo é apagado", "everything is deleted"),
    ("adicionar", "add"),
    ("atualizar", "update"),
    ("executar", "execute"),
    ("bloqueadas", "blocked"),
    ("apagar", "delete"),
    ("buscar", "search"),
    ("sucesso", "success"),
    ("listar", "list"),
    ("não", "no"),
    ("enviar", "send"),
    ("dados", "data"),
    ("sim", "yes"),
]

def translate_text(text):
    """Apply all translations to a text string."""
    for pt, en in TRANSLATIONS:
        text = text.replace(pt, en)
    return text

def translate_svg(filepath):
    """Translate all text content in an SVG file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all text content between > and < (inside elements)
    # Also handle <desc> content
    pattern = r'>([^<]+)<'
    
    def replace_match(m):
        text = m.group(1)
        translated = translate_text(text)
        return '>' + translated + '<'
    
    new_content = re.sub(pattern, replace_match, content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

# Process all SVGs
en_dir = os.path.join(os.path.dirname(__file__), 'rest2mcp', 'src', 'assets', 'en')
for fname in os.listdir(en_dir):
    if fname.endswith('.svg'):
        fpath = os.path.join(en_dir, fname)
        changed = translate_svg(fpath)
        print(f"{'CHANGED' if changed else 'no change'}: {fname}")

print("\nDone!")
