from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_agent.service import KnowledgeAgent, query_response_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval hit rate and latency.")
    parser.add_argument("cases", type=Path, help="CSV with query,expected_source")
    parser.add_argument("--online", action="store_true", help="Allow online fallback during evaluation.")
    args = parser.parse_args()

    agent = KnowledgeAgent()
    rows = list(csv.DictReader(args.cases.open(encoding="utf-8")))
    results: list[dict[str, object]] = []
    latencies: list[int] = []
    hits = 0

    for row in rows:
        started = time.perf_counter()
        response = agent.query(row["query"], use_online_fallback=args.online)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        payload = query_response_to_dict(response)
        expected = row.get("expected_source", "")
        hit = any(expected and expected in str(citation.get("title", "")) for citation in payload["citations"])
        hits += int(hit)
        latencies.append(elapsed_ms)
        results.append(
            {
                "query": row["query"],
                "expected_source": expected,
                "hit": hit,
                "confidence": payload["confidence"],
                "usedSearch": payload["usedSearch"],
                "latencyMs": elapsed_ms,
            }
        )

    summary = {
        "cases": len(rows),
        "hitRate": hits / len(rows) if rows else 0,
        "avgLatencyMs": statistics.mean(latencies) if latencies else 0,
        "p95LatencyMs": percentile(latencies, 0.95),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * ratio))
    return ordered[index]


if __name__ == "__main__":
    main()
