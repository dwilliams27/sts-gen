#!/usr/bin/env python3
"""Build a playable STS mod from a ContentSet JSON file.

Usage:
    uv run python scripts/build_mod.py data/runs/20260226_045456/5_content_set.json
    uv run python scripts/build_mod.py data/runs/20260226_045456/5_content_set.json -o output/necromancer

To compile (requires Java 8+ JDK, Maven, and game JARs):
    uv run python scripts/build_mod.py content_set.json \\
        --sts-jar ~/Library/Application\\ Support/Steam/steamapps/common/SlayTheSpire/desktop-1.0.jar \\
        --basemod-jar ~/Library/Application\\ Support/Steam/steamapps/common/SlayTheSpire/mods/BaseMod.jar \\
        --mts-jar ~/Library/Application\\ Support/Steam/steamapps/common/SlayTheSpire/ModTheSpire.jar
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sts_gen.ir.content_set import ContentSet
from sts_gen.mod_builder.builder import ModBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an STS mod from a ContentSet JSON.")
    parser.add_argument("content_set", type=Path, help="Path to ContentSet JSON file")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output directory (default: output/<mod_id>)")
    parser.add_argument("--sts-jar", type=Path, default=None, help="Path to desktop-1.0.jar")
    parser.add_argument("--basemod-jar", type=Path, default=None, help="Path to BaseMod.jar")
    parser.add_argument("--mts-jar", type=Path, default=None, help="Path to ModTheSpire.jar")
    parser.add_argument("--skip-compile", action="store_true", default=False, help="Skip Maven compilation")
    args = parser.parse_args()

    # Load content set
    print(f"Loading {args.content_set}...")
    with open(args.content_set) as f:
        raw = json.load(f)

    cs = ContentSet.model_validate(raw)
    print(f"  mod: {cs.mod_name} ({cs.mod_id})")
    print(f"  {len(cs.cards)} cards, {len(cs.relics)} relics, {len(cs.potions)} potions, {len(cs.status_effects)} statuses")

    # Determine output directory
    output_dir = args.output or Path("output") / cs.mod_id
    print(f"\nBuilding to {output_dir}/...")

    # Build
    builder = ModBuilder(
        cs,
        output_dir,
        sts_jar=args.sts_jar,
        basemod_jar=args.basemod_jar,
        mts_jar=args.mts_jar,
        skip_compile=args.skip_compile or (args.sts_jar is None),
    )

    result = builder.build()

    # Report — count files in the project dir, not the JAR
    project_dir = output_dir
    java_files = list(project_dir.rglob("*.java"))
    res_dir = project_dir / "src" / "main" / "resources"
    json_files = list(res_dir.rglob("*.json")) if res_dir.exists() else []
    png_files = list(project_dir.rglob("*.png"))

    print(f"\nDone! Project at: {project_dir}")
    print(f"  {len(java_files)} Java source files")
    print(f"  {len(json_files)} JSON localization files")
    print(f"  {len(png_files)} PNG image assets")

    if result.suffix == ".jar":
        print(f"\nJAR built: {result}")
        print(f"Copy to your SlayTheSpire/mods/ folder to play!")
    else:
        print(f"\nTo compile manually:")
        print(f"  cd {result}")
        print(f"  mvn package")
        print(f"  cp target/*.jar ~/Library/Application\\ Support/Steam/steamapps/common/SlayTheSpire/mods/")


if __name__ == "__main__":
    main()
