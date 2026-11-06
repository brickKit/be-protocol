# 兼容矩阵

协议版本、官方 SDK 版本之间能不能混用（装配项目协议 18 的“兼容矩阵”）。每发一个协议版本，在第 1 节加一行，最后一列写装配项目的正式文档（`docs/zh/`）在哪里接了这次改动，或“无：<为什么>”（`compat_test.go` 检查它不空；设计者或运维要知道的行为改了，正式文档就要跟着改）；SDK 每次换协议版本，在第 2 节加一行。

**“线上兼容”指**：两个组件各自实现的协议版本不同，彼此的调用（用户面与系统面）、错误、截止时间、追踪与事件仍然互相读得懂，结果与同一版本时相同。只改实现者自己内部行为的规则（例如自己的熔断、自己的转发节奏），不影响线上兼容，但实现旧版本的组件仍带着旧行为。

## 1. 协议版本

| 版本 | 改了什么 | 影响线上 | 与上一版混用 | 装配项目的正式文档 |
| --- | --- | --- | --- | --- |
| alpha.19 | （本表的起点：仍在使用的最旧 SDK 实现的版本） | — | — | — |
| alpha.20 | P4.23 认领只接管已过期的幂等记录（文字改成与实现一致） | 否 | 兼容 | 无：文字改成与实现一致，设计层没有对应的选择 |
| alpha.21 | P1.6 就绪也答 `HEAD` | 否（探针与平台，不是组件之间） | 兼容 | 无：探针与平台的约定 |
| alpha.22 | P4.27 SDK 自己对授权成员的后台调用不经熔断；P4.28 连接失败后重新解析主机名；P8.24 定义在启动后提交、就绪不等它被接受 | 否（各自内部） | 兼容；实现旧版的成员在授权成员不可用时就绪得晚 | 决定 D78（P4.27）、安全 08（P8.24）；P4.28 无：SDK 内部 |
| alpha.23 | P8.24 被拒的提交继续重试 | 否 | 兼容 | 安全 08 |
| alpha.24 | 新的错误原因 `DEFINITION_PENDING`（`UNAVAILABLE`，503，可重试） | 是：授权成员可能答出旧调用方不认识的原因 | 兼容：调用方按 gRPC 码与 HTTP 状态归类结果（P4、P3.2），不认识的原因按它的码处理，503 照样可重试 | 安全 08、安全 09a |
| alpha.25 | P8.24 只有登记过的资源类型才答 `DEFINITION_PENDING`，别的答 `REQUEST_INVALID` | 否（只改授权成员何时答哪个） | 兼容 | 安全 08 |
| alpha.26 | P6.32 轮询只转发有待转发行的分区 | 否 | 兼容；**不要用这一版**：它的 `vectors/SHA256SUMS` 没有重新生成，自己的检查不过，用 alpha.27 | 无：SDK 内部的转发节奏 |
| alpha.27 | alpha.26 加上重新生成的 `SHA256SUMS` | 否 | 兼容 | 无：只重新生成校验和 |
| alpha.28 | P4.13 熔断的打开期从 5 秒起、试探失败加倍到 30 秒（原为固定 30 秒） | 否（调用方自己的熔断） | 兼容；实现旧版的调用方在依赖重启后多等到 30 秒 | 决定 D79 |
| alpha.29 | P6.33 消费者忽略载荷里不认识的字段；读模型按聚合订阅，不认识的类型标为不完整并取回；本文件 | 否（消费者自己的处理） | 兼容；实现旧版的读模型按类型订阅，收不到来源新加的动作 | 协议 02（部分订阅）、协议 19（版本与产物） |
| alpha.30 | P5.32 迁移遇到被较新版本迁移过的库，什么也不做、按成功结束；P3.10 没有注册的方法或路由答 `CAPABILITY_UNSUPPORTED`（501）而不是 `NOT_FOUND`；P4.29 调用方把不带 ErrorInfo 的 `UNIMPLEMENTED` 当作 `CAPABILITY_UNSUPPORTED` | 是：没有的路由从 404 变成 501 | 兼容：调用方按码归类，`UNIMPLEMENTED` 不重试、不计入熔断，新旧都一样；实现旧版的组件的迁移遇到更新的库仍会失败，滚动升级与回退要等它们升到本版 | 协议 14（结构迁移的回退）、协议 19（版本与产物） |
| alpha.31 | 只改本文件：第 2 节补上 alpha.30 的 SDK，第 3 节按协议 18 的 SK09 改写 | 否 | 兼容 | 无：只改本文件 |
| alpha.32 | P1.21 进程里的 SDK 不早于外壳任何成员要求的最低版本；Python 外壳启动时按成员包元数据里的 `be-sdk>=` 核对，没有声明或不满足的拒绝启动 | 否（外壳自己的启动检查） | 兼容；Python 成员要在包元数据里声明最低 SDK，否则 a35 起的外壳拒绝承载它 | 协议 17 |
| alpha.33 | 只改文字：P6.14 写明凭证地址的主机名要求（部署里每个组件的 `OBJECT_STORE_URL` 用同一个主机名）与它在配置一章的指引 | 否 | 兼容 | 根 AGENTS.md 的易错点、底层选择、数据与生命周期 |
| alpha.34 | P6.31 按顺序处理的订阅是整个订阅一次一条（所有实例合起来），一条等重投时后面的也等；原来只写“一次一条”，SDK 只做到每个实例一次一条 | 否（订阅方自己的处理） | 兼容；没有组件用到按顺序的订阅 | 底层选择的消息运输 |
| alpha.35 | P4.30 系统面的服务器给每条连接设最长寿命（30 秒起，到时体面关闭），调用方重连后连接分到各个副本 | 否（服务器自己的连接管理；HTTP/2 的 GOAWAY 是标准行为，旧调用方照常重连） | 兼容；旧版本的服务器不关连接，调它的调用方仍只落在一个副本上 | 底层选择的调用与错误 |
| alpha.36 | P8.2 不认识的 `kid` 引起的刷新进行中时，其余遇到不认识的 `kid` 的请求等它结束，不先答失败 | 否（核验方自己的处理） | 兼容；实现旧版的核验方（`be-sdk-go` alpha.40 及以前）在启动时没取到公钥、或签发方换密钥后的第一阵并发请求里，除第一个外答 `DEPENDENCY_UNAVAILABLE`（可重试） | 无：核验方自己的处理，线协议是权威 |
| alpha.37 | CK-ID-01 加上 P8.2 刷新进行中的并发情形（只改检查的条文；规则在 alpha.36 已改） | 否 | 兼容；没有行为变化 | 无：只改检查的条文 |
| alpha.38 | COMPAT.md 补写 `be-sdk-go` alpha.42、`be-sdk-python` a39 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.39 | 本表加“装配项目的正式文档”一列，检查要求每一行写明正式文档改在哪里，或为什么不用改 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.40 | P6.34 启动时连不上运输不退出，每秒重试，与 P5.10 的数据库一样；凭据或 scheme 不对 78、PostgreSQL 队列的库不存在 69；检查 CK-BUS-10 | 否（组件自己的启动） | 兼容；实现旧版的组件（`be-sdk-go` alpha.42、`be-sdk-python` a39 及以前）启动时连不上运输就以 69 退出，靠平台重启；同机开机、运输晚到时会退出一次 | 部署模式指南的已知风险（组件随下次连锁发布换上之前仍会退出一次）；交接 |
| alpha.41 | COMPAT.md 补写 `be-sdk-go` alpha.43、`be-sdk-python` a40 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.42 | P6.28 写明领取的两条路各沿按位置排序的部分索引、领取语句按每次的参数规划；`migrations-bus` 的 0003 用在途投递的 `(durable, seq)` 部分索引替换按 `lease_until` 的租约索引 | 否（总线库的索引） | 兼容；旧版 SDK 照常工作，迁移由新版的 `migrate` 跑一次；在从没 analyze 过的表上，旧的索引让租约过期那条路逐行走整个积压 | 无：SDK 与总线库的实现细节，正式文档不涉及 |
| alpha.43 | COMPAT.md 补写 `be-sdk-go` alpha.44、alpha.45 与 `be-sdk-python` a41 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.44 | COMPAT.md 补写 `be-sdk-go` alpha.46–alpha.48 与 `be-sdk-python` a42、a43 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.45 | P5.33 SDK 的语句用缓存的通用计划，打开数据库的进程每 2 秒调用迁移建的 `be_analyze_stale()`，对统计落后的队列表 analyze（组件 `migrations/` 0010、`migrations-bus/` 0004）；P6.28 改为领取用缓存的计划、统计落后由 P5.33 处理（原来按每次的参数规划）；P6.35 转发沿按位置排序的未发布索引读取（0010 换掉 `be_outbox_unpublished`）；检查 CK-DB-10 | 否（SDK 与它的表的实现细节） | 兼容；旧版 SDK 不调用这个函数，照常工作，迁移由新版的 `migrate` 跑一次；旧版 SDK 在新索引上读未发布行时按位置排序取，比原来快 | 无：SDK 与它的表的实现细节，正式文档不涉及 |
| alpha.46 | COMPAT.md 补写 `be-sdk-go` alpha.49 与 `be-sdk-python` a44 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.47 | P7.23 空闲的成员每个轮询间隔只认领一次（轮询叫醒的工作者领到项再叫醒下一个），cron 在下一个槽之前不开事务；P5.33 的 `be_analyze_stale()` 改为按 oid 读统计函数（组件 `migrations/` 0011、`migrations-bus/` 0005，判断不变） | 否（SDK 自己的轮询与它的表的实现细节） | 兼容；旧版 SDK 照旧每个工作者各自轮询；迁移由新版的 `migrate` 跑一次，旧版 SDK 调用的是同一个函数 | 无：SDK 内部的轮询节奏与统计维护，正式文档不涉及 |
| alpha.48 | COMPAT.md 补写 `be-sdk-go` alpha.50 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.49 | 第 09 章加入水位来源：P9.13–P9.18 来源一侧（按流声明并列出可补取的组件、标准系统方法 `be.source.v1.WatermarkService/Pull`，消息在 `proto/`；核对连续位置上的行、回声与锁内编号、页标记绑定实例与纪元、响应的声明），P9.19–P9.25 消费者一侧（连续位置、时钟、补取的触发与响应的处理、水位、判断、隔离），P9.26–P9.29 来源身份与对齐状态（协议 02 的对齐状态表，第一次采用、`stalled` 与 `blocked` 的出口）、纪元、对齐（P0、对齐代次、重启）与绊线；P9.11 别的实现实例与别的部署的输入改为按状态表转 `blocked`（原来只是不应用），P9.11、P9.12 加上“已清理”墓碑的 `min_read_position` 与同版本摘要不同的绊线；P6.1 注明回声行的分区例外；检查 CK-WM-01…10；向量 `watermark-pull-check`、`watermark-pull-outcome`、`watermark-epoch`、`watermark-value`、`watermark-judge`、`watermark-source-state`；`make check` 加上 `proto/` 的 buf STANDARD 检查 | 是：水位来源多了一个系统方法，信封多了回声类型 `be.source.echo.v1` | 兼容：只做加法；不声明水位来源的流行为不变，按类型订阅的消费者收不到回声（P6.33）；实现旧版的投影消费者对别的实现实例的输入只是不应用、不转 `blocked` | 无：协议 02 的“来源水位”第 1–11 步与对齐状态表落成线协议，设计不变 |
| alpha.50 | 迁移 0012：水位消费者的表（来源状态、各分区的连续位置与 P0、补取记录、失败计数、隔离）与投影行的 `min_read_seq`；P9.13 写明补取方法要有一个登记的操作；P9.16 续页失效答 `QUERY_PLAN_CHANGED`（原写 `FAILED_PRECONDITION`，错误目录里没有这个通用原因）；P9.19、P9.25 写明表与失败计数的方式 | 否（消费者自己的表；补取的错误原因只给续页） | 兼容；迁移只加表与可空列，旧版 SDK 照常工作 | 无：表与错误原因是实现细节 |
| alpha.51 | COMPAT.md 补写 `be-sdk-go` alpha.51 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.52 | COMPAT.md 补写 `be-sdk-go` alpha.52、alpha.53 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.53 | P8.1 访问令牌必带正整数的 `be_sv`；P8.25–P8.28 令牌陈旧（准入比较视图里账号的安全状态版本）、代表用户的调用被下游答 401 时按 `AUTHORIZATION_UNPROVABLE` 回答、身份成员的安全状态版本与标准系统方法 `be.session.v1.SessionService`（`proto/be/session/v1/session.proto`）；账号状态记录多必填的 `security_version`，视图的主体条目多可选的 `security_version`；新的第 11 章“边缘的会话层”；新原因 `SESSION_ENDED`、`CSRF_HEADER_REQUIRED`；`make check` 先查 gofmt | 是：令牌与两种安全记录的字段、新的系统方法与原因 | **要按顺序升级**：实现新版的组件拒绝不带 `be_sv` 的令牌，所以先升级身份成员（签发 `be_sv`），再升级组件；授权成员把版本写进视图之前 P8.25 按 0 处理，不会答 `TOKEN_STALE`；新原因按码归类（P3.2），旧调用方照常 | 协议 20 的登录与会话、安全 09a（账号状态、视图、错误）、底层选择的边缘入口、AI 决定 A117–A119 |
| alpha.54 | COMPAT.md 补写 `be-sdk-go` alpha.54 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.55 | COMPAT.md 补写 `be-sdk-go` alpha.55、alpha.56 与 `be-sdk-python` a45 所实现的协议版本 | 否 | 兼容；没有行为变化 | 无：只改本文件 |
| alpha.56 | P8.11 核验回答的分片项多可选的 `read_only`：为真时只续普通读取的有效期，高风险的有效期不动（安全 03 的续发与关闭：来源水位在 `D_src_high` 与 `D_src_read` 之间）；向量 `view-accept` 多 8 例与结果 `renewed_read`、`replaced_read`、`adopted_read` | 是：核验回答多一个字段 | **要按顺序升级**：组件先升到实现本版的 SDK，授权成员才开始答 `read_only`；实现旧版的组件不认识这个字段（契约 `be.authz.v3` 的 `ShardAnswer.read_only`，`contract-infra-authz` alpha.2 起），把高风险的有效期也续上：来源停滞时高风险操作不关闭 | 安全 09a（核验回答的字段） |
| alpha.57 | P9.30–P9.33 来源的快照与批量读取是 SDK 自带的标准系统方法 `be.source.v1.RecordService`（`Read`、`Snapshot`，`proto/be/source/v1/records.proto`）：来源按流声明读取的组件与读取函数，水位来源的流必须声明；回答按 P9.18 声明来源，消费者只用已采用的主库的回答；新能力 `projection-records` | 是：新的系统方法 | 兼容：新方法，没有旧的调用方；实现旧版的来源没有这两个方法，对它们答 `CAPABILITY_UNSUPPORTED`（P3.10），消费者的对齐不能完成 | 协议 02 的来源要提供什么（S3） |
| alpha.58 | `records.proto` 的 `Record` 与 `ReadResult` 多 `claim`：内容是对象存储的引用（同事件的 `beclaim`）；P9.30 写明 | 是：新字段 | 兼容：alpha.57 没有 SDK 实现过 | 无：只补 alpha.57 的消息 |
| alpha.59 | P7.24 queue 工作项排入时可以声明最早执行时刻 `run_at`，未到期的 `pending` 不被认领；P7.5 的认领条件随之写成 `pending` 或 `retry_wait` 且 `run_at <= now()` | 否：只在组件自己的表里 | 兼容：以前的 SDK 排入的项 `run_at` 都是排入的时刻；`be-sdk-go` 的认领一直核对 `pending` 的 `run_at`，`be-sdk-python` 还没有工作项的运行时 | 协议 01（工作项的字段、认领语句） |
| alpha.60 | P7.13 业务等待的 `run_at` 按已等待的时长退避（再等与已等的一样久，1 秒起，上限 5 分钟） | 否：只在组件自己的表里 | 兼容：以前的 SDK 每次等待都是 1 秒，等一天要认领 86 400 次；改后约 300 次（加倍十来次到 5 分钟，之后 86 400 / 300 ≈ 288 次） | 协议 01（状态迁移的等待结果） |
| alpha.61 | P8.29 只减少访问的操作（`tightening_only`）的准入不随分片因来源水位而关闭：授权成员最后回答 `read_only` 或 `closed` 的分片，用最后换上的视图判定并标明“依据未证明为最新” | 否：组件内部的准入 | 兼容：没有新的线上字段；实现旧版的 SDK 对这类操作照旧随分片关闭（来源停住时撤权与停用办不了），升级后才能办理 | 安全 03 的只减少访问的操作 |
| alpha.62 | P9.34 按最后已应用的事实判断：`stalled` 的来源也按行判断、不看水位的年龄，回答带对齐状态与水位年龄；向量 `watermark-judge` 加 `basis` 字段与 13 例 | 否：消费者本地的判断 | 兼容：新的一种问法，原来的判断（`basis` 缺省为 `fresh`）不变；只有按安全 03 办理只减少访问的操作的成员（授权成员）用它 | 协议 02 第 9 步的“按最后已应用的事实判断”；安全 03 的只减少访问的操作 |
| alpha.63 | 安全记录 `be.security.change_result` 加可选字段 `basis`（`last_applied`：请求者按来源最后已应用的事实判断，依据未证明为最新） | 是：授权成员的用户面回答 | 兼容：可选字段；按旧 schema 严格校验（`additionalProperties: false`）的读取方遇到它会拒绝，读取方先升级 | 安全 09a 的变更结果；安全 03 的只减少访问的操作 |
| alpha.64 | P8.14 组件按自己的资源定义核对视图里的每个段，不合格的（少一维、多一维、原子不合维度、写不可读、区间缺端）不参与求值；P8.15 对操作 K 可读的字段取 K 自己的段；P8.30 读者拒绝 `required_features` 含不认识功能名的记录、忽略 `ext`；P8.31 掩码的输出形状（不可读字段为 `null` 并列在 `_masked`）；P9.4 列表的 `readable_only`；向量 `segment-eval` 加 r10、八个场景、`action_fields` 与 `action_list`、每种维度的筛选、`check` 与 `mask` 两种例子，`security-records` 加 `read` 字段与三例 | 是：用户面的输出形状（被掩码的字段由删掉改为 `null` 加 `_masked`）；列表回答可带 `readable_only` | 兼容：调用方多看到一个 `_masked` 键与值为 `null` 的字段；实现旧版的 SDK 不核对段，缺维度的段在它那里等于这一维不限，授权成员先保证视图里没有这种段（`infra/authz` 3.0.23 起），组件再升级 | 安全 01 的 AE04、AE08；安全 06 的 SC10；安全 07 的 FX01、FX12；安全 09a 的 EN05、EN06、EN08–EN10 |
| alpha.65 | `capabilities.json` 的 `protocol` 与 `fs.go` 的 `Version` 改正为本版（alpha.64 两处都漏改，仍写 alpha.63，SDK 的功能矩阵检查因此拒绝钉 alpha.64）；加检查：COMPAT 第 1 节最后一行就是 `capabilities.json` 的版本。条款与向量同 alpha.64 | 否 | 兼容；**不要用 alpha.64**，用本版 | 无：只改版本字段与检查 |
| alpha.66 | 向量文件的 `protocol` 按本版重新生成（alpha.65 只改了 `fs.go` 与 `capabilities.json`，向量仍写 alpha.63，自己的检查不过）；生成器改为从 `fs.go` 读版本，版本号只剩两处手改，两处都有检查。条款与向量内容同 alpha.64 | 否 | 兼容；**不要用 alpha.64、alpha.65**，用本版 | 无：只改版本字段与生成器 |
| alpha.67 | P8.17 写明命中位图的每一位都是布尔值：谓词因 NULL 的列为 NULL 时记为未命中（`COALESCE(谓词, FALSE)`）。套件的授权剖面在 Go 探针上发现：`be-sdk-go` alpha.71 的命中表达式对 NULL 的维度值得到 NULL，按布尔值扫描的组件整页答 500 | 否：组件内部的查询 | 兼容；实现旧版的 SDK 给出的命中表达式可能为 NULL，组件要自己当作未命中 | 无：查询的编译细节，线协议是权威 |
| alpha.68 | 向量 `segment-eval` 加记录 r11（法人 LE1、部门为 NULL）：经一段可见、另一段的列为 NULL 时命中位为假（P8.17 的 alpha.67 写明，向量此前没有这种行） | 否 | 兼容 | 无：只加向量 |
| alpha.69 | 只改文字：第 2 节补上 `be-sdk-go` alpha.57–alpha.73、`be-sdk-python` a46–a51 所实现的协议版本（此前漏记）；P8.14、P8.15、P8.31 的检验一栏加上套件的 CK-AZ-05（授权剖面） | 否 | 兼容；没有行为变化 | 无：只改本文件与检验的条文 |
| alpha.70 | 安全记录 `be.security.account_status` 加可选字段 `confirmation`（受保护的账号状态变更所用的确认记录）；P9.16 允许水位来源声明“回声之前”的一步（外部产品承载的来源先拉取产品的变更，失败不写回声、答 `UNAVAILABLE`） | 是：身份成员发出的账号状态可以带新字段 | 兼容：可选字段；按旧 schema 严格校验的读取方（授权成员）遇到它会拒绝，读取方先升级；回声之前的一步只在来源内部 | 安全 09a 的账号状态；安全 03 的“身份成员由外部产品承载时” |
| alpha.71 | 新的第 12 章：运行档案（对象锁的桶、记录的形状与签名、类别与保留期、恢复代次的读取与推进）与告警渠道（P12.1–P12.8）；能力 `run-profile` | 否：组件之间的线不变，只有写运行档案与告警的执行者用到 | 兼容 | 协议 15、底层选择的不随恢复回退的存储 |
| alpha.72 | 第 12 章加证据（P12.9–P12.14）：记录 `be.evidence.record` 的形状与摘要、按（id，phase）只收一次、记录者即调用者、回执、列出、证据存储不回退；向量 `evidence-record`；能力 `evidence-store`（组件）、`full-recovery`（装配） | 否：新的系统方法由审计组件提供，原有的线不变 | 兼容 | 协议 15 的证据表与证据的写入 |
| alpha.73 | 第 12 章加记录者一侧（P12.15–P12.18）：本地证据发件表与 `be.evidence.transfer`、收紧两段写、变更历史与提交序号、“已体现”按记录身份；迁移 0013（`be_evidence_outbox`、`be_change_history`、`be_evidence_counter`）；能力 `evidence-writer` | 否：组件自己的表与对证据存储的调用 | 兼容：新表由迁移建立 | 协议 15 的证据的写入 |
| alpha.74 | P12.9 改正：`position` 只在 `effective` 与 `general` 上（`cancelled` 的事务没有提交，没有序号；alpha.72 写成“只有意图没有”，记录者写不出合规的“已取消”）；向量 `evidence-record` 加 `position-by-phase`，`cancelled` 的例子去掉位置 | 是：证据存储的核对按新规则 | 不兼容的改正：按 alpha.72 核对的证据存储会拒绝不带位置的“已取消”，证据存储（`infra/audit` 3.0.16）先升 | 协议 15 的证据的写入 |
| alpha.75 | 迁移 0013 改正：`be_evidence_outbox.ord` 用标识列（与 SDK 其余的表一样），alpha.73、74 写成 `bigserial`，运行角色没有那个序列的使用权限，插入被拒。0013 发布后还没有任何组件应用过（实现它的 `be-sdk-go` alpha.78 以本版为准），所以就地改正 | 否 | 兼容：不要用 alpha.73、74 的 0013 | — |
| alpha.76 | P12.16 加：意图编码不成时记严重日志 `evidence_intent_unsealed`，由写入意图的 SDK 记（组织成员第一版的移动意图因此全部静默丢失，测试才发现） | 否（记录者自己的日志） | 兼容 | 无：SDK 的日志，设计层没有对应的选择 |
| alpha.77 | 第 6 章加“进度与补发”（P6.36–P6.40）：收件表记来源位置、按运行段与投递寿命 L 求进度（向量 `inbox-progress`）、`be.source.v1.ResendService.Resend`（消息身份另起）、消费者库回退之后要补发、超出保留的修复与 `be_resend_gap`；P6.12 的清理记下删到的位置；迁移 0014；能力 `redelivery` | 是：新的标准系统方法（只增加，不改原有的线） | 兼容：实现旧版的生产者没有 `Resend`，调用方得到“未实现”并记错误日志；旧版的消费者不记位置，进度为空（从保留的开头补发） | 协议 15 的“发件表的保留与消费者进度” |
| alpha.78 | 第 01 章加“恢复模式”（P1.22–P1.24）：`RECOVERY_PHASE`（第 02 章，进程级）、恢复就绪时 `/readyz` 答 200（P1.6 改）、`frozen` 与 `redelivering` 两个阶段运行什么；新的错误原因 `MAINTENANCE`（503，可重试）；能力 `recovery-mode` | 是：恢复中用户面答新的原因 | 兼容：不认识的原因按码归类，503 可重试；实现旧版的成员不认识 `RECOVERY_PHASE`，在恢复中照常运行，所以整套恢复前全部成员要先升到实现本版的 SDK | 协议 15 的恢复流程、协议 17 的启动与停止 |
| alpha.79 | 第 12 章加“重放”（P12.19–P12.22）：`be.evidence.v1.ReplayService.Replay`（只有 `ops/recover` 调用）、已体现、按类别重新执行、不重做前置校验、恢复工具的顺序；第 01 章的恢复阶段加 `replaying`（身份成员在恢复阶段不签发、不发布公钥集合）；能力 `evidence-replay`、`replay-order` | 是：新的标准系统方法 | 兼容：实现旧版的组件没有 `ReplayService`，恢复工具得到“未实现”，把它的记录列入复核 | 协议 15 的第 6 步 |
| alpha.80 | P9.35：水位“不早于某一时刻”与被问到时立即补取（整套恢复的 6.4）；安全处置的 `origin` 加 `recovery_review`（6.5 关闭复核中的主体） | 是：授权成员发出的处置可以带新的来源 | 兼容：按旧 schema 严格校验处置的读取方遇到新取值会拒绝，读取方先升级；P9.35 只在消费者内部 | 协议 15 的 6.4–6.5、安全 09a 的安全处置 |
| alpha.81 | P6.11 加：正常停止时放弃自己持有的转发租约，成员停止等它做完 | 否（同一成员的进程之间） | 兼容：不放弃的旧实现只是接替得慢 | 协议 15 的恢复流程（A140 每换一个阶段重启一次） |
| alpha.82 | 操作定义的 `audit` 加 `strict`（严格档：敏感读取与导出得到转运回执之后才释放数据，P8.19）；P8.19 写明受限字段在 `changes` 里换成摘要 | 是：组件可以声明 `strict` | 兼容：按旧 schema 严格校验定义的授权成员会拒绝声明 `strict` 的定义，授权成员先升级；受限字段原本就不许记明文（记录表），这里写明怎样换 | 协议 03 的敏感读取与严格档 |
| alpha.83 | 新的第 13 章：对外命令（P13.1–P13.10）：命令与尝试表（迁移 0015）、按（业务组件，业务参考号）幂等与参数摘要、状态转移、发送前先提交、不可撤回的命令发出前写证据、结果分类、结果未知时先查与重发条件、重发截止、能力声明、只查询模式；向量 `external-command`；能力 `external-commands` | 否：组件自己的表与工作项，适配器与外部系统之间的线由适配器定 | 兼容：新表由迁移建立 | 协议 10 的对外命令、协议 15 的第 7 步 |
| alpha.84 | 改正：迁移 0015 加 `accepted_since`（`accepted` 的终结时限与转人工要从受理时算起，借更新时刻会每写一次就重算）；P13.4 的发出记录是阶段 `intent`（它不在业务事务里，没有提交序号，`general` 要求带位置，P12.9）。0015 发布后还没有任何组件应用过（实现它的 `be-sdk-go` 以本版为准），所以就地改正 | 否 | 兼容：不要用 alpha.83 的 0015 | — |
| alpha.85 | 第 01 章的恢复阶段加 `verifying`（第 7–9 步）与 `read_only`（只读开放）；第 13 章加外部对账（P13.11–P13.13，`be.external.v1.ReconcileService`，向量 `external-reconcile`）；新的第 14 章：整套恢复的核对（`be.recovery.v1.CheckService`：一致性检查与 SDK 自带的检查、损失范围的对象查询、单号的已用最大值与提升；审计损失由恢复工具求）；能力 `recovery-checks`、`recovery-loss` | 是：新的标准系统方法 | 兼容：实现旧版的成员没有 `CheckService`，恢复工具得到“未实现”并列入清单；不认识新阶段的成员在这两个阶段启动即失败（配置错误），整套恢复前全部成员要先升级 | 协议 15 的第 7–10 步 |
| alpha.86 | 外部对账（P13.11–P13.13）补全：请求带故障时刻（`failed_at`）；没有对上的命令写下最早一次可能的发送与 `unrecorded_until`（迁移 0016 加列），P13.6 的最长处理时间从记下的最后一次与它中较晚的算起，P13.7 的“最后使用”没有记下最后一次时取最早一次；最早一次可能的发送：可能到达的第一次，否则没结束的发送尝试的开始，否则 T；列出的时间窗之前就可能发出过的另按参考号查询；结论按恢复留存在 `be_external_reconciled`（迁移 0016），同一次恢复再调用时重新匹配仍未终结的并回答全部结论；`manual` 参加匹配，没有对上时不被降级；外部未终结的记录对上时取 `accepted`；外部记录取不到时整次调用答 `DEPENDENCY_UNAVAILABLE`；`ReconcileService` 与 `CheckService` 共用组件定义的恢复操作；P14.5 的提升回答提升后的值、空号交给属主登记作废 | 否：只有恢复工具调用 | 兼容：alpha.85 的对账还没有实现；迁移 0016 只加可空列与新表 | 协议 15 的第 7、10 步 |
| alpha.87 | P14.1：检查读库只经总是回滚的事务，跨组件的一项在读取之间经系统面问另一边；P14.3：业务变更与敏感读取的审计 `target` 带变更之后的版本 `version`，所问版本为空时还在答 `present`（恢复工具列“无法判断”），没登记的类型答 `CAPABILITY_UNSUPPORTED` | 否 | 兼容：`target` 本来不限键；不带版本的旧记录照“无法判断”处理 | 协议 15 的第 8、9 步 |
| alpha.88 | P14.5：签发连续单号的业务变更，审计记录的 `changes.document_number` 带所签的号（法人、序列代码、期间、号），恢复工具从审计存储取 T 之后的最大值（原先写的“证据类别 `document_number`”没有记录者，取消） | 否 | 兼容：不带的旧记录只是取不到，按属主的 `Numbers` | 协议 15 的第 10 步 |
| alpha.89 | P2.11：恢复阶段是进程的状态，外壳里没有设置它的成员按设置了它的成员的阶段运行（原先按“没设置就不用这项资源”，清单不声明它的成员会在别的成员冻结时照常运行；T10e 演练发现） | 否 | 兼容：只改外壳里的成员怎样取阶段 | 协议 15 的冻结 |
| alpha.90 | P1.23：`frozen` 以外的恢复阶段里审计转运照常运行（原先恢复阶段里一切后台工作都停，重放写下的审计到开放才送出，第 8 步的审计积压检查不会通过；T10e 演练发现） | 否 | 兼容：只多送出 | 协议 15 的第 6–10 步 |
| alpha.91 | P12.20 加“核对”：效果在恢复组之外的类别（协议 15 的 6.7，身份产品不在恢复组内时的凭据收紧）由组件注册核对，在事务之外问那一方，答 `consistent` 或 `inconsistent`（列复核），不写变更历史 | 是：重放可以答两个新的结果 | 兼容：不认识新结果的旧恢复工具按“未知结果”列复核；旧组件对这些类别照旧答 `unsupported` | 协议 15 的 6.7 |
| alpha.92 | P1.23：`frozen` 以外的恢复阶段里证据转运也照常运行（原先只有审计转运；恢复中写下的证据结论到开放才送出，重放把它们当成只有意图而列入复核；T11 演练发现） | 否 | 兼容：只多送出 | 协议 15 的第 5–10 步 |
| alpha.93 | P12.23：双通道失效时 SDK 补写一条类别为 `evidence_double_failure` 的一般记录（向量 `evidence-record` 的类别多一个），恢复工具不重放它、第 9 步列为损失；第 13 步起的阶段不变 | 是：证据存储多收一个类别 | 兼容：证据存储（审计组件）先升级，否则拒收这一类（记录者把它记成被拒、不再重送） | 协议 15 的证据表与第 9 步 |
| alpha.94 | 安全记录 `be.security.account_status` 加可选字段 `evidence`（引起变更的证据记录身份，身份侧处置的 `signal_ref`）；P12.20 加重放结果 `deferred`，P12.22 恢复工具在 6.4 之后再问、仍推迟的列复核；P12.23 改正：不可撤回命令的发出记录两处都写不进时命令不发出，不记 | 是：账号状态可以带新字段；重放可以答新结果 | 兼容：按旧 schema 严格校验账号状态的读取方（授权成员）先升级；旧恢复工具把 `deferred` 当作未知结果列复核 | 安全 08 的身份侧处置的派生、安全 09a、协议 15 的 6.3 |
| alpha.95 | 第 12 章加“信任材料历史”（P12.24–P12.27）：`trust.ca` 与 `trust.credential` 记录的形状（轮换由新旧两把 CA 签名）、受信的 CA（从当前信任根沿双签的轮换往前）、一条签名的记录在接收时刻是否可信（链到受信的 CA，链上没有在 t > r − 偏差时已吊销的证书）、签发者先写运行档案再发布、吊销不推迟；向量 `trust-history` | 否：组件之间的线不变，读运行档案与告警渠道的执行者（恢复工具）用到 | 兼容 | 协议 15 的 6.2 与证据表的信任材料一行 |
| alpha.96 | P12.4：`writer` 的组件必须是签名证书的服务身份，否则记录不用（原先只核对签名与证书链，拿到一个组件的凭据能写出以另一个组件为写入者的告警）；P12.27：信任材料只记在运行档案，签发者留存写不进的吊销记录、可达后补写；证据类别去掉 `trust_material`（没有记录者，A148）；向量 `trust-history` 加写入者的两例，`evidence-record` 的类别少一个 | 否：组件之间的线不变 | 兼容：组件写的记录本来以自己为写入者；证据存储拒收 `trust_material`，没有组件写它 | 协议 15 的 6.2 与证据表的信任材料一行 |
| alpha.97 | 新的一章 15“冷热转层”（P15.1–P15.37）：数据类别的声明、单元目录（SDK 的迁移 0017）、规范行与单元的摘要、候选与封存、写屏障（触发器）、认领与发布的代次与纪元、清单与对象的键、释放的条件、目录快照与读取租约、冷读的限度、解冻、保全与销毁、擦除的新清单版本、路线更换、恢复核对 `be.tiering`、规划函数；向量 `tier-digest`、`tier-manifest`、`tier-plan`。错误原因加 `RECORD_SEALED`；`QUERY_PLAN_CHANGED` 也用于目录快照变了。运行档案加类别 `backup`；证据类别加 `erasure` | 否：新的能力，组件声明了数据类别才用到 | 兼容：证据存储（审计组件）先升级才收 `erasure`；没有声明数据类别的组件不变 | 协议 11 |
| alpha.98 | 第 15 章：迁移 0018 给单元加阻塞原因与到期时刻（P15.12）；写屏障的 SQLSTATE `BE001` 进向量 `db-errors`，映射为 `RECORD_SEALED`（P15.13） | 否 | 兼容：只多两列与一行映射 | 协议 11 |
| alpha.99 | 第 15 章：迁移 0019（单元的 `route_version`、解冻的 `be_tier_thaw`）；写屏障放行 SDK 自己对一个单元的写（事务级的 `be.tier_unit`）；释放按 `route_version` 比较租约；备份记录的 `finished_at`；解冻的副本与它的清理 | 否 | 兼容：只多一列、一张表与写屏障的一种放行 | 协议 11 |

