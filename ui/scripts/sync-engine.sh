#!/usr/bin/env bash
# Vendor the copilot engine into api/_engine for Vercel deployment.
# SOURCE OF TRUTH is the v2 repo — never edit api/_engine by hand; re-run this
# after engine changes, then commit. (Vercel deploys this repo alone, so the
# engine must travel with it.)
#
# DENYLIST, not allowlist: an allowlist silently omits new modules, and the
# failure only shows up as a 500 in production (docent.py was missed exactly
# that way — copilot.py imported it and every /api/chat request crashed at
# import). Anything the engine adds now travels by default; only the dev-only
# entrypoints below are excluded.
set -euo pipefail

ENGINE="${ENGINE_DIR:-$(cd "$(dirname "$0")/../.." && pwd)/engine}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/api/_engine"

# dev-only: local servers, eval CLI, fixture generator, tests
EXCLUDE="serve_api.py serve2.py serve_apps.py cli.py simulate.py test_validator.py test_connector.py test_connector_planner.py test_track_a.py test_native_action.py test_mapping_explanation.py make_mailbox.py"

# automation/ and apps/ are genuine peer packages (see engine/router.py) —
# both travel whole, not flattened, so their `from . import schema`-style
# relative imports keep working unchanged in api/_engine.
PACKAGES="automation apps"

mkdir -p "$DEST"
rm -f "$DEST"/*.py "$DEST"/*.json
for pkg in $PACKAGES; do rm -rf "$DEST/$pkg"; done
for path in "$ENGINE"/*.py "$ENGINE"/*.json; do
  f="$(basename "$path")"
  case " $EXCLUDE " in *" $f "*) continue ;; esac
  cp "$path" "$DEST/$f"
done
for pkg in $PACKAGES; do
  mkdir -p "$DEST/$pkg"
  cp "$ENGINE/$pkg"/*.py "$DEST/$pkg/"
done

# every vendored module must import with only its siblings present, or the
# omission surfaces as a production 500 instead of a failed sync
( cd "$DEST" && for m in *.py; do
    python3 -c "import importlib.util,sys; sys.path.insert(0,'.'); \
      importlib.import_module('${m%.py}')" \
      || { echo "SYNC FAILED: ${m} cannot import from api/_engine" >&2; exit 1; }
  done
  for pkg in $PACKAGES; do
    for path in "$pkg"/*.py; do
      m="$(basename "$path" .py)"
      [ "$m" = "__init__" ] && continue
      python3 -c "import importlib.util,sys; sys.path.insert(0,'.'); \
        importlib.import_module('$pkg.$m')" \
        || { echo "SYNC FAILED: $pkg/$m.py cannot import from api/_engine" >&2; exit 1; }
    done
  done )

echo "synced from $ENGINE:" && ls "$DEST"
echo "engine commit: $(git -C "$ENGINE" rev-parse --short HEAD)" > "$DEST/ENGINE_VERSION"
cat "$DEST/ENGINE_VERSION"
