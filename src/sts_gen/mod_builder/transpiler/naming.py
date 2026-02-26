"""IR identifier → Java naming conventions.

Converts snake_case IR identifiers into Java class names, STS internal IDs,
image paths, and package names used by the generated mod.
"""

from __future__ import annotations

import re


def to_class_name(ir_id: str) -> str:
    """Convert an IR id to a Java class name.

    ``"fire_slash"`` → ``"FireSlash"``
    ``"my_mod:burning_rage"`` → ``"BurningRage"``
    ``"Strike"`` → ``"Strike"``
    """
    # Strip mod prefix if present (e.g., "my_mod:burning_rage" → "burning_rage")
    _, _, local = ir_id.rpartition(":")
    if not local:
        local = ir_id

    # Split on underscores and non-alphanumeric, capitalise each part
    parts = re.split(r"[_\s\-]+", local)
    return "".join(p.capitalize() for p in parts if p)


def to_sts_id(mod_id: str, ir_id: str) -> str:
    """Convert an IR id to the STS-internal string ID used in save files etc.

    ``("pyromancer", "fire_slash")`` → ``"pyromancer:FireSlash"``
    """
    return f"{_mod_prefix(mod_id)}:{to_class_name(ir_id)}"


def to_card_class_name(ir_id: str) -> str:
    """Card class name — identical to base class name."""
    return to_class_name(ir_id)


def to_power_class_name(ir_id: str) -> str:
    """Power class name — appends 'Power' suffix.

    ``"Burning"`` → ``"BurningPower"``
    ``"BurningPower"`` → ``"BurningPower"``
    """
    # Check if the raw input already ends with "Power" before class-name conversion
    _, _, local = ir_id.rpartition(":")
    if not local:
        local = ir_id
    if local.endswith("Power"):
        local = local[: -len("Power")]
    base = to_class_name(local) if "_" in local or " " in local or "-" in local else (local[0].upper() + local[1:] if local else local)
    return f"{base}Power"


def to_relic_class_name(ir_id: str) -> str:
    """Relic class name — identical to base class name."""
    return to_class_name(ir_id)


def to_potion_class_name(ir_id: str) -> str:
    """Potion class name — identical to base class name."""
    return to_class_name(ir_id)


def to_image_path(mod_id: str, category: str, ir_id: str) -> str:
    """Build a resource path for an image asset.

    ``("pyromancer", "cards", "fire_slash")``
    → ``"pyromancerResources/img/cards/FireSlash.png"``
    """
    prefix = _mod_prefix(mod_id)
    class_name = to_class_name(ir_id)
    return f"{prefix}Resources/img/{category}/{class_name}.png"


def to_package_name(mod_id: str) -> str:
    """Convert a mod_id to a Java package path.

    ``"pyromancer"`` → ``"pyromancer"``
    ``"my_mod:Pyromancer"`` → ``"pyromancer"``
    """
    return _mod_prefix(mod_id).lower()


def to_package_path(mod_id: str) -> str:
    """Full Java package string.

    ``"pyromancer"`` → ``"sts_gen.pyromancer"``
    """
    return f"sts_gen.{to_package_name(mod_id)}"


def _mod_prefix(mod_id: str) -> str:
    """Extract the short mod prefix from a mod_id.

    ``"user:Pyromancer"`` → ``"Pyromancer"``
    ``"pyromancer"`` → ``"pyromancer"``
    """
    # If mod_id has a colon (user:ModName), take the right part
    _, _, local = mod_id.rpartition(":")
    if not local:
        local = mod_id
    # Remove spaces/special chars but keep capitalisation
    return re.sub(r"[^a-zA-Z0-9]", "", local)


def mod_class_name(mod_id: str) -> str:
    """Main mod initializer class name.

    ``"pyromancer"`` → ``"PyromancerMod"``
    """
    prefix = _mod_prefix(mod_id)
    # Capitalise first letter
    prefix = prefix[0].upper() + prefix[1:] if prefix else "Mod"
    if prefix.endswith("Mod"):
        return prefix
    return f"{prefix}Mod"


def character_class_name(mod_id: str) -> str:
    """Character class name.

    ``"pyromancer"`` → ``"Pyromancer"``
    """
    prefix = _mod_prefix(mod_id)
    return prefix[0].upper() + prefix[1:] if prefix else "Character"
