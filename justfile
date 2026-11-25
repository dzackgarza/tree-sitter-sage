ai_review_ci_schema_version := "1"
ai_review_ci_profile := "sage"
ai_review_ci_ref := "main"
ai_review_ci_release_channel := "main"
ai_review_ci_workflow_template_version := "1"
ai_review_ci_local_delegation := "global-justfile"
ai_review_ci_default_branch := "main"

[doc("List available recipes.")]
default:
    @just --list

[doc("Commit-tier QC: committed parser tables must match a fresh generate,")]
test-commit:
    tree-sitter generate
    if ! git diff --quiet -- src/parser.c src/grammar.json src/node-types.json tree-sitter.json; then echo "ERROR: committed parser is stale; run tree-sitter generate (and build --wasm) and commit." >&2; exit 1; fi
    tree-sitter test
    @just -f ~/ai-review-ci/justfiles/sage.just -d . test-commit

[doc("Push-tier QC, then refresh every local installation consuming this grammar.")]
test-push:
    tree-sitter test
    @just -f ~/ai-review-ci/justfiles/sage.just -d . test-push
    @just refresh-local

[doc("Run CI acceptance QC through the central implementation.")]
test-ci:
    @just -f ~/ai-review-ci/justfiles/sage.just -d . test-ci

[doc("Put a Sage on a bare runner, for the QC workflow's setup_recipe hook.")]
ci-provision-sage:
    #!/usr/bin/env bash
    set -euo pipefail
    docker create --name sage-dist sagemath/sagemath:10.10.beta0
    sudo install -d -o "$(id -un)" -g "$(id -gn)" /home/sage
    docker cp sage-dist:/home/sage/sage /home/sage/sage
    docker rm sage-dist
    sage_bin=/home/sage/sage/sage
    "$sage_bin" -pip install --quiet pytest coverage
    "$sage_bin" -pip install --quiet -e .
    site_packages="$("$sage_bin" -python -c 'import site; print(site.getsitepackages()[0])')"
    printf 'import sageparse.preparser\n' > "$site_packages/sageparse-preparser.pth"
    echo "SAGE_BIN=$sage_bin" >> "${GITHUB_ENV:-/dev/stdout}"
    "$sage_bin" -c "import sys; print('sage', sys.version)"
    "$sage_bin" -python -c "import sage.repl.preparse, sageparse.preparser; assert sage.repl.preparse.preparse is sageparse.preparser.preparse, 'the preparser did not install'"

[doc("Refresh the live consumers.  The Python installs are editable, so their")]
refresh-local:
    sage -pip install --quiet --force-reinstall --no-deps -e .
    uv pip install -p ~/gitclones/sage-lsp-server/.venv --quiet --force-reinstall --no-deps -e .
    cp tree-sitter-sage.wasm ~/research/jupyterlab-sage-syntax/static/static/tree-sitter-sage.wasm
