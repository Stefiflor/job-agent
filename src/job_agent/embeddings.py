"""Embeddings locales con model2vec: gratis, sin GPU y sin PyTorch.

Detrás de un Protocol para poder cambiar de proveedor (Voyage, OpenAI, sentence-transformers)
sin tocar el resto del código, y para usar uno falso en los tests.
"""

from typing import Protocol

import numpy as np

MODELO_DEFAULT = "minishlab/potion-base-8M"


class Embedder(Protocol):
    nombre: str

    @property
    def dim(self) -> int: ...

    def encode(self, textos: list[str]) -> np.ndarray: ...


class Model2VecEmbedder:
    def __init__(self, modelo: str = MODELO_DEFAULT):
        self.nombre = modelo
        self._modelo = None

    def _cargar(self):
        if self._modelo is None:  # carga perezosa: la primera vez descarga ~30 MB
            from model2vec import StaticModel

            self._modelo = StaticModel.from_pretrained(self.nombre)
        return self._modelo

    @property
    def dim(self) -> int:
        return int(self.encode(["x"]).shape[1])

    def encode(self, textos: list[str]) -> np.ndarray:
        v = np.asarray(self._cargar().encode(textos), dtype=np.float32)
        return normalizar(v)


def normalizar(v: np.ndarray) -> np.ndarray:
    """Vectores de norma 1: así la similitud coseno es un producto punto."""
    normas = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(normas == 0, 1, normas)
