# 参考项目与验收证据

## 开发前参考

以下为 2026 年 11 月 17 日获取的仓库快照。对照了第一方目录、关键源码、测试或仓库已有构建检查以及运行文档。参考的是工程验证方式，项目代码独立实现。

| 仓库和快照 | 阅读范围与结论 |
|---|---|
| [Kite x402 Explorer](https://github.com/CarryWang/kite-x402-explorer/tree/d5a2a6a9e6ade77ee38202c2aace9cc73373c7bf) | README、模拟结算、凭证异常审查、凭证测试和 CI。该项目区分模拟与链上凭证。本项目也明确区分运行记录类型。 |
| [Kite x402 Hono](https://github.com/BrKDDD/kite-x402-hono/tree/5e2adeb97ffb0d3a2d5b1c3f70f84831a316fff4) | README、贡献说明、服务端结算归档、查询测试和 CI。其结算归档用于支付服务。本项目按调用方的 Agent 运行和调用 ID 建本地账本。 |
| [Kite x402 Axum](https://github.com/tianzeshi-study/kite-x402-axum/tree/461e3b2bd743d89a4b24ddf080f1decbc1b7d299) | README、服务端结算账本、支付集成测试和 CI。其测试将 HTTP 和结算故障分开验证。本项目分别记录 HTTP、服务报告和链上观察。 |
| [Kite Agent ZK Attestation](https://github.com/Anyi-zheng/kite-agent-zk-attestation/tree/4844546eaeeb54bb9d8dc66eb0ff69460191cc9d) | README、证明中继、证明边界测试、验证器配置。参考其对证据来源和失败状态的明确约束。 |
| [Kite Counter dApp](https://github.com/gokite-ai/kite_counter_dapp/tree/42e33d7ead7c7e576ef58dcf3757760e88938311) | README、网络配置、应用入口、合约与包命令。该快照的第一方目录与包脚本未找到测试套件，可用构建与 lint 检查。 |

## 可复现的链上证据

- `python -m scripts.demo --live` 回查 [KiteScan 公开历史交易](https://testnet.kitescan.ai/tx/0x51ba634e11cfa21a015e0e8f18d0aac341083e2f67acc491653a12be02a68544)。验证结果为 `confirmed`，区块号 `22044967`，日志索引 `1`，金额 `97900000000000000` 个 pieUSD 最小单位。调用标识是合成的，交易来源标为 `manual`。
- 同一演示的模拟超时返回 `unknown / no_transaction_hash`。
- 对 [Kite 官方 x402 测试资源](https://passport.dev.gokite.ai/x402/test) 发起未授权 GET，收到 HTTP 402 和真实 `PAYMENT-REQUIRED`，其中列出 Kite 测试网、pieUSD 和 `exact` 报价。把该响应头通过 `capture --http-headers` 导入，SQLite 记录 `402 / no_payment_response`，链上核验为 `unknown / no_transaction_hash`。

## 本地验证

- 补充真实付款复现脚本后，Windows 的 Python 3.13 环境通过 20 个单元和 CLI 测试，覆盖最终响应选择、重复结算头拒绝、非审计字段不落库，以及付款脚本的测试网、代币、收款方、金额和签名域边界。首版的测试数为 17。
- 项目通过贡献文件扫描。在独立临时仓库验证了暂存区和工作区的区分，以及对命中内容的脱敏输出。
- 从声明的 setuptools 构建后端生成 wheel，在干净虚拟环境中离线安装，确认 `kite-agent-ledger --help` 可运行。
- 三个项目技能通过格式校验。首个提交 `9cd296ea29acf3074f74efd7a2cd427247a2e7cf` 的 [GitHub Actions](https://github.com/yuzhiyang1/kite-agent-ledger/actions/runs/44218135122) 已通过 Windows、Linux 与 Python 3.11、3.13 的四组检查。

## 2026 年 11 月 18 日支付联调进展

- 使用官方 CLI `6.13.6`，下载文件的 SHA-256 与官方 bundle `115` 的清单一致。
- 生产账号登录成功，`sandbox on` 和 `sandbox status` 均报告启用。但 Agent 登记返回 `sandbox mode mismatch`，服务器标记为 `X-Kite-Mode=live`，CLI 在模式不一致时中止。生产端的测试币水龙头也返回禁用。
- 官方开发后台 `https://passport.dev.gokite.ai` 的健康检查返回 `backend_env=dev`，生产登录在该环境返回 `invalid auth session`。完成独立验证码登录后，沙盒 Agent 登记成功，并通过开发后台水龙头领取到链 ID `2368` 的 pieUSD，链上回执状态为成功。
- 为官方测试接口申请的独立沙盒会话已获本人 Passkey 批准，实际额度为每次 `0.1`、累计 `0.2` pieUSD，时效为 `15` 分钟。使用固定幂等键调用 `session execute` 两次，均返回 Passport 服务端 `internal error`。当时会话的已用与保留金额均为零，测试钱包余额为 `100 pieUSD`。
- 随后使用内存中的临时测试钱包，通过开发环境水龙头领取测试币，直接向同一官方接口签署一次 `0.1 pieUSD` 的 EIP-3009 授权。核对链 ID、代币、收款方、金额和链上签名域后才提交。
- 接口返回 `HTTP 200` 及 `PAYMENT-RESPONSE`。账本保存 `reported_success` 和证据来源 `payment_response`，从该头提取 [结算交易](https://testnet.kitescan.ai/tx/0xa101089244d7dfefea527370954a21719f25ce7d3d763299b1eec372a0219c6f)，核验结果为 `confirmed / exact_transfer`，区块号 `22045141`、日志索引 `1`。
- 临时钱包余额从 `100000000000000000000` 降至 `99900000000000000000` 个最小单位，扣款恰好为 `100000000000000000`，即 `0.1 pieUSD`。付款与链上核验流程使用本项目的 `Intent`、`Ledger.capture` 和 `verify` API；复现方法见 [测试与部署](TESTING.md#真实付款复现)。Passport 托管执行仍受上述服务端错误影响。

## 活动提交状态

- 项目版本为 `0.1.0`。公开仓库为 [yuzhiyang1/kite-agent-ledger](https://github.com/yuzhiyang1/kite-agent-ledger)，初始交付分支为 `trunk`。提交及 CI 以该仓库的实时记录为准。
- Open Dev Data 登记待办理。项目技术关联及可运行示例见 [README](../README.md)。登记结果、生态映射生效、抓取和开发者归因分别核验。
- 后续按 [贡献说明](../CONTRIBUTING.md) 保存每次真实贡献日期、链接、变更摘要、测试及合并状态。
