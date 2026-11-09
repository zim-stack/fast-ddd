.PHONY: docs.install
docs.install: ## Example install docs dependency
	uv add --group docs <dependency>

.PHONY: docs.serve
docs.serve: ## Start docs server
	uv run mkdocs serve

.PHONY: docs.build
docs.build: ## Generate static docs site
	uv run mkdocs build --strict

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
docs.list-versions: ## List all published docs versions on gh-pages
	uv run mike list

.PHONY: docs.pygmentize
docs.pygmentize-css: ## Generate light and dark Pygments CSS for MkDocs Material (uses DARK and LIGHT style names from https://pygments-styles.org)
	uv run pygmentize -S $(DARK) -f html -a '[data-md-color-scheme="slate"] .highlight' > docs/_stylesheets/code-dark.css
	uv run pygmentize -S $(LIGHT) -f html -a '[data-md-color-scheme="default"] .highlight' > docs/_stylesheets/code-light.css
