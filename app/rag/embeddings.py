import hashlib
import numpy as np


EMBED_DIM = 1536


def deterministic_embedding(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    seed = int.from_bytes(h[:8], "big")
    rng = np.random.default_rng(seed)
    v = rng.normal(0, 1, EMBED_DIM)
    v = v / np.linalg.norm(v)
    return v.astype(float).tolist()
