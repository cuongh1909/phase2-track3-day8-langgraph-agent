.PHONY: install test lint typecheck run-scenarios grade-local clean \
	bonus-mermaid bonus-parallel bonus-time-travel bonus-crash-recovery

install:
	pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

run-scenarios:
	python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json

grade-local:
	python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json

bonus-mermaid:
	python -m langgraph_agent_lab.cli export-mermaid --output outputs/graph.mmd

bonus-parallel:
	python -m langgraph_agent_lab.cli demo-parallel-fanout

bonus-time-travel:
	python -m langgraph_agent_lab.cli demo-time-travel

bonus-crash-recovery:
	python -m langgraph_agent_lab.cli demo-crash-recovery --sqlite-db outputs/crash_recovery_demo.db

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov dist build *.egg-info outputs/*.json outputs/*.db outputs/*.mmd
