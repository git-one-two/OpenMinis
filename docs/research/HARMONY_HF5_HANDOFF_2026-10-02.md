# Harmony hf5：恢复流程修正与真机诊断
日期：2026-10-02。状态：候选，华为真机验收尚未完成。

## hf4 验收事实
原始数据在 docs/research/hf4-device/，commit 2853190cc91f。
/bin/true 372/400 成功，28 次 SIGKILL；shebang 40/40 execve EFAULT。
写后 exit182：39 次写入并返回182，1 次 SIGKILL且未写入。
不能据此声称用户代码被重放；退出码与写入次数验收均失败。

## hf5 改动
源代码 commit 63f94e960bd2b4a11f2d7b81f860e03b401ba69b，APK versionCode=11405。
- 改写 loader EXIT 为 EXEC 时，要求 PTRACE_SYSCALL 返回阶段，维持 sysexit_pending。
- ARM64 seccomp 过滤增加 exit 停止点，使恢复入口在加速模式也可观察。
- loader hook 移到 restore_original_regs=false 之后；保留 ORIGINAL 快照会清掉的 dirty 标记，避免寄存器修改不写回。
- 继续只恢复已确认处于固定地址 loader、尚未越过 PR_SET_NAME 的单个子程序；不重放父程序。
- 保留原 pinned Termux loader，不把 fork 重编 loader 替换进 APK。
- 输出有大小上限的诊断文件：/var/minis/shared/work/OpenMinis-investigation/HF5_exec_diag.log。
  记录 pid/阶段/错误码/sysnum/pc/sp/重试次数，不记录 argv、环境内容或密钥。
  阶段包括 retry-start、retry-register、retry-failed、shebang-expand、kernel-exec。
  errno 会在诊断写入后恢复，文件上限约128KiB，写入失败不改变命令结果。

## 实际验证
原生 ARM64 Linux CI 使用完整 PRoot 和 APK 的 pinned loader，非 mock/非QEMU。
run 36988594045 成功，共24组240个子进程：
seccomp 开/关 × 故障0/1/3/4次 × true/shebang/user182。
故障由临时测试源码故意改写 loader mmap 参数产生；负面对照必须真正命中故障才通过。
1或3次故障后恢复；4次故障超过最多3次重试后保留182。
保留 shebang 中空格、换行、中文参数；用户写入恰好一次并返回182。
测试注入仅在临时 CI 目录，未进入 APK。此结果不证明 Huawei kernel 已修复。

## 真机接手
安装 home-dev-control 的 hf5 APK，版本应显示1.14-dev-hf5。
更新分支后，在 Agent shell 中运行：
python3 docs/research/hf5-device/verify_hf5.py --samples 400

上传生成的 VERIFY_2026-10-02_hf5.json 和 HF5_exec_diag.log 到 docs/research/hf5-device/。
仅取测试所需日志；不要上传密钥/token或整份环境变量。无需开启 PROOT_VERBOSE。
报告含逐样本结果和本轮新增诊断内容，脚本不改代码、不递归调用 debug.shellExecute。
同 hf4 验收条件：400/400 true、40/40 shebang、40个用户182且恰好40次写入、参数保持、父进程存活。
任何一项未过都继续视为未修复。shebang EFAULT 的设备根因尚未定位，须用新增阶段日志区分翻译层与 kernel exec。
