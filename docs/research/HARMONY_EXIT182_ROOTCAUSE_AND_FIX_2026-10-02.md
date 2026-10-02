# 华为/HarmonyOS 设备 OpenMinis 1.14 沙盒 exit-182 随机崩溃：根因定案、候选修复与接手指引

日期：2026-10-02（跨 10-01/10-02 多个调查会话汇总定稿）

> **hf3 接手复核纠正（2026-10-02）**：本文“182 后重试整条命令零副作用”的结论不成立：一个内层 exec 的 loader 失败，不排除外层用户代码已经执行。旧 reg.c 候选补丁还存在 iovec 指针复用、32 位 syscall 回读、AArch32 布局与未再次校验等问题，不能原样用于构建。实际修复与验收以 [hf3 交接](HARMONY_HF3_HANDOFF_2026-10-02.md) 为准。本文未包含其引用的 §2 原始 trace，因此“内核根因定案”目前是原会话推断，本轮尚未独立复核真机原始证据。
分支：`upgrade/openminis-1.14-harmony`
前置文档：`docs/research/HARMONY_AGENT_SANDBOX_CRASH_2026-10-01.md`（第一份研究报告；本文是其最终定案与修复稿）
读者：接手推进的任何人/任何 AI（ChatGPT、新会话等）。本文自包含，不依赖任何历史会话上下文。

> 沙盒环境注意（对在真机沙盒里跑命令的会话都适用）：若用户环境变量 `PROOT_VERBOSE=6` 仍在，外层 proot 会向每条 shell 命令的 stderr 灌 ~350KB trace，上下文会被淹没。定案后建议删除该变量；若必须抓现场，命令一律 `cmd > /tmp/x.txt 2>&1` 落盘、再用文件读取工具查看，不要把输出引入对话。

## 0. 一页速览（先读这里）

| 项 | 内容 |
|---|---|
| 设备 | 华为 HarmonyOS ROM / Linux kernel 5.10.43 aarch64 / App `com.openminis.app.dev`（OpenMinis 1.14 dev） |
| 沙盒 | Alpine 3.21.3 rootfs + proot（vendored Termux loader 5.1.107-70，jniLibs `.so` 打包） |
| 症状 | 每条 shell 命令 ~4–7% 概率无输出死亡：**exit code 182**（= proot ELF loader 的 `FATAL()`，wstatus 0xb600）；亦有 SIGSEGV/SIGBUS 与 `event.c:568` 断言形态 |
| 根因 | 本 ROM 内核在 ptrace 停止↔恢复循环中，**偶发不能忠实保留跟踪态**（寄存器文件回到陈旧快照 / 最近写丢失）。loader 执行 MMAP_FILE 语句时读到陈旧 x0（典型 `0xfffffffffffffff2`=-14 错误码残留）→ `status != stmt->mmap.addr` → FATAL → exit 182 |
| 证据 | 真机 v6 现场抓取 ≥5 次独立死亡窗口，形态完全一致（§2.3）；POKEDATA 1000/1000 全过（内存写原语正常）；ET_EXEC 0% vs ET_DYN 4–7%（ptrace 周期数差异决定暴露度） |
| 候选修复 1 | proot `reg.c` 补丁：写回顺序调整 + 写后回读、不匹配即重写一次。**已编译通过，未装机验证**。能拦"停止期间写回丢失"（机制 b），拦不住"恢复时刻陈旧快照"（机制 a） |
| 候选修复 2 | App 层 182 安全重试：182=loader FATAL 发生在 guest 任何代码执行前 → 重试零副作用。**未实施**（§4.2）。这是无论内核细节如何都成立的兜底方案 |
| 已判死路线 | 换 proot pin（两 pin loader/execve 路径逐字节相同）；PROOT_LOADER 热替 app-data（W^X 在 mmap PROT_EXEC 层拦截）；嵌套 proot A/B 修复验证（结果不代表外层） |
| 下一步优先级 | ①App 层 182 重试（止血）②NDK 重编 proot+loader+APK → 真机 catch182.sh 量化 ③无效则 loader_diag2 拆 FATAL 分支定位 ④上游报告 |

