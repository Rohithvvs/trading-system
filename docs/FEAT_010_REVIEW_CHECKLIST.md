# Human Review Checklist (FEAT-010)

This checklist is used to review shadow execution results for candidate features before they are promoted to production.

## News Deduplication (news_dedup) Promotion Review

- [ ] **Validation Report Review**: Confirm the Challenger Validation Report has been generated and reviewed.
- [ ] **Deduplication Rate**: Verify the deduplication rate is within the healthy threshold of 5% to 40%.
- [ ] **False-Positive Rate**: Verify the false-positive rate is stable or improved compared to the Sprint 1 baseline.
- [ ] **Sentiment Score Impact**: Confirm the average sentiment score shows no inflation relative to baseline calculations.
- [ ] **Operational Health**: Confirm that no errors were thrown by the deduplication logic in the logs during the 14-day shadow window.
- [ ] **Rollback Capability**: Confirm the kill-switch and rollback mechanism have been verified in a test environment.
