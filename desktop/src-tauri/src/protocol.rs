//! Bounded, versioned Launcher frames. Human messages are never protocol evidence.
use serde::Deserialize;
use serde_json::Value;
use std::io::{BufRead, Read};
use std::sync::mpsc::{self, Receiver};
use std::time::Duration;

const MAX_RESPONSE: u64 = 4 * 1024 * 1024;
pub const RESPONSE_TIMEOUT: Duration = Duration::from_secs(120);

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope {
    schema_version: u32,
    request_id: String,
    kind: String,
    payload: Value,
}

pub enum Response { Progress(Value), Result(Value), Error(String) }

fn valid_rpf_work(work: &Value) -> bool {
    let fields = ["estimated_actions", "completed_actions", "entries", "elapsed_seconds", "budget_seconds", "active_seconds"];
    work.is_object()
        && fields.iter().all(|field| work[*field].as_u64().is_some())
        && work["estimated_actions"].as_u64().unwrap_or(0) > 0
        && work["completed_actions"].as_u64() <= work["estimated_actions"].as_u64()
        && work["budget_seconds"].as_u64().unwrap_or(0) > 0
        && work["slow_action"].is_boolean() && work["budget_exceeded"].is_boolean()
}

pub fn decode(line: &str, request_id: &str) -> Result<Response, String> {
    let row: Envelope = serde_json::from_str(line).map_err(|e| format!("Invalid Launcher response: {e}"))?;
    if row.schema_version != 1 || row.request_id != request_id || !row.payload.is_object() {
        return Err("Launcher response identity or payload mismatch".into());
    }
    match row.kind.as_str() {
        "progress" => {
            if row.payload["schema_version"].as_u64() != Some(1)
                || row.payload["event"] != "launcher.progress"
                || !row.payload.get("percentage").is_some_and(|value|
                    value.is_null() || value.as_u64().is_some_and(|number| number <= 100))
                || !row.payload["message"].is_string()
                || row.payload.get("heartbeat").is_some_and(|value| !value.is_boolean())
                || row.payload.get("rpf_work").is_some_and(|value| !valid_rpf_work(value)) {
                return Err("Invalid Launcher progress schema".into());
            }
            Ok(Response::Progress(row.payload))
        }
        "result" => Ok(Response::Result(row.payload)),
        "error" => row.payload["message"].as_str().map(|v| Response::Error(v.into()))
            .ok_or_else(|| "Invalid Launcher error schema".into()),
        _ => Err("Unknown Launcher response kind".into()),
    }
}

pub fn read_frame(reader: &mut impl BufRead) -> Result<String, String> {
    let mut line = String::new();
    let count = reader.take(MAX_RESPONSE + 1).read_line(&mut line).map_err(|e| e.to_string())?;
    if count == 0 || count as u64 > MAX_RESPONSE || !line.ends_with('\n') {
        return Err("Launcher service ended or exceeded its response limit".into());
    }
    Ok(line)
}

pub fn frames(mut reader: impl BufRead + Send + 'static) -> Receiver<Result<String, String>> {
    // A hung read cannot trap the command thread. Bound queued memory as well
    // as each frame; no unbounded stdout collection or detached request retry.
    let (send, receive) = mpsc::sync_channel(2);
    std::thread::spawn(move || {
        let mut connected = true;
        loop {
            let frame = read_frame(&mut reader);
            let failed = frame.is_err();
            // On an uncertain operation the broker closes stdin and detaches
            // this receiver, but must still drain stdout until the service
            // finishes. Do not break its pipe mid-write or accumulate frames.
            if connected && send.send(frame).is_err() { connected = false; }
            if failed { break; }
        }
    });
    receive
}

pub fn next_frame(receive: &Receiver<Result<String, String>>, timeout: Duration) -> Result<String, String> {
    receive.recv_timeout(timeout).map_err(|e| format!("Launcher service connection interrupted: {e}"))?
}

