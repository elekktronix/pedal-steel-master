"""Factory copedant setups from PSG Compass: Emmons E9, Emmons C6, and GFI 12-String Universals."""

from core.models import CopedantChange, Neck, NeckType, SplitRule, SteelGuitar, StringPitch


# =========================================================================
# 1. BE E9 3P-5KL-1HS (Standard Buddy Emmons 10-String E9 with Half-Stop)
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
    ][cite: 29]

    pedals = {
        "P1": CopedantChange("P1", "P1 (A)", {5: 2, 10: 2}),
        "P2": CopedantChange("P2", "P2 (B)", {3: 1, 6: 1}),
        "P3": CopedantChange("P3", "P3 (C)", {4: 2, 5: 2}),
    }[cite: 29]

    knee_levers = {
        "LKL": CopedantChange("LKL", "LKL", {4: 1, 8: 1}),
        "VL": CopedantChange("VL", "VL", {5: -1, 10: -1}),
        "LKR": CopedantChange("LKR", "LKR", {4: -1, 8: -1}),
        "RKL": CopedantChange("RKL", "RKL", {2: 1, 6: -2}),
        "RKR": CopedantChange("RKR", "RKR", {2: -2, 9: -1}),
        "RKR2": CopedantChange("RKR2", "RKRHS", {2: -1}),
    }[cite: 29]

    splits = [
        SplitRule(2, ["RKR", "RKR2"], -3, is_active=False, description="RKR + RKRHS compound drop"),
        SplitRule(4, ["P3", "LKL"], 2, is_active=True, description="P3 raise + LKL raise stop at F#"),
        SplitRule(4, ["P3", "LKR"], 1, is_active=True, description="P3 raise + LKR lower split to F natural"),
        SplitRule(5, ["P1", "VL"], 1, is_active=True, description="P1 raise + VL lower split to C natural"),
        SplitRule(5, ["P3", "VL"], 1, is_active=True, description="P3 raise + VL lower split to C natural"),
        SplitRule(6, ["P2", "RKL"], -1, is_active=False, description="P2 raise + RKL lower split to G natural"),
        SplitRule(10, ["P1", "VL"], 1, is_active=True, description="P1 raise + VL lower split to C natural"),
    ][cite: 29]

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
        author_bio="Buddy Emmons, Legendary steel guitarist and innovator of the E9 tuning. His setup became the industry standard. In the mid 1950's, he contributed to the evolution of the pedal steel guitar by splitting the function of the two pedals that changed the pitch of several strings from the I chord to IV chord. This 'split-pedal' setup became the standard pedal arrangement in the E9 tuning, since it allows greater musical flexibility than the earlier pedal setup pioneered by Bud Isaacs. Buddy also expanded the tuning from 8 to 10 strings, adding the first two so-called 'chromatic' strings.",
        social_media="Reference: https://b0b.com/wp/copedents/buddy-emmons-e9th/",
    )[cite: 29]


# =========================================================================
# 2. BE C6 5P-4KL (Standard Buddy Emmons 10-String C6 Copedant)
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
    ][cite: 26]

    pedals = {
        "P1": CopedantChange("P1", "P4", {4: 2, 8: 2}),
        "P2": CopedantChange("P2", "P5", {5: -1, 9: 1, 10: 2}),
        "P3": CopedantChange("P3", "P6", {2: 1, 6: -1}),
        "P4": CopedantChange("P4", "P7", {3: 2, 4: 2}),
        "P5": CopedantChange("P5", "P8", {1: 1, 7: 1, 9: -1, 10: -3}),
    }[cite: 26]

    knee_levers = {
        "LKL": CopedantChange("LKL", "LKL", {4: -1}),
        "LKR": CopedantChange("LKR", "LKR", {4: 1}),
        "RKL": CopedantChange("RKL", "RKL", {3: -1}),
        "RKR": CopedantChange("RKR", "RKR", {3: 1}),
    }[cite: 26]

    splits = [
        SplitRule(3, ["P4", "RKL"], 1, is_active=False, description="P7 raise + RKL lower split on C4"),
        SplitRule(3, ["P4", "RKR"], 3, is_active=False, description="P7 raise + RKR raise on C4"),
        SplitRule(4, ["P1", "LKL"], 1, is_active=False, description="P4 raise + LKL lower split on A3"),
        SplitRule(4, ["P1", "LKR"], 3, is_active=False, description="P4 raise + LKR raise on A3"),
        SplitRule(4, ["P4", "LKL"], 1, is_active=False, description="P7 raise + LKL lower split on A3"),
        SplitRule(4, ["P4", "LKR"], 3, is_active=False, description="P7 raise + LKR raise on A3"),
    ][cite: 26]

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
        author_bio="Buddy Emmons is largely responsible for the design of the C6th copedent. A Jerry Byrd disciple, Buddy instructed Shot Jackson to put a C6th tuning on the back neck of his guitar. He specified the changes of the 8th pedal to reflect Byrd's C6/A7 tuning, and the 5th and 6th pedals to get the most common bar slants heard in Byrd's playing. (Bob White is credited with the standard P7 changes.) Sometimes Buddy raised the 6th string E to F on P4 instead of the standard A to B changes. It's a popular alternative.",
        social_media="Reference: https://b0b.com/wp/copedents/buddy-emmons-c6th-copedent/",
    )[cite: 26]


