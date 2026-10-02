> ChatGPT 源码复核更正（2026-10-02）：HF5 未修复的判分不变。下文 §2 把日志 sysnum=61 当作 ARM64 Linux getdents64 的解释错误：日志使用 get_sysnum() 返回的 PRoot neutral enum，syscall/sysnums.list 第61项为 PR_execve。kernel-exec 位于 execve sysexit，调用者PC在ld-musl并不能证明getdents64或动态链接器寄存器损坏。retry-register 聚合errno=22也不足以确认具体ptrace request/内核拒绝原因。原始JSON中user182为37个182+3个-9（不是39+3）；缺的3次写入只能证明启动失败，不是用户写完后的退出码被吞。原判读保留作历史，修复方向见 docs/research/HARMONY_HF6_LEGACY_BASELINE_2026-10-02.md。

# hf5-device 真机复测判读（2026-10-02，400 样本 + 40×3 侧例）

前置：`docs/research/HARMONY_EXIT182_ROOTCAUSE_AND_FIX_2026-10-02.md`（根因定案）、`docs/research/hf3-device/`、`docs/research/hf4-device/`（两轮未修好）。
**总判：hf5 未解决**——崩溃率 6%（24/400 SIGKILL），量级与根因基线（182，5–7%）相同；但 HF5 新增原生诊断日志首次抓到失败内部机理（见 §2），价值大。

## 1. 五项检查判分

| 检查项 | 结果 | 证据 |
|---|---|---|
| retry_environment_enabled | PASS（重试环境已启用） | flags: RETRY=1, VERIFY_REGSET=1 |
| all_nested_true_pass | **FAIL** | /bin/true ×400 = {0: 376, **−9 SIGKILL: 24**} |
| shebang_argv_preserved | **FAIL** | shebang×40 = **40/40 execve EFAULT(Errno 14)**，诊断日志 retries=0 |
| user182_preserved | **FAIL** | user-write-exit182: 39 命中 182 + 3 次 −9（被吞） |
| user_writes_exactly_once | **FAIL** | writes=37/40，缺 3 次 |
| argv_env_preserved / parent_still_alive | PASS | "a b'\\n中文 $ x|1|1"，"alive" |
| hf5_native_installed | **PASS** | APK `libproot.so` = `b94022ea…`（与 HF5 期望精确匹配）；loader 仍 `44ef39c1…` 未变 |

失败率横向：hf3 前 8/150≈5.3%（182）→ hf4 28/400=7%（−9）→ hf5 24/400=6%（−9）。**三轮同量级，未改善**。

## 2. 新证据（HF5 native 诊断，HF5_exec_diag.log 13580B）

阶段统计：`kernel-exec 40 / retry-start 27 / retry-register 27 / retry-failed 27`。

### 2.1 失败形态已明确到内核现场：两次独立中毒点

**形态 A：loader 后期 ld-musl 阶段 getdents64 EFAULT（40 次，shebang 路径）**
```
stage=kernel-exec code=-14 status=1 sysnum=61 pc=3f00048634 sp=7f4e9c4e05 retries=0
```
- `sysnum=61` = arm64 `getdents64`；`pc=0x3f00048634` 已在 ld-musl 代码区（0x3f00_0000_0000 基址段），**不是** proot loader 的 MMAP 链现场
- 含义：elf 装载已完成、动态链接器已接管，proot 跟踪下其 getdents64 缓冲区指针(x1)为 EFAULT → 与根因定案一致：**ptrace 停止↔恢复边界的寄存器写丢失对任何 syscall 通用**（此前只见过 loader 语句窗口的 mmap 现场）
- `retries=0`：**App 重试机制完全没有覆盖这条路径**（见 §2.3）

