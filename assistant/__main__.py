"""Entry point:  python -m assistant        (terminal chat)
                python -m assistant web    (browser chat)"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="assistant", description="A local personal assistant chatbot.")
    parser.add_argument("mode", nargs="?", default="chat", choices=["chat", "web"],
                        help="chat = terminal (default), web = browser")
    parser.add_argument("--port", type=int, default=5000, help="port for web mode (default 5000)")
    args = parser.parse_args()

    if args.mode == "web":
        from .web import run_web
        run_web(args.port)
    else:
        from .cli import run_cli
        run_cli()


if __name__ == "__main__":
    main()
