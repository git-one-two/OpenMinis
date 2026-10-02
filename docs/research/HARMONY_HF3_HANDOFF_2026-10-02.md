# HarmonyOS OpenMinis hf3：代码修复与验证交接（2026-10-02）

## 当前结论

- 源码分支：`upgrade/openminis-1.14-harmony`，修复提交 `2c0756ed09d8597e9bad4bdf63dba8a5b7985191`。
- 本轮已修复代码层缺陷，正在执行 CI 的 NDK 构建、沙盒回归测试和 APK 构建。
- **未连接到用户手机（adb devices 为空），没有真机修复成功的证据。**
- 旧报告指向 ptrace/loader 路径，但“华为内核丢失恢复快照”仍需原始现场与对照实验验证；不能由退出码 182 单独证明。
- 旧交接文档缺少其引用的 §2 现场正文。用户手机共享目录里的原始 v6 日志尚未由本轮读取。

## 关键纠正

1. Loader 的 182 只证明**该次 exec 的目标**未进入用户代码；不证明整条 shell 命令此前没有执行。内层 exec 崩溃时，外层命令可能早已写入文件或发送请求。
2. 原研究补丁复用 `struct iovec regs`：写 syscall 号后其地址仍指向 syscall 变量，再拿它重写 NT_PRSTATUS，属于错误寄存器缓冲区。
3. NT_ARM_SYSTEM_CALL 返回的是 32 位 int。用 64 位 word 读回并直接比较负 syscall 编号，会产生伪失配。
4. AArch32 的寄存器布局不同，不能直接套用 AArch64 的前 33 个 64 位 word 比较。
5. 一次重写后必须再验证；持续失配不能假装写入成功。

## hf3 实现

- 内层命令 shell 在任何用户代码之前写入 `<status>.started`，写入失败立即以 125 退出。
- `FreshProcessShell` 仅在未越过命令开始标记且发生 loader 182 / 原始 wait 状态 0xb600 时重试。
- 上限 3 次，退避 0 / 50 / 200ms；所有尝试共用原超时预算，Stop 在同一个 shell 实例上持续生效。
- 已开始的命令不自动重放；原有 early signal 重试也增加此边界。
- NDK 构建自动应用 `deps/patches/0002-harmony-regset-verify.patch`；旧 research patch 仅保留为历史材料，不参与构建。
- 原生校验独立使用 GPR 和 syscall 两个 iovec，32 位 syscall，有界写回/回读，忽略 pstate，持续失配返回 EIO。
- 新增原生开关 `PROOT_VERIFY_REGSET=1`，个人 dev 的 Agent 默认开启；设置为 `0` 可回到原来的寄存器写回路径以做对照。AArch32 保留上游逻辑。
- loader64/loader32 均保留原 sha256 固定的 vendored Termux 版本；没有从 app-data 执行新 loader。

## 验证证据

- 本轮 C 故障注入测试：8 组通过（正常写回、GPR 首写丢失、syscall 首写丢失、持续丢失、短回读、pstate 归一化、ptrace 错误、错误长度）。
- 用真实修复 helper 编译运行，启用 AddressSanitizer / UndefinedBehaviorSanitizer。本地执行环境受 ptrace 限制，LeakSanitizer 单独关闭；CI 继续运行默认 sanitizer。
- Kotlin 用例覆盖：启动 loader 重试预算；Stop/超时/普通退出；无输出但已写入的命令退出 182 不重跑；标记写失败阻止副作用；引号/heredoc/管道语义。
- CI 运行： https://github.com/git-one-two/OpenMinis/actions/runs/36965604625 （最终结果待构建完成后追加）。
- 包身份：`com.openminis.app.dev`，versionCode 11403，versionName `1.14-dev-hf3`。
- 桌面原 keystore 仅本机用于签名，不写入仓库。预期证书 SHA256：`87586030a1614be88a5f66f3a09c4f476782fb755f6af81f2287126d12cf5d60`。

## 真机验收（未完成）

1. 删除 App 设置里的 `PROOT_VERBOSE`（旧现场值 6），避免每条命令输出海量诊断。不要把 `PROOT_LOADER` 改成 app-data 路径。
2. 同签名覆盖安装 hf3，保留会话与设置；绝不卸载清数据。
3. 先测原来的真实 Agent 任务；分别记录命令成功率、182/139/135/断言次数与 [proot-loader-retry] 命中。
4. 用共享目录原 `catch182.sh` 至少 150 样本测试嵌套 exec 的原生路径；**它不能量化 App 的启动重试**。App 重试需要独立的 fresh shell 调用。
5. 开关 `PROOT_VERIFY_REGSET=1/0` 同条件对照；若开启导致更坏行为，先关闭，不据此认定内核修复成功。
6. 检查取消/超时、普通失败、长输出、文件写入、终端及后台 daemon。随后至少 24h 日常使用。
7. 若仍存在命令开始后的随机 exec 死亡，继续 loader 分支诊断与 chain 恢复路径；不要扩大成盲目整条命令重试。
