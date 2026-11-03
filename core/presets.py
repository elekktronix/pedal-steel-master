"""Stock presets for standard Emmons E9, C6, and PSG Compass factory setups."""

from core.models import CopedantChange, HalfStopRule, Neck, NeckType, SplitRule, SteelGuitar, StringPitch


# =========================================================================
# 1. Original User Default: 10-String E9 Chromatic
# =========================================================================
def build_standard_emmons_e9_10() -> Neck:
    """Standard 10-string E9 Chromatic with P1-P3, knee levers (LKL, LKR, RKL, RKR), and LKV."""
    tuning = [
        StringPitch.from_name(1, "F#", 4),
        StringPitch.from_name(2, "D#", 4),  # Eb4
        StringPitch.from_name(3, "G#", 4),
        StringPitch.from_name(4, "E", 4),
        StringPitch.from_name(5, "B", 3),
        StringPitch.from_name(6, "G#", 3),
        StringPitch.from_name(7, "F#", 3),
        StringPitch.from_name(8, "E", 3),
        StringPitch.from_name(9, "D", 3),
        StringPitch.from_name(10, "B", 2),
    ]

    pedals = {
        "P1": CopedantChange(id="P1", label="Pedal 1 (A)", changes={5: 2, 10: 2}),
        "P2": CopedantChange(id="P2", label="Pedal 2 (B)", changes={3: 1, 6: 1}),
        "P3": CopedantChange(id="P3", label="Pedal 3 (C)", changes={4: 2, 5: 2}),
    }

    knee_levers = {
        "LKL": CopedantChange(id="LKL", label="LKL (E raises)", changes={4: 1, 8: 1}),
        "LKR": CopedantChange(id="LKR", label="LKR (E lowers)", changes={4: -1, 8: -1}),
        "LKV": CopedantChange(id="LKV", label="LKV (B lowers)", changes={5: -1, 10: -1}),
        "RKL": CopedantChange(
            id="RKL",
            label="RKL",
            changes={1: 2, 2: 1, 6: -2},  # F#->G#, Eb->E, G#->F#
        ),
        "RKR": CopedantChange(
            id="RKR",
            label="RKR",
            changes={2: -2, 7: 2, 9: -1},  # Eb->C#, F#->G#, D->C#
        ),
    }

    splits = [
        SplitRule(4, ["P3", "LKL"], 2, is_active=True, description="P3 raise + LKL raise stop at F#"),
        SplitRule(4, ["P3", "LKR"], 1, is_active=True, description="P3 raise + LKR lower split to F natural"),
        SplitRule(5, ["P1", "LKV"], 1, is_active=True, description="P1 raise + LKV lower split to C natural"),
        SplitRule(10, ["P1", "LKV"], 1, is_active=True, description="P1 raise + LKV lower split to C natural"),
    ]

    return Neck(
        name="10-String E9 Chromatic",
        neck_type=NeckType.E9,
        string_count=10,
        open_tuning=tuning,
        pedals=pedals,
        knee_levers=knee_levers,
        splits=splits,
        description="Standard 10-string E9 Chromatic setup with standard Emmons ABC pedals and 5 knee levers.",
        author="User Preset",
    )


# =========================================================================
# 2. Original User Default: 10-String C6
# =========================================================================
def build_standard_c6_10() -> Neck:
    """10-string C6 configured with High D and user's P4-P8, RKL, RKR copedant."""
    tuning = [
        StringPitch.from_name(1, "D", 4),
        StringPitch.from_name(2, "E", 4),
        StringPitch.from_name(3, "C", 4),
        StringPitch.from_name(4, "A", 3),
        StringPitch.from_name(5, "G", 3),
        StringPitch.from_name(6, "E", 3),
        StringPitch.from_name(7, "C", 3),
        StringPitch.from_name(8, "A", 2),
        StringPitch.from_name(9, "F", 2),
        StringPitch.from_name(10, "C", 2),
    ]

    pedals = {
        "P4": CopedantChange(id="P4", label="P4", changes={4: 2, 8: 2}),                # A->B
        "P5": CopedantChange(id="P5", label="P5", changes={5: -1, 9: 1, 10: 2}),        # G->F#, F->F#, C->D
        "P6": CopedantChange(id="P6", label="P6", changes={2: 1, 6: -1}),               # E->F, E->Eb
        "P7": CopedantChange(id="P7", label="P7", changes={3: 2, 4: 2}),                # C->D, A->B
        "P8": CopedantChange(id="P8", label="P8", changes={1: 1, 7: 1, 9: -1, 10: -3}), # D->D#, C->C#, F->E, C->A
    }

    knee_levers = {
        "LKL": CopedantChange(id="LKL", label="LKL", changes={}),
        "LKV": CopedantChange(id="LKV", label="LKV", changes={}),
        "LKR": CopedantChange(id="LKR", label="LKR", changes={}),
        "RKL": CopedantChange(id="RKL", label="RKL", changes={3: -1}),  # C -> B
        "RKR": CopedantChange(id="RKR", label="RKR", changes={4: -1}),  # A -> Ab
    }

    return Neck(
        name="10-String C6",
        neck_type=NeckType.C6,
        string_count=10,
        open_tuning=tuning,
        pedals=pedals,
        knee_levers=knee_levers,
        splits=[],
        description="Standard 10-string C6 copedant with High D tuning, pedals P4-P8, and RKL/RKR.",
        author="User Preset",
    )


