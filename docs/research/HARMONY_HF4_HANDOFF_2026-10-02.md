# Harmony hf4：子程序启动阶段恢复候选
时间：2026-10-02（Asia/Shanghai）。真机验收尚未完成。

## 直接依据
hf3 真机原始脚本在一个 Python 进程里调用 subprocess.run(['/bin/true'])。
8/80 个子进程返回 182，Python 本身继续执行并成功写报告。
因此 FreshProcessShell 整条命令的启动重试不会覆盖这个阶段。
证据见 docs/research/hf3-device/；不将 kernel 恢复寄存器假设当作已证明事实。

## 实现
- 保留已验证并固定哈希的 Termux loader，修改其 tracer。
- 仅在 PROOT_EXEC_LOADER_RETRY=1 且 PROOT_VERIFY_REGSET=1 时启用。
- 仅原生 ARM64、无 guest ptracer、无 QEMU、固定地址 ET_EXEC loader。
- 从实际 loader ELF 的唯一 executable PT_LOAD 取得范围，不猜 ASLR 偏移。
- 安装包 loader 已反汇编确认：PR_SET_NAME 是跳到程序入口前的最后 syscall。
- 在该提交边界前，只有 loader 地址范围内的 exit(182) 可以重定向为 execve。
- 内核构建的 argv/envp 保留在原始栈上；重启已经展开 shebang 的解释器，不重复扩展脚本。
- 保留脚本原始 AT_EXECFN/comm 字符串。
- 每次 exec 最多 3 次恢复，普通新 exec 重置次数。父 shell/Python 不回退。
- loader 的只读 ELF fd 加 O_CLOEXEC，重试 exec 后自动关闭。
- 注入 exec 失败或寄存器提交失败时终止当前子进程，不能返回到 loader 的 unreachable 分支。
- 用户代码开始后、其他退出码、范围不明确、参数读取失败、guest 映射与 loader 相交时均不恢复。
- 即使 ORIGINAL/CURRENT 都已改为 execve，也强制更新独立 NT_ARM_SYSTEM_CALL，防止内核仍执行 exit。
- 在 DEV_TOOLS 的 FreshProcessShell 默认开启，用户环境最后覆盖。

## 本地验证
- Android NDK r28.1 的 ARM64 helper、syscall、reg 源码通过 -Wall -Wextra -Werror 语法检查。
- 编译实际 helper 函数体的注入测试通过：参数、shebang、次数、提交边界、主动退出182、fd flags、无效栈、
  失败后的子进程终止、ELF 范围身份、禁用开关、重叠映射。
- 这些测试不模拟 Huawei 内核，不能当作真机成功证据。
- 正式 CI 还需完整原生构建、旧 regset 注入测试、所有 sandbox 测试及 APK 打包。

## 真机验收
1. 安装原签名 hf4，不清数据；运行相同 verify_chatgpt.py，保留与 hf3 的可比样本。
2. 追加报告进程中 PROOT_EXEC_LOADER_RETRY 和 PROOT_VERIFY_REGSET 的值。
3. 复跑原始真实 Agent 任务，确认子进程无182且 Agent 不挂起。
4. 若仍失败，提供精简 App 日志中的 [proot-exec-loader-retry] 行和失败的 native stderr。
5. PROOT_EXEC_LOADER_RETRY=0 可单独关闭新候选；PROOT_VERIFY_REGSET=0 同时使新候选不启用。

## 已交付安装包
- 代码提交：fa22a70d3156ef04b67a65603acdbeda0d01df30。
- CI：https://github.com/git-one-two/OpenMinis/actions/runs/36974374774，全部步骤成功。
- 原签名证书 SHA256：87586030a1614be88a5f66f3a09c4f476782fb755f6af81f2287126d12cf5d60。
- APK：OpenMinis-1.14-dev-hf4.apk，66,242,710 字节；com.openminis.app.dev / 11404 / 1.14-dev-hf4。
- APK SHA256：f90bb758f0c5f0bf6789ec30a4453c82f47201918b64588ad8d14a8600aa444d。
- libproot.so：273,288 字节；SHA256 aa29de2e337606b2720e3ae990319041fb4e208a2e13281d792cd85c1fe15e93。
- 两个 loader 保留原固定哈希，不应凭 loader 哈希未变判为未更新。
- 手机仍未接入 adb，本轮真机效果尚未验证。
