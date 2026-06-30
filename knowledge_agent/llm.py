from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Iterator

from .models import RetrievalResult, SearchResult


class LlmProvider:
    """Define the common answer-generation interface used by the agent service."""

    def answer(self, query: str, local_results: list[RetrievalResult], search_results: list[SearchResult]) -> str:
        """Generate a final Markdown answer from local and optional web evidence."""
        raise NotImplementedError

    def stream_answer(
        self,
        query: str,
        local_results: list[RetrievalResult],
        search_results: list[SearchResult],
    ) -> Iterator[str]:
        """Stream answer fragments when the underlying provider supports it."""
        answer = self.answer(query, local_results, search_results)
        if answer:
            yield answer


class ExtractiveLlmProvider(LlmProvider):
    """Deterministic local fallback used when no external LLM is configured."""

    def answer(self, query: str, local_results: list[RetrievalResult], search_results: list[SearchResult]) -> str:
        """Return a concise Markdown answer summarized from retrieved evidence."""
        evidence_points = summarize_local_evidence(query, local_results)
        lines = ["## 回答"]
        if evidence_points:
            lines.append(_answer_from_points(query, evidence_points))
            lines.append("")
            lines.append("## 依据摘要")
            lines.extend(f"- {point}" for point in evidence_points)
        else:
            lines.append("本地知识库没有足够依据回答这个问题。")

        notes: list[str] = []
        if search_results:
            notes.extend(_web_summaries(search_results))
        if not evidence_points:
            notes.append("建议补充相关文档后再提问，或开启联网查证获取外部参考。")
        if notes:
            lines.append("")
            lines.append("## 补充说明")
            lines.extend(f"- {note}" for note in notes)
        return "\n".join(lines)


class HttpJsonLlmProvider(LlmProvider):
    """Adapter for a private LLM gateway.

    The endpoint receives {"query": ..., "contexts": [...]} and should return
    {"answer": "..."}.
    """

    def __init__(self, endpoint: str, api_key: str | None = None, timeout_seconds: float = 20) -> None:
        """Store HTTP gateway configuration for later answer-generation calls."""
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def answer(self, query: str, local_results: list[RetrievalResult], search_results: list[SearchResult]) -> str:
        """Call a private LLM gateway with explicit grounded-summary instructions."""
        contexts = [
            {"type": "local", "source": item.source, "content": item.content, "score": item.score}
            for item in local_results
        ] + [
            {"type": "web", "source": item.url, "content": item.snippet, "title": item.title}
            for item in search_results
        ]
        instructions = (
            "请只基于 contexts 回答 query。先总结知识库内容，再回答用户问题；"
            "不要逐字照搬大段原文，不要编造 contexts 中没有的信息。"
            "请输出 Markdown，固定包含“## 回答”和“## 依据摘要”；"
            "只有在联网内容、依据不足或失败说明存在时才输出“## 补充说明”。"
        )
        payload = json.dumps(
            {"query": query, "contexts": contexts, "instructions": instructions},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=payload, method="POST")
        request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = str(result.get("answer") or "").strip()
        if answer:
            return answer
        return ExtractiveLlmProvider().answer(query, local_results, search_results)


