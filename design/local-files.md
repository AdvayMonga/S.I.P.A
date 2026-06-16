# design/local-files.md

Local-file reading + vision — two of the "base toolbox" capabilities (Claude-parity built-in tools).

## `fs` server (read-only, scoped)

`servers/fs/server.py`, spawned **only when `FS_READ_ROOTS` is set** (os.pathsep-separated absolute
dirs). Empty → no filesystem access at all. Tools:

- **`read_file(path)`** → UTF-8 text (truncated at 100k chars).
- **`list_dir(path)`** → JSON `[{name, dir}]`.
- **`read_image(path)`** → an image the model can *see* (FastMCP `Image`).

**Safety:** every path goes through `resolve_within(path, roots)` — it resolves the path (following
symlinks) and requires the result to sit under a configured root, so there's no escaping via `..` or
a symlink. Read-only by design; write/exec is a separate, deliberately-gated capability (sandbox).
"Only what you give it": access is exactly the configured roots, nothing else.

## Vision (host passes image content)

The model "sees" an image when a tool returns image content. The host previously kept only **text**
from tool results; now `host._to_content` converts MCP result content → Anthropic content: a plain
string when it's all text (back-compatible — every existing text tool is unchanged), or a **list of
text/image blocks** when an image is present. `read_image` is the first producer; any future tool
that returns an image (e.g. a screenshot or web-image tool) gets vision for free.

So: `read_image(~/Desktop/shot.png)` → image block → the model describes/reasons over it.

## Adaptive thinking (provider, not a server)

Separately, `config.thinking` (default **on**) makes `AnthropicProvider` pass
`thinking={"type": "adaptive"}` — better reasoning on hard turns. Thinking tokens bill at the output
rate, so it costs a little more when it thinks; `max_tokens` was raised to 16000 for headroom. Toggle
off in config to return to zero-thinking cost.

## Deferred

Filesystem **write/edit** and **code execution** (the powerful, risky tier) are gated behind the
sandbox milestone — see `BACKLOG.md`. Web-image vision (fetch an image by URL) is a small follow-up.
