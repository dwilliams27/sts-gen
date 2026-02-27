#!/bin/bash
set -e

STS_DIR="$HOME/Library/Application Support/Steam/steamapps/common/SlayTheSpire"
MODS_DIR="$STS_DIR/SlayTheSpire.app/Contents/Resources/mods"

# Allow override via argument or find in default build locations
JAR="${1:-}"
if [ -z "$JAR" ]; then
    # Check /tmp build dir first, then local output/
    for candidate in /tmp/necromancer-mod/target/necromancer-0.1.0.jar output/necromancer/target/necromancer-0.1.0.jar; do
        if [ -f "$candidate" ]; then
            JAR="$candidate"
            break
        fi
    done
fi

if [ -z "$JAR" ] || [ ! -f "$JAR" ]; then
    echo "ERROR: JAR not found."
    echo "Usage: $0 [path/to/mod.jar]"
    echo "Or build first with scripts/build_mod.py"
    exit 1
fi

mkdir -p "$MODS_DIR"
cp "$JAR" "$MODS_DIR/"

echo "Installed to: $MODS_DIR/$(basename "$JAR")"
echo ""
echo "Launch: Steam → Slay the Spire → Play → 'Play with Mods'"
echo "Check Necromancer, click Play, start a new run."
