# ai-review-ci Python QC delegation justfile.
# The central implementation lives in ~/ai-review-ci/justfiles/python.just.
# Public recipes delegate to that central justfile while preserving this repo as the caller root.

# ai-review-ci contract variables consumed by doctor and workflow installers.
ai_review_ci_schema_version := "1"
ai_review_ci_profile := "sage"
ai_review_ci_ref := "main"
ai_review_ci_release_channel := "main"
ai_review_ci_workflow_template_version := "1"
ai_review_ci_local_delegation := "global-justfile"
ai_review_ci_default_branch := "main"

# List available recipes.
default:
    @just --list

# Commit-tier QC: committed parser tables must match a fresh generate,
# then the grammar's corpus/highlight suites, then central Python QC.
test-commit:
    tree-sitter generate
    # Name the generated artifacts, not all of `src`: the compiler sources
    # under `src/sageparse` live there too, and `generate` never writes them.
    if ! git diff --quiet -- src/parser.c src/grammar.json src/node-types.json tree-sitter.json; then echo "ERROR: committed parser is stale; run tree-sitter generate (and build --wasm) and commit." >&2; exit 1; fi
    tree-sitter test
    @just -f ~/ai-review-ci/justfiles/sage.just -d . test-commit

# Push-tier QC, then refresh every local installation consuming this grammar.
test-push:
    tree-sitter test
    @just -f ~/ai-review-ci/justfiles/sage.just -d . test-push
    @just refresh-local

# Run CI acceptance QC through the central implementation.
test-ci:
    @just -f ~/ai-review-ci/justfiles/sage.just -d . test-ci

# Put a Sage on a bare runner, for the QC workflow's setup_recipe hook.
#
# Sage ships no wheel, so this is a package install rather than a pip one,
# and it is slow. That is fine: CI time is not wall-clock anyone waits on,
# and the alternative -- gating a Sage preparser on something that is not
# Sage -- is how this repo already got a suite that passed against
# `sage -python`, an interpreter with no sage.all in it.
ci-provision-sage:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends sagemath
    sage_bin="$(command -v sage)"
    "$sage_bin" --python -m pip install --quiet pytest
    echo "SAGE_BIN=$sage_bin" >> "${GITHUB_ENV:-/dev/stdout}"
    "$sage_bin" -c "import sys; print('sage', sys.version)"

# Refresh the live consumers.  The Python installs are editable, so their
# finder maps `sageparse` straight at src/ and every compiler edit — new
# modules included — is live in the next session with no reinstall.  The
# compiled binding is not: `tree-sitter generate` rewrites src/parser.c,
# and only rebuilding produces a matching _binding.abi3.so.  So this
# recipe exists for the grammar, and running it after a pure compiler
# change is harmless but unnecessary.  The JupyterLab overlay fetches the
# committed wasm by name and needs the copy either way.
refresh-local:
    sage -pip install --quiet --force-reinstall --no-deps -e .
    uv pip install -p ~/gitclones/sage-lsp-server/.venv --quiet --force-reinstall --no-deps -e .
    cp tree-sitter-sage.wasm ~/research/jupyterlab-sage-syntax/static/static/tree-sitter-sage.wasm
