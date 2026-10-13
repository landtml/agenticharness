//! Rust components of the Upper-Right Harness.

/// Version of the harness these components target. Keep in step with src/urh/__init__.py.
pub const HARNESS_VERSION: &str = "0.1.0";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_is_set() {
        assert_eq!(HARNESS_VERSION.split('.').count(), 3);
    }
}
