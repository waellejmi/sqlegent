from dataclasses import dataclass

from config.app_config import AppConfig


@dataclass
class EmbeddingProfile:
    model_name: str

    @property
    def id(self) -> str:
        return f"local:{self.model_name}"


class LocalSentenceTransformerEmbedder:
    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        normalize_embeddings: bool,
        batch_size: int,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "Missing dependency 'sentence-transformers'. Install project dependencies first."
            ) from exc

        init_device = None if device == "auto" else device
        self._model = SentenceTransformer(model_name, device=init_device)
        self._normalize_embeddings = normalize_embeddings
        self._batch_size = batch_size
        self.profile = EmbeddingProfile(model_name=model_name)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=True,
            normalize_embeddings=self._normalize_embeddings,
            convert_to_numpy=True,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            return []
        result = self.embed_texts([text])
        return result[0] if result else []


def build_local_embedder() -> LocalSentenceTransformerEmbedder:
    config = AppConfig()
    return LocalSentenceTransformerEmbedder(
        model_name=config.EMBEDDING_MODEL_NAME,
        device=config.EMBEDDING_DEVICE,
        normalize_embeddings=config.EMBEDDING_NORMALIZE,
        batch_size=config.EMBEDDING_BATCH_SIZE,
    )
