"""REPL front-end: read a line, run a turn, print the reply. No daemon yet."""

import asyncio
from typing import Any

from .config import Settings
from .host import MCPHost
from .loop import run_turn
from .provider import AnthropicProvider


async def _main() -> None:
    settings = Settings()  # type: ignore[call-arg]  # loaded from env / .env
    provider = AnthropicProvider(settings)
    async with MCPHost(str(settings.vault_path)) as host:
        history: list[Any] = []
        print("S.I.P.A. ready. Ctrl-D to exit.")
        while True:
            try:
                user = await asyncio.to_thread(input, "you> ")
            except EOFError:
                print()
                break
            if not user.strip():
                continue
            reply = await run_turn(history, user, provider, host)
            print(f"sipa> {reply}")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
