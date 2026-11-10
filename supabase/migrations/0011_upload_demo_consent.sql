-- Consent is recorded only by the demo-gated upload route; legacy uploads stay unconsented.
alter table uploads add column demo_consent_at timestamptz;
