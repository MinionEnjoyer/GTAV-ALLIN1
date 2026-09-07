fn main() {
    println!("cargo:rerun-if-env-changed=ALLIN1_LAUNCHER_BUILD_ID");
    println!("cargo:rerun-if-env-changed=ALLIN1_LAUNCHER_RUNTIME");
    if std::env::var("PROFILE").as_deref() == Ok("release") {
        assert!(!tauri_build::is_dev(), "Release builds must enable tauri/custom-protocol to embed the frontend");
        let build_id = std::env::var("ALLIN1_LAUNCHER_BUILD_ID")
            .expect("Release builds require tools/launcher_desktop_candidate.py");
        assert!(build_id.len() == 32 && build_id.bytes().all(|c| c.is_ascii_hexdigit()), "Invalid Launcher build identity");
        println!("cargo:rustc-env=ALLIN1_LAUNCHER_BUILD_ID={build_id}");
    }
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["launcher_request", "select_path", "close_launcher", "frontend_ready", "initial_handoff"])
    )).expect("Launcher build manifest");
}