**形态 B：proot pre-entry 重试路径 getdents64 被写歪 + 寄存器重写被内核 EINVAL 拒绝（27 次）**
```
stage=retry-start   code=1 status=0 sysnum=61 pc=20000002fc sp=7e6d8a2c88 retries=1
stage=retry-register code=22 status=1 sysnum=61 pc=20000002fc sp=7e6d8a2c17 retries=1
stage=retry-failed  code=543003651095 status=1 sysnum=61 pc=20000002fc sp=7e6d8a2c17 retries=1
```
- retry-start：HF5 校验器主动判定失败（code=1）
- retry-register：**HF5 对子进程重打寄存器 → 内核返回 EINVAL(errno=22)**，27/27 全部被拒
- retry-failed：code=543003651095 ≈ 0x7E6D8A2C17（**= sp 异常值**，不是合法 PC/结果指针！）→ 寄存器写歪后拿不到结果寄存器，子进程停在 syscall 状态被外层清理
- **注意 pc=20000002fc 在 loader 代码区**（0x2000000000 RO 段内偏移 0x2fc）——这批是 loader 自身 retry 段的现场

### 2.2 算术闭合

```
24(SIGKILL nested-true) + 3(user-write-exit182 被吞) = 27 = retry-failed 次数
40 (shebang) = kernel-exec 阶段数（retries=0，死在重试之外）
```
重试机制对它自己启动的 27 次全部失败（EINVAL）；对不在其覆盖内的 40 次一次未试。**两条路径全军覆没。**

### 2.3 判读给修复方向的三个明确切口（转 ChatGPT）

1. **retry-register EINVAL 27/27 = HF5 的寄存器重写 API 用法与内核拒绝条件不匹配**。怀疑点（按概率）：
   a) SETREGSET `iov_len` 用了错误结构长度（arm64 NT_PRSTATUS 期望 user_regs_struct 272B = 34×8；HF5 或从 Java 层取 34*4?）
   b) 写回发生在子进程已进入 syscall-restart 状态（PTRACE_SYSCALL 已挂）时，该内核拒绝 NT_ARM_SYSTEM_CALL 或部分寄存器写（真 EINVAL 来源需用 PTRACE_GETREGSET 先探）
   c) 写的对象是 chain-restart 窗口中的 tracee，内核要求先 PTRACE_DETACH/中断。建议：retry-register 失败时**dump errno 完整路径**（哪个 request、哪个iov_len、当时 wait status），一条日志成本可定位
2. **shebang 路径 retries=0**：重试判定条件没覆盖"execve 阶段 EFAULT"的形态——检测条件里可能只认 182/loader code，没认 Errno14-from-execve。需要在 shebang 判定条件里加入 EFAULT 检测（execve 系统调用的 sysexit 返回 −14 且该进程从未执行 → 重试安全）
3. **覆盖面仍为零 loader 校验**：APK libproot-loader.so 哈希三轮未变（44ef39c1…）。本轮所有死亡都在"loader/ld-musl + 停止恢复边界"，proot 主程序补丁（§4.1）拦不住恢复时刻丢写。若走 App 重试路线（§4.2）+ 补 shebang EFAULT 判定，应能将用户可见失败压到 <0.5%。彻底根治仍需内核侧（本 ROM 无解）或 proot chain.c 内重拨方案。

## 3. 上传文件清单（本目录）

- `VERIFY_2026-10-02_hf5.json` — 采集全量（480 行：flags、exit counts、writes、checks、apk hashes、每 sample rows、native_diagnostics 摘要）
- `HF5_exec_diag.log` — native 诊断日志全量（13580B；含 stage=/time=/pid= 行；pid 为沙盒内瞬时值无隐私）
- `verify_hf5.py` — 采集脚本原样收录（可复跑：`python3 docs/research/hf5-device/verify_hf5.py --samples 400`）
- `hf5-analysis.md` — 本判读文档

敏感性：四件均经 ghp_/github_pat_/authorization/token/api_key/secret/password 模式扫描 = 0 命中；未含密钥或 token；pid 为临时沙盒值。
结论证据等级：真机实测（本轮采集），无推断部分未标注；§2.3 三条切口为建议方向，属推断，已标注。