# =========================================================================
# 3. BE E9 3P-5KL-1HS
# =========================================================================
def build_be_e9_3p_5kl_1hs() -> Neck:
    tuning = [
        StringPitch(1, 66, "F#4"),
        StringPitch(2, 63, "D#4"),
        StringPitch(3, 68, "G#4"),
        StringPitch(4, 64, "E4"),
        StringPitch(5, 59, "B3"),
        StringPitch(6, 56, "G#3"),
        StringPitch(7, 54, "F#3"),
        StringPitch(8, 52, "E3"),
        StringPitch(9, 50, "D3"),
        StringPitch(10, 47, "B2"),
    ]

    pedals = {
        "P1": CopedantChange("P1", "P1 (A)", {5: 2, 10: 2}),
        "P2": CopedantChange("P2", "P2 (B)", {3: 1, 6: 1}),
        "P3": CopedantChange("P3", "P3 (C)", {4: 2, 5: 2}),
    }

    knee_levers = {
        "LKL": CopedantChange("LKL", "LKL", {4: 1, 8: 1}),
        "VL": CopedantChange("VL", "VL", {5: -1, 10: -1}),
        "LKR": CopedantChange("LKR", "LKR", {4: -1, 8: -1}),
        "RKL": CopedantChange("RKL", "RKL", {2: 1, 6: -2}),
        "RKR": CopedantChange("RKR", "RKR", {2: -2, 9: -1}),
        "RKR2": CopedantChange("RKR2", "RKRHS", {2: -1}),
    }

    splits = [
        SplitRule(2, ["RKR", "RKR2"], -3, is_active=False, description="RKR + RKRHS compound drop"),
        SplitRule(4, ["P3", "LKL"], 2, is_active=True, description="P3 raise + LKL raise stop at F#"),
        SplitRule(4, ["P3", "LKR"], 1, is_active=True, description="P3 raise + LKR lower split to F natural"),
        SplitRule(5, ["P1", "VL"], 1, is_active=True, description="P1 raise + VL lower split to C natural"),
        SplitRule(5, ["P3", "VL"], 1, is_active=True, description="P3 raise + VL lower split to C natural"),
        SplitRule(6, ["P2", "RKL"], -1, is_active=False, description="P2 raise + RKL lower split to G natural"),
        SplitRule(10, ["P1", "VL"], 1, is_active=True, description="P1 raise + VL lower split to C natural"),
    ]

    return Neck(
        name="BE E9 3P-5KL-1HS",
        neck_type=NeckType.E9,
        string_count=10,
        open_tuning=tuning,
        pedals=pedals,
        knee_levers=knee_levers,
        splits=splits,
        description="Standard Buddy Emmons E9 setup with 3 pedals and 5 knee levers for traditional country steel guitar, includes a Half Stop in RKR.",
        author="PSG Compass",
        author_bio="Buddy Emmons, Legendary steel guitarist and innovator of the E9 tuning. His setup became the industry standard.",
        social_media="Reference: https://b0b.com/wp/copedents/buddy-emmons-e9th/",
    )