补丁文件在本文同步提交的 `docs/research/patches/reg-c-huawei-regset-verify.diff`。关键文件与工具索引见 §6；负面清单合集见 §8。

## 1. 症状与故障面（真机实测）

### 1.1 故障面测定（2026-10-02 多组对照实验，出处 HANDOFF-2026-10-02.md）

| 目标类型 | 样本 | 失败 | 说明 |
|---|---|---|---|
| ET_EXEC 静态（direct execve） | 300 | **0** | 挂载链最短 |
| ET_EXEC + INTERP（动态非 PIE） | 200 | **0** | |
| ET_DYN 静态 PIE | 300 | 21 (~7%) | |
| ET_DYN 动态（busybox 等，/bin/true） | 150 | 8 (~5%，全为 182) | catch182.sh 最近基线 |
| shebang 脚本 direct execve | 漂移 | 曾 19/20 与 ~100% EFAULT 记录；另一测 0/12 | 同机制不同暴露度，**勿用单点数字断言** |
| shell 内建 | — | 0 | 不经新进程 execve |
| open×8000 / mmap(MAP_FIXED)×500 / 文件 mmap×200 | 各组 | 0 | 排除纯 syscall 风暴假说 |
| POKEDATA/PEEKDATA/process_vm_writev（合法地址） | 1000 | 0 | **内存写原语正常** → 指向寄存器/跟踪态族 |

结论：**故障概率 ≈ f(该进程经历的 ptrace 周期数)**，而非 f(某类 syscall)。ET_DYN（loader+ld.so 全程被跟踪）周期最多、最先暴露；ET_EXEC 最短、未观察中招。182 / SIGSEGV / SIGBUS / event.c:568 是同一根源的三种表现。

### 1.2 exit 182 的确切含义（源码定案）

- wstatus `0xb600` = WIFEXITED 正常退出、exit code 182。
- 出处：proot loader 的 `FATAL()` 宏 → `SYSCALL(EXIT, 1, 182)`（loader.c:47；两代 pin 的 loader 逐字节相同）。
- **182 = loader 放弃加载**，发生在 guest 用户代码（busybox/sh）任何指令执行之前 → 同参数重试零副作用（§4.2 方案的根基）。
- fork 版 loader.c 全文无任何 VERBOSE/note 调用 → 调大 PROOT_VERBOSE 不会有 loader 内部日志（实测确认）；loader 可观测化的唯一手段 = 拆退出码（loader_diag2，§4.3）。## 3. 根因（原会话假说，待原始证据与真机对照复核）

**本 ROM（华为 HarmonyOS，kernel 5.10.43）在 ptrace 停止↔恢复循环中偶发不能忠实保留跟踪态。** 具体拆成两个不可区分表象（对 proot 而言都表现为"写进去了、恢复时不翼而飞"）：

- **机制 a（恢复时刻陈旧快照）**：内核在恢复 tracee 时使用陈旧的寄存器文件快照，最近一次（或数次）PTRACE_SETREGSET 写入的结果丢失或部分丢失。
- **机制 b（停止期间写丢失）**：写入在 tracee 停止窗口内即未生效（GETREGSET 回读可发现）。

proot 的 `chain_next_syscall`（syscall/chain.c）在链式 syscall 重启时用 `poke_reg` 改写 SYSARG/INSTR_POINTER 等并 `restart_how=PTRACE_SYSCALL`，每周期 2 次 SETREGSET；loader 每条语句都依赖这套机制的精确性。任一机制中招即出现 §2.1/§2.2 现场：

- x0 = 上一发内核返回值残留（−14 EFAULT / −22 EINVAL 均实测出现）、x1–x5 = 本发新值 → MMAP_FILE 失配 → **182**
- IP 写入丢失/回拨落错 → **SIGSEGV/SIGBUS**（垃圾 entry）
- 事件序与 restart_how 失步 → **event.c:568 断言**（signal 6）

