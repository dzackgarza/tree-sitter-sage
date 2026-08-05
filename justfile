# Gates invoked by the machine-wide ai-review-ci git hooks:
# pre-commit runs `just test-commit`, pre-push runs `just test-push`.

default:
	@just test-commit

# Corpus and compiler proofs against the committed parser.
test-commit:
	tree-sitter test
	sage -python -m pytest -q tests

# A push refreshes every local installation consuming this grammar.
test-push: test-commit refresh-local

# The three live consumers hold copies, not links: the Sage venv and
# the sage-lsp-server venv carry site-packages installs, and the
# JupyterLab overlay (served develop-mode from the research tree)
# fetches the committed wasm by name.
refresh-local:
	sage -pip install --quiet --force-reinstall --no-deps .
	uv pip install -p ~/gitclones/sage-lsp-server/.venv --quiet --force-reinstall --no-deps .
	cp tree-sitter-sage.wasm ~/research/jupyterlab-sage-syntax/static/static/tree-sitter-sage.wasm
