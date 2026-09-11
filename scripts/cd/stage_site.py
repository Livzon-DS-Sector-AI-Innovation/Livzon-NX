"""Create a candidate site config; do not replace/reload the live site."""
import argparse
from pathlib import Path
import re

STREAM_ROUTE = r"^/api/v1/(agent/(chat/stream|llm/chat/completions)|hr/ai/chat/stream|research/literature/analyze|production/(mc|fa)/(lineage/ai-analysis-stream|chat/send))$"


def api_locations(match: re.Match) -> str:
    indent, body = match.groups()
    stream_body = re.sub(r"\s*proxy_(read_timeout|send_timeout|buffering)\s+[^;]+;", "", body)
    stream = (f"{indent}location ~ {STREAM_ROUTE} {{\n"
              f"{indent}    limit_conn dazah_streams 12;\n"
              f"{indent}    proxy_read_timeout 3600s;\n"
              f"{indent}    proxy_send_timeout 300s;\n"
              f"{indent}    proxy_buffering off;{stream_body}\n{indent}}}\n")
    ordinary = f"{indent}location /api/ {{\n{indent}    include /etc/nginx/dazah-api-guard.conf;{body}}}"
    return stream + ordinary


def mcp_location(match: re.Match) -> str:
    indent, body = match.groups()
    body = re.sub(r"\s*proxy_buffering\s+[^;]+;", "", body)
    return (f"{indent}location /mcp/ {{\n{indent}    limit_conn dazah_mcp 16;\n"
            f"{indent}    proxy_buffering off;{body}}}")


def guarded_config(source: str) -> str:
    if "dazah-server-guard.conf" in source:
        raise ValueError("site is already guarded; inspect before restaging")
    result, servers = re.subn(r"(?m)^(\s*)server\s*\{", r"\1server {\n\1    include /etc/nginx/dazah-server-guard.conf;", source)
    result, api = re.subn(r"(?m)^(\s*)location\s+/api/\s*\{([^{}]*)\}", api_locations, result)
    result = re.sub(r"(?m)^(\s*)location\s+/mcp/\s*\{([^{}]*)\}", mcp_location, result)
    if not servers or not api:
        raise ValueError("unrecognized site layout; do not guess routing")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit("candidate exists; refusing to overwrite")
    args.destination.write_text(guarded_config(args.source.read_text()))
