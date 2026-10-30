# 短视频脚本 Agent：提交说明

## 项目信息

| 项目 | 内容 |
| --- | --- |
| 题目 | 短视频脚本 Agent |
| GitHub | [linlinlin12138/short-video-script-agent](https://github.com/linlinlin12138/short-video-script-agent) |
| 运行入口 | Python CLI，支持真实模型和离线 Mock |
| 依赖 | Python 3.10+，应用与测试仅使用标准库 |
| 投入时间 | 约3小时，估算，未连续计时 |
| AI辅助 | Codex、Claude；具体分工见 [AI使用与个人贡献](04-ai-usage.md) |

评审版本以提交信息中提供的完整 commit SHA 为准。仓库包含源码、测试、合成素材、运行记录、评估文档及代码版本快照。

## 快速运行

在项目根目录执行，离线运行无需密钥：

```sh
python3 -m unittest discover -s tests -v
python3 -m src.cli --input examples/inputs/normal.json --model mock --output-dir runs/normal
```

执行后可在 `runs/normal/` 查看输入、脚本输出与 Trace。Mock 用于验证调用流程，不作为真实模型决策效果的证据。

真实模型运行需按 [.env.example](../.env.example) 配置本地 `.env`：

```sh
python3 -m src.cli --input examples/inputs/normal.json --model live --env-file .env --api responses --reasoning-effort medium --timeout 60 --output-dir runs/live-normal
```

该命令会调用模型服务。无需重新调用模型也可按下文核对已保存的真实运行证据。

## 主要验收结果

| 场景 | 实际结果 | 评审入口 |
| --- | --- | --- |
| 正常生成 | 目标30秒，成稿24.1秒、4镜，最终真实语义审核通过 | [输出](../examples/live/normal/output.json)、[Trace](../examples/live/normal/trace.jsonl) |
| 超时后修正 | 普通30秒请求，36.2秒超时后自主压缩为20.1秒，再次检查通过，无门禁拒绝 | [输出](../examples/live/duration_revision/output.json)、[Trace](../examples/live/duration_revision/trace.jsonl) |
| 工具失败恢复 | 临时检索失败后模型重试成功，成稿22.8秒，最终真实语义审核通过 | [输出](../examples/live/tool_failure/output.json)、[Trace](../examples/live/tool_failure/trace.jsonl) |
| 缺关键信息 | 缺少目标时长时，以中文问句请求补充 | [运行记录](../examples/live/missing_info/) |
| 无素材 | 两次检索无结果后请求补充资料，没有编造产品能力 | [运行记录](../examples/live/no_material/) |

前三条来自最新版的独立真实运行。缺信息、无素材保留语义层加入前的历史记录，不作为新版语义审核通过的证据。超时场景共尝试4次，全部记录保留，选中的有效修正路径不代表稳定成功率。

自动化测试共53项，全部通过。固定36句真实审核中，语义层与最终层均有35/36符合预期，留出集20/20。仍有一条编造声明“做出爆款视频”漏检，同次误拦标题，失败记录完整保留。详细指标、采样过程和限制见 [评估报告](03-evaluation.md)。

## 证据核对

以下命令不联网，不产生模型调用费用：

```sh
python3 -m examples.live.verify_results
python3 -m examples.live.verify_semantic_runs
python3 -m examples.checker.verify_claim_eval
```

核对内容包括最终分镜时长与总时长、素材引用、脚本版本与哈希、真实语义审核返回，以及36句评估的输入、输出、统计和源码快照。原始模型返回不被替换。固定评估的代码版本清单为运行后补录，已明确标记这一限制。

建议先看 [README](../README.md) 和上述三条独立真实路径，再阅读 [方案设计](02-solution.md)、[评估报告](03-evaluation.md)、[个人贡献](04-ai-usage.md) 与 [复盘](05-retrospective.md)。

## 交付范围与限制

项目完成了检索、脚本生成、估时、规则与语义审核、修改后重检及明确结束状态的核心链路；设置了模型轮数和工具调用上限。未实现界面、线上部署或生产级运行环境。

语义审核仍可能漏检或误报，单次小样本结果不能代表通用准确率。时长来自文本估算，尚未使用真实配音或成片校准。产品素材为合成资料，不含真实密钥或隐私数据。

`submission.zip` 是便于下载和本地运行的交付副本，随附文件清单与SHA-256；源码、文档和运行证据以本次提交的GitHub版本为准。
