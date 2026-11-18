# Kite Agent Ledger

Kite Agent Ledger 是一个给 Agent 开发者使用的命令行工具。一次任务调用 x402 付费 API 后，它把调用结果、服务返回的结算凭证和 Kite 测试网上的 pieUSD 转账记录关联起来。它能回答某个任务的哪一次调用查到了付款，以及哪些调用的结果仍待核验。

## 功能

- 按 Agent 任务 ID 汇总付费调用，单独记录 HTTP 状态和链上核验状态。
- 从 x402 v2 `PAYMENT-RESPONSE` 提取交易哈希，支持导入外部客户端的 HTTP 响应头，以及在凭证丢失后补录已知哈希。
- 通过 Kite 测试网 RPC 核对交易状态、pieUSD 合约、付款方、收款方及最小单位金额，重复核验保留历史。
- 用 SQLite 保存最小审计数据。一次调用一个交易哈希，同一哈希在本地账本只归属一次调用。

## 快速开始

需要 Python 3.11 或更新版本。运行时只使用 Python 标准库。以下命令按 PowerShell 编写，`python -m` 形式也适用于其他平台。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m kite_agent_ledger.cli --help
.\.venv\Scripts\python.exe -m scripts.demo
.\.venv\Scripts\python.exe -m scripts.demo --live
```

默认演示模拟一次超时，输出 `unknown`。加上 `--live` 会额外回查一笔公开的 Kite 测试网历史转账，输出真实交易哈希、区块号和事件索引。该回查使用合成任务标识和手工导入的历史交易，作为链上核验演示。两种演示都使用临时数据库。

CLI 可通过 `--db` 或环境变量 `KITE_LEDGER_DB` 指定数据库，通过 `reconcile --rpc-url` 或 `KITE_LEDGER_RPC_URL` 指定可信 HTTPS RPC。直接设置进程环境变量，样例见 [配置文件](.env.example)。

## KiteAI 技术关联

| 部分 | 源码 | 验证内容 |
|---|---|---|
| x402 v2 结算凭证 | [model.py](kite_agent_ledger/model.py) | 解析 `PAYMENT-RESPONSE`，只接收 Kite 测试网凭证。 |
| Kite 测试网交易 | [chain.py](kite_agent_ledger/chain.py) | 通过官方 RPC 核验链 ID `2368` 及官方测试代币合约的 `Transfer` 事件。 |
| Agent 调用归因 | [store.py](kite_agent_ledger/store.py) | 把已知证据关联到任务和调用 ID，保留重复核验历史及哈希归属。 |

相关官方材料见 [Kite 网络](https://docs.gokite.ai/kite-chain/1-getting-started/network-information)、[Kite x402 服务与测试网示例](https://github.com/gokite-ai/kite-x402-services) 和 [x402 v2 HTTP](https://github.com/x402-foundation/x402/blob/main/specs/transports-v2/http.md)。

## 范围

首版面向 Kite 测试网 pieUSD 的 x402 v2 `exact` 付款。调用方负责报价校验、授权、支付和重试决策，账本只接收调用元数据并核验证据。链上 `confirmed` 表示当前 RPC 中存在匹配事件，报告同时列出 HTTP 交付状态及证据来源。发生重组时重新核验。跨主机任务协调、批量结算和多签授权在首版范围之外。

使用、贡献和验收材料见 [CLI 用法](docs/USAGE.md)、[架构与开发](docs/ARCHITECTURE.md)、[测试与部署](docs/TESTING.md)、[贡献说明](CONTRIBUTING.md) 和 [变更记录](CHANGELOG.md)。许可证见 [MIT](LICENSE)。
