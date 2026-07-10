# Risk Analysis

## 1. Migration Breakage
- **Risk**: Adding `user_id` foreign keys to existing trading tables (Orders, Positions, Portfolio) will fail if those tables contain orphaned data that cannot be mapped to a user.
- **Mitigation**: Handle the migration in two steps: 1) Add nullable `user_id` and backfill it with a default "system" user or the first registered admin. 2) Alter column to `NOT NULL`.

## 2. API Lockdown Impact
- **Risk**: Existing frontend components might abruptly fail when APIs start requiring the `Authorization` header, causing a broken UI during the transition period.
- **Mitigation**: Deploy the backend changes alongside the frontend interceptor changes. Wrap all API calls in a generic API client that automatically handles token injection and `401` redirects.

## 3. Redis Single Point of Failure
- **Risk**: If Redis goes down, the `get_current_user` dependency will fail to check the blocklist or rate limits.
- **Mitigation**: Implement a fallback mechanism or fail-open/fail-closed policy. Given this is a trading app, fail-closed is safer (deny access if Redis is unreachable), but High Availability Redis clustering should be deployed in production.

## 4. Email Delivery Latency
- **Risk**: Delays in sending the Email Verification or Password Reset OTP can lead to user frustration and support tickets.
- **Mitigation**: Offload email sending to background tasks (`BackgroundTasks` in FastAPI or APScheduler) so the API response is immediate. Use a reliable transactional email provider (e.g., AWS SES or SendGrid).
