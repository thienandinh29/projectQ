-- 0004 (P1): the decision audit trail behind the "Vì sao?" panel (SPEC.md, "Decision audit trail").
-- One row per `DecisionTrace` (app/engine/trace.py). Additive only.
--
-- The engine is pure and returns traces; P2's services insert them next to the attempt that caused
-- them, and the API returns them. Columns mirror the model so traces can be filtered by learner,
-- concept and kind; `evidence` and `alternatives` stay jsonb because they are shown, not queried.

create table decision_traces (
    id           uuid primary key default gen_random_uuid(),
    learner_id   uuid not null references learners (id) on delete cascade,
    -- A slug is unique only within a subject, so the subject travels with it. No foreign key to
    -- concepts: a trace is history and must survive a graph rebuild that re-creates concept rows.
    subject_id   uuid not null references subjects (id) on delete cascade,
    concept_slug text not null,
    -- The attempt this decision was made about; null for decisions with no attempt (a plain review).
    attempt_id   uuid references attempts (id) on delete set null,
    kind         text not null
                 check (kind in ('bkt_update', 'placement_step', 'root_cause', 'next_item', 'review')),
    at           timestamptz not null,
    -- P(L_{t-1}) and P(L_t); null where p_known is not what the decision is about (e.g. a review).
    -- double precision, not real: the trail must hold exactly the numbers the engine computed.
    prior        double precision check (prior between 0 and 1),
    posterior    double precision check (posterior between 0 and 1),
    evidence     jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence) = 'object'),
    rule         text not null,  -- machine-readable rule id, e.g. 'root_cause.lowest_p_known'
    rule_vi      text not null,  -- the same explanation in Vietnamese, shown to the learner
    alternatives jsonb not null default '[]'::jsonb check (jsonb_typeof(alternatives) = 'array')
);

-- "Show me why", newest first, for one learner (optionally narrowed to a subject or concept).
create index decision_traces_learner_idx
    on decision_traces (learner_id, subject_id, at desc);
-- The traces that belong to one attempt, for the response of POST /attempts.
create index decision_traces_attempt_idx
    on decision_traces (attempt_id) where attempt_id is not null;
