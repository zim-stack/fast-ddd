
.PHONY: docs.serve
docs.serve: ## Start docs server
	mkdocs serve

.PHONY: docs.build
docs.build: ## Generate static docs site
	mkdocs build --strict

.PHONY: docs.deploy
docs.deploy: ## Deploy docs to github pages. Builds the site and pushes it to a gh-pages branch
	mkdocs gh-deploy --force

.PHONY: docs.install
docs.install:
	uv pip install --group docs <docs-dependency>
