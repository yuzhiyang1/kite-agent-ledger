# 测试、部署与排障

## 本地检查

```powershell
python scripts/check_contribution.py
python -m unittest discover -s tests -v
python -m pip wheel --no-deps --wheel-dir dist .
python -m pip install --no-index --find-links dist kite-agent-ledger
kite-agent-ledger --help
```

暂存后可用 `python scripts/check_contribution.py --staged` 读取 Git 索引。检查器针对常见密钥、环境文件和本地构建产物，人工仍需复核本次差异。CI 在 Windows 和 Linux 上运行文件检查、测试、构建和安装。

测试包括合法凭证、超时、错误链或付款方、金额不符、交易回滚、重复转账、畸形 RPC 证据、重复调用、并发哈希争用和 CLI 退出码。离线测试使用受控数据，不需要钱包或 RPC。

## 演示和真实测试网验证

```powershell
python -m scripts.demo
python -m scripts.demo --live
```

第一条验证超时后仍为 `unknown`。第二条回查示例中固定的**公开历史 pieUSD 转账**，验证本项目解析真实 Kite RPC 和链上事件的能力。回查结果使用 `manual` 证据来源；示例将两条记录标记为独立场景。维护情况与活动材料见 [证据记录](EVIDENCE.md)。

完整付费联调由已授权的测试网调用方完成。先用 `open` 登记测试钱包和可信报价，完成一次 Kite 沙盒支付，再把客户端导出的 HTTP 响应头通过标准输入交给 `capture CALL_ID --http-headers`，执行 `reconcile CALL_ID`。仅能取得支付活动里的交易哈希时，先登记实际 HTTP 观察，再用 `attach` 补录，报告会标注手工来源。保存 HTTP 结果、凭证来源、链上对账结果和可公开的交易链接。官方沙盒步骤见 [Kite x402 Services](https://github.com/gokite-ai/kite-x402-services#readme)。

## 部署和排障

把构建的 wheel 安装到 Agent Worker 的 Python 虚拟环境，让服务账户独占配置和数据库的写权限。并行任务可以共享同一个本地 SQLite 文件。使用受信的 HTTPS RPC，并保持 Agent 运行标识和调用标识稳定。

- `no_transaction_hash` 先从调用方或付款记录恢复哈希，再补录。
- `rpc_unavailable` 检查可信 RPC 地址、DNS、代理和网络配置，然后重新核验。
- `rpc_wrong_chain` 核对 RPC 是否连接 Kite 测试网 `2368`。
- `wrong_amount` 或 `expected_transfer_missing` 人工核对原始报价和付款方、收款方及代币，保留证据。
- 哈希冲突时核对两个任务的调用记录。先确认应当归属的唯一一次调用，再处理账本冲突。
