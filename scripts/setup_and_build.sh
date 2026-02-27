#!/bin/bash
set -e

# ── 1. Install JDK 17 + Maven ──────────────────────────────────────────
# STS ships Java 8 — need JDK 17 to cross-compile (JDK 21+ dropped Java 8 target)
brew install openjdk@17 maven

# Make JDK 17 available
sudo ln -sfn "$(brew --prefix openjdk@17)/libexec/openjdk.jdk" /Library/Java/JavaVirtualMachines/openjdk-17.jdk
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"

# Verify it's 17, not 25
java -version
mvn --version

# ── 2. Locate STS game JARs ────────────────────────────────────────────
STS_DIR="$HOME/Library/Application Support/Steam/steamapps/common/SlayTheSpire"

# macOS: the game jar is inside the .app bundle
STS_JAR="$STS_DIR/SlayTheSpire.app/Contents/Resources/desktop-1.0.jar"

# BaseMod and ModTheSpire from Steam Workshop
echo ""
echo "Looking for BaseMod.jar and ModTheSpire.jar..."
BASEMOD_JAR=$(find "$HOME/Library/Application Support/Steam/steamapps" -name "BaseMod.jar" 2>/dev/null | head -1)
MTS_JAR=$(find "$HOME/Library/Application Support/Steam/steamapps" -name "ModTheSpire.jar" 2>/dev/null | head -1)

echo "STS_JAR:     $STS_JAR"
echo "BASEMOD_JAR: $BASEMOD_JAR"
echo "MTS_JAR:     $MTS_JAR"

if [ ! -f "$STS_JAR" ]; then
    echo "ERROR: desktop-1.0.jar not found at $STS_JAR"
    exit 1
fi
if [ -z "$BASEMOD_JAR" ]; then
    echo "ERROR: BaseMod.jar not found. Install BaseMod from Steam Workshop."
    exit 1
fi
if [ -z "$MTS_JAR" ]; then
    echo "ERROR: ModTheSpire.jar not found. Install ModTheSpire from Steam Workshop."
    exit 1
fi

# ── 3. Generate + compile the mod ────────────────────────────────────────
cd "$(dirname "$0")/.."
rm -rf output/necromancer

uv run python scripts/build_mod.py \
    data/runs/20260226_045456/5_content_set.json \
    -o output/necromancer \
    --sts-jar "$STS_JAR" \
    --basemod-jar "$BASEMOD_JAR" \
    --mts-jar "$MTS_JAR"

# ── 4. Install the JAR ─────────────────────────────────────────────────
MODS_DIR="$STS_DIR/SlayTheSpire.app/Contents/Resources/mods"
mkdir -p "$MODS_DIR"
cp output/necromancer/target/*.jar "$MODS_DIR/"

echo ""
echo "Done! JAR installed to: $MODS_DIR/"
ls -la "$MODS_DIR/"*.jar
echo ""
echo "Launch STS via ModTheSpire (Steam → Play → 'Play with Mods')"
echo "Check the Necromancer mod, then start a run."
