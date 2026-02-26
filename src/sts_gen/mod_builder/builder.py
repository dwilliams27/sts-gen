"""ModBuilder — top-level API for IR → playable JAR.

Orchestrates the full pipeline: transpile → localize → generate art →
assemble project → optionally compile with Maven.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from sts_gen.ir.content_set import ContentSet

from .project import ModProject
from .transpiler.naming import to_package_name

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class ModBuilder:
    """Top-level entry point for generating STS mods from IR ContentSets.

    Usage::

        builder = ModBuilder(content_set, Path("output/my_mod"))
        jar_path = builder.build()
    """

    def __init__(
        self,
        content_set: ContentSet,
        output_dir: Path | str,
        *,
        sts_jar: Path | str | None = None,
        basemod_jar: Path | str | None = None,
        mts_jar: Path | str | None = None,
        skip_compile: bool = False,
    ):
        self.content_set = content_set
        self.output_dir = Path(output_dir)
        self.sts_jar = Path(sts_jar) if sts_jar else None
        self.basemod_jar = Path(basemod_jar) if basemod_jar else None
        self.mts_jar = Path(mts_jar) if mts_jar else None
        self.skip_compile = skip_compile

        self._jinja = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            keep_trailing_newline=True,
        )

    def build(self) -> Path:
        """Generate project → optionally compile → return JAR or project path.

        Returns:
            Path to JAR file if compiled, or path to project directory
            if ``skip_compile=True`` or compilation JARs not provided.
        """
        # Step 1: Assemble the project
        project = ModProject(self.content_set, self.output_dir)
        project_dir = project.assemble()

        # Step 2: Generate build files
        self._generate_pom(project_dir)
        self._generate_mts_json(project_dir)

        # Step 3: Optionally compile
        if not self.skip_compile and self._can_compile():
            return self._compile(project_dir)

        return project_dir

    def _generate_pom(self, project_dir: Path) -> None:
        """Generate pom.xml from template."""
        template = self._jinja.get_template("pom.xml.j2")
        pkg = to_package_name(self.content_set.mod_id)

        ctx = {
            "artifact_id": pkg,
            "version": self.content_set.version,
            "mod_name": self.content_set.mod_name,
            "sts_jar": str(self.sts_jar.resolve()) if self.sts_jar else "/path/to/desktop-1.0.jar",
            "basemod_jar": str(self.basemod_jar.resolve()) if self.basemod_jar else "/path/to/BaseMod.jar",
            "mts_jar": str(self.mts_jar.resolve()) if self.mts_jar else "/path/to/ModTheSpire.jar",
        }

        pom = template.render(**ctx)
        (project_dir / "pom.xml").write_text(pom, encoding="utf-8")

    def _generate_mts_json(self, project_dir: Path) -> None:
        """Generate ModTheSpire.json from template."""
        template = self._jinja.get_template("ModTheSpire.json.j2")
        cs = self.content_set

        ctx = {
            "mod_id": cs.mod_id,
            "mod_name": cs.mod_name,
            "author": cs.author,
            "version": cs.version,
            "description": f"A custom STS character: {cs.mod_name}",
        }

        mts_json = template.render(**ctx)

        # Place in resources root so it ends up in the JAR root
        resources_dir = project_dir / "src" / "main" / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        (resources_dir / "ModTheSpire.json").write_text(mts_json, encoding="utf-8")

    def _can_compile(self) -> bool:
        """Check if we have everything needed for compilation."""
        if not self.sts_jar or not self.basemod_jar or not self.mts_jar:
            return False
        if not self.sts_jar.is_file():
            return False
        if not self.basemod_jar.is_file():
            return False
        if not self.mts_jar.is_file():
            return False
        # Check Maven is available
        try:
            subprocess.run(
                ["mvn", "--version"],
                capture_output=True,
                timeout=10,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _compile(self, project_dir: Path) -> Path:
        """Compile the project using Maven. Returns path to JAR."""
        result = subprocess.run(
            ["mvn", "package", "-q"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Maven build failed:\n{result.stdout}\n{result.stderr}"
            )

        # Find the JAR in target/
        target = project_dir / "target"
        jars = list(target.glob("*.jar"))
        if not jars:
            raise RuntimeError("Maven build succeeded but no JAR found in target/")

        return jars[0]