pub fn poll_frame(receive: &Receiver<Result<String, String>>, timeout: Duration) -> Result<Option<String>, String> {
    match receive.recv_timeout(timeout) {
        Ok(frame) => frame.map(Some),
        Err(mpsc::RecvTimeoutError::Timeout) => Ok(None),
        Err(error) => Err(format!("Launcher service connection interrupted: {error}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::io::Cursor;

    fn frame(kind: &str, payload: Value) -> String {
        json!({"schema_version":1,"request_id":"one","kind":kind,"payload":payload}).to_string()
    }
    #[test]
    fn terminal_and_versioned_progress_frames() {
        assert!(matches!(decode(&frame("result", json!({"saved":true})), "one"), Ok(Response::Result(_))));
        assert!(matches!(decode(&frame("error", json!({"message":"denied"})), "one"), Ok(Response::Error(_))));
        assert!(matches!(decode(&frame("progress", json!({"schema_version":1,"event":"launcher.progress","percentage":50,"message":"staged"})), "one"), Ok(Response::Progress(_))));
        assert!(matches!(decode(&frame("progress", json!({"schema_version":1,"event":"launcher.progress","percentage":null,"message":"Checking sources"})), "one"), Ok(Response::Progress(_))));
    }
    #[test]
    fn rejects_unrelated_ambiguous_or_malformed_envelopes() {
        let valid = frame("result", json!({}));
        for invalid in [
            valid.replace("\"one\"", "\"other\""),
            valid.replace("\"schema_version\":1", "\"schema_version\":1.0"),
            valid.replace("\"schema_version\":1", "\"schema_version\":true"),
            valid.replace("\"schema_version\":1", "\"schema_version\":2"),
            valid.replace("\"schema_version\":1", "\"schema_version\":1,\"schema_version\":1"),
            valid.replace("\"schema_version\":1", "\"extra\":true,\"schema_version\":1"),
            frame("unknown", json!({})), frame("result", json!([])), frame("error", json!({})),
        ] { assert!(decode(&invalid, "one").is_err(), "{invalid}"); }
    }
    #[test]
    fn rejects_legacy_or_invalid_progress() {
        for payload in [
            json!({"percentage":50,"message":"unversioned"}),
            json!({"schema_version":1,"event":"other","percentage":50,"message":"wrong producer"}),
            json!({"schema_version":1,"event":"launcher.progress","percentage":101,"message":"bad"}),
            json!({"schema_version":1,"event":"launcher.progress","percentage":-1,"message":"bad"}),
            json!({"schema_version":1,"event":"launcher.progress","percentage":0.5,"message":"bad"}),
            json!({"schema_version":1,"event":"launcher.progress","message":"missing percentage"}),
        ] { assert!(decode(&frame("progress", payload), "one").is_err()); }
    }
    #[test]
    fn heartbeats_are_progress_not_completion_and_workload_metadata_is_bounded() {
        let payload = json!({"schema_version":1,"event":"launcher.progress","percentage":25,"message":"Verifying RPF",
            "heartbeat":true,"rpf_work":{"estimated_actions":1260,"completed_actions":315,"entries":420,
                "elapsed_seconds":1443,"budget_seconds":6420,"active_seconds":130,"slow_action":true,"budget_exceeded":false}});
        assert!(matches!(decode(&frame("progress", payload.clone()), "one"), Ok(Response::Progress(_))));
        for (key, value) in [("estimated_actions", json!(0)), ("completed_actions", json!(1261)),
            ("elapsed_seconds", json!(-1)), ("budget_seconds", json!(true)), ("active_seconds", json!(1.5)),
            ("slow_action", json!("yes"))] {
            let mut invalid = payload.clone(); invalid["rpf_work"][key] = value;
            assert!(decode(&frame("progress", invalid), "one").is_err());
        }
        let mut invalid = payload; invalid["heartbeat"] = json!("alive");
        assert!(decode(&frame("progress", invalid), "one").is_err());
    }
    #[test]
    fn frame_bound_and_utf8_are_enforced() {
        for invalid in [vec![], b"{}".to_vec(), vec![b'x'; MAX_RESPONSE as usize + 1], vec![255, b'\n']] {
            assert!(read_frame(&mut Cursor::new(invalid)).is_err());
        }
        assert_eq!(read_frame(&mut Cursor::new(b"{}\nnext\n")).unwrap(), "{}\n");
    }
    #[test]
    fn pipe_eof_and_missing_response_do_not_block_forever() {
        let receive = frames(Cursor::new(b"{}\n"));
        assert_eq!(next_frame(&receive, Duration::from_secs(1)).unwrap(), "{}\n");
        assert!(next_frame(&receive, Duration::from_secs(1)).is_err());
        let (_send, receive) = mpsc::sync_channel(1);
        assert!(next_frame(&receive, Duration::from_millis(5)).is_err());
    }
}
