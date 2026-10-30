# 提交说明

## 评审顺序

1. 阅读 [README](../README.md)，运行离线测试和 CLI。
2. 查看 [真实运行说明](../examples/live/README.md) 与 [评估报告](03-evaluation.md)，逐项对应输入、输出和 Trace。
3. 重点查看超时路径：最新版普通30秒请求：36.2秒超时 → 模型自主压缩为20.1秒，并通过真实语义判定；最终检查通过且没有门禁拒绝。
4. 查看 [方案](02-solution.md)、[AI 使用](04-ai-usage.md)、[复盘](05-retrospective.md)，理解事实检查边界和个人贡献记录。

## 交付状态

项目已包含题目要求的源码、测试、合成数据、五份规定文档、依赖说明、环境变量示例及正常/不足/失败运行材料。另附独立复核脚本和真实失败历史。当前没有线上界面或部署，不属于本题必需范围。

正式提交仍需：

- 候选人补充实际投入时间；问题发现与修改方案贡献已记录在04-ai-usage.md，另有独立工作时再按实际追加，并保留AI辅助分工说明。
- 正常、超时修正、工具失败已用最新版重跑并核对真实语义判定；missing_info/no_material尚保留历史记录。36句真实评估已完成，语义/最终层35/36符合预期，留出集20/20，开发集仍有一条目标句漏检和同次标题误报，详见03-evaluation.md。
- 仓库为https://github.com/linlinlin12138/short-video-script-agent。提交前我会将其改为Public，并在切换后以未登录状态确认可访问；不再采用私有仓库邀请评审账号的交付方式。
- 填写题号或题名、仓库 URL 和最终 commit SHA。考题未给出本题数字编号，不能自行编造。

可使用以下提交信息格式，但下列占位符不是已完成的交付信息：

```text
题目：短视频脚本 Agent（题号按原试卷补充）
GitHub URL：https://github.com/linlinlin12138/short-video-script-agent
最终 commit SHA：以本次推送后的 git rev-parse HEAD 和远程 main 一致结果为准
实际投入时间：待本人补充
```

## Git 仓库边界

本项目已经初始化独立 .git。发布或继续提交前，仍应确认 git rev-parse --show-toplevel 返回本项目目录，再添加文件。不要在上层仓库执行 git add . 或直接使用其远程地址。

dist/submission.zip 是仅包含本项目允许文件的交付副本，排除了 .env、运行缓存和其他目录。它便于检查或迁移，不能替代考核要求的 GitHub 仓库与 SHA。解压后的项目仍需按 README 安装和运行。

## 复核记录

离线安装和运行的独立副本复核见 [delivery-check.txt](../examples/delivery-check.txt)。该复核不重新调用付费模型，也不更改保存的真实模型结果。

本次已按要求重新生成dist/submission.zip，包含最终文档、36句真实评估输入/输出/Trace、版本清单与源码快照。文件清单及逐文件SHA-256保存在dist/submission-manifest.json。压缩包不包含.env、Git元数据、编辑器配置和运行缓存；以后仅在明确要求时更新。
