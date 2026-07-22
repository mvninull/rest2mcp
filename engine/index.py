import hashlib

from rank_bm25 import BM25Okapi
import numpy as np


class ToolIndex:
    def __init__(self):
        from fastembed import TextEmbedding

        self._embedder = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        self.tools: list[dict] = []
        self._embeddings: np.ndarray | None = None
        self._bm25: BM25Okapi | None = None
        self._corpus: list[str] = []
        # assinatura do conjunto de tools atualmente indexado, usada para
        # detetar se um rebuild é realmente necessário (evita recalcular
        # embeddings quando o catálogo não mudou entre pedidos)
        self._signature: str | None = None

    @staticmethod
    def compute_signature(tools: list[dict]) -> str:
        """Hash estável do conjunto de tools (nome+descrição+schema).
        Usado para decidir se o índice já existente pode ser reaproveitado
        em vez de recalcular embeddings a cada pedido."""
        parts = sorted(
            f"{t.get('name', '')}\x1f{t.get('description', '')}\x1f{t.get('input_schema', t.get('parameters', {}))}"
            for t in tools
        )
        return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()

    def rebuild_if_changed(self, tools: list[dict]) -> bool:
        """Reconstrói o índice só se o catálogo mudou desde o último rebuild.
        Devolve True se reconstruiu, False se reaproveitou o índice existente."""
        sig = self.compute_signature(tools)
        if sig == self._signature and self.tools:
            return False
        self.rebuild(tools, _signature=sig)
        return True

    def rebuild(self, tools: list[dict], _signature: str | None = None):
        self.tools = tools
        self._corpus = [self._tool_text(t) for t in tools]
        self._signature = _signature if _signature is not None else self.compute_signature(tools)

        if self._corpus:
            self._embeddings = np.array(list(self._embedder.embed(self._corpus)))
            tokenized = [t.lower().split() for t in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._embeddings = np.array([])
            self._bm25 = None

    def _tool_text(self, tool: dict) -> str:
        name = tool.get("name", "")
        desc = tool.get("description", "")
        input_schema = tool.get("input_schema", tool.get("parameters", {}))
        params = " ".join(input_schema.get("properties", {}).keys()) if isinstance(input_schema, dict) else ""
        # Inclui os nomes dos parâmetros no texto indexado — o paper de
        # discovery semântico usa Tool/Purpose/Capabilities/Parameters como
        # âncoras; nome+descrição sozinhos perdem sinal em tools parecidas
        # (ex: read_file vs write_file vs copy_file).
        return f"Tool: {name}\nPurpose: {desc}\nParameters: {params}"

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.tools:
            return []

        query_emb = np.array(list(self._embedder.query_embed(query)))

        if len(self._embeddings) > 0:
            semantic_scores = np.dot(self._embeddings, query_emb.T).flatten()
        else:
            semantic_scores = np.zeros(len(self.tools))

        if self._bm25:
            tokenized_query = query.lower().split()
            bm25_scores = self._bm25.get_scores(tokenized_query)
            bm25_scores = self._normalize(bm25_scores)
        else:
            bm25_scores = np.zeros(len(self.tools))

        sem_norm = self._normalize(semantic_scores) if semantic_scores.size > 0 else semantic_scores

        hybrid = 0.5 * sem_norm + 0.5 * bm25_scores

        top_indices = np.argsort(hybrid)[-top_k:][::-1]

        # Graceful degradation (paper, secção 6.4): mesmo que nenhuma tool
        # ultrapasse threshold nenhum (query ambígua tipo "como faço um bolo",
        # scores todos a 0), devolvemos sempre o top-k na mesma. A versão
        # anterior filtrava `if hybrid[idx] > 0`, o que podia devolver uma
        # lista vazia — a LLM recebe zero tools mesmo havendo catálogo, e
        # não tem como saber que "não há tool relevante" é diferente de
        # "a pesquisa falhou". O paper recomenda explicitamente nunca deixar
        # o LLM sem contexto mínimo de tools.
        return [self.tools[i] for i in top_indices]

    def _normalize(self, scores: np.ndarray) -> np.ndarray:
        mn, mx = scores.min(), scores.max()
        if mx - mn < 1e-10:
            return np.zeros_like(scores)
        return (scores - mn) / (mx - mn)