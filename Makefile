VIRTUAL_ENV ?= .venv

# =============
#  Development
# =============

$(VIRTUAL_ENV): poetry.lock
	@poetry install --with dev
	@poetry run pre-commit install --hook-type pre-push
	@touch $(VIRTUAL_ENV)

.PHONY: test
# target: test - Runs tests
t test: $(VIRTUAL_ENV)
	@poetry run pytest tests.py

.PHONY: mypy
# target: mypy - Code checking
mypy: $(VIRTUAL_ENV)
	@poetry run mypy

# ==============
#  Bump version
# ==============

.PHONY: release
VPART?=minor
# target: release - Bump version
release:
	@git checkout develop
	@git pull
	@poetry version $(VPART)
	@git commit -am "Bump version: `poetry version -s`"
	@git tag `poetry version -s`
	@git checkout master
	@git pull
	@git merge develop
	@git checkout develop
	@git push --tags origin develop master

.PHONY: minor
minor: release

.PHONY: patch
patch:
	make release VPART=patch

.PHONY: major
major:
	make release VPART=major
