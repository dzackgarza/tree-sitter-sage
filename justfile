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
    @just test-without-sage
    @just refresh-local

# The suite again, in an interpreter with no Sage in it.
#
# The Sage profile runs pytest under Sage, which is what makes the
# runtime claims provable.  This repo also claims the opposite: the
# compiler core and the rule tables carry no Sage import, so an editor or
# language server can lower a file without a Sage installation.  Nothing
# in the profile checks that, and it is not a claim about the tests — it
# is a claim about the package, and it holds only as long as no core
# module grows a Sage import.
#
# Central QC's pytest recipe runs in an ephemeral `uvx` environment,
# which is exactly the interpreter that claim describes.  The Sage-only
# modules skip here by design; that is the point of running it twice.
test-without-sage:
    @just -f ~/ai-review-ci/justfiles/python.just -d . _pytest

# Run CI acceptance QC through the central implementation.
test-ci:
    @just -f ~/ai-review-ci/justfiles/sage.just -d . test-ci

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
