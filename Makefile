# ReconStream -- temporal correctness for streaming financial reconciliation.
#
# `make reproduce` is the clean-room path: it fetches P1, brings up the event
# store, runs every experiment, regenerates the figures and builds the paper.

PY      ?= ./.venv/bin/python
PIP     ?= ./.venv/bin/pip
FLINK   := flink:1.20-scala_2.12-java17

.PHONY: help setup data experiments figures paper test lint reproduce clean distclean up down flink-image

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | column -t -s "$$(printf '\t')"

.venv:
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt

setup: .venv vendor/finalitybench ## create the venv and fetch FinalityBench (P1)

vendor/finalitybench:
	@if [ -d ../finalitybench ]; then \
	  echo "using sibling checkout at ../finalitybench"; \
	else \
	  $(PY) -c "import sys; sys.path.insert(0,'src'); from reconstream._p1 import clone_p1; clone_p1()"; \
	fi

up: ## start the PostgreSQL event store
	docker compose up -d
	@for i in $$(seq 1 40); do \
	  docker exec reconstream-eventstore pg_isready -U reconstream -d reconstream >/dev/null 2>&1 && break; \
	  sleep 1; \
	done
	@echo "event store ready on localhost:55432"

down: ## stop the event store
	docker compose down

flink-image: ## pull the pinned Flink image used by E7
	docker pull $(FLINK)

data: setup ## nothing to download -- the workloads are generated
	@echo "workloads are generated from P1 at run time; nothing to fetch"

experiments: setup up ## run E1-E10
	$(PY) experiments/e1_main.py
	$(PY) experiments/e2_frontier.py
	$(PY) experiments/e3_shift.py
	$(PY) experiments/e4_idleness.py
	$(PY) experiments/e5_costs.py
	$(PY) experiments/e6_sql_parity.py
	$(PY) experiments/e8_defects.py
	$(PY) experiments/e9_worked_instance.py
	$(PY) experiments/e7_flink.py
	$(PY) experiments/e10_contention.py

figures: ## regenerate every figure from results/
	$(PY) figures/make_figures.py

paper: figures ## build the PDF
	cd paper && latexmk -pdf -interaction=nonstopmode reconstream.tex

test: setup ## unit tests and sanity checks
	$(PY) -m pytest tests/

reproduce: distclean setup up flink-image experiments figures paper test arxiv verify ## clean-room end to end
	@echo
	@echo "reproduction complete -- results/ figures/ paper/reconstream.pdf"

arxiv: paper ## build the submission tarball and compile it standalone
	$(PY) scripts/make_arxiv.py

verify: ## the gates that must pass before a release
	$(PY) scripts/verify_claims.py
	$(PY) scripts/check_provenance.py
	$(PY) scripts/check_prose_numbers.py

clean:
	rm -rf paper/*.aux paper/*.log paper/*.out paper/*.fls paper/*.fdb_latexmk
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

distclean: clean
	rm -f results/*.json figures/*.pdf paper/reconstream.pdf
