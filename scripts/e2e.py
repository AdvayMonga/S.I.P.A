"""Live end-to-end smoke test of the daemon over the socket (throwaway vault, real API).
Run: uv run python scripts/e2e.py   — NOT part of `make check` (costs API tokens)."""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from bot.cli import _make_handler, _servers  # noqa: E402
from bot.config import Settings  # noqa: E402
from bot.conversation import Conversation  # noqa: E402
from bot.daemon import ASK_PREFIX, Daemon  # noqa: E402
from bot.host import MCPHost  # noqa: E402
from bot.loop import Approver  # noqa: E402
from bot.provider import make_provider  # noqa: E402
from bot.sources import SocketSource  # noqa: E402
from bot.subagent import BackgroundDelegator  # noqa: E402

KEY = next(
    line.strip().split("=", 1)[1]
    for line in open(".env")
    if line.startswith("ANTHROPIC_API_KEY=")
)
SOCK = "/tmp/sipa_e2e.sock"


async def send(msg: str, answer: str = "n", timeout: float = 150) -> str:
    """Connect, send one message, handle any mid-turn approval question, return the reply."""
    reader, writer = await asyncio.open_unix_connection(SOCK)
    writer.write((msg + "\n").encode())
    await writer.drain()
    while True:
        line = await asyncio.wait_for(reader.readline(), timeout)
        if not line:
            writer.close()
            return "[connection closed]"
        text = line.decode()
        if text.startswith(ASK_PREFIX):
            print(f"   ↪ daemon asked: {text[len(ASK_PREFIX):].strip()}  → answering '{answer}'")
            writer.write((answer + "\n").encode())
            await writer.drain()
            continue
        writer.close()
        return text.strip()


async def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    vault = tmp / "vault"
    vault.mkdir()
    work = tmp / "work"
    work.mkdir()
    (vault / "seed.md").write_text("# Seed\nThrowaway vault for an end-to-end test.\n")
    Path(SOCK).unlink(missing_ok=True)

    settings = Settings(
        anthropic_api_key=KEY,
        vault_path=vault,
        index_path=tmp / "index.db",
        vault_search_db_path=tmp / "vs.db",
        scheduler_state_path=tmp / "sched.json",
        memory_db_path=tmp / "mem.db",
        socket_path=Path(SOCK),
        exec_root=str(work),
        thinking=False,  # cheaper/faster for the smoke test
    )
    provider = make_provider(settings)
    print(f"booting daemon · throwaway vault={vault}")
    async with MCPHost(_servers(settings)) as host:
        convo = Conversation()
        delegator = BackgroundDelegator(provider, host)
        approver = Approver("ask")
        daemon = Daemon(_make_handler(convo, provider, host, delegator, approver))

        async def present_bg(i: int, task: str, result: str) -> None:
            note = f"[background #{i} done: {task}]\n{result}\nTell the user briefly it finished."
            await daemon.submit(note, daemon.notify)

        delegator.set_notify(present_bg)
        runner = asyncio.create_task(daemon.run([SocketSource(SOCK)]))
        await asyncio.sleep(1.0)  # bind + servers embed the seed vault

        print(f"tools available: {sorted(t['name'] for t in host.tools_for_model())}\n")

        print("1) basic turn")
        print(f"   reply: {await send('Reply with exactly: pong')}\n")

        print("2) vault create (real tool → throwaway vault)")
        r = await send("Create a note photosynthesis.md with a one-sentence summary.")
        print(f"   reply: {r}")
        print(f"   vault .md files now: {sorted(p.name for p in vault.glob('*.md'))}\n")

        print("3) memory across messages")
        await send("Remember that my favorite color is teal.")
        print(f"   recall: {await send('What is my favorite color? One word.')}\n")

        print("4) approval-gated shell (answering 'y')")
        print(f"   reply: {await send('Run the shell command: echo approved_works', answer='y')}\n")

        print("5) approval-gated shell (answering 'n' → should be denied)")
        print(f"   reply: {await send('Run the shell command: echo should_not_run', answer='n')}\n")

        print("6) background delegation + proactive push")
        sub_r, sub_w = await asyncio.open_unix_connection(SOCK)
        sub_w.write(b":subscribe\n")
        await sub_w.drain()
        await asyncio.sleep(0.3)
        ack = await send("Use delegate_background to research what an LLM is, then report back.")
        print(f"   ack: {ack}")
        try:
            push = await asyncio.wait_for(sub_r.readline(), 150)
            print(f"   PUSH received: {push.decode().strip()[:160]}\n")
        except TimeoutError:
            print("   (no push within timeout — model may not have backgrounded)\n")
        sub_w.close()

        runner.cancel()
    print("done.")


asyncio.run(main())
