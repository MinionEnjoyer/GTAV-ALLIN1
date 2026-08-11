"""Tk launcher editor for traffic, garages, and character inventories."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from allin1.config import Config
from allin1.customization import CHARACTERS, CharacterLoadout, GarageSaveStore, LoadoutStore
from allin1.vehicles.database import VehicleDatabase

GEAR = {
    "ARMOR_SUPER_LIGHT", "ARMOR_LIGHT", "ARMOR_STANDARD", "ARMOR_HEAVY",
    "ARMOR_SUPER_HEAVY", "ARMOR_JUGGERNAUT", "GADGET_PARACHUTE",
    "WEAPON_SMOKEGRENADE", "WEAPON_FIREEXTINGUISHER", "WEAPON_PETROLCAN",
    "WEAPON_HAZARDCAN", "WEAPON_NIGHTVISION",
}


class CharacterCustomizationDialog(tk.Toplevel):
    def __init__(self, parent, project_root: Path, scripts: Path, config: Config) -> None:
        super().__init__(parent)
        self.title("Character Customization")
        self.geometry("800x600")
        self.config_data = config
        database = VehicleDatabase.load(project_root / "data" / "vehicles.toml")
        self.models = sorted(vehicle.model for vehicle in database)
        with open(project_root / "data" / "weapons.toml", "rb") as stream:
            self.weapons = sorted(item["name"] for item in tomllib.load(stream)["weapons"])
        self.garage_store = GarageSaveStore(scripts / "ALLIN1_garage.json", set(self.models))
        self.loadout_store = LoadoutStore(scripts / "ALLIN1_characters.json", set(self.weapons), GEAR)
        try:
            self.garages = self.garage_store.load()
        except (OSError, ValueError):
            self.garages = {character: [] for character in CHARACTERS}
        self.loadouts = self.loadout_store.load()
        self.character = tk.StringVar(value=CHARACTERS[0])
        tabs = ttk.Notebook(self); tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self._traffic_tab(tabs)
        self._garage_tab(tabs)
        self._inventory_tab(tabs)
        self._outfit_tab(tabs)

    def _traffic_tab(self, tabs) -> None:
        frame = ttk.Frame(tabs, padding=14); tabs.add(frame, text="Traffic Spawner")
        fields = (
            ("Maximum driven vehicles", "max_driven"), ("Minimum spawn distance", "spawn_distance_min"),
            ("Maximum spawn distance", "spawn_distance_max"), ("Cleanup distance", "cleanup_distance"),
            ("Driven cooldown (ms)", "driven_cooldown_ms"), ("Scan cooldown (ms)", "scan_cooldown_ms"),
            ("Scan radius", "scan_radius"), ("Minimum replacement distance", "minimum_replace_distance"),
            ("Replacement chance (0–1)", "replacement_chance"),
        )
        self.traffic_vars = {}
        for row, (label, name) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            variable = tk.StringVar(value=str(getattr(self.config_data.traffic, name)))
            self.traffic_vars[name] = variable
            ttk.Entry(frame, textvariable=variable, width=18).grid(row=row, column=1, sticky="w")
        ttk.Button(frame, text="Apply traffic settings", command=self._save_traffic).grid(row=len(fields), column=0, pady=14)

    def _save_traffic(self) -> None:
        try:
            integer_fields = {"max_driven", "driven_cooldown_ms", "scan_cooldown_ms"}
            for name, variable in self.traffic_vars.items():
                setattr(self.config_data.traffic, name, int(variable.get()) if name in integer_fields else float(variable.get()))
            self.config_data.validate()
            messagebox.showinfo("Traffic", "Traffic settings are valid. Use Save settings in the main window to deploy them.")
        except ValueError as exc:
            messagebox.showerror("Invalid traffic settings", str(exc))

    def _character_picker(self, frame, command) -> None:
        ttk.Label(frame, text="Character").pack(anchor="w")
        box = ttk.Combobox(frame, textvariable=self.character, values=CHARACTERS, state="readonly")
        box.pack(anchor="w", pady=(0, 8)); box.bind("<<ComboboxSelected>>", lambda _: command())

    def _garage_tab(self, tabs) -> None:
        frame = ttk.Frame(tabs, padding=14); tabs.add(frame, text="Garage Saves")
        self._character_picker(frame, self._refresh_garage)
        self.garage_list = tk.Listbox(frame); self.garage_list.pack(fill="both", expand=True)
        buttons = ttk.Frame(frame); buttons.pack(fill="x", pady=8)
        for label, command in (("Add", self._add_vehicle), ("Remove", self._remove_vehicle),
                               ("Import…", self._import_garage), ("Export…", self._export_garage),
                               ("Repair", self._repair_garage),
                               ("Save", self._save_garage)):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=3)
        self._refresh_garage()

    def _refresh_garage(self) -> None:
        self.garage_list.delete(0, "end")
        for item in self.garages[self.character.get()]:
            self.garage_list.insert("end", f"Slot {item['slot'] + 1}: {item['model']}")

    def _add_vehicle(self) -> None:
        model = simpledialog.askstring("Add vehicle", "Vehicle spawn model:", parent=self)
        if not model: return
        model = model.lower().strip()
        if model not in self.models:
            messagebox.showerror("Unknown vehicle", model); return
        used = {item["slot"] for item in self.garages[self.character.get()]}
        slot = next((value for value in range(10) if value not in used), None)
        if slot is None: messagebox.showerror("Garage full", "This garage has 10 vehicles."); return
        self.garages[self.character.get()].append({"model": model, "slot": slot, "color1": 0, "color2": 0})
        self._refresh_garage()

    def _remove_vehicle(self) -> None:
        selected = self.garage_list.curselection()
        if selected: self.garages[self.character.get()].pop(selected[0]); self._refresh_garage()

    def _save_garage(self) -> None:
        try: self.garage_store.save(self.garages); messagebox.showinfo("Garage", "Garage save updated.")
        except (OSError, ValueError) as exc: messagebox.showerror("Garage save failed", str(exc))

    def _import_garage(self) -> None:
        path = filedialog.askopenfilename(filetypes=(("JSON", "*.json"),))
        if path: self.garage_store.import_file(Path(path)); self.garages = self.garage_store.load(); self._refresh_garage()

    def _export_garage(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if path: self.garage_store.export_file(Path(path))

    def _repair_garage(self) -> None:
        try:
            report = self.garage_store.repair()
            self.garages = self.garage_store.load()
            self._refresh_garage()
            messagebox.showinfo("Garage repair", f"Kept {report.kept}, reassigned "
                                f"{report.reassigned}, quarantined {report.quarantined}.")
        except OSError as exc:
            messagebox.showerror("Garage repair failed", str(exc))

    def _inventory_tab(self, tabs) -> None:
        frame = ttk.Frame(tabs, padding=14); tabs.add(frame, text="Weapons & Gear")
        self._character_picker(frame, self._refresh_inventory)
        panes = ttk.Frame(frame); panes.pack(fill="both", expand=True)
        self.available = tk.Listbox(panes, selectmode="extended"); self.available.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(panes); controls.pack(side="left", padx=8)
        ttk.Button(controls, text="Add →", command=self._add_inventory).pack(pady=4)
        ttk.Button(controls, text="← Remove", command=self._remove_inventory).pack(pady=4)
        self.owned = tk.Listbox(panes, selectmode="extended"); self.owned.pack(side="left", fill="both", expand=True)
        ttk.Button(frame, text="Save character loadouts", command=self._save_inventory).pack(anchor="w", pady=8)
        self._refresh_inventory()

    def _refresh_inventory(self) -> None:
        self.available.delete(0, "end"); self.owned.delete(0, "end")
        loadout = self.loadouts[self.character.get()]
        owned = set(loadout.weapons) | set(loadout.gear)
        for item in self.weapons + sorted(GEAR):
            (self.owned if item in owned else self.available).insert("end", item)

    def _add_inventory(self) -> None:
        loadout = self.loadouts[self.character.get()]
        loadout.managed = True
        for index in reversed(self.available.curselection()):
            item = self.available.get(index); (loadout.gear if item in GEAR else loadout.weapons).append(item)
        self._refresh_inventory()

    def _remove_inventory(self) -> None:
        loadout = self.loadouts[self.character.get()]
        loadout.managed = True
        for index in reversed(self.owned.curselection()):
            item = self.owned.get(index)
            if item in loadout.weapons: loadout.weapons.remove(item)
            if item in loadout.gear: loadout.gear.remove(item)
        self._refresh_inventory()

    def _save_inventory(self) -> None:
        try: self.loadout_store.save(self.loadouts); messagebox.showinfo("Characters", "Loadouts saved; GBAY will use the same inventory state.")
        except (OSError, ValueError) as exc: messagebox.showerror("Loadout save failed", str(exc))

    def _outfit_tab(self, tabs) -> None:
        frame = ttk.Frame(tabs, padding=14); tabs.add(frame, text="Outfit Unlocker")
        self._character_picker(frame, self._refresh_outfit)
        self.outfit_managed = tk.BooleanVar()
        self.outfit_unlock = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Manage this character's outfit", variable=self.outfit_managed).pack(anchor="w")
        ttk.Checkbutton(frame, text="Unlock all native component variants", variable=self.outfit_unlock).pack(anchor="w")
        preset_row = ttk.Frame(frame); preset_row.pack(fill="x", pady=4)
        self.preset_name = tk.StringVar()
        self.preset_box = ttk.Combobox(preset_row, textvariable=self.preset_name, width=24)
        self.preset_box.pack(side="left")
        ttk.Button(preset_row, text="Save preset", command=self._save_preset).pack(side="left", padx=3)
        ttk.Button(preset_row, text="Load preset", command=self._load_preset).pack(side="left", padx=3)
        ttk.Button(preset_row, text="Delete", command=self._delete_preset).pack(side="left", padx=3)
        ttk.Label(frame, text="Drawable and texture IDs are checked against the active character in-game.").pack(anchor="w", pady=(2, 8))
        panes = ttk.Frame(frame); panes.pack(fill="both", expand=True)
        self.component_vars = self._variation_grid(panes, "Components", 12)
        self.prop_vars = self._variation_grid(panes, "Props (-1 removes)", 8, prop=True)
        ttk.Button(frame, text="Save outfit", command=self._save_outfit).pack(anchor="w", pady=8)
        self._refresh_outfit()

    @staticmethod
    def _variation_grid(parent, title: str, count: int, prop: bool = False):
        frame = ttk.LabelFrame(parent, text=title, padding=8); frame.pack(side="left", fill="both", expand=True, padx=4)
        ttk.Label(frame, text="Slot").grid(row=0, column=0)
        ttk.Label(frame, text="Drawable").grid(row=0, column=1)
        ttk.Label(frame, text="Texture").grid(row=0, column=2)
        variables = []
        for slot in range(count):
            drawable = tk.StringVar(value="-1" if prop else "0"); texture = tk.StringVar(value="0")
            ttk.Label(frame, text=str(slot)).grid(row=slot + 1, column=0)
            ttk.Entry(frame, textvariable=drawable, width=8).grid(row=slot + 1, column=1, padx=3, pady=1)
            ttk.Entry(frame, textvariable=texture, width=8).grid(row=slot + 1, column=2, padx=3, pady=1)
            variables.append((drawable, texture))
        return variables

    def _refresh_outfit(self) -> None:
        outfit = self.loadouts[self.character.get()].outfit
        self.outfit_managed.set(outfit.managed); self.outfit_unlock.set(outfit.unlock_all)
        self.preset_box.configure(values=sorted(outfit.presets))
        for variables, values in ((self.component_vars, outfit.components), (self.prop_vars, outfit.props)):
            for (drawable, texture), value in zip(variables, values):
                drawable.set(str(value.drawable)); texture.set(str(value.texture))

    def _save_outfit(self) -> None:
        outfit = self.loadouts[self.character.get()].outfit
        try:
            outfit.managed = self.outfit_managed.get(); outfit.unlock_all = self.outfit_unlock.get()
            self._capture_outfit_fields()
            self.loadout_store.save(self.loadouts)
            messagebox.showinfo("Outfit", "Outfit saved. It will apply when this character becomes active.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Outfit save failed", str(exc))

    def _save_preset(self) -> None:
        try:
            self._capture_outfit_fields()
            self.loadout_store.save_preset(self.loadouts[self.character.get()].outfit,
                                           self.preset_name.get())
            self.loadout_store.save(self.loadouts); self._refresh_outfit()
        except (OSError, ValueError) as exc: messagebox.showerror("Preset failed", str(exc))

    def _load_preset(self) -> None:
        try:
            self.loadout_store.apply_preset(self.loadouts[self.character.get()].outfit,
                                            self.preset_name.get())
            self._refresh_outfit()
        except (KeyError, ValueError) as exc: messagebox.showerror("Preset failed", str(exc))

    def _delete_preset(self) -> None:
        outfit = self.loadouts[self.character.get()].outfit
        if self.preset_name.get() in outfit.presets:
            del outfit.presets[self.preset_name.get()]
            self.loadout_store.save(self.loadouts); self.preset_name.set(""); self._refresh_outfit()

    def _capture_outfit_fields(self) -> None:
        outfit = self.loadouts[self.character.get()].outfit
        for variables, values in ((self.component_vars, outfit.components), (self.prop_vars, outfit.props)):
            for (drawable, texture), value in zip(variables, values):
                value.drawable = int(drawable.get()); value.texture = int(texture.get())