为什么 ET_EXEC 不崩：其加载路径 ptrace 周期最少（无需 loader 逐语句映射），掷骰子次数少到观测不到；ET_DYN/PIE/loader 链周期数高几个数量级 → 4–7% 发生率与"每周期小概率×周期数大"吻合。宿主内存压力与崩溃率无显著相关（400 次采样成功/失败组 MemAvailable 均值差 <3MB）——**"内存不足"是伪相关**，不要再查它。

## 4. 修复方案（现状：候选补丁已实施，验证链未走完）

### 4.1 proot reg.c 补丁（已打、已编译，未装机验证）

文件：`docs/research/patches/reg-c-huawei-regset-verify.diff`（相对 `OpenMinis/proot@1b444ee` 的 `src/tracee/reg.c`）。

内容（`[T-huawei-regset-dr]` 注释锚点）：
1. **顺序调整**：先写 NT_PRSTATUS（通用寄存器组）再写 NT_ARM_SYSTEM_CALL（syscall 号），原代码反向。
2. **(2a) syscall 号写后回读**：GETREGSET(NT_ARM_SYSTEM_CALL) 校验，不匹配立即重写一次。
3. **(2b) 通用寄存器组写后回读**：GETREGSET(NT_PRSTATUS) 只比较前 33 个 word（x0–x30、sp、pc；pstate 被内核写时屏蔽会产生假阳性，必须跳过），不匹配重写一次。

限制（诚实声明）：这只拦**机制 b**。若死亡发生在机制 a（tracee 已恢复、寄存器在恢复时刻被内核丢弃快照），停机期间校验无能为力——**装机后大概率只是降低崩溃率而非归零**（本会话多次 182 恰落在 proot 主程序自身的 trace 上，说明 a/b 均在真机发生）。
编译证据：沙盒 musl 构建 `REBUILT_OK attempt=3`，reg.o 5352B（基线 5032B，+320B 为校验代码）；二进制 sha256 已存 `v6fail/binaries/BINARIES_README.txt`。**该二进制只验证了语法语义，未在真机外层环境验证效果**。

### 4.2 App 层 182 安全重试（待实施，优先级最高）

**hf3 纠正：**182 的语义是某一次 exec 的 loader 放弃，仅证明该次目标未进入用户代码。整条命令此前可能已经执行、写入文件或发送请求，不能无条件重跑。hf3 在内层命令 shell 进入任何用户代码之前写入独立 started 标记，标记写失败以 125 退出；仅未越过此边界的 loader 失败才允许最多 3 次启动重试，并共用原超时预算、遵守取消。实现见 `LoaderStartupRetryPolicy.kt` / `FreshProcessShell.kt` / `ForegroundCommandGroup.kt`。

以下原建议保留作为历史材料，不能不加上述边界直接实施：

- `SeccompFallbackPolicy.kt`（现有"动态链接异常退出自动兼容重试"的所在，Issue #186 机制）：将 **exit 182 与 0xb600 状态识别为 `loader-fatal` 类**，走既有重试通道（建议退避：立刻 1 次 → 50ms → 200ms，上限 3 次；并在日志埋点统计命中数）。
- `FreshProcessShell.kt`/`ExecutionCoordinator.kt`：把 `[Shell not running] (exit code: 182)` 的静默失败改为打点+重试后仍失败才上抛。
- 保留现有强兼容模式；注意与 AgentSandboxCompatibility 状态机解耦（重试是进程级机制，不应改变兼容档位）。

### 4.3 loader_diag2（已备好、未消费）

