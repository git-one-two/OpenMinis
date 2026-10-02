## 修正：shebang-argv 40/40 全部为 execve EFAULT (Errno 14)
- 退出码 None + error=[Errno 14] Bad address → subprocess 在 execve 阶段即失败（shebang 解释器加载路径）
- 与定案文档历史结论一致：shebang direct execve 在故障窗口 ~100%% EFAULT

## 最终归类
- nested-true 400: {'0': 372, '-9': 28}
- user-write-exit182 40: {'182': 39, '-9': 1}
- shebang 40: {'EFAULT': 40}（EFAULT 40/40）
- writes=39/40 (缺 1 次: 某 user-write-exit182 子进程被 retry 吞掉, 退出码 -9)

## 综合判分（对照 ChatGPT hf4 五项检查）
- retry_environment_enabled    PASS
- all_nested_true_pass         FAIL
- shebang_argv_preserved       FAIL
- user182_preserved            FAIL
- user_writes_exactly_once     FAIL
- argv_env_preserved           PASS
- parent_still_alive           PASS

PASS: retry_environment_enabled 2/3 flags on（PROOT_VERBOSE=null 属正常）
FAIL: all_nested_true_pass（-9 x28 = SIGKILL）
FAIL: shebang_argv_preserved（EFAULT x40 = 100%失败）
FAIL: user182_preserved + user_writes_exactly_once（重试通道吞掉 1 次用户级 182）
PASS: argv_env_preserved + parent_still_alive（管道/参数/中文名保留正常）

## 与基线对比
| 指标 | hf3 前 | hf4 现在 |
|---|---|---|
| /bin/true（ET_DYN 直跑）fail | 8/150 (=5.3%) 全 182 | 28/400 (7%) 全 -9 (SIGKILL) |
| shebang fail | 0/12 ~ 19/20 漂移 | 40/40 (100%) EFAULT |
| user182 吞码 | 未测 | 1/40 |

## 结论
hf4 未解决失败，且失败形态从 182 转为 SIGKILL/-9：
(1) 重试环境已启用（retry=1/verify=1）
(2) 但 SIGKILL 比例 ≈7% 与旧 182 率同量级 → 宿主/外层最终放弃重试的路径仍未修复
(3) shebang 100% EFAULT — 历史上最恶劣形态，比 hf3 复测(1/10)明显恶化
(4) user-write-exit182 吞码 1/40 = 语义正确性缺口（用户程序"写后退出182"被重试层吞掉一次）
(5) apk libproot.so 已换（aa29de2e）、loader 未变（44ef39c1）— 与 hf3 相同，App 层改动未伴随 loader 重编
