# design/web-search.md

The `web` MCP server — gives the bot **current/external information** it otherwise lacks (its
knowledge is training-cutoff + your vault + memory). Unlocks "research a subject and take notes with
sources." Realizes part of VISION §10's daily-log/research flow.

## Shape

A capability server like the others (`servers/web/`), spawned by the host — but **only when
`TAVILY_API_KEY` is set** (cli skips it otherwise, so the bot still runs without web access).

- **`web_search(query, max_results=5)`** → JSON hits `[{title, url, content, score}]` (snippet +
  source). For discovery.
- **`web_fetch(url)`** → JSON `{url, content}` — the full page extracted as markdown (Tavily
  `extract`). For deep reading of a specific page. The model searches → fetches → cites → writes a
  note, all in one turn via the existing tool loop.

## Backend-agnostic (the reusable point)

`backend.py` defines a `WebBackend` protocol (`search` + `fetch`) + `SearchResult` / `FetchResult`
dataclasses — the same swappable-seam pattern as `embedding.Embedder`. Today's impl is `TavilyBackend` (Tavily: purpose-built for agents,
returns clean content + citations, free tier covers personal use, no card). Swapping to SearXNG
(self-hosted OSS) / Brave / Exa later is a one-class change behind the protocol — nothing that
consumes `web_search` changes. Choosing the *capability* (MCP server) over Anthropic's provider-side
`web_search` keeps it provider-agnostic (survives a local model) and reusable, per SIPA's design.

## Key handling

`TAVILY_API_KEY` lives in gitignored `.env` (documented name-only in `.env.example`); the host passes
it to the server's env. Never committed.

## Scope / deferred

- `search_depth="basic"` (1 credit/query). Advanced depth + richer params (topic, time_range) are
  available to expose later.
- A self-hosted SearXNG backend (full OSS, private) is the eventual alternative — `BACKLOG.md`.
