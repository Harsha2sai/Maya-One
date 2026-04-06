# Lessons

- [2026-03-27] Needed to avoid assuming class inheritance hierarchy. When implementing mocks for classes with complex constructors (e.g., SupabaseService) use `implements` and explicit method overrides instead of subclassing no-arg constructors.
