"""Minimal socket client: talk to a running daemon from another terminal or front-end.

Run with `python -m bot.client`. The socket path the desktop app / Telegram client will reuse."""

import asyncio
import sys

from .config import Settings


async def chat(path: str) -> None:
    reader, writer = await asyncio.open_unix_connection(path)
    print(f"connected to {path}. Ctrl-D to exit.")
    try:
        while True:
            try:
                line = await asyncio.to_thread(input, "you> ")
            except EOFError:
                break
            if not line.strip():
                continue
            writer.write((line + "\n").encode())
            await writer.drain()
            reply = await reader.readline()
            if not reply:
                print("daemon closed the connection")
                break
            print(f"sipa> {reply.decode().rstrip()}")
    finally:
        writer.close()


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]  # loaded from env / .env
    try:
        asyncio.run(chat(str(settings.socket_path.resolve())))
    except (ConnectionRefusedError, FileNotFoundError):
        print("no daemon listening — start it with `make run` first", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
