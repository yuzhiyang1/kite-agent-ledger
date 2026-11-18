---
name: kite-delivery-evidence
description: 为 Kite Agent Ledger 准备提交、PR 或 KiteAI 活动验收材料，核对待提交差异、测试证据、作者归属、活跃贡献记录和 Open Dev Data 登记状态。
---

# 核对交付证据

1. 对照 `CONTRIBUTING.md` 和 `docs/TESTING.md`，检查改动范围、README 与运行命令。运行自动检查和受影响的测试，涉及包入口时验证安装后的命令。
2. Git 待提交区用 `python scripts/check_contribution.py --staged` 检查。人工复核暂存差异，并用 GitHub 当前账号资料核验作者邮箱归属。可使用该账号的 GitHub noreply 邮箱；归属仍不明确时再向贡献者确认。仅展示核验结果，保护个人邮箱和凭据。
3. 准备 PR 或活动材料时，记录仓库、关联 Issue、PR、Commit、实际开发日期、测试结果和合并状态。任务一按自然月独立日期统计，使用真实开发日期。任务二保留原创项目的版本和演示记录。
4. 分别记录公开仓库状态、Open Dev Data 登记状态和 EC 的实际归因证据。引用已核实的链接，尚未发生的步骤标注待完成。
