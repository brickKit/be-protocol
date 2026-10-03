[English](14-background-jobs.md) · [中文](14-background-jobs.zh.md)

# P14 后台工作

所有不由请求触发的工作，都属于五种声明过的种类之一，由运行时监督，状态放在组件自己的 schema 里。表：`besdk_job_lease`、`besdk_job_slot`、`besdk_job_queue`、`besdk_reconcile`（[ddl/](../ddl/)）。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P14.1 | MUST，INTERNAL | 所有不由请求触发的工作，都声明成下面五种之一。模块代码从不自己跑 ticker 循环（门禁 `module-ticker-scan`）。每个作业有一个在组件内唯一的名字；运行时自己的作业以 `be.` 为前缀命名（`be.outbox`、`be.lifecycle`、`be.cleanup`、`be.authz.changes`、`be.snapshot.<name>`） | — |
| P14.2 | MUST | 监督见 [P1.7](01-process-and-lifecycle.zh.md)。每次运行都有超时，必须声明；到了超时就取消这次运行。两个副本对同一个 cron 时间槽只跑一次；singleton 同一时刻只有一个持有者，持有者死掉后，另一个副本在租约 TTL 之内接手；一个入队的作业在所有副本之间只执行一次；在回滚的事务里入队的作业不存在；失败的运行被重启，进程不退出 | CP-JOBS-01, CP-JOBS-02, CP-JOBS-03, CP-JOBS-04, CP-JOBS-05 |
| P14.3 | MUST | 指标（每个序列还带 `component`）：`be_job_runs_total{job,result}`、`be_job_duration_seconds{job}`、`be_job_last_success_timestamp_seconds{job}`、`be_queue_depth{kind,state}`、`be_queue_oldest_age_seconds{kind}`、`be_reconcile_pending{name}`、`be_reconcile_oldest_age_seconds{name}`、`be_reconcile_giveups_total{name}` | CP-OBS-03 |
| P14.4 | SHOULD | 只读的运维端点 `GET /{domain}/{name}/_ops/jobs`，由权限键 `<domain>.<name>.ops` 保护：给出每个作业的种类、上次成功、上次错误和队列深度（[`openapi/ops.yaml`](../openapi/ops.yaml)） | — |
| P14.5 | MUST | `JOBS_OVERRIDES`（[schema](../schemas/jobs-overrides.schema.json)）按作业名覆盖 `interval`、`cron` 和 `enabled`，运行时自己的作业也包括在内。覆盖里出现未知的作业名，记一条 WARN 日志并忽略。`enabled: false` 只停掉进程内的调度；`job run` 照样跑这个作业（P14.8） | CP-JOBS-01 |
| P14.6 | MUST | 调度要么是五个字段的 cron 表达式，在 `BUSINESS_TIMEZONE` 里求值，除非作业声明了另一个 IANA 时区；要么是 `@every <duration>`（Go duration 语法，至少 `1s`），它的时间槽是从 Unix 纪元起这个间隔的整数倍，所以每个副本算出的时间槽都一样。别的一概不接受（没有秒字段、没有 `@daily`、没有 `@reboot`）；声明的或经 `JOBS_OVERRIDES` 覆盖的调度不合法，就是配置错误（退出 78）。停机之后，错过的时间槽只补跑最近一个 | CP-JOBS-01 |
| P14.7 | MUST | handler 是幂等的：至少一次意味着一次运行或一个入队的作业可能执行两次；它按 `unique_key` 或业务键去重。`done` 的队列行和旧的时间槽行，过了保留期由运行时的清理 singleton 删除 | — |
| P14.8 | MAY | 只跑一次某个作业。运行时可以提供入口 `<entrypoint> job run <name>`（同一个镜像、同一份配置和密钥文件）：它像起服务的入口一样检查 schema 版本（[P1.8](01-process-and-lifecycle.zh.md)），不起任何服务、不跑别的后台工作，经与进程内调度器相同的表把声明过的作业 `<name>` 跑**一次**，然后退出。`cron`：在 `besdk_job_slot` 里认领现在或之前最近的那个时间槽（已被认领则什么都不做）；`singleton`：在 `besdk_job_lease` 里为这次运行拿租约（租约在别处则什么都不做）；`every` 和 `reconciler`：照常认领、跑一轮；`queue`：在作业的超时之内把该类就绪的行处理一遍。持有者是 `<组件 ID>/job-run:<实例 id>`。运行成功或什么都不做（日志写明原因）退出 0，运行失败退出 1，任务名不存在退出 64（[P1.1](01-process-and-lifecycle.zh.md)），配置错误退出 78。不管 `JOBS_OVERRIDES` 里的 `enabled` 怎么写它都会跑，所以把重活改由外部触发时，运维给进程内那一份设 `enabled: false`，再从外部触发 `job run`：宿主机的 cron 或 systemd 定时器执行 `docker compose --project-directory <根目录> -p <项目> -f .brickkit/generated/compose.yaml run --rm --no-deps <服务名> job run <name>`，或一个手写的、不带 `brickkit.io/project` 标签的 Kubernetes CronJob。不管谁来触发、同时有几个触发，一个时间槽仍只跑一次。提供它的运行时在 `/_be/info` 的 `capabilities` 里列出 `job_run`（[P20.4](20-self-description-and-versioning.zh.md)） | CP-JOBS-06 |

