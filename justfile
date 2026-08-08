# ai-review-ci Python QC delegation justfile.
# The central implementation lives in ~/ai-review-ci/justfiles/python.just.
# Public recipes delegate to that central justfile while preserving this repo as the caller root.

# ai-review-ci contract variables consumed by doctor and workflow installers.
ai_review_ci_schema_version := "1"
ai_review_ci_profile := "python"
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
    @just -f ~/ai-review-ci/justfiles/python.just -d . test-commit

# Push-tier QC, then refresh every local installation consuming this grammar.
test-push:
    tree-sitter test
    @just -f ~/ai-review-ci/justfiles/python.just -d . test-push
    @just test-sage
    @just refresh-local

# The suite again, under Sage's own interpreter.
#
# Central QC runs pytest through `uvx`, an ephemeral environment with no
# Sage in it by construction, so every test asserting that lowered output
# builds a real Sage object skips there and the gate goes green without
# having checked the one thing this package exists to do.  That run still
# earns its place — it is what proves the core imports and lowers without
# Sage, which editors and language servers depend on — but it cannot be
# the only run.  This one has Sage, so nothing skips.
#
# Sage is a hard dependency of this gate.  A missing SAGE_BIN is a broken
# setup and fails here rather than silently reducing what is proved.
test-sage:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "${SAGE_BIN:-}" ] || [ ! -x "${SAGE_BIN:-}" ]; then
        echo "ERROR: SAGE_BIN is unset or not executable (current: '${SAGE_BIN:-<unset>}')." >&2
        echo "       This repo is Sage's preparser; its tests do not mean anything without Sage." >&2
        echo "       FIX: export SAGE_BIN=\"\$(command -v sage)\"" >&2
        exit 1
    fi
    echo "============================="
    echo "=== Running: pytest under Sage ($SAGE_BIN) ==="
    echo "# Proves lowered output builds real Sage objects; nothing skips here."
    "$SAGE_BIN" --python -m pytest tests/ -q --no-header -p no:cacheprovider

# Run CI acceptance QC through the central implementation.
test-ci:
    @just -f ~/ai-review-ci/justfiles/python.just -d . test-ci

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
