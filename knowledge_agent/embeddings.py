from __future__ import annotations

from collections import Counter
import hashlib
import math
import re


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class HashingEmbeddingModel:
    """Small local embedding model for a dependency-light prototype.

    It uses hashed token and bigram features with L2 normalization. This is not
    a replacement for a production embedding model, but it gives deterministic
    semantic-ish retrieval good enough for local development and tests.
    """

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> dict[str, float]:
        features: Counter[int] = Counter()
        tokens = self._tokens(text)
        for token in tokens:
            features[self._bucket("tok:" + token)] += 1.0
        for left, right in zip(tokens, tokens[1:]):
            features[self._bucket("bi:" + left + right)] += 1.5

        norm = math.sqrt(sum(value * value for value in features.values()))
        if norm == 0:
            return {}
        return {str(index): value / norm for index, value in features.items()}

    def similarity(self, left: dict[str, float], right: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        if len(left) > len(right):
            left, right = right, left
        score = sum(value * right.get(index, 0.0) for index, value in left.items())
        return max(0.0, min(1.0, score))

    def _bucket(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(digest, "big") % self.dimensions

    def _tokens(self, text: str) -> list[str]:
        raw_tokens = [match.group(0).lower() for match in TOKEN_RE.finditer(text)]
        joined_cjk = "".join(token for token in raw_tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff")
        char_bigrams = [joined_cjk[index : index + 2] for index in range(max(0, len(joined_cjk) - 1))]
        return raw_tokens + char_bigrams