class OpenAICompatibleLlmProvider(LlmProvider):
    """Adapter for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float = 0.2,
        timeout_seconds: float = 20,
    ) -> None:
        """Store OpenAI-compatible API configuration for chat completion calls."""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds

    def answer(self, query: str, local_results: list[RetrievalResult], search_results: list[SearchResult]) -> str:
        """Call the configured chat model and fall back to local summarization on empty output."""
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(query, local_results, search_results)},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = _extract_chat_answer(result)
        if answer:
            return answer
        return ExtractiveLlmProvider().answer(query, local_results, search_results)

    def stream_answer(
        self,
        query: str,
        local_results: list[RetrievalResult],
        search_results: list[SearchResult],
    ) -> Iterator[str]:
        """Stream answer fragments from OpenAI-compatible chat-completions APIs."""
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "stream": True,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(query, local_results, search_results)},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {self.api_key}")

        collected: list[str] = []
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = _extract_chat_delta(chunk)
                if not delta:
                    continue
                collected.append(delta)
                yield delta

        if collected:
            return

        fallback = self.answer(query, local_results, search_results)
        if fallback:
            yield fallback


def _system_prompt() -> str:
    """Return the fixed grounded-answer prompt used for chat-completion models."""
    return (
        "你是个人知识库问答 Agent。你必须只基于提供的本地知识库片段和联网查证片段回答。"
        "先总结知识库内容，再回答用户问题；不要逐字照搬大段原文；不要编造没有依据的信息。"
        "请输出 Markdown，固定包含“## 回答”和“## 依据摘要”。"
        "只有存在联网内容、依据不足或错误说明时，才输出“## 补充说明”。"
        "如果知识库没有足够依据，请直接说明依据不足。"
    )


def _user_prompt(query: str, local_results: list[RetrievalResult], search_results: list[SearchResult]) -> str:
    """Build the user message that carries query and retrieval contexts to the LLM."""
    contexts = [
        {
            "type": "local",
            "source": item.source,
            "score": item.score,
            "content": item.content,
        }
        for item in local_results
    ] + [
        {
            "type": "web",
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet,
            "fetched_at": item.fetched_at,
        }
        for item in search_results
    ]
    return json.dumps({"query": query, "contexts": contexts}, ensure_ascii=False, indent=2)


def _extract_chat_answer(result: dict[str, object]) -> str:
    """Extract assistant content from an OpenAI-compatible chat-completion response."""
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, str):
        return ""
    return content.strip()


def _extract_chat_delta(result: dict[str, object]) -> str:
    """Extract one incremental text delta from an OpenAI-compatible stream chunk."""
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
        return "".join(parts)
    return ""


def summarize_local_evidence(query: str, local_results: list[RetrievalResult], max_points: int = 4) -> list[str]:
    """Extract short, query-relevant, de-duplicated evidence points from local chunks."""
    query_terms = _tokenize(query)
    candidates: list[tuple[float, int, str]] = []
    for result_index, result in enumerate(local_results[:5]):
        for sentence in _split_sentences(result.content):
            compact = _compact_sentence(sentence)
            if not compact:
                continue
            score = _sentence_score(compact, query_terms, result.score)
            candidates.append((score, result_index, compact))
    candidates.sort(key=lambda item: (-item[0], item[1], len(item[2])))

    points: list[str] = []
    seen: set[str] = set()
    for score, _, sentence in candidates:
        normalized = _normalize_for_dedupe(sentence)
        if score <= 0 and points:
            continue
        if not normalized or normalized in seen or _is_near_duplicate(normalized, seen):
            continue
        points.append(_truncate(sentence, 120))
        seen.add(normalized)
        if len(points) >= max_points:
            break
    return points


def _answer_from_points(query: str, points: list[str]) -> str:
    """Compose the concise conclusion section from extracted evidence points."""
    if not points:
        return "本地知识库没有足够依据回答这个问题。"
    lead = points[0].rstrip("。；;，, ")
    return f"根据知识库内容，{lead}。"


def _web_summaries(search_results: list[SearchResult]) -> list[str]:
    """Build short supplemental notes from web search snippets."""
    notes: list[str] = []
    for result in search_results[:3]:
        snippet = _truncate(_compact_sentence(result.snippet), 110)
        if snippet:
            notes.append(f"联网查证补充：{result.title}：{snippet}")
    return notes


def _split_sentences(text: str) -> list[str]:
    """Split Chinese and English prose into sentence-like fragments."""
    fragments: list[str] = []
    for line in text.splitlines():
        cleaned = _clean_markdown_line(line)
        if not cleaned:
            continue
        fragments.extend(part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", cleaned) if part.strip())
    return fragments


def _compact_sentence(sentence: str) -> str:
    """Normalize one candidate sentence and drop fragments that are too small to explain anything."""
    compact = re.sub(r"\s+", " ", sentence).strip(" -—\t\r\n")
    compact = re.sub(r"^(问题要点|回答总结|暴露的信息|核心内容|结论|能力状态|学习来源)[：:]\s*", "", compact)
    if len(compact) < 8:
        return ""
    return compact


def _clean_markdown_line(line: str) -> str:
    """Remove Markdown structure markers so evidence extraction keeps content, not headings."""
    compact = line.strip()
    if not compact:
        return ""
    if re.match(r"^#{1,6}\s+", compact):
        return ""
    compact = re.sub(r"^[-*+]\s+", "", compact)
    compact = re.sub(r"^\d+[.)、]\s+", "", compact)
    compact = re.sub(r"`([^`]+)`", r"\1", compact)
    compact = re.sub(r"\*\*([^*]+)\*\*", r"\1", compact)
    compact = re.sub(r"\*([^*]+)\*", r"\1", compact)
    if re.fullmatch(r"(问题要点|回答总结|暴露的信息|核心内容|结论|能力状态|学习来源)[：:]?", compact):
        return ""
    return compact


def _tokenize(text: str) -> set[str]:
    """Tokenize a mixed Chinese/English query for lightweight relevance scoring."""
    tokens = set(match.group(0).lower() for match in re.finditer(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text))
    cjk = "".join(token for token in tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff")
    tokens.update(cjk[index : index + 2] for index in range(max(0, len(cjk) - 1)))
    return {token for token in tokens if token}


def _sentence_score(sentence: str, query_terms: set[str], retrieval_score: float) -> float:
    """Score a sentence by retrieval rank signal and overlap with query terms."""
    sentence_terms = _tokenize(sentence)
    if not sentence_terms:
        return retrieval_score
    overlap = len(query_terms & sentence_terms)
    overlap_ratio = overlap / max(1, len(query_terms))
    return retrieval_score + overlap_ratio * 0.8


def _normalize_for_dedupe(text: str) -> str:
    """Create a compact key used to remove exact and near duplicate summary points."""
    return re.sub(r"\W+", "", text.lower())


def _is_near_duplicate(candidate: str, existing: set[str]) -> bool:
    """Detect whether a candidate sentence mostly repeats an existing evidence point."""
    candidate_chars = set(candidate)
    if not candidate_chars:
        return False
    for item in existing:
        item_chars = set(item)
        if not item_chars:
            continue
        overlap = len(candidate_chars & item_chars) / max(1, min(len(candidate_chars), len(item_chars)))
        if overlap >= 0.88:
            return True
    return False


def _truncate(text: str, limit: int) -> str:
    """Limit a text fragment while preserving a readable sentence ending."""
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip("，,；; ") + "…"
