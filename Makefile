.PHONY: docs.install
docs.install: ## Example install docs dependency
	uv add --group docs <dependency>

.PHONY: docs.serve
docs.serve: ## Start docs server
	uv run mkdocs serve

.PHONY: docs.build
docs.build: ## Generate static docs site
	uv run mkdocs build --strict

#.PHONY: docs.deploy
#docs.deploy: ## Deploy docs to github pages. Builds the site and pushes it to a gh-pages branch
#	mkdocs gh-deploy --force

.PHONY: docs.release
docs.release: ## Publish a versioned docs release. Usage: make docs.release VERSION=0.1.0
	uv run mike deploy --push --update-aliases $(VERSION) latest
	uv run mike set-default --push latest

.PHONY: docs.deploy-dev
docs.deploy-dev: ## Publish the current master docs under the dev alias
	uv run mike deploy --push dev

.PHONY: docs.unpublish-all
docs.unpublish-all: ## Removes every published version from the gh-pages branch and push that change, so the live documentation site goes down.
	@read -p "This deletes ALL published docs. Type 'yes' to continue: " ans && [ "$$ans" = "yes" ] && uv run mike delete --all --push || echo "Aborted."

.PHONY: docs.unpublish-version
docs.unpublish-version: ## Removes one published docs version from gh-pages. Usage: make docs.unpublish-version VERSION=0.1.0
	@test -n "$(VERSION)" || (echo "VERSION is required. Usage: make docs.unpublish-version VERSION=0.1.0" && exit 1)
	@read -p "This deletes docs version $(VERSION). Type 'yes' to continue: " ans && [ "$$ans" = "yes" ] && uv run mike delete --push $(VERSION) || echo "Aborted."

.PHONY: docs.list-versions
docs.list-versions:
	uv run mike list