# =========================================================================
# 3. GFI 12U 7P-5KL (12-String Universal Factory Standard)
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
    ][cite: 27]

    pedals = {
        "P1": CopedantChange("P1", "P1", {5: 2, 9: 2}),
        "P2": CopedantChange("P2", "P2", {3: 1, 6: 1, 10: 1}),
        "P3": CopedantChange("P3", "P3", {4: 2, 5: 2}),
        "P4": CopedantChange("P4", "P4", {9: 1, 11: -1, 12: -3}),
        "P5": CopedantChange("P5", "P5", {7: -1, 11: 1, 12: 2}),
        "P6": CopedantChange("P6", "P6", {4: 1, 8: -2}),
        "P7": CopedantChange("P7", "P7", {5: 2, 6: 2}),
    }[cite: 27]

    knee_levers = {
        "LKL": CopedantChange("LKL", "LKL", {4: 1, 8: 1}),
        "VL": CopedantChange("VL", "VL", {5: -1}),
        "LKR": CopedantChange("LKR", "LKR", {4: -1, 8: -1}),
        "RKL": CopedantChange("RKL", "RKL", {1: 1, 7: 1}),
        "RKR": CopedantChange("RKR", "RKR", {2: -1, 9: 3}),
    }[cite: 27]

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
    ][cite: 27]

    return Neck(
        name="GFI 12U 7P-5KL",
        neck_type=NeckType.UNIVERSAL_12,
        string_count=12,
        open_tuning=tuning,
        pedals=pedals,
        knee_levers=knee_levers,
        splits=splits,
        description="Default factory standard set up with 7 Pedals and 5 Knee Levers that the Company GFI gives to its S-12 K U and S-12 P K U models of 12 String Pedal Steel Guitar.",
        author="PSG Compass",
        author_bio="Copedent Created by PSG Compass Developer.",
        social_media="Reference: https://www.gfimusicalproducts.com/_files/ugd/deb4ea_d3379f7ee3a748578a91157a3517e2a9.pdf",
    )[cite: 27]


# =========================================================================
# 4. GFI 12U 7P-5KL-3HS (12-String Universal with Half-Stops in P1, P3, P7)
# =========================================================================
def build_gfi_12u_7p_5kl_3hs() -> Neck:
    base = build_gfi_12u_7p_5kl()
    # Add half-stop split overrides
    hs_splits = list(base.splits)
    hs_splits.extend([
        SplitRule(4, ["LKL", "P3HS"], 1, is_active=True, description="LKL + P3HS split"),
        SplitRule(4, ["LKR", "P3HS"], 0, is_active=True, description="LKR + P3HS cancel"),
        SplitRule(5, ["VL", "P1HS"], 0, is_active=True, description="VL + P1HS cancel"),
        SplitRule(5, ["VL", "P3HS"], 0, is_active=True, description="VL + P3HS cancel"),
        SplitRule(5, ["VL", "P7HS"], 0, is_active=True, description="VL + P7HS cancel"),
        SplitRule(9, ["RKR", "P1HS"], 3, is_active=True, description="RKR + P1HS compound raise"),
    ])[cite: 28]

    return Neck(
        name="GFI 12U 7P-5KL-3HS",
        neck_type=NeckType.UNIVERSAL_12,
        string_count=12,
        open_tuning=base.open_tuning,
        pedals=base.pedals,
        knee_levers=base.knee_levers,
        splits=hs_splits,
        description="Default factory standard set up with 7 Pedals and 5 Knee Levers that the Company GFI gives to its S-12 K U and S-12 P K U models of 12 String Pedal Steel Guitar. This version includes Half Stops in P1, P3 and P7.",
        author="PSG Compass",
        author_bio="Copedent Created by PSG Compass Developer.",
        social_media="Reference: https://www.gfimusicalproducts.com/_files/ugd/deb4ea_d3379f7ee3a748578a91157a3517e2a9.pdf",
    )[cite: 28]


def build_standard_d10_guitar() -> SteelGuitar:
    """Builds multi-neck collection featuring all factory copedants."""
    return SteelGuitar(
        name="PSG Compass Pro Collection",
        necks=[
            build_be_e9_3p_5kl_1hs(),
            build_be_c6_5p_4kl(),
            build_gfi_12u_7p_5kl(),
            build_gfi_12u_7p_5kl_3hs(),
        ],
    )