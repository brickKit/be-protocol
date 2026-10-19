"""Chapter 05: database errors and the migration lint (P5.7, P5.8, P5.13)."""
from common import write


# ---------------------------------------------------------------- database (P5.7, P5.8, P5.13)
def db_errors_vectors():
    # sqlstate, reason, retried inside the transaction entry
    rows = [
        ("40001", "TX_CONFLICT", True, "serialization failure; retried, then TX_CONFLICT"),
        ("40P01", "TX_CONFLICT", True, "deadlock; retried, then TX_CONFLICT"),
        ("55P03", "LOCK_TIMEOUT", False, "lock_timeout"),
        ("57014", "STATEMENT_TIMEOUT", False, "statement_timeout (query canceled)"),
        ("53300", "DEPENDENCY_UNAVAILABLE", False, "too many connections"),
        ("57P01", "DEPENDENCY_UNAVAILABLE", False, "admin shutdown"),
        ("57P02", "DEPENDENCY_UNAVAILABLE", False, "crash shutdown"),
        ("57P03", "DEPENDENCY_UNAVAILABLE", False, "cannot connect now"),
        ("23505", "INTERNAL", False, "unique violation the module did not handle"),
        ("42P01", "INTERNAL", False, "undefined table"),
        ("connect", "DEPENDENCY_UNAVAILABLE", False, "no connection could be made (not an SQLSTATE)"),
    ]
    cases = [{"id": f"db-{state}", "sqlstate": state, "reason": reason, "retried": retried, "note": note}
             for state, reason, retried, note in rows]
    write("db-errors", ["P5.7", "P5.8"],
          "到达事务入口的数据库错误：哪些重试（重做整个事务，最多 3 次尝试），最终答哪个 reason。sqlstate 为 connect 表示还没有 "
          "SQLSTATE 的连接失败。DEPENDENCY_UNAVAILABLE 带 metadata dependency=db。模块自己返回的错误原样传出。",
          cases, {"sqlstate": "SQLSTATE，或 connect", "reason": "domain 为 be 的 reason",
                  "retried": "是否在事务入口内重试", "note": "说明"})


LINT_RULES = {
    "NAME": "文件名不是 <版本>_<小写下划线标题>.up.sql",
    "DOWN": "回退迁移（生产只向前）",
    "DUP_VERSION": "两个文件版本相同",
    "SET": "语句以 SET 或 RESET 开头",
    "TX_CONTROL": "语句以 BEGIN、START TRANSACTION、COMMIT、END、ROLLBACK、SAVEPOINT 或 RELEASE 开头",
    "GRANT": "语句以 GRANT、REVOKE 或 REASSIGN 开头",
    "ROLE_SCHEMA": "CREATE、ALTER 或 DROP 一个 ROLE、USER、GROUP 或 SCHEMA",
    "DEFAULT_PRIVILEGES": "ALTER DEFAULT PRIVILEGES",
    "DROP_OWNED": "DROP OWNED",
    "OWNER": "语句中任何位置的 OWNER TO",
    "CONCURRENTLY": "语句中任何位置的 CONCURRENTLY（不能在文件的事务中执行）",
    "SESSION_IN_BODY": "以 CREATE [OR REPLACE] FUNCTION、CREATE [OR REPLACE] PROCEDURE 或 DO 开头的语句，其美元引号正文（去掉注释）"
                       "里有会留在连接上的会话状态：在正文开头、分号之后或 BEGIN、DECLARE、THEN、ELSE、LOOP 之后紧接着的 "
                       "SET（下一个词不是 LOCAL、TRANSACTION、CONSTRAINTS）或 RESET；set_config(参数, 参数, false)，参数是单引号字面量"
                       "或 $n；pg_advisory_lock 或 pg_try_advisory_lock（含共享版本）。动态 EXECUTE 的字符串不检查",
    "SCHEMA_NAME": "用组件自己的 schema 名限定名字（<schema>. 或带双引号的 \"<schema>\".）",
}