诊断版 loader（与官方仅差 7 个立即数：FATAL 分支改写成 60–66），宿主路径 `/data/data/com.openminis.app.dev/files/minis-global/shared/work/OpenMinis-investigation/diag-loaders/loader_diag2`（755 已确认）。解码表：60=open 失败 / 61=MMAP_ANON 不等值 / 62=close(OPEN_NEXT) / 63=**MMAP_FILE 不等值** / 64=未知 action / 65=close(START)。
**注意**：`PROOT_LOADER` 环境变量指 app-data 路径会 EACCES（W^X 拦截，已判死两次）——loader_diag2 只能在**重新打包 APK** 时替换 `jniLibs` 里的 `libproot-loader.so`（同尺寸、stub 偏移 0x4460 不变），或未来 App 支持 loader 内打包替换时使用。

### 4.4 NDK 重编验证链（修复落地必经，需 PC）

1. PC NDK r28+ 按 `deps/build_proot.sh` 构建打上 §4.1 补丁的 proot + loader（musl/沙盒内构建只算占位证据）。
2. 构建产物放 `src/android/app/src/main/assets/proot-aarch64` + `jniLibs/arm64-v8a/libproot{,-loader}.so`（可先只换 proot）。
3. `src/android/app/build.gradle.kts` 当前签名配置不动 keystore 内容；APK 装机后先跑 `catch182.sh`（见 §6.2）≥150 样本，对比基线 8/150；再跑 24h 日常使用观测。
4. 若 182 降幅 <2× → 大头是机制 a：转 loader_diag2 分支定位（§4.3）+ 纯内核侧 workaround（如 chain 窗口内 PTRACE_GETREGS 回读重拨——需改 chain.c，本补丁未含）。## 5. 已判死路线（勿再尝试，附判死证据）

| 路线 | 判死证据 |
|---|---|
| 换 proot pin（回退旧 8cf13e9） | 两 pin 的 loader.c/enter.c/elf.c/auxv.c/tracee.c/event.c 逐字节一致；换 pin 不改变 182 行为 |
| `PROOT_LOADER` 指向 app-data 路径热替 | 两次实测：外层 proot execve loader 直接 EACCES → 本 ROM W^X 在 **mmap PROT_EXEC 层**拦 app_data_file（execve 层不拦：/tmp 拷贝直跑正常；nativeLibraryDir 例外因 SELinux 执行许可）。**设置环境变量 PROOT_LOADER=/data/data/... 即全沙盒死锁，只能删变量解救** |
| 嵌套 proot A/B 验证修复效果 | 嵌套环境 exec 链自身差异 → smoke 全空/ENOENT，结果不代表外层行为；A/B 只能用于**源码语义冒烟**（如 loader stub 偏移验证），不能量化崩溃率 |
| Termux loader 原包重建 | Termux 原包已 404；git 内 vendored 版（5.1.107-70）是唯一源，勿试图从上游重取 |
| 内存压力假说 / no-ASLR 假说 | MemAvailable 组均值差 <3MB（400 样本）；personality(ADDR_NO_RANDOMIZE) 返回 EPERM（无 no-ASLR 权限，ASLR 常开，伪相关） |
| seccomp/offload/netlink 假说 | 强保守模式（NO_SECCOMP=1 + 无 offload + 无 fake-netlink + serialized）下崩溃依旧 |
| PROOT_VERBOSE 拿 loader 内日志 | fork 版 loader.c 无任何 VERBOSE 调用（全文检索）——v 调多大都没有 loader 输出；唯一出口=拆退出码 |

## 6. 资产索引（都在 `git-one-two/OpenMinis` 分支内或用户沙盒共享区）

### 6.1 仓库内
- `docs/research/HARMONY_AGENT_SANDBOX_CRASH_2026-10-01.md` — 第一份研究报告（症状与早期假设）
- `docs/research/HARMONY_EXIT182_ROOTCAUSE_AND_FIX_2026-10-02.md` — **本文**（定案）
- `docs/research/patches/reg-c-huawei-regset-verify.diff` — reg.c 候选补丁
- `deps/build_proot.sh` — 构建脚本（注释里就是 W^X 教训原文）
- App 侧关键文件：`FreshProcessShell.kt`（loader/envVars 注入 L310-323）、`SeccompFallbackPolicy.kt`（182 重试改造点）、`PersistentShell.kt`、`ExecutionCoordinator.kt`、`PRootKernel.kt`、`AgentSandboxCompatibility.kt`

