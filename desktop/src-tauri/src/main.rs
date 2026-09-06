#![cfg_attr(windows, windows_subsystem = "windows")]
use serde_json::{json, Value};
mod protocol;
mod package_probe;
mod launch_cancel;
use std::io::{BufReader, Read, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::Receiver;
use std::sync::{atomic::{AtomicBool, AtomicU64, Ordering}, Arc, Mutex};
use tauri::{Emitter, Manager, State, WindowEvent};

const OPERATIONS: &[&str] = &["catalog", "inspect", "review", "apply", "load_profile", "health", "check_update", "read_garages", "check_sdk_update", "startup_status", "open_activity_folder", "open_launcher_release"];
#[derive(Default)]
struct PendingHandoff { listening: bool, request: Option<Value> }
struct Handoff(Mutex<PendingHandoff>);
fn parse_handoff(args: &[String]) -> Option<Value> {
    let value = |flag: &str| args.iter().position(|arg| arg == flag).and_then(|i| args.get(i + 1));
    if value("--workspace").map(String::as_str) != Some("packages") { return None; }
    let package = value("--package-id");
    if package.is_some_and(|id| id.len() < 2 || id.len() > 64 || !id.bytes().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"._-".contains(&c))) { return None; }
    let traffic = match value("--traffic").map(String::as_str) { Some("on") => Some(true), Some("off") => Some(false), None => None, _ => return None };
    if traffic.is_some() && package.is_none() { return None; }
    Some(json!({"schema_version":1,"workspace":"mods","package_id":package,"traffic":traffic}))
}
struct Sidecar { child: Child, input: Option<ChildStdin>, output: Option<Receiver<Result<String, String>>>, diagnostics: Arc<Mutex<Vec<u8>>> }
impl Sidecar {
    fn finish_without_more_requests(&mut self) {
        // EOF asks the single-request service to exit after its current work.
        // The detached frame reader drains stdout without terminating a writer.
        self.input.take();
        self.output.take();
    }
}
struct Broker { process: Mutex<Option<Sidecar>>, busy: AtomicBool, uncertain: AtomicBool, write_pending: AtomicBool, closing: AtomicBool, ready: AtomicBool, sequence: AtomicU64, launch_cancel: launch_cancel::LaunchCancel }
impl Broker {
    fn new() -> Self { Self { process: Mutex::new(None), busy: AtomicBool::new(false), uncertain: AtomicBool::new(false), write_pending: AtomicBool::new(false), closing: AtomicBool::new(false), ready: AtomicBool::new(false), sequence: AtomicU64::new(1), launch_cancel: Default::default() } }
    fn start(&self, app: &tauri::AppHandle) -> Result<Sidecar, String> {
        let (mut command, project) = if cfg!(debug_assertions) {
            let project = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap().to_path_buf();
            let python = std::env::var_os("ALLIN1_LAUNCHER_PYTHON").map(std::path::PathBuf::from).unwrap_or_else(|| project.join(".venv/Scripts/python.exe"));
            let mut command = Command::new(python);
            command.args(["-m", "allin1.desktop_host"]);
            command.env("PYTHONPATH", project.join("src"));
            (command, project)
        } else {
            let root = app.path().resource_dir().map_err(|e| e.to_string())?;
            let executable = root.join("sidecar/ALLIN1-Launcher-Sidecar.exe");
            if !executable.is_file() { return Err("Packaged Launcher service is missing; use the qualified installer".into()); }
            let mut command = Command::new(executable);
            command.arg("--expected-build-id").arg(option_env!("ALLIN1_LAUNCHER_BUILD_ID").ok_or("Launcher shell has no build identity")?);
            (command, root.join("resources"))
        };
        command.arg("--project-root").arg(&project);
        // A developer-only isolated preview never receives game-write or launch authority.
        let preview = if cfg!(debug_assertions) { std::env::var_os("ALLIN1_LAUNCHER_PREVIEW_STATE") } else { None };
        if let Some(state) = preview { command.arg("--state-root").arg(state); }
        else { command.args(["--allow-game-writes", "--allow-launch"]); }
        command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
        command.env("ALLIN1_LAUNCHER_EXECUTABLE", std::env::current_exe().map_err(|e| e.to_string())?);
        #[cfg(windows)] { use std::os::windows::process::CommandExt; command.creation_flags(windows_sys::Win32::System::Threading::CREATE_NO_WINDOW); }
        let mut child = command.spawn().map_err(|e| format!("Could not start Launcher service: {e}"))?;
        let input = child.stdin.take().ok_or("Service stdin unavailable")?;
        let output = protocol::frames(BufReader::new(child.stdout.take().ok_or("Service stdout unavailable")?));
        let errors = child.stderr.take().ok_or("Service stderr unavailable")?;
        // Drain diagnostics so a verbose native tool cannot deadlock the pipe.
        let diagnostics = Arc::new(Mutex::new(Vec::new()));
        let captured = diagnostics.clone();
        std::thread::spawn(move || {
            let mut reader = BufReader::new(errors); let mut block = [0; 4096];
            while let Ok(count) = reader.read(&mut block) {
                if count == 0 { break; }
                if let Ok(mut tail) = captured.lock() {
                    tail.extend_from_slice(&block[..count]);
                    let excess = tail.len().saturating_sub(8192);
                    tail.drain(..excess);
                }
            }
        });
        Ok(Sidecar { child, input: Some(input), output: Some(output), diagnostics })
    }
    fn request(&self, app: &tauri::AppHandle, operation: &str, payload: Value) -> Result<Value, String> {
        if self.closing.load(Ordering::Acquire) || self.uncertain.load(Ordering::Acquire) { return Err("Launcher service stopped or its last operation has an unknown outcome. Reconnect explicitly; do not repeat a write until its outcome is verified.".into()); }
        let mut slot = self.process.lock().map_err(|_| "Service lock poisoned")?;
        if slot.is_none() { *slot = Some(self.start(app)?); }
        let service = slot.as_mut().unwrap();
        let id = format!("launcher-{}", self.sequence.fetch_add(1, Ordering::Relaxed));
        let request = json!({"schema_version":1,"request_id":id,"operation":operation,"payload":payload});
        let mut encoded = serde_json::to_vec(&request).map_err(|e| e.to_string())?;
        if encoded.len() >= 1024 * 1024 { return Err("Request exceeds 1 MiB".into()); }
        encoded.push(b'\n');
        self.uncertain.store(true, Ordering::Release);
        self.write_pending.store(operation == "apply", Ordering::Release);
        let result = (|| {
        let input = service.input.as_mut().ok_or("Launcher service is finishing an interrupted request")?;
        input.write_all(&encoded).and_then(|_| input.flush()).map_err(|e| e.to_string())?;
        let cancel_id = format!("{id}-cancel");
        let mut cancel_pending = false;
        let mut terminal = None;
        let mut last_frame = std::time::Instant::now();
        loop {
            if let Some(review) = self.launch_cancel.take() {
                let control = json!({"schema_version":1,"request_id":cancel_id,"operation":"cancel_launch","payload":{"review_id":review}});
                writeln!(input, "{control}").and_then(|_| input.flush()).map_err(|e| e.to_string())?;
                cancel_pending = true;
            }
            let frame = protocol::poll_frame(service.output.as_ref().ok_or("Launcher response channel detached")?, std::time::Duration::from_millis(100)).map_err(|error| {
                let detail = service.diagnostics.lock().map(|bytes| String::from_utf8_lossy(&bytes).trim().to_string()).unwrap_or_default();
                if detail.is_empty() { error } else { format!("{error}\nService diagnostic: {detail}") }
            })?;
            let Some(line) = frame else {
                if last_frame.elapsed() >= protocol::RESPONSE_TIMEOUT { return Err("Launcher service response timed out".into()); }
                continue;
            };
            last_frame = std::time::Instant::now();
            let identity: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
            if cancel_pending && identity["request_id"] == cancel_id {
                match protocol::decode(&line, &cancel_id)? {
                    protocol::Response::Result(_) | protocol::Response::Error(_) => cancel_pending = false,
                    _ => return Err("Unexpected cancellation response".into()),
                }
            } else {
                match protocol::decode(&line, &id)? {
                    protocol::Response::Progress(payload) => {
                        if operation == "apply" { self.launch_cancel.update(&payload); }
                        let _ = app.emit("launcher-progress", payload);
                    }
                    response => { self.launch_cancel.clear(); terminal = Some(response); }
                }
            }
            // Drain the control acknowledgement even if the cancelled apply
            // finishes first, so it cannot contaminate the next request.
            if !cancel_pending {
                if let Some(response) = terminal.take() {
                    self.uncertain.store(false, Ordering::Release);
                    self.write_pending.store(false, Ordering::Release);
                    return match response {
                        protocol::Response::Result(payload) => Ok(payload),
                        protocol::Response::Error(message) => Err(message),
                        _ => unreachable!(),
                    };
                }
            }
        }
        })();
        self.launch_cancel.clear();
        if result.is_err() && self.uncertain.load(Ordering::Acquire) {
            service.finish_without_more_requests();
        }
        result
    }
    fn close(&self) -> Result<(), String> {
        if self.busy.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire).is_err() { return Err("Wait for the current Launcher operation to finish".into()); }
        let result = (|| {
            let mut slot = self.process.lock().map_err(|_| "Service lock poisoned")?;
            if let Some(service) = slot.as_mut() {
                if self.uncertain.load(Ordering::Acquire) && self.write_pending.load(Ordering::Acquire) && service.child.try_wait().map_err(|e| e.to_string())?.is_none() { return Err("A service write has an unknown outcome; automatic termination is blocked".into()); }
                // The request loop has returned a terminal result; no write is active.
                let _ = service.child.kill(); let _ = service.child.wait();
            }
            self.closing.store(true, Ordering::Release); *slot = None; Ok(())
        })();
        self.busy.store(false, Ordering::Release); result
    }
    fn reconnect(&self) -> Result<Value, String> {
        if self.closing.load(Ordering::Acquire) { return Err("Launcher is closing".into()); }
        let mut slot = self.process.lock().map_err(|_| "Service lock poisoned")?;
        if let Some(service) = slot.as_mut() {
            if self.uncertain.load(Ordering::Acquire) && self.write_pending.load(Ordering::Acquire)
                && service.child.try_wait().map_err(|e| e.to_string())?.is_none() {
                return Err("Cannot terminate an uncertain writer. Wait for the service to exit and verify the files/receipts before retrying; no action was replayed.".into());
            }
            service.child.kill().or_else(|error| if service.child.try_wait()?.is_some() { Ok(()) } else { Err(error) }).map_err(|e| e.to_string())?;
            service.child.wait().map_err(|e| e.to_string())?;
        }
        *slot = None;
        self.uncertain.store(false, Ordering::Release);
        self.write_pending.store(false, Ordering::Release);
        Ok(json!({"reconnected":true,"replayed":false,"reviews_invalidated":true}))
    }
}

