# 项目开发约定

本项目面向调用方，将 Agent 运行中的 HTTP 调用和 Kite 测试网链上支付关联。对用户使用中文，代码注释优先说明业务条件、证据边界和容易误用的状态。

- 接到开发任务时，先读 [贡献说明](CONTRIBUTING.md)。新增功能或修复走 [贡献范围技能](skills/kite-contribution-scope/SKILL.md)。
- 涉及 x402、链上 RPC、账本持久化、状态分类或敏感数据时，使用 [支付证据审查技能](skills/kite-payment-review/SKILL.md)。
- 交付、创建 PR 或汇总贡献时，使用 [交付证据技能](skills/kite-delivery-evidence/SKILL.md)，记录实际通过的检查和未验证项。
- 提交前用 `python scripts/check_contribution.py --staged` 检查拟提交文件，并按 [测试与部署说明](docs/TESTING.md) 验证。遇到扫描误报时复核具体文件和位置。
- Git 提交和 PR 署名遵循 [贡献说明](CONTRIBUTING.md) 的本人提交规则。技能用于审查和准备材料，发布动作按用户授权执行。
