# design/cloud-presence.md

**Status: sketch only — not built, not fully designed.** Captured from a 2026-06-15 discussion about
reliable "text me reminders" delivery. Revisit and decide the open tradeoff before building.

## Problem

A local-only daemon (VISION's model) can't fire reminders while the laptop is asleep/off. For
"reach me anywhere, anytime" delivery (e.g. calendar reminders), something always-on must run off
the device. Tension: SIPA is privacy-first (vault + memory never leave the device).

## Principle: brain local, cloud dumb

The cloud piece holds **no personal data and no intelligence** — a forgetful **outbox with a timer**.
The local daemon does all thinking and hands the cloud only finished, pre-approved reminders + when/
where to send them.

```
LOCAL (brain)                              CLOUD (dumb relay, always-on)
 daemon                    sync (HTTPS)     queue: {id, fire_at(UTC), channel, dest, text}
  ├ calendar MCP (reads)  ───upsert/cancel▶ cron tick → deliver due → Telegram/Twilio → 📱
  ├ reminder planner (cal + memory → text)
  └ pushes scheduled pings ◀──poll on wake── inbound replies queued
```

- **Local:** reminder planner reads calendar + memory/vault, composes the message, picks fire-time,
  pushes pre-rendered pings to the relay (idempotent upsert by id; cancel on change).
- **Cloud relay:** tiny always-on service holding only the queue + delivery creds (bot token /
  Twilio). Fires on its own cron, delivers, deletes after send. No calendar creds, no vault, no
  memory, no LLM. Cheap host (Cloudflare Worker + KV + Cron Trigger, or small Fly.io/VPS).

## Why this bounds the privacy cost

Only the finished reminder text — the same words you'd see anyway — leaves the device. Relay is
forgetful (delete-after-deliver, short retention).

## Resilience win

Daemon pushes the day's pings ahead of time → laptop can die after morning planning and you still get
today's reminders. Decouples *decide* (local, intermittent) from *deliver* (cloud, always-on).

## The open tradeoff (decide before building)

**Freshness.** The relay only knows what the daemon last pushed; a meeting added while the laptop
slept won't be reminded. Options, in increasing data-in-cloud: (a) accept it; (b) give the relay
read-only calendar access; (c) relay polls the calendar itself (becomes a second brain — defeats the
point). This choice is the core discussion when we build it.

## Fits existing seams

- Outbound: reminder-planner capability + sync client → relay's small HTTP API.
- Inbound (replies): another `Source` feeding the event router, drained on next wake.
- Delivery channel (Telegram/Twilio) shared with the general "text me" feature.
