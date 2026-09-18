"""Public, transport-independent Launcher API. No HTTP listener or shell eval.

The SDK can inspect its build outputs here and continue through the same
review/apply boundary used by the desktop. New actions fail closed.
"""
from __future__ import annotations

import copy
import time

from allin1.desktop_service import GAME_ACTIONS, LOCAL_ACTIONS, LauncherService, digest
from allin1.preview_render_pool import MAX_PREVIEW_WORKERS

READS = {
    "catalog": [], "inspect": ["module", "config", "source", "profile"],
    "health": [], "load_profile": ["name"], "read_garages": ["source"],
    "startup_status": [], "check_update": [], "check_sdk_update": [],
}
EXTERNAL = {"open_activity_folder", "open_launcher_release"}
# Explicit action parameters: adding a backend action requires a contract entry.
ACTION_FIELDS = {
    "download_previews": ["categories"],
    "save_config": [], "sync_config": [], "install": ["reactor_consent", "rpf_loader_consent"],
    "uninstall": [], "launch": ["skip_previews", "skip_preview_categories", "quick_launch", "missing_previews_only"], "prepare_previews": ["skip_previews", "skip_preview_categories", "missing_previews_only"], "save_profile": ["name"], "delete_profile": ["name"],
    "export_profile": ["name", "destination"], "import_preferences": ["source"],
    # Collections require an explicit component selection.  The desktop uses
    # this for schema-v6 package bundles, so agents must be able to review the
    # exact same component instead of being rejected before the shared review
    # boundary sees the request.
    "package_install": ["source", "settings", "component_id", "expected_state_sha256"],
    "package_enable": ["id"], "package_disable": ["id"], "package_uninstall": ["id"],
    "content_enable": ["id"], "content_disable": ["id"], "content_settings": ["id", "settings"],
    "save_content_preferences": ["id", "settings"],
    "ped_population_save": ["document", "expected_document_sha256"],
    "weapon_population_save": ["document", "expected_document_sha256"],
    "traffic_population_save": ["document", "expected_document_sha256"],
    "characters_save": ["document", "expected_document_sha256", "expected_state_sha256"],
    "garages_save": ["document", "expected_document_sha256", "expected_state_sha256"],
    "garages_repair": [], "garages_export": ["destination"], "diagnostics": ["destination"],
    "sdk_install": ["source"], "sdk_install_release": [], "sdk_uninstall": [], "sdk_open": ["workspace"],
    "assistant_save": ["assistant_config"], "assistant_install_archive": ["source", "profile"],
    "assistant_install_qwen": ["profile"], "assistant_uninstall": [],
}


def schema(fields, required=()):
    types = {"config": "object", "settings": "object", "document": "object", "assistant_config": "object",
             "confirmed": "boolean", "reactor_consent": "boolean", "rpf_loader_consent": "boolean", "skip_previews": "boolean", "quick_launch": "boolean", "missing_previews_only": "boolean", "workers": "integer"}
    from allin1.preview_policy import PREVIEW_CATEGORIES
    return {"type": "object", "additionalProperties": False,
            "properties": {field: ({"type": "array", "items": {"type": "string", "enum": list(PREVIEW_CATEGORIES)}, "uniqueItems": True, "maxItems": 3,
                                    **({"minItems": 1} if field == "categories" else {})}
                                   if field in {"skip_preview_categories", "categories"} else {"type": "integer", "minimum": 1, "maximum": MAX_PREVIEW_WORKERS}
                                   if field == "workers" else {"type": types.get(field, "string")}) for field in fields}, "required": list(required)}