## 五种后台工作

| 种类 | 语义 | 机制 | 表 |
|---|---|---|---|
| `every` | 每个副本都按自己的定时器跑；并发也安全，因为它拿到的工作是原子认领的 | 定时器；工作行用 `FOR UPDATE SKIP LOCKED` 认领 | — |
| `singleton` | 在所有副本和进程之间，同一时刻最多只有一次运行 | 租约，TTL 30 s，每过 TTL/3 续约；丢了租约就取消这次运行；`epoch` 是防护令牌，每次接手 +1 | `besdk_job_lease` |
| `cron` | 每个时间槽在所有副本之间恰好跑一次 | 对 `(name, slot_at)` 做 `INSERT … ON CONFLICT DO NOTHING`；插入成功的一方跑这个时间槽并设 `done_at`；没有领导者 | `besdk_job_slot` |
| `queue` | 在业务事务里入队，提交后至少执行一次 | 在业务事务里插入（带 `unique_key` 时用 `ON CONFLICT DO NOTHING`）；worker 用 `SKIP LOCKED` 认领 `state = 'ready' AND run_at <= now()` 的行，设 `running` 和 `lease_until`，**在任何事务之外**执行 handler；失败时 `attempts` 加一，并按退避设 `run_at`；重试用尽就设 `dead`，并在一个事务里调用 dead handler；`running` 的行过了 `lease_until` 可以再被认领 | `besdk_job_queue` |
| `reconciler` | 推进已经过了截止时间、还在进行中的流程 | 候选由组件自己的 SQL 选出（非终态且已过截止时间）；每个候选带租约认领；handler 在任何事务之外执行；结果在一个短事务里应用，事务里重新核对状态机；退避；超过上限就放弃（挂起并开一条异常待办） | `besdk_reconcile` |

租约行和时间槽行里的 `holder` 是 `<component ID>/<instance id>`；在外壳里是成员的 ID，所以成员之间从不共享租约、时间槽或队列。

## 语句

```sql
-- singleton：拿到或续约租约（先用 INSERT … ON CONFLICT DO NOTHING 建好行）
UPDATE besdk_job_lease
   SET holder = $me, epoch = CASE WHEN holder = $me THEN epoch ELSE epoch + 1 END,
       expires_at = now() + $ttl
 WHERE name = $name AND (expires_at < now() OR holder = $me)
RETURNING epoch;

-- cron：认领一个时间槽
INSERT INTO besdk_job_slot (name, slot_at, holder) VALUES ($name, $slot, $me)
ON CONFLICT (name, slot_at) DO NOTHING RETURNING 1;

-- reconciler：认领一项
INSERT INTO besdk_reconcile (name, item_id, lease_until) VALUES ($name, $id, now() + $lease)
ON CONFLICT (name, item_id) DO UPDATE SET lease_until = now() + $lease
 WHERE (besdk_reconcile.lease_until IS NULL OR besdk_reconcile.lease_until < now())
   AND besdk_reconcile.next_at <= now()
RETURNING attempts;
```

一项到达终态，就删掉它的 `besdk_reconcile` 行。

## 说明

- 同一个组件的独立运行和外壳运行并排存在时，通过同一批行协调，因为这些表在组件的 schema 里。
- 默认不用 Kubernetes CronJob，不用 `pg_cron`，不用外部调度器：工作留在进程里。需要隔离资源的作业先移出外壳（自己的容器和 `resources`）；那样仍不够时才经 P14.8 从外部触发，外部触发同样经这批行协调。
