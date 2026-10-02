# hf6-device 真机复测判读（2026-10-02 19:xx，400+40×3）

**总判：hf6 未解决**——八月原包执行栈（loader 12d2b63e + proot da94efb1 已确认装机）在新包装内 182 失败率 33/400=**8.2%**，与修复前基线（5-7%）同量级。**这是本轮最有分量的对照：八月"能跑"的同一套二进制在 1.14 包装下照样崩 → 崩的差异不在 proot/loader 二进制本身，而在 1.14 App 壳的执行环境（FreshProcessShell 注入参数/绑定/启动时序/串行化策略）**。

## 判分
- legacy_environment           PASS
- all_nested_true_pass         FAIL
- shebang_argv_preserved       FAIL
- user182_preserved            PASS
- user_writes_exactly_once     FAIL
- argv_env_preserved           PASS
- parent_still_alive           PASS
- hf6_legacy_loader_installed  PASS
- hf6_native_installed         PASS

## 数据
- flags: {'PROOT_EXEC_LOADER_RETRY': None, 'PROOT_VERIFY_REGSET': None, 'PROOT_VERBOSE': None}（legacy_environment PASS：retry/verify 两变量确已消除）
- nested-true 400: {'0': 367, '182': 33}
- shebang 40: EFAULT 40 个; 其余 0 个（exit 分布 {}）
- user-write-exit182 40: {'182': 40}（182 全保留，无吞码 → legacy 栈无 §4.2 类语义缺口）
- writes=38/40（缺 2 次 = 两个 user-write 子进程 execve 阶段 182 死亡，写入未达——注意这是「从未执行」型缺口，非 hf5 的「执行后吞码」型）
- apk: libproot.so=da94efb1(✓期望), libproot-loader.so=12d2b63e(✓期望=八月原包)
- 用时: 16s 完成全部（含 400 次采样）— 无 retry 层开销

## 三轮横向对照
| 轮 | 执行栈 | 失败率 | 形态 |
|---|---|---|---|
| hf3 前(基线) | 1.14 + 44ef39c1 loader | 8/150≈5.3% | 182 |
| hf3 | 同上（reg.c补丁进 proot 主程序） | 8/80=10% | 182 |
| hf4 | libproot.so=aa29de2e + App 层重试 | 28/400=7% | **−9 SIGKILL**（重试末端未恢复）|
| hf5 | libproot.so=b94022ea + 原生校验 | 24/400=6% | −9 24 次 + retry-register EINVAL 27/27 |
| **hf6** | **八月 loader+proot 原包** | **33/400=8.2%** | **182 回来了**（与基线同形） |

## 判读与切口
1. **失败与二进制无关**：hf6 用八月原包 loader/proot，仍 8.2% 182——排除"新 proot/loader 编译产物引入缺陷"。差异只能在 App 壳如何运行同一套二进制。
2. **形态回归 182**：legacy 栈没有 retry/verify 层 → 死亡直接以原始 182 露出（没有 SIGKILL 转移面）——进一步支持 182↔−9 是同一底层失败在上层不同处理下的不同投影。
3. **八月版为何当时"稳定"而现在不稳**：(a) 当时 App 壳为 0.20-preview-dev（执行参数/绑定集合不同）而 hf6 只回填了 libproot 系二进制、壳仍是 1.14；(b) 当时使用频率/并发远低于今天 Agent 会话串行压制；(c) 八月记录本身未必做过 400 样本采样——"稳定"可能只是暴露少。建议 ChatGPT 对比 0.20 与 1.14 壳的 FreshProcessShell/PRootKernel 执行参数全集（env、bind、-0/-r/-b 顺序、工作目录、setsid 包装），找 182 率的环境敏感项。
4. **下一步最高性价比**：在 1.14 壳里逐项复刻 0.20 壳的执行参数做 A/B；同时把 hf5 retry-register EINVAL 三切口（iov_len 272B/syscall-restart 时序）修入 HF 系重试——两条线独立推进互不阻塞。

*证据等级：真机实测 400 样本；§判读 3 的 (a)(b)(c) 为推断已标注。敏感扫描 0 命中。*
