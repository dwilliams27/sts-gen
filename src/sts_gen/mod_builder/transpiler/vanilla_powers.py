"""Mapping of vanilla status effect names to their fully-qualified STS Power classes.

When the IR references a vanilla status like "Vulnerable", the transpiler needs
to know the exact Java class to instantiate.  This module provides that mapping.
"""

from __future__ import annotations

# Vanilla status name → fully qualified Java Power class
VANILLA_POWER_MAP: dict[str, str] = {
    # Debuffs
    "Vulnerable": "com.megacrit.cardcrawl.powers.VulnerablePower",
    "Weak": "com.megacrit.cardcrawl.powers.WeakPower",
    "Frail": "com.megacrit.cardcrawl.powers.FrailPower",
    "Poison": "com.megacrit.cardcrawl.powers.PoisonPower",
    "Constricted": "com.megacrit.cardcrawl.powers.ConstrictedPower",
    "Entangled": "com.megacrit.cardcrawl.powers.EntanglePower",
    "No Draw": "com.megacrit.cardcrawl.powers.NoDrawPower",
    "Choked": "com.megacrit.cardcrawl.powers.ChokePower",
    "Bias": "com.megacrit.cardcrawl.powers.BiasPower",
    "Hex": "com.megacrit.cardcrawl.powers.HexPower",
    "Lock-On": "com.megacrit.cardcrawl.powers.LockOnPower",
    "Draw Reduction": "com.megacrit.cardcrawl.powers.DrawReductionPower",
    # Buffs
    "Strength": "com.megacrit.cardcrawl.powers.StrengthPower",
    "Dexterity": "com.megacrit.cardcrawl.powers.DexterityPower",
    "Artifact": "com.megacrit.cardcrawl.powers.ArtifactPower",
    "Thorns": "com.megacrit.cardcrawl.powers.ThornsPower",
    "Plated Armor": "com.megacrit.cardcrawl.powers.PlatedArmorPower",
    "Metallicize": "com.megacrit.cardcrawl.powers.MetallicizePower",
    "Ritual": "com.megacrit.cardcrawl.powers.RitualPower",
    "Rage": "com.megacrit.cardcrawl.powers.RagePower",
    "Barricade": "com.megacrit.cardcrawl.powers.BarricadePower",
    "Blur": "com.megacrit.cardcrawl.powers.BlurPower",
    "Buffer": "com.megacrit.cardcrawl.powers.BufferPower",
    "Burst": "com.megacrit.cardcrawl.powers.BurstPower",
    "Dark Embrace": "com.megacrit.cardcrawl.powers.DarkEmbracePower",
    "Demon Form": "com.megacrit.cardcrawl.powers.DemonFormPower",
    "Double Tap": "com.megacrit.cardcrawl.powers.DoubleTapPower",
    "Evolve": "com.megacrit.cardcrawl.powers.EvolvePower",
    "Feel No Pain": "com.megacrit.cardcrawl.powers.FeelNoPainPower",
    "Fire Breathing": "com.megacrit.cardcrawl.powers.FireBreathingPower",
    "Flame Barrier": "com.megacrit.cardcrawl.powers.FlameBarrierPower",
    "Juggernaut": "com.megacrit.cardcrawl.powers.JuggernautPower",
    "Combust": "com.megacrit.cardcrawl.powers.CombustPower",
    "Corruption": "com.megacrit.cardcrawl.powers.CorruptionPower",
    "Brutality": "com.megacrit.cardcrawl.powers.BrutalityPower",
    "Regeneration": "com.megacrit.cardcrawl.powers.RegenPower",
    "Intangible": "com.megacrit.cardcrawl.powers.IntangiblePlayerPower",
    "Noxious Fumes": "com.megacrit.cardcrawl.powers.NoxiousFumesPower",
    "After Image": "com.megacrit.cardcrawl.powers.AfterImagePower",
    "Envenom": "com.megacrit.cardcrawl.powers.EnvenomPower",
    "Accuracy": "com.megacrit.cardcrawl.powers.AccuracyPower",
    "Vigor": "com.megacrit.cardcrawl.powers.VigorPower",
    "Pen Nib": "com.megacrit.cardcrawl.powers.PenNibPower",
    "Sadistic": "com.megacrit.cardcrawl.powers.SadisticPower",
    "Wraith Form": "com.megacrit.cardcrawl.powers.WraithFormPower",
    "Echo Form": "com.megacrit.cardcrawl.powers.EchoFormPower",
    "Panache": "com.megacrit.cardcrawl.powers.PanachePower",
    "Phantasmal": "com.megacrit.cardcrawl.powers.DoubleDamagePower",
}

# Vanilla status name → STS Power ID string (used in hasPower() checks)
VANILLA_POWER_ID_MAP: dict[str, str] = {
    "Vulnerable": "Vulnerable",
    "Weak": "Weakened",
    "Frail": "Frail",
    "Poison": "Poison",
    "Constricted": "Constricted",
    "Entangled": "Entangle",
    "No Draw": "No Draw",
    "Choked": "Choke",
    "Bias": "Bias",
    "Hex": "Hex",
    "Lock-On": "Lock-On",
    "Draw Reduction": "Draw Reduction",
    "Strength": "Strength",
    "Dexterity": "Dexterity",
    "Artifact": "Artifact",
    "Thorns": "Thorns",
    "Plated Armor": "Plated Armor",
    "Metallicize": "Metallicize",
    "Ritual": "Ritual",
    "Rage": "Rage",
    "Barricade": "Barricade",
    "Blur": "Blur",
    "Buffer": "Buffer",
    "Burst": "Burst",
    "Dark Embrace": "Dark Embrace",
    "Demon Form": "Demon Form",
    "Double Tap": "Double Tap",
    "Evolve": "Evolve",
    "Feel No Pain": "Feel No Pain",
    "Fire Breathing": "Fire Breathing",
    "Flame Barrier": "Flame Barrier",
    "Juggernaut": "Juggernaut",
    "Combust": "Combust",
    "Corruption": "Corruption",
    "Brutality": "Brutality",
    "Regeneration": "Regeneration",
    "Intangible": "IntangiblePlayer",
    "Noxious Fumes": "Noxious Fumes",
    "After Image": "After Image",
    "Envenom": "Envenom",
    "Accuracy": "Accuracy",
    "Vigor": "Vigor",
    "Pen Nib": "Pen Nib",
    "Sadistic": "Sadistic",
    "Wraith Form": "Wraith Form",
    "Echo Form": "Echo Form",
    "Panache": "Panache",
    "Phantasmal": "DoubleDamage",
}


def get_vanilla_power_class(status_name: str) -> str | None:
    """Return the fully-qualified Java class for a vanilla status, or None."""
    return VANILLA_POWER_MAP.get(status_name)


def get_vanilla_power_id(status_name: str) -> str | None:
    """Return the STS Power ID string for a vanilla status, or None."""
    return VANILLA_POWER_ID_MAP.get(status_name)


def is_vanilla_status(status_name: str) -> bool:
    """Check if a status name is a known vanilla status."""
    return status_name in VANILLA_POWER_MAP
