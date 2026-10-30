# 加入语义复核后的全部运行

一共 6 次运行，全部保留。输入都是 `examples/inputs/normal.json`（普通 30 秒请求，风格“简洁、实用”）；工具失败那次额外让检索第一次调用失败。

| 场景 | 运行 | 过程 | 用作正式记录 |
| --- | --- | --- | --- |
| 正常 | [attempt-01](normal/attempt-01/) | 24.1 秒，一次通过 | ✓ |
| 时长 | [attempt-01](duration_revision/attempt-01/) | 18.8 秒（太短）→ 29.9 秒 | |
| 时长 | [attempt-02](duration_revision/attempt-02/) | 25.6 秒，一次通过 | |
| 时长 | [attempt-03](duration_revision/attempt-03/) | 36.2 秒（太长）→ 20.1 秒 | ✓ 超时修正 |
| 时长 | [attempt-04](duration_revision/attempt-04/) | 28.2 秒，一次通过 | |
| 工具失败 | [attempt-01](tool_failure/attempt-01/) | 检索出错 → 重试 → 22.8 秒 | ✓ |

时长场景跑了 4 次，只有第 3 次出现超时，所以用它作为超时修正的记录。选中的三次已复制到 `examples/live/` 下的同名目录，对应关系见 [selection.json](selection.json)。

每次运行都保存了 `api-audit.json`，记录语义判定的实际请求和返回。`python3 -m examples.live.verify_semantic_runs` 会检查：最终版脚本拆出的句子和发给判定模型的一致、每句都有判定、产品声明引用了 P01-F1、用保存的判定结果重新跑一遍程序校验仍然通过，以及版本、哈希和时长与输出一致。结果见 [verification.json](verification.json)。

重新跑程序校验用的是保存下来的判定结果，不会再调用模型。判定结果是“通过”也不代表判定模型不会出错，36 句评估里它漏了一句，见 [评估报告](../../../docs/03-evaluation.md)。