# =========================================================================
# 4. BE C6 5P-4KL
# =========================================================================
def build_be_c6_5p_4kl() -> Neck:
    tuning = [
        StringPitch(1, 62, "D4"),
        StringPitch(2, 64, "E4"),
        StringPitch(3, 60, "C4"),
        StringPitch(4, 57, "A3"),
        StringPitch(5, 55, "G3"),
        StringPitch(6, 52, "E3"),
        StringPitch(7, 48, "C3"),
        StringPitch(8, 45, "A2"),
        StringPitch(9, 41, "F2"),
        StringPitch(10, 36, "C2"),
    ]

    pedals = {
        "P1": CopedantChange("P1", "P4", {4: 2, 8: 2}),
        "P2": CopedantChange("P2", "P5", {5: -1, 9: 1, 10: 2}),
        "P3": CopedantChange("P3", "P6", {2: 1, 6: -1}),
        "P4": CopedantChange("P4", "P7", {3: 2, 4: 2}),
        "P5": CopedantChange("P5", "P8", {1: 1, 7: 1, 9: -1, 10: -3}),
    }

    knee_levers = {
        "LKL": CopedantChange("LKL", "LKL", {4: -1}),
        "LKR": CopedantChange("LKR", "LKR", {4: 1}),
        "RKL": CopedantChange("RKL", "RKL", {3: -1}),
        "RKR": CopedantChange("RKR", "RKR", {3: 1}),
    }

    splits = [
        SplitRule(3, ["P4", "RKL"], 1, is_active=False, description="P7 raise + RKL lower split on C4"),
        SplitRule(3, ["P4", "RKR"], 3, is_active=False, description="P7 raise + RKR raise on C4"),
        SplitRule(4, ["P1", "LKL"], 1, is_active=False, description="P4 raise + LKL lower split on A3"),
        SplitRule(4, ["P1", "LKR"], 3, is_active=False, description="P4 raise + LKR raise on A3"),
        SplitRule(4, ["P4", "LKL"], 1, is_active=False, description="P7 raise + LKL lower split on A3"),
        SplitRule(4, ["P4", "LKR"], 3, is_active=False, description="P7 raise + LKR raise on A3"),
    ]

    return Neck(
        name="BE C6 5P-4KL",
        neck_type=NeckType.C6,
        string_count=10,
        open_tuning=tuning,
        pedals=pedals,
        knee_levers=knee_levers,
        splits=splits,
        description="Standard Buddy Emmons C6th copedent with 5 pedals and 4 knee levers.",
        author="PSG Compass",
        author_bio="Buddy Emmons is largely responsible for the design of the C6th copedent.",
        social_media="Reference: https://b0b.com/wp/copedents/buddy-emmons-c6th-copedent/",
    )


# =========================================================================
# 5. GFI 12U 7P-5KL (12-String Universal)
# =========================================================================
def build_gfi_12u_7p_5kl() -> Neck:
    tuning = [
        StringPitch(1, 66, "F#4"),
        StringPitch(2, 63, "D#4"),
        StringPitch(3, 68, "G#4"),
        StringPitch(4, 64, "E4"),
        StringPitch(5, 59, "B3"),
        StringPitch(6, 56, "G#3"),
        StringPitch(7, 54, "F#3"),
        StringPitch(8, 52, "E3"),
        StringPitch(9, 47, "B2"),
        StringPitch(10, 44, "G#2"),
        StringPitch(11, 40, "E2"),
        StringPitch(12, 35, "B1"),
    ]

    pedals = {
        "P1": CopedantChange("P1", "P1", {5: 2, 9: 2}),
        "P2": CopedantChange("P2", "P2", {3: 1, 6: 1, 10: 1}),
        "P3": CopedantChange("P3", "P3", {4: 2, 5: 2}),
        "P4": CopedantChange("P4", "P4", {9: 1, 11: -1, 12: -3}),
        "P5": CopedantChange("P5", "P5", {7: -1, 11: 1, 12: 2}),
        "P6": CopedantChange("P6", "P6", {4: 1, 8: -2}),
        "P7": CopedantChange("P7", "P7", {5: 2, 6: 2}),
    }

    knee_levers = {
        "LKL": CopedantChange("LKL", "LKL", {4: 1, 8: 1}),
        "VL": CopedantChange("VL", "VL", {5: -1}),
        "LKR": CopedantChange("LKR", "LKR", {4: -1, 8: -1}),
        "RKL": CopedantChange("RKL", "RKL", {1: 1, 7: 1}),
        "RKR": CopedantChange("RKR", "RKR", {2: -1, 9: 3}),
    }

    splits = [
        SplitRule(4, ["P3", "LKL"], 2, is_active=True, description="P3 raise + LKL raise"),
        SplitRule(4, ["P3", "LKR"], 1, is_active=True, description="P3 raise + LKR lower split to F natural"),
        SplitRule(4, ["P6", "LKL"], 1, is_active=True, description="P6 raise + LKL raise"),
        SplitRule(4, ["P6", "LKR"], 0, is_active=True, description="P6 raise + LKR lower cancel"),
        SplitRule(5, ["P1", "VL"], 1, is_active=True, description="P1 raise + VL lower split to C natural"),
        SplitRule(5, ["P3", "VL"], 1, is_active=True, description="P3 raise + VL lower split to C natural"),
        SplitRule(5, ["P7", "VL"], 1, is_active=True, description="P7 raise + VL lower split to C natural"),
        SplitRule(7, ["P5", "RKL"], 0, is_active=True, description="P5 lower + RKL raise cancel"),
        SplitRule(8, ["P6", "LKL"], -1, is_active=True, description="P6 lower + LKL raise split to Eb"),
        SplitRule(8, ["P6", "LKR"], -2, is_active=True, description="P6 lower + LKR lower compound drop"),
        SplitRule(9, ["P1", "RKR"], 3, is_active=True, description="P1 raise + RKR raise"),
        SplitRule(9, ["P4", "RKR"], 3, is_active=True, description="P4 raise + RKR raise"),
        SplitRule(11, ["P4", "P5"], 0, is_active=True, description="P4 lower + P5 raise cancel on E2"),
        SplitRule(12, ["P4", "P5"], -1, is_active=True, description="P4 lower + P5 raise split on B1"),
    ]

    return Neck(
        name="GFI 12U 7P-5KL",
        neck_type=NeckType.UNIVERSAL_12,
        string_count=12,
        open_tuning=tuning,
        pedals=pedals,
        knee_levers=knee_levers,
        splits=splits,
        description="Default factory standard setup with 7 Pedals and 5 Knee Levers for 12 String Universal.",
        author="PSG Compass",
    )


