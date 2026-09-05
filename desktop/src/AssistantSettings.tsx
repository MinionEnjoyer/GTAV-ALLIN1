import { useState } from "react";
import type { RecordData } from "./client";
import { Field } from "./Fields";

const thinkingControls = ["thinking.chat_template_kwargs", "thinking.enable_thinking", "thinking.reasoning_effort"];
export default function AssistantSettings({ session, draft, setDraft, locked, review, choose, inspect }: {
  session: RecordData; draft?: RecordData; setDraft: (value: RecordData) => void; locked: boolean;
  review: (action: string, payload?: RecordData) => void;
  choose: (kind: string, adopt: (path: string) => void) => Promise<void>;
  inspect: (payload: RecordData, adopt: (value: RecordData) => void) => void;
}) {
  const [profile, setProfile] = useState("recommended"), [hardware, setHardware] = useState<RecordData | null>(null);
  const status = session.status, values = draft ?? status?.config;
  if (!values) return null;
  const source = session.sources.find((item: RecordData) => item.profile === profile);
  const change = (key: string, value: unknown) => setDraft({ ...values, [key]: value });
  const field = (key: string, label: string, choices?: string[], limits: RecordData = {}) =>
    <Field key={key} name={key} descriptor={{ label, choices, ...limits }} value={values[key]} disabled={locked}
      change={(value) => change(key, value)} />;
  return <section aria-label="Optional assistant">
    <h2>Optional assistant</h2>
    <p>{status.detail}</p><p className="path">{status.root}</p>
    <p>This Launcher-owned pack is separate from the SDK. Installing a model does not enable it or start inference. API secrets stay in environment variables.</p>
    <div className="split">
      <section>
        <h3>Managed model pack</h3>
        <label>Download profile<select value={profile} disabled={locked || !!draft} onChange={(event) => { setProfile(event.target.value); setHardware(null); }}>
          {session.sources.map((item: RecordData) => <option key={item.profile} value={item.profile}>{item.profile} · {item.display_name}</option>)}
        </select></label>
        {source && <p>{source.display_name} · {(source.total_download_bytes / 1024 ** 3).toFixed(2)} GiB download · {source.minimum_ram_gb} GB minimum RAM</p>}
        <div className="toolbar">
          <button disabled={locked} onClick={() => inspect({ module: "assistant_hardware", profile }, (value) => setHardware(value.hardware))}>Check assistant hardware</button>
          <button disabled={locked || !!draft} onClick={() => review("assistant_install_qwen", { profile })}>Review model download</button>
          <button disabled={locked || !!draft} onClick={() => void choose("package", (source) => review("assistant_install_archive", { source }))}>Import assistant pack</button>
          <button disabled={locked || !!draft || !status.installed} onClick={() => review("assistant_uninstall")}>Remove managed assistant pack</button>
        </div>
        {hardware && <div aria-label="Assistant hardware assessment">
          <p>{hardware.compatible ? "Hardware check passed" : "Hardware requirements not met"}</p>
          {[...hardware.blockers, ...hardware.warnings].map((message: string) => <p key={message}>{message}</p>)}
          <p>Required free space: {(hardware.required_free_disk_bytes / 1024 ** 3).toFixed(2)} GiB</p>
        </div>}
        <p>Removal keeps configuration and custom runtime/model files outside the managed pack.</p>
      </section>
      <section>
        <h3>Assistant configuration</h3>
        <div className="fields">
          <Field name="mode" descriptor={{ label: "Assistant mode", choices: ["disabled", "managed_local", "custom_local", "compatible_api"] }} value={values.mode} disabled={locked}
            change={(mode) => setDraft({ ...values, mode,
              capabilities: values.capabilities.length ? values.capabilities : ["structured_output.json_schema", "thinking.chat_template_kwargs", "prompt_cache"],
              thinking: values.thinking === "provider_default" ? "disabled" : values.thinking })} />
          {field("workflow", "Assistant workflow", ["installer", "diagnostic"])}
          {field("profile", "Configuration profile", ["low", "recommended", "custom"])}
          {field("context_tokens", "Context tokens", undefined, { type: "integer", minimum: 2048, maximum: 32768 })}
          {field("temperature", "Temperature", undefined, { minimum: 0, maximum: 1, step: 0.05 })}
        </div>
        {values.mode === "compatible_api" && <div className="fields">
          {field("endpoint", "Compatible API URL")}{field("model_name", "API model name")}{field("api_key_env", "API key environment variable")}
        </div>}
        {values.mode === "custom_local" && <>
          {field("runtime_path", "Custom runtime path")}
          <button disabled={locked} onClick={() => void choose("assistant_runtime", (path) => change("runtime_path", path))}>Browse custom runtime</button>
          {field("model_path", "Custom GGUF model path")}
          <button disabled={locked} onClick={() => void choose("assistant_model", (path) => change("model_path", path))}>Browse custom model</button>
        </>}
        {values.mode !== "disabled" && <>
          <div className="fields">
            <Field name="thinking_control" descriptor={{ label: "Provider thinking control", choices: thinkingControls }}
              value={values.capabilities.find((value: string) => thinkingControls.includes(value)) ?? thinkingControls[0]} disabled={locked}
              change={(value) => change("capabilities", [...values.capabilities.filter((item: string) => !thinkingControls.includes(item)), value])} />
            {field("thinking", "Thinking", ["disabled", "enabled", "provider_default"])}
            {field("llama_cpp_revision", "llama.cpp revision")}
            {field("model_sha256", "Model SHA-256 (optional)")}
          </div>
        </>}
        <button disabled={locked || !draft} onClick={() => review("assistant_save", { assistant_config: values })}>Review assistant settings</button>
      </section>
    </div>
  </section>;
}
