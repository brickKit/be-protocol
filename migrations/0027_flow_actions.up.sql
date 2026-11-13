-- The action grants of the flow kernel (chapter 17, P17.19, P17.20; chapter 20): one per principal candidate of a
-- pending task's intent, not a secret. The result is recorded once final (P20.8): the action and what came of it
-- (approved, or the refusal's reason); a retryable outcome records nothing.
CREATE TABLE be_flow_action_grant (
    id               uuid PRIMARY KEY,
    task_id          uuid NOT NULL REFERENCES be_flow_task (id),
    principal        text NOT NULL,
    task_version     bigint NOT NULL,
    security_version bigint NOT NULL,
    actions          text[] NOT NULL,
    expires_at       timestamptz NOT NULL,
    issued_at        timestamptz NOT NULL DEFAULT now(),
    result_action    text,
    result           text,
    result_at        timestamptz
);
CREATE INDEX be_flow_action_grant_task ON be_flow_action_grant (task_id);
