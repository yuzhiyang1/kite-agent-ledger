# 命令行和 Python 用法

以下命令假设安装项目的虚拟环境已加入 PATH。也可使用 `python -m kite_agent_ledger.cli`。全局 `--db` 放在子命令前。成功时标准输出为 JSON，错误信息输出到标准错误。地址使用 20 字节十六进制字符串，金额是十进制的 pieUSD 最小单位。比如 `100000000000000000` 代表 0.1 pieUSD。

```powershell
kite-agent-ledger open --run-id run-001 --call-id call-001 --service example-api `
  --payer 0x1111111111111111111111111111111111111111 `
  --recipient 0x2222222222222222222222222222222222222222 --amount 100000000000000000

# 示例模拟调用超时。真实调用应传实际 HTTP 状态及 PAYMENT-RESPONSE。
'{"http_status":null,"payment_response":null}' | kite-agent-ledger capture call-001
kite-agent-ledger reconcile call-001
kite-agent-ledger report run-001
kite-agent-ledger history call-001
```

| 命令 | 输入 | 结果 |
|---|---|---|
| `open` | 任务、调用、服务标识及付款条件 | 调用记录 |
| `capture CALL_ID` | 标准输入 JSON 对象。字段为 `http_status`（整数或 `null`）和 `payment_response`（Base64 字符串或 `null`）。使用 `--http-headers` 时读取原始 HTTP 响应头 | 调用记录及服务报告分类 |
| `attach CALL_ID TX_HASH` | 已记录 HTTP 观察且还没有哈希的调用、来自独立可信渠道的交易哈希 | 更新后调用记录，证据来源为 `manual` |
| `reconcile CALL_ID` | 调用 ID，可选 `--rpc-url` | 链上观测，包含状态和原因。存在时列出区块与事件索引 |
| `report RUN_ID` | 任务 ID | 该任务的调用数组，附当前交易最近状态 |
| `history CALL_ID` | 调用 ID | 按写入顺序列出核验历史 |

退出码 `0` 表示命令成功，`reconcile` 只有链上匹配时返回 `0`。 `1` 表示本地存储或输入不可用，`2` 表示参数或输入错误，`3` 表示核验未确认付款，`4` 表示调用或哈希归属冲突。

如果已授权的客户端能在标准输出导出响应头，可通过管道交给 `kite-agent-ledger capture CALL_ID --http-headers`。只传入 HTTP 响应头，以空行结束。对于含代理握手、临时响应或前序 402 的输出，账本只提取最终响应的 HTTP 状态和 `PAYMENT-RESPONSE`。格式错误、截断和重复结算头会被拒绝。使用 JSON 导入即可记录连接超时。

Python 集成时在业务实际调用的边界读取白名单字段。配置中的付款条件应来自可信报价或预设策略。以下代码中的地址、金额及响应均由调用方提供。

```python
from contextlib import closing
from kite_agent_ledger.model import Intent
from kite_agent_ledger.store import Ledger

with closing(Ledger("kite-ledger.sqlite3")) as ledger:
    ledger.open_call(Intent(call_id, run_id, service_id, payer, recipient, atomic_amount))
    # next: 调用方执行已授权的 x402 请求，再记录下面两个字段。
    ledger.capture(call_id, response_status, payment_response_header)
```

API 完成前若进程退出，已登记的调用仍可见。调用方可从自己的执行器或支付记录恢复哈希，再通过 `reconcile` 复核。所有命令都可使用独立数据库做测试。
