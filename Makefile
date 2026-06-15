.PHONY: check lint type test fmt run dev

check: lint type test

lint:
	uv run ruff check .

type:
	uv run pyright

test:
	uv run pytest -q

fmt:
	uv run ruff format .

run:
	uv run sipa

dev:
	./scripts/dev.sh
