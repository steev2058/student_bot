from app.rag.embeddings import deterministic_embedding


def test_deterministic_embedding_shape():
    v = deterministic_embedding("abc")
    assert len(v) == 1536
    assert abs(sum(x*x for x in v) - 1.0) < 1e-6
