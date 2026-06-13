.PHONY: check lint type test fmt run

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
