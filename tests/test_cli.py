from __future__ import annotations

from ticktick_mcp.cli import build_parser


def test_serve_defaults_to_streamable_http():
    args = build_parser().parse_args(["serve"])

    assert args.command == "serve"
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000


def test_serve_accepts_sse_network_options():
    args = build_parser().parse_args(
        ["serve", "--transport", "sse", "--host", "0.0.0.0", "--port", "9000"]
    )

    assert args.transport == "sse"
    assert args.host == "0.0.0.0"
    assert args.port == 9000
