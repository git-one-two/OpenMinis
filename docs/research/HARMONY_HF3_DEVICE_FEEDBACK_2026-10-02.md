# hf3 首次真机反馈：底层失败仍存在

记录时间：2026-10-02 14:03（Asia/Shanghai）。
状态：验收未通过，不能宣称问题已经修复。

## 用户截图报告（尚未取得原始脚本和日志）
- Minis 报告直接运行 /bin/true：8/80 失败。
- Minis 报告 shebang 直跑：1/10 失败。
- 截图中的 libproot.so 哈希前缀 07f497b1 与 hf3 打包值匹配。
- libproot-loader.so 哈希前缀 44ef39c1 与原有固定 loader 匹配。loader 未替换是本次构建设计。
- PROOT_VERBOSE 显示 unset。
- 报告位于手机 /var/minis/shared/work/OpenMinis-investigation/VERIFY_2026-10-02_chatgpt.md。
- 原始脚本位于同目录 omdiag/verify_chatgpt.py。
- 以上为截图转述，尚未独立复跑；无法从截图证明测试参数、环境或入口。

## 已核对的 hf3 代码
- 来源提交 4a8fedf245bb3209e762d9a4aa3b85e12b78824e。
- FreshProcessShell.execute 已接入 LoaderStartupRetryPolicy，识别 182/0xb600，最多 3 次重试。
- 内层 shell 写入 started 标记后不允许重跑整条命令。
- 这保护已完成写文件等操作的命令，不能改为无条件按 182 重试。
- 直接通过 Python subprocess 启动 proot 会绕过上述 App 策略；需查看脚本才能判断本次测试是否如此。
- 原生 SET/GET regset 校验通过单元注入场景，并不证明 Huawei 内核恢复 tracee 后不会出现异常。
- 尚未验证 Agent 原始任务或 App 重试后的真机成功率。

## 下一步需要的证据
1. 将上述报告和原始脚本上传当前分支，保留命令 argv、环境、样本结果；不要上传 token、私钥。
2. 分别测裸 proot 与真实 debug.shellExecute(strategy=fresh) 路径。
3. App 验收脚本 scripts/harmony_device_acceptance.py 必须从 PC 运行、App 空闲；不能从正在占用 Agent 全局互斥锁的沙盒内调用自身 debug.shellExecute。
4. 若 App 路径失败，记录 started 边界、重试次数、退出码及精简 native 失败日志，区分启动阶段与用户命令内子进程。
5. 在原始失败证据到齐前，不依据截图猜测链式 syscall 修复，也不把已有安全重试误认为未实现。