# =========================================================================
# 6. GFI 12U 7P-5KL-3HS (12-String Universal with Half-Stops)
# =========================================================================
def build_gfi_12u_7p_5kl_3hs() -> Neck:
    base = build_gfi_12u_7p_5kl()
    hs_splits = list(base.splits)
    # Half-stop engagement is the token "<ID>_HALF" (see docs/architecture/02-pitch-resolution.md).
    hs_splits.extend([
        SplitRule(4, ["LKL", "P3_HALF"], 1, is_active=True, description="LKL + P3 half-stop split"),
        SplitRule(4, ["LKR", "P3_HALF"], 0, is_active=True, description="LKR + P3 half-stop cancel"),
        SplitRule(5, ["VL", "P1_HALF"], 0, is_active=True, description="VL + P1 half-stop cancel"),
        SplitRule(5, ["VL", "P3_HALF"], 0, is_active=True, description="VL + P3 half-stop cancel"),
        SplitRule(5, ["VL", "P7_HALF"], 0, is_active=True, description="VL + P7 half-stop cancel"),
        SplitRule(9, ["RKR", "P1_HALF"], 3, is_active=True, description="RKR + P1 half-stop compound raise"),
    ])
    half_stops = [
        HalfStopRule("P1", 5, 1, description="P1 half-stop: B -> C"),
        HalfStopRule("P1", 9, 1, description="P1 half-stop: B -> C"),
        HalfStopRule("P3", 4, 1, description="P3 half-stop: E -> F"),
        HalfStopRule("P3", 5, 1, description="P3 half-stop: B -> C"),
        HalfStopRule("P7", 5, 1, description="P7 half-stop: B -> C"),
        HalfStopRule("P7", 6, 1, description="P7 half-stop: G# -> A"),
    ]

    return Neck(
        name="GFI 12U 7P-5KL-3HS",
        neck_type=NeckType.UNIVERSAL_12,
        string_count=12,
        open_tuning=base.open_tuning,
        pedals=base.pedals,
        knee_levers=base.knee_levers,
        splits=hs_splits,
        half_stops=half_stops,
        description="12 String Universal setup with 7 Pedals, 5 Knee Levers, and 3 Half-Stops in P1, P3, P7.",
        author="PSG Compass",
    )


def build_standard_d10_guitar() -> SteelGuitar:
    """Multi-neck collection featuring user defaults alongside PSG Compass setups."""
    return SteelGuitar(
        name="Pedal Steel Master Collection",
        necks=[
            build_standard_emmons_e9_10(),
            build_standard_c6_10(),
            build_be_e9_3p_5kl_1hs(),
            build_be_c6_5p_4kl(),
            build_gfi_12u_7p_5kl(),
            build_gfi_12u_7p_5kl_3hs(),
        ],
    )