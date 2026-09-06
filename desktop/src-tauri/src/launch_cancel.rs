//! Only a cancellation signal bypasses the ordinary single-operation broker.
use serde_json::{json, Value};
use std::sync::Mutex;

#[derive(Default)]
struct Active { review: String, available: bool, queued: bool, requested: bool }
#[derive(Default)]
pub struct LaunchCancel(Mutex<Active>);
impl LaunchCancel {
    pub fn update(&self, progress: &Value) {
        let mut active = self.0.lock().unwrap();
        let review = progress["launch_review_id"].as_str().unwrap_or("");
        if active.review != review { *active = Active { review: review.into(), ..Default::default() }; }
        active.available = !review.is_empty() && progress["cancellable"] == true;
    }
    pub fn request(&self, payload: &Value) -> Result<Value, String> {
        let mut active = self.0.lock().map_err(|_| "Launch cancellation lock poisoned")?;
        let review = payload["review_id"].as_str().unwrap_or("");
        if payload.as_object().map(|p| p.len()) != Some(1) || review.is_empty() || active.review != review {
            return Err("Cancel launch requires the active launch review".into());
        }
        if active.requested { return Ok(json!({"status":"requested"})); }
        if !active.available { return Err("Launch preparation has finished; GTA will not be terminated".into()); }
        active.requested = true;
        active.queued = true;
        Ok(json!({"status":"requested"}))
    }
    pub fn take(&self) -> Option<String> {
        let mut active = self.0.lock().unwrap();
        if !active.queued { return None; }
        active.queued = false;
        Some(active.review.clone())
    }
    pub fn clear(&self) { *self.0.lock().unwrap() = Active::default(); }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_current_preparing_launch_can_be_cancelled_once() {
        let control = LaunchCancel::default();
        assert!(control.request(&json!({"review_id":"a"})).is_err());
        control.update(&json!({"launch_review_id":"a","cancellable":true}));
        assert!(control.request(&json!({"review_id":"stale"})).is_err());
        assert!(control.request(&json!({"review_id":"a","pid":42})).is_err());
        control.request(&json!({"review_id":"a"})).unwrap();
        control.request(&json!({"review_id":"a"})).unwrap();
        assert_eq!(control.take(), Some("a".into()));
        assert_eq!(control.take(), None);
        control.clear();
        control.update(&json!({"launch_review_id":"b","cancellable":false}));
        assert!(control.request(&json!({"review_id":"b"})).is_err());
        assert!(control.request(&json!({"review_id":"a"})).is_err());
    }
}
