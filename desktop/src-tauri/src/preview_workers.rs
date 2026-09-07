//! Bounded, review-scoped scheduling signal; no second mutating operation.
use serde_json::{json, Value};
use std::sync::Mutex;

#[derive(Default)]
struct Active { review: String, maximum: u64, queued: Option<u64> }
#[derive(Default)]
pub struct PreviewWorkers(Mutex<Active>);
impl PreviewWorkers {
    pub fn update(&self, progress: &Value) {
        let mut active = self.0.lock().unwrap();
        let status = &progress["preview_render"];
        let review = if status["enabled"] == true { status["review_id"].as_str().unwrap_or("") } else { "" };
        if active.review != review { *active = Active { review: review.into(), ..Default::default() }; }
        active.maximum = status["max_workers"].as_u64().unwrap_or(1).min(8);
    }
    pub fn request(&self, payload: &Value) -> Result<Value, String> {
        let mut active = self.0.lock().map_err(|_| "Preview control lock poisoned")?;
        let review = payload["review_id"].as_str().unwrap_or("");
        let count = payload["workers"].as_u64().unwrap_or(0);
        if payload.as_object().map(|p| p.len()) != Some(2) || review.is_empty() || review != active.review
            || count == 0 || count > active.maximum {
            return Err("Worker changes require the active preview review and a supported integer count".into());
        }
        active.queued = Some(count);
        Ok(json!({"status":"queued"}))
    }
    pub fn take(&self) -> Option<Value> {
        let mut active = self.0.lock().unwrap();
        let count = active.queued.take()?;
        Some(json!({"review_id":active.review,"workers":count}))
    }
    pub fn clear(&self) { *self.0.lock().unwrap() = Active::default(); }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preview_control_is_scoped_bounded_and_coalesced() {
        let control = PreviewWorkers::default();
        assert!(control.request(&json!({"review_id":"a","workers":2})).is_err());
        control.update(&json!({"preview_render":{"enabled":true,"review_id":"a","max_workers":8}}));
        for bad in [json!({"review_id":"old","workers":2}), json!({"review_id":"a","workers":true}),
                    json!({"review_id":"a","workers":9}), json!({"review_id":"a","workers":2,"pid":1})] {
            assert!(control.request(&bad).is_err());
        }
        control.request(&json!({"review_id":"a","workers":2})).unwrap();
        control.request(&json!({"review_id":"a","workers":8})).unwrap();
        assert_eq!(control.take(), Some(json!({"review_id":"a","workers":8})));
        control.request(&json!({"review_id":"a","workers":1})).unwrap();
        assert_eq!(control.take(), Some(json!({"review_id":"a","workers":1})));
        assert_eq!(control.take(), None);
        control.clear();
        assert!(control.request(&json!({"review_id":"a","workers":2})).is_err());
    }
    #[test]
    fn preview_control_preserves_hardware_cap_and_absolute_ceiling() {
        let control = PreviewWorkers::default();
        control.update(&json!({"preview_render":{"enabled":true,"review_id":"a","max_workers":2}}));
        assert!(control.request(&json!({"review_id":"a","workers":3})).is_err());
        control.update(&json!({"preview_render":{"enabled":true,"review_id":"a","max_workers":100}}));
        assert!(control.request(&json!({"review_id":"a","workers":9})).is_err());
        assert!(control.request(&json!({"review_id":"a","workers":8})).is_ok());
    }
}