def contract():
    if set(ACTION_FIELDS) != GAME_ACTIONS | LOCAL_ACTIONS:
        raise ValueError("Launcher action catalog is incomplete; update its explicit contract")
    return {
        "schema_version": 1, "kind": "launcher_api_catalog", "transport": "stdio-json-lines",
        "review_lifetime_seconds": 300, "default_authority": "read_only",
        "operations": [{"name": name, "risk": "network_read" if name.startswith("check_") else "read_only",
                        "input_schema": schema(fields)} for name, fields in READS.items()] + [
            {"name": name, "risk": "external_open", "input_schema": schema([])} for name in sorted(EXTERNAL)] + [
            {"name": "review", "risk": "plan_only", "input_schema": {"oneOf": [
                {**schema(["action", "config", *fields], ["action"]),
                 "properties": {**schema(["config", *fields])["properties"], "action": {"const": action}}}
                for action, fields in sorted(ACTION_FIELDS.items())]}},
            {"name": "apply", "risk": "reviewed_mutation", "input_schema": schema(
                ["review_id", "review_sha256", "confirmed"], ["review_id", "review_sha256", "confirmed"])},
            {"name": "cancel_launch", "risk": "launch_control", "input_schema": schema(["review_id"], ["review_id"])},
            {"name": "set_preview_workers", "risk": "render_control", "input_schema": schema(["review_id", "workers"], ["review_id", "workers"])},
        ],
        "actions": [{"name": name, "risk": "launch" if name == "launch" else "game_write" if name in GAME_ACTIONS else "external_open" if name == "sdk_open" else "local_write",
                     "requires_review": True, "parameters": ["config", *fields]}
                    for name, fields in sorted(ACTION_FIELDS.items())],
        "sdk_happy_path": ["SDK validates and exports a package", "inspect: module=package, source=<export>",
                           "review: action=package_install, source=<export>, settings=<reviewed settings>, expected_state_sha256=<inspection>",
                           "apply: review_id, review_sha256, confirmed=true", "inspect: module=mods"],
        "notes": ["Keep one agent-api process alive for review/apply; review IDs are session-local and single-use.",
                  "Content injectors: inspect module ped_manager, weapon_manager or vehicle_manager; edit its population document; review the corresponding ped_population_save, weapon_population_save or traffic_population_save with expected_document_sha256 from inspection; apply only after approval. Catalogs must be installed and receipt-authorized. Policies take effect on next game/script start, and saves require a closed game.",
                  "launch and prepare_previews accept skip_preview_categories (weapons, vehicles, gear) to skip new renders while validating caches, and missing_previews_only=true to keep intact indexed generated/default images even after model/renderer updates and fill missing entries only. launch also accepts quick_launch=true to skip all preview discovery and rendering, leaving existing artwork unchanged. Neither bypasses launch safety or approval.",
                  "download_previews installs pinned vanilla image packs without rendering. Optional categories selects weapons, vehicles and/or gear; omission selects all. Requires reviewed game-write authority and a closed game. Generated/custom artwork is preserved.",
                  "During a launch apply, send cancel_launch with its review_id in the same agent-api session. A requested acknowledgement is not completion; wait for the apply result. Cancellation never terminates GTA after dispatch.",
                  "Preview runs start with one worker. While progress.preview_render.enabled is true, set_preview_workers(review_id, workers) adjusts the active review's scheduling limit (1–8, hardware constrained). Lowering drains active jobs without killing them. Timings, RAM and advisory warnings are in progress.preview_render; GPU memory is not measured.",
                  "CLI review emits a 5-minute plan; CLI apply requires its approval hash and explicit write authority.",
                  "No automatic action replay. Reinspect files/receipts after an interrupted write.",
                  "Field schemas describe the transport; the shared service validates package, path, configuration and domain constraints."],
    }