### 6.2 沙盒共享区（真机会话可见，`/var/minis/shared/work/OpenMinis-investigation/`）
- `STATUS.md` / `HANDOFF-2026-10-02.md` — 推进状态与此前交接（本文部分引用其证据编号）
- `catch182.sh` — **崩溃捕获标准工具**（A=/bin/true 150 发压测、B=shebang 复现、产物落 `out182/A_*.jsonl`；基线 A_miss=8/150 全 182，shebang 0/12）
- `diag-loaders/loader_diag2` — 诊断 loader（§4.3）
- `v6fail/` — 定案现场：`DEATH_EVIDENCE.md`（两形态原文）、`batch-verify.log`、`binaries/`（基线/补丁二进制 sha256 + `reg-fix.diff`）
- `old-apk/` — 旧 0.20 APK 提取物（loader 对比用）
- `out182/` — 各轮捕获历史

### 6.3 环境事实（接手真机操作的会话须知）
- 外层 proot 环境变量由 `FreshProcessShell.kt` 注入；**用户环境变量（App 设置→环境变量）最后写入、可覆盖一切**（已验证 PROOT_VERBOSE/PROOT_LOADER 两条通道）。危险项：设空串=全命令 ENOENT。
- App 文件日志可经 `/proc/<appPid>/fd/97` 读（PID 会变）；数据库 `databases/minis.db`（fd 111 曾可复制；`parts_json` 字段名是 `value`）。
- shebang shim 工具（minis-config 等 17 字节 `#!/bin/sh` 包装）在崩溃期 100% EFAULT——**改用 `sh <文件>` 或 python3 直调**。

## 7. 建议的接手执行清单（按序）

1. **（0 成本）删 `PROOT_VERBOSE` 环境变量**（App 设置→环境变量）——定案后不再需要；留着就是每命令 350KB 噪声。
2. **立即实施 §4.2 App 层 182 重试**（纯 Kotlin，1-2 文件），发一版 dev APK 装机 → 观察 24h。
3. 并行 PC NDK 重编（§4.4），产出含 §4.1 补丁的 proot，第二版 APK 装机 → `catch182.sh` 前后对比（样本 ≥150/组）。
4. 按 §4.3/§4.4.4 分叉决策：降幅达标→收口；不达标→loader_diag2 分支定位或 chain.c 回读重拨。
5. （可选，上游）以本文 §2 证据向 proot 上游（proot-me/termux）报告 ptrace 停止-恢复寄存器丢失现象——附 v6 trace 原文；华为内核问题若被上游确认，修复会以更普适形态回来。

## 8. 负面清单（本会话已证伪，别再引用）

1. "9 组链式参数错配"统计 — 采集脚本从未跑成，**作废**；可用统计只有 catch182.sh 真实样本。
2. "mmap 翻译层损坏" — POKEDATA/文 mmap 对照全过，未证明。
3. "POKEDATA workaround 需求" — 合法地址 1000/1000，前提不成立。
4. "新 pin 的 fake_netlink/link2symlink 引入" — 与故障面无相关（强保守下依旧崩）。
5. "no-ASLR 显著相关" — personality 被 EPERM（伪相关）。
6. "低内存触发" — §3 末段。
7. "A/B 嵌套修复验证有效" — §5。
8. 沙盒内musl自建 proot 的 loader 布局（67KB 单段、-Ttext 异常）与 APK 产物不同构 — 若要 loader 修改实验，一律基于 vendored Termux 源 + NDK 构建，不要用沙盒自建布局。

（§1.1 的 shebang 数字漂移、§4.1 的"未装机验证"状态都是刻意保留的不确定性——接手者重测时以新样本为准。）

— 完 —

*文档生成：2026-10-02，Minis 会话（沙盒内取证，崩溃打断下完成，全部结论可溯源至 §6.2 文件）。*