-- The flow kernel (chapter 17): a simple flow's instances, tasks, candidates and decisions, kept by the runtime in the
-- component's own schema next to its documents (one transaction for the document and its approval). The employee
-- projection the assignment resolves against is the runtime's projection `be.flow.employee` in be_projection (the
-- appointments and account links of mdm.employee). Nobody else reads these tables.
CREATE TABLE be_flow_instance (
    id                 uuid PRIMARY KEY,
    flow_key           text NOT NULL,
    flow_version       int NOT NULL,
    task_type          text NOT NULL,
    document_type      text NOT NULL,
    document_id        uuid NOT NULL,
    document_number    text,
    legal_entity_id    uuid,
    key_revision       bigint NOT NULL,            -- the document's key revision the instance approves (P17.4)
    digests            jsonb NOT NULL,             -- one approval basis digest a step (P17.4)
    assignments        jsonb NOT NULL,             -- each step's assignment, its parameters bound at the start (P17.3)
    reject_outcome     text NOT NULL CHECK (reject_outcome IN ('rejected', 'returned')),
    summary            jsonb NOT NULL,             -- the public summary the task projections carry (P17.15)
    initiator          text NOT NULL,              -- the initiating account
    initiator_person   text NOT NULL,              -- the person it was at the start (its employee, or the account itself)
    state              text NOT NULL CHECK (state IN ('running', 'approved', 'rejected', 'returned', 'withdrawn',
                           'superseded')),
    step               int NOT NULL,               -- the current step (1-based)
    version            bigint NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
-- at most one running or approved instance a document (P17.4)
CREATE UNIQUE INDEX be_flow_instance_live ON be_flow_instance (document_type, document_id)
    WHERE state IN ('running', 'approved');

CREATE TABLE be_flow_task (
    id            uuid PRIMARY KEY,
    instance_id   uuid NOT NULL REFERENCES be_flow_instance (id),
    step          int NOT NULL,
    state         text NOT NULL CHECK (state IN ('pending', 'decided', 'superseded', 'paused')),
    paused_reason text CHECK (paused_reason IN ('projection_incomplete', 'no_assignee')),
    version       bigint NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'paused') = (paused_reason IS NOT NULL))
);
CREATE INDEX be_flow_task_of ON be_flow_task (instance_id, step);
-- the re-resolution of paused tasks after the employee projection changes (P17.8)
CREATE INDEX be_flow_task_paused ON be_flow_task (created_at) WHERE state = 'paused';

-- A task's current candidates (P17.9): replaced whole when the task changes.
CREATE TABLE be_flow_candidate (
    task_id   uuid NOT NULL REFERENCES be_flow_task (id),
    principal text NOT NULL,
    PRIMARY KEY (task_id, principal)
);
CREATE INDEX be_flow_candidate_of ON be_flow_candidate (principal);

-- At most one decision a task (P17.11): the task is the key.
CREATE TABLE be_flow_decision (
    task_id         uuid PRIMARY KEY REFERENCES be_flow_task (id),
    decision        text NOT NULL CHECK (decision IN ('approve', 'reject')),
    comment         text,
    by_account      text NOT NULL,
    by_person       text NOT NULL,
    key_revision    bigint NOT NULL,
    digest          text NOT NULL,
    decided_at      timestamptz NOT NULL DEFAULT now()
);
