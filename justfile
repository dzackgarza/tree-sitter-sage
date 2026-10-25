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
# The upstream Docker distribution, lifted out of its image onto the
# runner.  Two nearer routes do not work:
#
#   apt   -- Ubuntu carries no `sagemath` package after jammy, and the
#            runner image is noble, so there is no candidate to install.
#   conda -- conda-forge's Sage is a real sage.all but installs exactly one
#            binary, the small argparse CLI from `sage.cli`.  QC drives Sage
#            through the distribution's driver script (`--preparse`,
#            `-python`, `-pip`), and that script is not in the package.
#
# ghcr.io/dzackgarza/sage:develop is the research Sage environment, published
# by the fork from the same `just research-environment-sync` the desk runs. It
# is the Sage this grammar is written against -- upstream's distribution image
# is a different build on Python 3.12, and rejects anything requiring the 3.14
# the fork pins. Every repository writing Sage against that fork pulls this one
# build rather than compiling its own.
#
# SAGE_ROOT is baked in at configure time, so the tree is restored to /sage --
# the path it was configured at -- rather than relocated.

# CI: pull the research Sage environment and export SAGE_BIN.
ci-provision-sage:
    #!/usr/bin/env bash
    set -euo pipefail
    docker create --name sage-env ghcr.io/dzackgarza/sage:develop
    sudo install -d -o "$(id -un)" -g "$(id -gn)" /sage
    docker cp sage-env:/sage/. /sage/
    docker rm sage-env
    sage_bin=/sage/.venv/bin/sage
    # The suite runs under Sage's own interpreter; the image carries the
    # research environment but not a test runner.
    "$sage_bin" -pip install --quiet pytest coverage
    # The checkout under test, over whatever grammar the image carries.
    "$sage_bin" -pip install --quiet --no-deps -e .
    # Installing the distribution is not installing the preparser.
    # `sageparse.preparser` replaces Sage's entrypoints when it is
    # imported, and `sage --preparse` is a fresh process that imports
    # nothing of ours -- so without this, QC preparses this repo's own
    # demo with the preparser this repo replaces, and `2x*y` is a syntax
    # error.  A .pth line is how a package gets imported at interpreter
    # startup; on this developer's machine a sitecustomize does the same
    # job.
    site_packages="$("$sage_bin" -python -c 'import site; print(site.getsitepackages()[0])')"
    printf 'import sageparse.preparser\n' > "$site_packages/sageparse-preparser.pth"
    echo "SAGE_BIN=$sage_bin" >> "${GITHUB_ENV:-/dev/stdout}"
    "$sage_bin" -c "import sys; print('sage', sys.version)"
    "$sage_bin" -python -c "import sage.repl.preparse, sageparse.preparser; assert sage.repl.preparse.preparse is sageparse.preparser.preparse, 'the preparser did not install'"

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
