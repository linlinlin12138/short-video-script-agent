# AI 辅助记录（持续更新）

## 当前辅助范围

本仓库前三步内容由用户提出目标和分步授权，Codex 辅助完成：需求契约、合成资料和规则、三个工具、Agent 编排、HTTP 模型适配器、离线 Mock、CLI、测试、示例记录和说明文档。

## 已执行的验证

- 运行工具测试及 Agent 测试，目前 32 项通过，见 examples/test-results.txt。
- 实际执行 CLI 保存六组离线记录，见 examples/mock/README.md。
- 使用当前本地已有 jsonschema 校验六份任务输出符合 output.schema.json。
- 经用户授权，使用配置的 gpt-5.4-mini-2026-03-17 执行真实验收，五类结果见 examples/live/README.md。
- Codex 根据真实失败修改了提示、工具 schema、结束门禁和环境文件加载；保留修复前记录，未伪造成功路径。
- 独立重算最终时长和事实检查，校验最终版本、来源与输出 schema，并检查记录中未包含 API 密钥。
- 参考 OpenAI 官方函数调用文档核对协议：https://developers.openai.com/api/docs/guides/function-calling。
- Codex 辅助整理复盘、提交说明和白名单打包脚本；在解压后的独立副本和全新 venv 中复核离线安装、测试及 CLI，原始日志见 examples/delivery-check.txt。


