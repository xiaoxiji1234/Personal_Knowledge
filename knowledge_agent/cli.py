from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import KnowledgeAgent, query_response_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal knowledge QA agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("path", type=Path)

    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("question")
    query_parser.add_argument("--no-online", action="store_true")

    args = parser.parse_args()
    agent = KnowledgeAgent()
    if args.command == "upload":
        payload = agent.upload_path(args.path)
    else:
        response = agent.query(args.question, use_online_fallback=not args.no_online)
        payload = query_response_to_dict(response)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
