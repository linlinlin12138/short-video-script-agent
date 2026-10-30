# 短视频脚本 Agent

校招考核项目：生成有事实依据、满足时长约束、可编辑的短视频脚本。

当前完成需求定义、三个本地工具、Agent 循环、任务 CLI、真实模型 HTTP 适配器及离线 Mock。离线链路和五类真实模型用例已运行，包含超时后的实际改稿与重新检查；详见真实验收记录。

## 环境与运行

Python 3.10+，当前仅使用标准库，无需安装第三方依赖。离线模式无需密钥。以下命令均在仓库根目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

也可直接使用系统 Python，应用及测试不依赖任何第三方包：

```sh
python3 -m unittest discover -s tests -v
python3 -m examples.tools.run_examples
python3 -m src.cli --input examples/inputs/normal.json --model mock --output-dir runs/normal
python3 -m src.cli --input examples/inputs/normal.json --model mock --scenario duration_revision --output-dir runs/revision
```

第二条命令重新生成 `examples/tools/actual-results.json`，包含工具参数与真实返回值。工具调用示例：

```python
from src.tools import ToolSet

tools = ToolSet()
print(tools.execute("search_materials", {"query": "字幕功能"}))
```

## 评审入口

- [需求与验收清单](docs/01-requirements.md)
- [工具设计及边界](docs/02-solution.md)
- [当前验证结果](docs/03-evaluation.md)
- [真实模型验收记录](examples/live/README.md)
- [AI 使用与个人贡献边界](docs/04-ai-usage.md)
- [复盘及改进方向](docs/05-retrospective.md)
- [提交说明和待补充信息](docs/06-submission.md)
- [实际工具运行记录](examples/tools/actual-results.json)
- [输入格式](schemas/input.schema.json)
- [输出格式](schemas/output.schema.json)
- [输入示例](examples/inputs/normal.json)
- [合成素材](data/materials.json)
- [品牌规则](data/brand_rules.json)

真实模型已保存正常、缺信息、无素材、工具失败和超时修正五类记录。下一步重点改进文案质量和重复运行稳定性。事实检查限定受控表达，清单外内容保守拒绝，不提供通用语义核验。时长为估算，未验证真实配音。

## 真实模型与 CLI 配置

在本地终端设置 OPENAI_API_KEY 和 OPENAI_MODEL，模型须支持 Chat Completions 函数调用。OPENAI_BASE_URL 默认为 https://api.openai.com/v1，可指向兼容服务 API 根地址。配置示例见 .env.example；可用 --env-file .env 显式加载，进程环境变量优先，不执行任何 Shell 内容。

```sh
python3 -m src.cli --input examples/inputs/normal.json --model live --env-file .env --output-dir runs/live-normal
```

每次保存 input.json、output.json、trace.jsonl。退出码：0 为 completed，1 为明确未完成，2 为配置或输入错误。默认最多 10 次工具调用、12 轮模型决策、单次 HTTP 超时 45 秒。--max-tools、--max-rounds、--timeout 可下调上限；--data-dir 指定测试资料目录，--fail-tool 注入一次指定工具的临时错误。--scenario 仅适用于 Mock。

缺少业务字段时可以传入不完整 JSON；非法字段类型和非正时长由 CLI 拒绝。Mock 是固定模拟器，包含预设文案和修正策略，只验证编排。[离线运行记录](examples/mock/README.md)均已标记 mock，不构成真实模型证据。当前时长只要求不超过目标，不要求填满目标时长。

已有真实结果可离线独立复核，不消耗模型额度：

```sh
python3 -m examples.live.verify_results
```

## 本地交付包

```sh
python3 scripts/package_submission.py
```

生成 dist/submission.zip 和文件哈希清单，排除密钥文件、Git 元数据和运行缓存。正式提交仍需 GitHub URL、最终 commit SHA，以及本人补充的实际用时和个人贡献，见 [提交说明](docs/06-submission.md)。
