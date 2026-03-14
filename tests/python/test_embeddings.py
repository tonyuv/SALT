import pytest
from salt_agent.embeddings import TextEmbedder


@pytest.fixture(scope="module")
def embedder():
    return TextEmbedder()


def test_embed_returns_correct_dimension(embedder):
    vec = embedder.embed("Hello world")
    assert len(vec) == 384


def test_embed_batch(embedder):
    vecs = embedder.embed_batch(["Hello", "World", "Test"])
    assert len(vecs) == 3
    assert all(len(v) == 384 for v in vecs)


def test_similar_texts_have_high_cosine(embedder):
    v1 = embedder.embed("The cat sat on the mat")
    v2 = embedder.embed("A cat was sitting on a mat")
    similarity = sum(a * b for a, b in zip(v1, v2))
    assert similarity > 0.8


def test_dissimilar_texts_have_lower_cosine(embedder):
    v1 = embedder.embed("The cat sat on the mat")
    v2 = embedder.embed("Quarterly financial earnings report for Q3")
    similarity = sum(a * b for a, b in zip(v1, v2))
    assert similarity < 0.5
