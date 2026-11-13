-- The local abandon time of an external command (chapter 13, P13.14): past it a prepared, retry_wait or unknown command
-- is not sent, queried or awaited any more, and fails as expired.
ALTER TABLE be_external_command ADD COLUMN abandon_at timestamptz;
