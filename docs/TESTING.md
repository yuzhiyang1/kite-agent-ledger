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

联调前同时核对客户端的沙盒模式、实际后端环境和卖家报价。若 CLI 报 `sandbox mode mismatch` 且服务器返回 `X-Kite-Mode=live`，先确认官方可用的测试环境和相应登录，保持测试模式约束。只在已确认的 Kite 测试网 `eip155:2368` 与 pieUSD 合约上执行本项目的验收。当前已观察到的环境问题见 [联调证据](EVIDENCE.md)。

## 真实付款复现

先按 [Kite 安装说明](https://docs.gokite.ai/passport/install) 安装官方 `kpass`，并完成官方开发环境的账号登录和测试沙盒启用。运行以下命令会创建一个临时测试钱包，领取测试 pieUSD，再向官方测试接口付款一次 `0.1 pieUSD`。私钥仅驻留进程内存，账本保存调用元数据和结算结果。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-testnet.txt
kpass login --base-url https://passport.dev.gokite.ai
kpass sandbox on --base-url https://passport.dev.gokite.ai --output json
.\.venv\Scripts\python.exe -m scripts.testnet_payment --kpass kpass --db kite-testnet-validation.sqlite3
```

脚本固定测试网 `2368`、官方测试代币合约、卖家地址和 `0.1 pieUSD` 金额，并核对签名域与链上合约。重定向会被拒绝。付款仅尝试一次，凭证或网络结果不完整时账本保留未知状态。只有接口返回 200、链上匹配且钱包扣款恰好为预期金额，进程才返回 `0`。

该脚本直接签署测试钱包的 EIP-3009 授权并访问 x402 接口。Kite Passport 的 `session execute` 是另一条托管执行链路，其本次内部错误记录见 [验收证据](EVIDENCE.md)。账本本身的运行依赖仍为 Python 标准库，签名库只用于该付款脚本。

## 部署和排障

把构建的 wheel 安装到 Agent Worker 的 Python 虚拟环境，让服务账户独占配置和数据库的写权限。并行任务可以共享同一个本地 SQLite 文件。使用受信的 HTTPS RPC，并保持 Agent 运行标识和调用标识稳定。

- `no_transaction_hash` 先从调用方或付款记录恢复哈希，再补录。
- `rpc_unavailable` 检查可信 RPC 地址、DNS、代理和网络配置，然后重新核验。
- `rpc_wrong_chain` 核对 RPC 是否连接 Kite 测试网 `2368`。
- `wrong_amount` 或 `expected_transfer_missing` 人工核对原始报价和付款方、收款方及代币，保留证据。
- 哈希冲突时核对两个任务的调用记录。先确认应当归属的唯一一次调用，再处理账本冲突。
