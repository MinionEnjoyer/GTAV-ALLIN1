"""Fixed, property-scoped Story interior bridges; never global Online groups."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GarageBridge:
    key: str
    label: str
    source_pack: str
    source_device: str
    changeset: str
    ipls: tuple[str, ...]
    requires_loading: bool
    enabled_archives: tuple[str, ...] = ()

    @property
    def pack(self) -> str:
        return f"allin1_{self.source_pack}_{self.key}_bridge"

    @property
    def device(self) -> str:
        return f"dlc_{self.pack}"

    @property
    def group(self) -> str:
        return f"ALLIN1_STOCK_{self.source_pack}_{self.key}_V1".upper()

    @property
    def startup(self) -> str:
        return f"ALLIN1_{self.source_pack}_{self.key}_BRIDGE_AUTOGEN".upper()

    @property
    def marker(self) -> str:
        return f"{self.pack}.active"

    @property
    def receipt(self) -> str:
        return f"{self.pack}.runtime.json"

    @property
    def scope(self) -> str:
        return "garment_factory" if self.key == "garment" else self.key

    @property
    def activation(self) -> str:
        return f"explicit-{self.key}-entry-black-transition"

    @property
    def contract(self) -> str:
        return f"allin1-stock-{self.source_pack.replace('_', '-')}-{self.key}-black-transition-v1"


GARMENT = GarageBridge(
    "garment", "Garment Factory", "mp2024_02", "dlc_mp2024_02",
    "MP2024_02_MAP_UPDATE",
    ("m24_2_int_placement", "m24_2_int_placement_interior_int_hacker_garage_milo_"),
    True,
)
HARMONY = GarageBridge(
    "harmony", "Harmony", "mpbattle", "dlc_mpBattle",
    "MPBATTLE_INTERIOR_ADDITIONS",
    ("ba_int_placement_ba_interior_1_dlc_int_02_ba_milo_",), False,
    ("interiors/int_01_ba.rpf", "interiors/int_02_ba.rpf",
     "interiors/int_03_ba.rpf", "interiors/int_placement_ba.rpf", "mpBattleIPL.rpf"),
)
PALETO = GarageBridge(
    "paleto", "Paleto Bay", "mpvinewood", "dlc_mpVinewood",
    "mpVinewood_INTERIOR_ADDITIONS", ("vw_casino_garage",), True,
    ("interiors/vwdlc_int_01.rpf", "interiors/vwdlc_int_02.rpf",
     "interiors/vwdlc_int_03.rpf", "interiors/vwdlc_int_05.rpf",
     "interiors/int_placement_vw.rpf"),
)

ADDITIONAL_INTERIOR_BRIDGES = (HARMONY, PALETO)