def migration_lint_vectors():
    cases = [
        {"id": "plain-structure", "schema": "sales", "files": {
            "0001_orders.up.sql": "CREATE TABLE orders (id uuid PRIMARY KEY, status text NOT NULL);\n"
                                  "ALTER TABLE orders ALTER COLUMN status SET DEFAULT 'draft';\n"
                                  "CREATE INDEX orders_status ON orders (status);"}, "refused": []},
        {"id": "comments-and-literals-ignored", "schema": "sales", "files": {
            "0001_a.up.sql": "-- SET search_path = x;\n/* GRANT ALL */ CREATE TABLE a (note text DEFAULT 'COMMIT; SET x');\n"
                             "ALTER TABLE a ADD COLUMN \"sales.x\" int;"}, "refused": []},
        {"id": "function-body-is-one-statement", "schema": "sales", "files": {
            "0001_f.up.sql": "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $body$\nBEGIN\n  SET LOCAL lock_timeout = '1s';\n"
                             "  PERFORM 1;\nEND $body$;"}, "refused": []},
        {"id": "session-and-transaction-control", "schema": "sales", "files": {
            "0001_a.up.sql": "SET search_path = public;\nBEGIN;\nCREATE TABLE a (id int);\nCOMMIT;\nreset all;"},
         "refused": [{"file": "0001_a.up.sql", "rule": "SET"}, {"file": "0001_a.up.sql", "rule": "TX_CONTROL"},
                     {"file": "0001_a.up.sql", "rule": "TX_CONTROL"}, {"file": "0001_a.up.sql", "rule": "SET"}]},
        {"id": "provisioning-statements", "schema": "sales", "files": {
            "0001_a.up.sql": "GRANT SELECT ON a TO x;\ncreate role r;\nDROP SCHEMA s;\n"
                             "ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO x;\nDROP OWNED BY x;\n"
                             "ALTER TABLE a OWNER TO y;"},
         "refused": [{"file": "0001_a.up.sql", "rule": "GRANT"}, {"file": "0001_a.up.sql", "rule": "ROLE_SCHEMA"},
                     {"file": "0001_a.up.sql", "rule": "ROLE_SCHEMA"},
                     {"file": "0001_a.up.sql", "rule": "DEFAULT_PRIVILEGES"},
                     {"file": "0001_a.up.sql", "rule": "DROP_OWNED"}, {"file": "0001_a.up.sql", "rule": "OWNER"}]},
        {"id": "concurrently-and-own-schema", "schema": "sales", "files": {
            "0001_a.up.sql": "CREATE INDEX CONCURRENTLY i ON a (id);\nCREATE TABLE sales.b (id int);\n"
                             "CREATE TABLE \"sales\".c (id int);\nCREATE TABLE wholesales.d (id int);"},
         "refused": [{"file": "0001_a.up.sql", "rule": "CONCURRENTLY"}, {"file": "0001_a.up.sql", "rule": "SCHEMA_NAME"},
                     {"file": "0001_a.up.sql", "rule": "SCHEMA_NAME"}]},
        {"id": "session-state-in-function-and-do-bodies", "schema": "sales", "files": {
            "0001_a.up.sql": "CREATE FUNCTION a() RETURNS void LANGUAGE plpgsql AS $$ BEGIN SET search_path = x; END $$;\n"
                             "CREATE OR REPLACE FUNCTION b() RETURNS void LANGUAGE plpgsql AS $f$\nBEGIN\n"
                             "  PERFORM set_config('TimeZone', 'Asia/Tokyo', false);\nEND $f$;\n"
                             "CREATE PROCEDURE c() LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_lock(1); END $$;\n"
                             "DO $$ BEGIN RESET ALL; END $$;\n"
                             "CREATE FUNCTION d() RETURNS void LANGUAGE plpgsql AS $$\nBEGIN\n"
                             "  -- SET search_path = commented_out;\n  SET LOCAL lock_timeout = '1s';\n  UPDATE t SET a = 1;\n"
                             "  PERFORM set_config('x.y', 'z', true);\n  PERFORM pg_advisory_xact_lock(1);\nEND $$;\n"
                             "CREATE FUNCTION e() RETURNS int LANGUAGE sql SET search_path = public AS $$ SELECT 1 $$;\n"
                             "INSERT INTO notes (body) VALUES ($$BEGIN SET x = 1$$);"},
         "refused": [{"file": "0001_a.up.sql", "rule": "SESSION_IN_BODY"}, {"file": "0001_a.up.sql", "rule": "SESSION_IN_BODY"},
                     {"file": "0001_a.up.sql", "rule": "SESSION_IN_BODY"}, {"file": "0001_a.up.sql", "rule": "SESSION_IN_BODY"}]},
        {"id": "file-names", "schema": "sales", "files": {
            "0001_a.down.sql": "DROP TABLE a;", "2_Bad-Name.up.sql": "SELECT 1;", "0003_x.up.sql": "SELECT 1;",
            "3_y.up.sql": "SELECT 1;", "README.md": "not a migration"},
         "refused": [{"file": "0001_a.down.sql", "rule": "DOWN"}, {"file": "2_Bad-Name.up.sql", "rule": "NAME"},
                     {"file": "3_y.up.sql", "rule": "DUP_VERSION"}]},
    ]
    for c in cases:
        for r in c["refused"]:
            assert r["rule"] in LINT_RULES, r
    write("migration-lint", ["P5.13", "P5.31"],
          "迁移文件与迁移入口检查的拒绝项。语句按顶层分号切分；注释、字符串字面量与美元引号包起来的正文不单独算语句；"
          "含点号的双引号标识符是一个名字。文件按名字排序检查，语句按文件中的顺序，同一语句内按下面规则列出的顺序。"
          "不以 .sql 结尾的文件忽略。规则：" + "；".join(f"{k}: {v}" for k, v in LINT_RULES.items()) + "。",
          cases, {"schema": "组件的 schema", "files": "文件名到内容", "refused": "按顺序期望的拒绝项：文件与规则"})