class LauncherAPI:
    def __init__(self, service: LauncherService, *, allow_writes=False):
        self.service = service
        self.allow_writes = allow_writes

    @property
    def progress(self): return self.service.progress

    @progress.setter
    def progress(self, value): self.service.progress = value

    @property
    def rpf_progress(self): return getattr(self.service, "rpf_progress", None)

    @property
    def launch_cancellation(self): return self.service.launch_cancellation

    def cancel_launch(self, payload):
        self.validate(payload, ["review_id"])
        return self.service.cancel_launch(payload)

    @property
    def preview_render_control(self): return self.service.preview_render_control

    def set_preview_workers(self, payload):
        self.validate(payload, ['review_id', 'workers'])
        return self.service.set_preview_workers(payload)

    @staticmethod
    def validate(payload, fields):
        if not isinstance(payload, dict) or set(payload) - set(fields):
            raise ValueError("Unknown or invalid Launcher API parameters")
        for key, value in payload.items():
            expected = schema([key])["properties"][key]["type"]
            cls = {"string": str, "object": dict, "boolean": bool, "array": list, "integer": int}[expected]
            if type(value) is not cls:
                raise ValueError(f"Invalid type for {key}; expected {expected}")
            if key in {"skip_preview_categories", "categories"}:
                from allin1.preview_policy import validate_skip_categories
                validate_skip_categories(value)
                # Omit download categories to choose all packs.  An explicit
                # empty list is not a meaningful or reviewable download.
                if key == "categories" and not value:
                    raise ValueError("categories must select at least one preview category")
            if key == "workers" and not 1 <= value <= MAX_PREVIEW_WORKERS:
                raise ValueError(f"workers must be an integer from 1 to {MAX_PREVIEW_WORKERS}")

    def read(self, operation, payload):
        if operation not in READS and operation not in EXTERNAL:
            raise ValueError("Unknown Launcher API operation")
        self.validate(payload, READS.get(operation, []))
        if operation in EXTERNAL and not self.allow_writes:
            raise ValueError("External application opening requires --allow-writes")
        result = self.service.read(operation, payload)
        if operation == "catalog":
            return {**result, "api": contract(), "agent_authority": {"writes": self.allow_writes,
                    "game_writes": self.service.allow_game_writes, "launch": self.service.allow_launch}}
        return result

    def review(self, payload):
        action = payload.get("action")
        if not isinstance(action, str) or action not in ACTION_FIELDS:
            raise ValueError("Unknown Launcher API action")
        self.validate(payload, ["action", "config", *ACTION_FIELDS[action]])
        return {**self.service.review(payload), "executed": False}

    def apply(self, payload):
        self.validate(payload, ["review_id", "review_sha256", "confirmed"])
        if not self.allow_writes: raise ValueError("Mutations require --allow-writes")
        return {**self.service.apply(payload), "executed": True}

    def plan(self, payload):
        if payload.get("action") == "sdk_install_release" and self.service.sdk_release is None:
            self.read("check_sdk_update", {})
        review = self.review(payload)
        # Capture defaults now; never substitute new preferences during approval.
        request = copy.deepcopy(payload)
        if "config" not in request:
            from allin1.desktop_service import serializable
            request["config"] = serializable(self.service.config())
        plan = {"schema_version": 1, "kind": "launcher_approval_plan", "executed": False,
                "project": str(self.service.project), "state": str(self.service.state),
                "expires_at": time.time() + 300, "request": request,
                "state_sha256": self.service.snapshot(request), "review": review}
        return {**plan, "approval_sha256": digest(plan)}

    def apply_plan(self, plan, approval_sha256, *, confirmed=False):
        if not self.allow_writes or confirmed is not True:
            raise ValueError("Applying a plan requires --allow-writes and --confirm")
        if not isinstance(plan, dict): raise ValueError("Invalid Launcher approval plan")
        evidence = {key: value for key, value in plan.items() if key != "approval_sha256"}
        if not approval_sha256 or digest(evidence) != approval_sha256 or plan.get("approval_sha256") != approval_sha256:
            raise ValueError("Approval hash does not match the reviewed plan")
        if (plan.get("schema_version") != 1 or plan.get("kind") != "launcher_approval_plan"
                or plan.get("project") != str(self.service.project) or plan.get("state") != str(self.service.state)
                or not isinstance(plan.get("expires_at"), (int, float)) or not time.time() < plan["expires_at"] <= time.time() + 301):
            raise ValueError("Plan expired or belongs to another Launcher context")
        if plan["request"].get("action") == "sdk_install_release" and self.service.sdk_release is None:
            self.read("check_sdk_update", {})
        if self.service.snapshot(plan["request"]) != plan["state_sha256"]:
            raise ValueError("Files changed after review; create a fresh plan")
        review = self.review(plan["request"])
        from allin1.release_paths import contained, no_links
        claimed = contained(self.service.state, "approvals/" + approval_sha256 + ".claimed")
        no_links(claimed.parent).mkdir(parents=True, exist_ok=True)
        # Claim before execution. Even a crashed or uncertain writer cannot be
        # automatically replayed by a second CLI process.
        with no_links(claimed).open("xb") as stream:
            stream.write(b"Single-use approval claimed; inspect receipts before retrying.\n")
        return self.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
