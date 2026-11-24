"""Embeddings computed locally: text turned into a vector of 384 numbers for search by meaning.

The `fastembed` library runs the model in ONNX format, without PyTorch, which fits in the VPS memory.
We load the multilingual-e5-small model in the quantized version (int8 weights instead of float32):
on a Mac about 650 MB of process memory instead of 1.9 GB, with practically the same results.
"""

import threading

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

from app.config import settings

# Where fastembed should download files for the model name from .env. Xenova/... is the same model
# intfloat/multilingual-e5-small exported to ONNX and quantized.
_SOURCES: dict[str, tuple[str, str]] = {
    "intfloat/multilingual-e5-small": ("Xenova/multilingual-e5-small", "onnx/model_quantized.onnx"),
}
DIMENSIONS = 384

_model: TextEmbedding | None = None
# Background processing can run in several threads at once; the lock makes sure the model loads once.
_lock = threading.Lock()


def _get_model() -> TextEmbedding:
    global _model
    with _lock:
        if _model is None:
            repo, model_file = _SOURCES[settings.embedding_model]
            if repo not in {m["model"] for m in TextEmbedding.list_supported_models()}:
                TextEmbedding.add_custom_model(
                    model=repo,
                    pooling=PoolingType.MEAN,
                    normalization=True,
                    sources=ModelSource(hf=repo),
                    dim=DIMENSIONS,
                    model_file=model_file,
                )
            # threads=2: the VPS has 2 vCPUs, and another pipeline runs next to it.
            _model = TextEmbedding(repo, cache_dir=settings.embedding_cache_dir, threads=2)
        return _model


def embed_passage(text: str) -> list[float]:
    """Vector for the content being saved. The e5 models need the prefix "passage: " for content
    and "query: " for questions; without them search results are clearly worse."""
    vector = next(iter(_get_model().embed([f"passage: {text}"])))
    return [float(x) for x in vector]


def embed_query(text: str) -> list[float]:
    """Vector for a question during search (the MCP server will use it in step 6)."""
    vector = next(iter(_get_model().embed([f"query: {text}"])))
    return [float(x) for x in vector]


def warm_up() -> None:
    """Loads the model up front (e.g. when building the Docker image, to download the files)."""
    _get_model()