到 alpha.39 为止，信封（P6.13 的消息头）、错误体与 `google.rpc.Status` 的形状（P3.1、P3.2）、截止时间与追踪的传递（第 4 章）、发件表与收件表的结构都没有变：alpha.19 到 alpha.39 之间任意两个版本线上兼容（alpha.30 起没有的路由答 501，旧调用方按码归类，结果同样是不重试的失败）。

## 2. 官方 SDK 实现的协议版本

| SDK | 版本 | 协议 |
| --- | --- | --- |
| `be-sdk-go` | alpha.23–alpha.29 | alpha.19 |
| `be-sdk-go` | alpha.30–alpha.32 | alpha.21 |
| `be-sdk-go` | alpha.33 | alpha.23 |
| `be-sdk-go` | alpha.34、alpha.35 | alpha.24 |
| `be-sdk-go` | alpha.36 | alpha.27 |
| `be-sdk-go` | alpha.37 | alpha.28 |
| `be-sdk-go` | alpha.38 | alpha.30 |
| `be-sdk-go` | alpha.39 | alpha.34 |
| `be-sdk-go` | alpha.40 | alpha.35 |
| `be-sdk-go` | alpha.41 | alpha.36 |
| `be-sdk-go` | alpha.42 | alpha.37 |
| `be-sdk-go` | alpha.43、alpha.44 | alpha.40 |
| `be-sdk-go` | alpha.45–alpha.48 | alpha.42 |
| `be-sdk-go` | alpha.49 | alpha.45 |
| `be-sdk-go` | alpha.50 | alpha.47 |
| `be-sdk-go` | alpha.51–alpha.53 | alpha.50 |
| `be-sdk-go` | alpha.54–alpha.56 | alpha.53 |
| `be-sdk-go` | alpha.57 | alpha.56 |
| `be-sdk-go` | alpha.58、alpha.59 | alpha.58 |
| `be-sdk-go` | alpha.60 | alpha.59 |
| `be-sdk-go` | alpha.61–alpha.65 | alpha.60 |
| `be-sdk-go` | alpha.66 | alpha.61 |
| `be-sdk-go` | alpha.67–alpha.70 | alpha.62 |
| `be-sdk-go` | alpha.71 | alpha.66 |
| `be-sdk-go` | alpha.72、alpha.73 | alpha.68 |
| `be-sdk-go` | alpha.74–alpha.76 | alpha.70 |
| `be-sdk-go` | alpha.77 | alpha.71 |
| `be-sdk-go` | alpha.78 | alpha.75 |
| `be-sdk-go` | alpha.79 | alpha.76 |
| `be-sdk-go` | alpha.80 | alpha.77 |
| `be-sdk-go` | alpha.81 | alpha.78 |
| `be-sdk-go` | alpha.82、alpha.83 | alpha.79 |
| `be-sdk-go` | alpha.84–alpha.86 | alpha.80 |
| `be-sdk-go` | alpha.87 | alpha.81 |
| `be-sdk-go` | alpha.88 | alpha.82 |
| `be-sdk-go` | alpha.89 | alpha.84 |
| `be-sdk-go` | alpha.90 | alpha.86 |
| `be-sdk-go` | alpha.91、alpha.92 | alpha.87 |
| `be-sdk-go` | alpha.93 | alpha.88 |
| `be-sdk-go` | alpha.94 | alpha.89 |
| `be-sdk-go` | alpha.95 | alpha.90 |
| `be-sdk-go` | alpha.96 | alpha.91 |
| `be-sdk-go` | alpha.97、alpha.98 | alpha.92 |
| `be-sdk-go` | alpha.99 | alpha.93 |
| `be-sdk-go` | alpha.100 | alpha.94 |
| `be-sdk-go` | alpha.101 | alpha.95 |
| `be-sdk-go` | alpha.102 | alpha.96 |
| `be-sdk-go` | alpha.103 | alpha.98 |
| `be-sdk-go` | alpha.104 | alpha.98 |
| `be-sdk-go` | alpha.105 | alpha.99 |
| `be-sdk-python` | a20–a25 | alpha.19 |
| `be-sdk-python` | a26–a28 | alpha.21 |
| `be-sdk-python` | a29 | alpha.23 |
| `be-sdk-python` | a30、a31 | alpha.24 |
| `be-sdk-python` | a32 | alpha.27 |
| `be-sdk-python` | a33 | alpha.28 |
| `be-sdk-python` | a34 | alpha.30 |
| `be-sdk-python` | a35 | alpha.32 |
| `be-sdk-python` | a36 | alpha.34 |
| `be-sdk-python` | a37 | alpha.35 |
| `be-sdk-python` | a38 | alpha.36 |
| `be-sdk-python` | a39 | alpha.37 |
| `be-sdk-python` | a40 | alpha.40 |
| `be-sdk-python` | a41–a43 | alpha.42 |
| `be-sdk-python` | a44–a45 | alpha.45 |
| `be-sdk-python` | a46 | alpha.55 |
| `be-sdk-python` | a47 | alpha.56 |
| `be-sdk-python` | a48 | alpha.61 |
| `be-sdk-python` | a49 | alpha.66 |
| `be-sdk-python` | a50、a51 | alpha.68 |

Go 取 SDK 的 `go.mod` 里 `be-protocol` 的版本；Python 取包里 `besdk/_protocol/capabilities.json` 的 `protocol`。只列 alpha.19 以来的版本（Go alpha.23 起、Python a20 起）。

## 3. 同一进程里

一个外壳只承载同一语言的成员；进程里只有一个 SDK 版本，由外壳的构建决定，不早于任何成员要求的版本（装配项目协议 17、18 的 SK09）。Go 外壳的模块图对 `be-sdk-go` 只取一个版本（最小版本选择取各成员要求的最高版本），这一点由构建保证。Python 外壳用 `override-dependencies` 指定 `be-sdk-python` 的版本，可能比某个成员要求的旧：成员在包元数据里声明最低版本（依赖写 `be-sdk>=<它钉的版本>`，钉的 Git 标签照旧写在 `[tool.uv.sources]`），外壳启动时核对，没有声明或不满足的拒绝启动（P1.21，`be-sdk-python` a35 起）。成员按自己要求的版本测过，在外壳的版本上运行，靠 SDK 在同一主版本内向后兼容。
