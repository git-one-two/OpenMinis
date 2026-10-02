# HF6：恢复八月沙盒执行组件的对照候选
2026-10-02。HF5 真机验收失败，HF6 尚待真机验收。
## 已确认
HF5 /bin/true 376/400，shebang 0/40，用户写后182为37/40（缺3次写入）。
HF5 日志 sysnum=61 是 PRoot neutral enum PR_execve，不是 ARM64 Linux getdents64。
get_sysnum() 经 syscall/sysnums.list 转换；不能据此推出 ld-musl getdents64 寄存器损坏。
stage=kernel-exec 在 execve 的 sysexit 记录，调用者 PC 落于 ld-musl 属正常现象。
retry-register EINVAL 不能单凭聚合日志判断是哪一个 ptrace request 失败，更不能证明 ROM 一定无解。
## 为什么恢复旧组件
桌面保留的 OpenMinis-final.apk：0.20-preview-dev、versionCode20，原调试签名。
八月修复分支 fix/android-proot-native-offload 的最后提交022b5112，PRoot子模块8cf13e99。
旧组件：proot da94efb1、64位loader12d2b63e、32位loaderd08a819a。
当前HF5：proot b94022ea、loader44ef39c1。执行组件确实有变化。
HF6直接复用旧APK三个执行组件的原始字节，保持完整配对，assets proot与jni proot完全一致。
保留1.14的应用和现有用户数据布局；versionCode11406、versionName1.14-dev-hf6-legacy。
不把HF3-HF5的native恢复/寄存器校验补丁编译进此候选。
四条Shell入口停用native_offload与fake-netlink；旧proot不支持fake-netlink，且八月修复明确关闭不稳定offload。
native offload对应的手机专属Shell命令在此候选不可用；普通Linux开发工具继续使用。
## 构建与验证边界
deps/harmony-legacy/manifest.json逐个固定SHA256，来源为旧APK；附旧源码与应用参考提交。
CI使用scripts/stage_harmony_legacy.py验证并原样安装，不再调用build_proot.sh覆盖旧组件。
仍执行Android sandbox单元测试和APK构建；source/loader另在ARM64 Linux做协议兼容测试。
Linux测试使用旧source重新编译，不能冒充原Android二进制或Huawei验证。
脚本诊断log来自HF5，此候选不会生成HF6_exec_diag.log，无需上传或读取陈旧日志。
## 真机验收
安装home-dev-control的HF6候选，确认1.14-dev-hf6-legacy；更新upgrade/openminis-1.14-harmony。
运行 python3 docs/research/hf6-device/verify_hf6.py --samples 400
上传VERIFY_2026-10-02_hf6.json到docs/research/hf6-device/，不改代码。
需400/400 true、40/40shebang、40次用户182且恰好40次写入、参数与父进程正常、旧proot和loader哈希匹配。
任何一项失败都不判为修好；通过后还需真实开发任务验收。

## 对照结果与最终源码
PRoot 8cf13e99 到 1b444ee1 共10条提交，差异未修改 tracee/reg.c、tracee/mem.c、syscall/syscall.c、execve/exit.c 或 loader/loader.c。
APK loader 则确实不同；直接复用旧组件对照比继续假定内核根因更有辨别力。
ARM64 Linux CI 36995425310 成功：seccomp开/关各400 true、40 shebang、40用户182，共960个子程序。
参数与写入次数全通过。此检查验证旧source/loader协议，不代表Huawei通过。
HF6最终应用源码4ff6333a1ac88ccf3142798e1b2a8e2b21dad02d；最终构建CI36996013892。
关闭offload时停止其服务，清理先前版本生成的精确 no-op 占位脚本，避免手机专属命令假成功；普通用户脚本不符合该内容时不清理。

## 已发布并远端核对
https://github.com/git-one-two/home-dev-control/releases/tag/openminis-1.14-dev-hf6-legacy-20261002
releases/latest 已返回此tag；draft=false、prerelease=false。
APK OpenMinis-1.14-dev-hf6-legacy.apk，66,234,518字节。
SHA256 3d2122cbff15ccbe54be57f7cb28ca00dfedc00d75368a71dfc63c6d4c2509c2；GitHub asset digest与本地一致。
签名v2/v3通过，证书SHA256 87586030a1614be88a5f66f3a09c4f476782fb755f6af81f2287126d12cf5d60，与旧包一致。
APK三份执行组件与旧包逐字节哈希匹配；assets/proot-aarch64与jni libproot.so一致。
Android CI36996013892的sandbox单元测试及构建均成功。
发行版附hf6-verification.json和harmony-legacy-results.json。
当前状态：对照候选已发布，Huawei真机验收待回传；未宣称设备问题已修复。