#[tauri::command]
async fn launcher_request(app: tauri::AppHandle, broker: State<'_, Arc<Broker>>, operation: String, payload: Value) -> Result<Value, String> {
    if operation == "cancel_launch" { return broker.launch_cancel.request(&payload); }
    if operation != "reconnect_service" && !OPERATIONS.contains(&operation.as_str()) { return Err("Unknown Launcher operation".into()); }
    if broker.busy.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire).is_err() { return Err("Another Launcher operation is running".into()); }
    let broker = broker.inner().clone();
    tauri::async_runtime::spawn_blocking(move || { let result = if operation == "reconnect_service" { broker.reconnect() } else { broker.request(&app, &operation, payload) }; broker.busy.store(false, Ordering::Release); result }).await.map_err(|e| e.to_string())?
}
#[tauri::command]
fn frontend_ready(broker: State<'_, Arc<Broker>>) { broker.ready.store(true, Ordering::Release); }
#[tauri::command]
fn initial_handoff(state: State<'_, Handoff>) -> Option<Value> {
    let mut pending = state.0.lock().ok()?;
    pending.listening = true;
    pending.request.take()
}
#[tauri::command]
fn close_launcher(window: tauri::WebviewWindow, broker: State<'_, Arc<Broker>>) -> Result<(), String> { broker.close()?; window.destroy().map_err(|e| e.to_string()) }
#[tauri::command]
async fn select_path(kind: String) -> Result<Option<String>, String> {
    let dialog = rfd::AsyncFileDialog::new();
    let selected = match kind.as_str() {
        "game" | "folder" => dialog.pick_folder().await,
        "package" => dialog.add_filter("ALLIN1 package", &["zip", "toml"]).pick_file().await,
        "json" => dialog.add_filter("Saved content", &["json"]).pick_file().await,
        "assistant_runtime" => dialog.add_filter("Local assistant runtime", &["exe"]).pick_file().await,
        "assistant_model" => dialog.add_filter("GGUF model", &["gguf"]).pick_file().await,
        "diagnostics" => dialog.set_file_name("ALLIN1-diagnostics.zip").add_filter("ZIP", &["zip"]).save_file().await,
        "export_json" => dialog.set_file_name("ALLIN1-garages.json").add_filter("JSON", &["json"]).save_file().await,
        "export_profile" => dialog.set_file_name("ALLIN1-profile.toml").add_filter("TOML", &["toml"]).save_file().await,
        _ => return Err("Unknown dialog kind".into()),
    };
    Ok(selected.map(|handle| handle.path().to_string_lossy().into_owned()))
}
fn main() {
    if std::env::args().nth(1).as_deref() == Some("--verify-embedded-frontend") {
        match package_probe::inspect(&tauri::generate_context!(), option_env!("ALLIN1_LAUNCHER_BUILD_ID").unwrap_or(""), env!("CARGO_PKG_VERSION")) {
            Ok(report) => println!("{report}"),
            Err(error) => { eprintln!("{error}"); std::process::exit(1); }
        }
        return;
    }
    let initial = parse_handoff(&std::env::args().collect::<Vec<_>>());
    tauri::Builder::default().plugin(tauri_plugin_single_instance::init(|app, args, _| {
            if let Some(request) = parse_handoff(&args) {
                if let Ok(mut state) = app.state::<Handoff>().0.lock() {
                    if !state.listening || app.emit("launcher-handoff", &request).is_err() { state.request = Some(request); }
                }
            }
            if let Some(window) = app.get_webview_window("main") { let _ = window.unminimize(); let _ = window.set_focus(); }
        }))
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .manage(Arc::new(Broker::new()))
        .manage(Handoff(Mutex::new(PendingHandoff { listening: false, request: initial })))
        .on_window_event(|window, event| { if let WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close(); let broker = window.state::<Arc<Broker>>();
            if broker.ready.load(Ordering::Acquire) { let _ = window.emit("launcher-close-requested", ()); }
            else if broker.close().is_ok() { let _ = window.destroy(); }
        } })
        .invoke_handler(tauri::generate_handler![launcher_request, select_path, close_launcher, frontend_ready, initial_handoff])
        .run(tauri::generate_context!()).expect("ALLIN1 Launcher runtime");
}

#[cfg(test)]
mod tests {
    use super::*;
    fn args(values: &[&str]) -> Vec<String> { values.iter().map(|v| v.to_string()).collect() }
    #[test]
    fn handoff_only_reveals_packages_never_executes_mutations() {
        let request = parse_handoff(&args(&["launcher", "--workspace", "packages", "--package-id", "kriss-vector", "--traffic", "on"])).unwrap();
        assert_eq!(request["workspace"], "mods"); assert_eq!(request["traffic"], true);
        assert!(request.get("action").is_none());
        for values in [vec!["--workspace", "install"], vec!["--workspace", "packages", "--package-id", "../escape"], vec!["--workspace", "packages", "--traffic", "on"]] {
            assert!(parse_handoff(&args(&values)).is_none());
        }
    }
    #[test]
    fn close_refuses_active_requests_and_idle_close_is_final() {
        let broker = Broker::new(); broker.busy.store(true, Ordering::Release);
        assert!(broker.close().is_err()); assert!(!broker.closing.load(Ordering::Acquire));
        broker.busy.store(false, Ordering::Release); assert!(broker.close().is_ok());
        assert!(broker.closing.load(Ordering::Acquire));
    }
    #[cfg(windows)]
    fn waiting_service() -> Sidecar {
        use std::os::windows::process::CommandExt;
        // An owned, noninteractive stdin waiter: no game, network or files.
        let mut child = Command::new("powershell.exe")
            .args(["-NoProfile", "-NonInteractive", "-Command", "[Console]::In.ReadLine() | Out-Null"])
            .creation_flags(windows_sys::Win32::System::Threading::CREATE_NO_WINDOW)
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn().unwrap();
        let input = child.stdin.take().unwrap();
        let output = protocol::frames(BufReader::new(child.stdout.take().unwrap()));
        Sidecar { child, input: Some(input), output: Some(output), diagnostics: Arc::new(Mutex::new(Vec::new())) }
    }
    #[cfg(windows)]
    #[test]
    fn reconnect_terminates_stalled_read_only_service_without_replay() {
        let broker = Broker::new();
        *broker.process.lock().unwrap() = Some(waiting_service());
        broker.uncertain.store(true, Ordering::Release);
        let result = broker.reconnect().unwrap();
        assert_eq!(result["replayed"], false);
        assert_eq!(result["reviews_invalidated"], true);
        assert!(broker.process.lock().unwrap().is_none());
        assert!(!broker.uncertain.load(Ordering::Acquire));
    }
    #[cfg(windows)]
    #[test]
    fn uncertain_writer_is_not_terminated_and_reconnect_waits_for_exit() {
        let broker = Broker::new();
        *broker.process.lock().unwrap() = Some(waiting_service());
        broker.uncertain.store(true, Ordering::Release);
        broker.write_pending.store(true, Ordering::Release);
        let refused = broker.reconnect();
        let close_refused = broker.close();
        // Only the test owns and terminates this inert waiter, never the broker.
        let alive = {
            let mut slot = broker.process.lock().unwrap();
            let service = slot.as_mut().unwrap();
            let alive = service.child.try_wait().unwrap().is_none();
            service.child.kill().unwrap(); service.child.wait().unwrap(); alive
        };
        assert!(refused.unwrap_err().contains("uncertain writer"));
        assert!(close_refused.is_err()); assert!(alive);
        assert!(!broker.closing.load(Ordering::Acquire));
        assert!(broker.reconnect().is_ok());
        assert!(!broker.write_pending.load(Ordering::Acquire));
    }
    #[cfg(windows)]
    #[test]
    fn interrupted_response_requests_graceful_exit_without_killing_service() {
        let mut service = waiting_service();
        service.finish_without_more_requests();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        let exited = loop {
            if let Some(status) = service.child.try_wait().unwrap() { break status.success(); }
            if std::time::Instant::now() >= deadline { break false; }
            std::thread::sleep(std::time::Duration::from_millis(10));
        };
        if !exited { let _ = service.child.kill(); let _ = service.child.wait(); }
        assert!(exited, "stdin EOF should allow the owned fixture to finish normally");
    }
}
