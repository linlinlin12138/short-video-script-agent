# 评估记录：叙事与自然修正

## 最终结果概览

| 验证项目 | 最终结果 |
| --- | --- |
| 正常脚本 | 24.1秒、4镜，completed，最终真实semantic=passed |
| 超时修正 | 36.2→20.1秒，版本1→2，最终真实semantic=passed，无GUARD_REJECTED |
| 工具失败恢复 | 临时检索错误后模型重试成功，22.8秒，completed，最终真实semantic=passed |
| 固定36句审核 | 词法20/36；语义35/36；最终层35/36；36次真实调用均成功 |
| 留出集 | 编造声明12/12检出，正常叙事6/6放行，正确引用2/2放行 |
| 自动化测试 | 本次提交前重新运行53项unittest，全部通过 |
| 离线核对 | verify_results、verify_semantic_runs、verify_claim_eval均通过，无新增模型调用 |

语义层仍漏检开发集“做出爆款视频”，并在同次误拦标题；目标声明检出率为21/22。该失败完整保留，没有把整份脚本被拦截算成目标句命中。缺信息和无素材的记录早于语义层，不据此宣称这两条路径已完成新版真实审核。三条成稿、36句评估和早期开发采样分别统计，详细证据与边界见后文。

代码内容版本为`8a11784b006e66353ec70616724d4afe42d1ecdfae3572c8cc7e5e957ba52522`，与36条Trace的绑定及运行后补录限制见“新Trace对应的代码版本”。最终Git提交包含这些历史运行材料，不将其SHA说成当时的运行SHA。

仓库提交方式：[GitHub仓库](https://github.com/linlinlin12138/short-video-script-agent)将在提交前改为Public，评审可直接通过公开链接查看。此前访问核验时仓库仍为私有，当前账号有pull/push权限，默认分支为main，匿名API返回404；这些是切换前的核验事实，不代表公开访问已确认。改为公开后需再以未登录状态确认可读，最终提交SHA应与远程main一致。

本版根据评审意见（含 Claude 评审）修改：取消非事实叙事白名单，引入时长下限，增加顶层来源、中文问句校验、重试语义与检索改写建议，并重构Agent。旧证据保存在examples/history/v1及实际失败尝试目录中，不用旧的1.5秒结果证明本版达标。

## 语义层加入前的历史结果

| 验收点 | 实际结果 | 文件 |
| --- | --- | --- |
| A01 正常 | completed，28.6秒、3镜、P01-F1、source_ids=[P01]，有开场/创作者情境/拍摄建议/互动结尾 | [输入](../examples/history/pre-semantic-rerun/normal/input.json)、[输出](../examples/history/pre-semantic-rerun/normal/output.json)、[Trace](../examples/history/pre-semantic-rerun/normal/trace.jsonl) |
| A02 缺信息 | 中文问句“请告诉我目标时长（例如30秒、60秒）？”；此前尝试检索被缺信息门禁拦截 | [目录](../examples/live/missing_info/) |
| A03 无素材 | 两次相关查询无命中，随后请求视频降噪资料，没有编造能力 | [目录](../examples/live/no_material/) |
| A04 工具错误 | retryable临时检索错误后真实重试，随后改稿、重新检查并completed，21.6秒 | [历史目录](../examples/history/pre-semantic-rerun/tool_failure/) |
| A05 超时后修正 | 普通30秒、简洁实用输入；15.3秒偏短 → 扩写到30.4秒超限 → 压缩为28.6秒；最终规则通过，0次GUARD_REJECTED | [历史目录](../examples/history/pre-semantic-rerun/duration_revision/) |

正常与超时入口复用同一次plain_medium实际执行，覆盖A01/A05，不重复计为两次独立运行。没有输入指定首稿分镜数或修改策略，没有手改估时。首稿是偏短而非超时；实际超时发生在第二版，第三版完成压缩。记录完整保留该事实。

另一条独立路径是临时错误后的重试恢复，无素材则改写后请求补充，构成不同工具反馈导致不同动作的真实路径。原生骨架和完成校验仍存在，但自然超时主记录没有依靠其拒绝来驱动改稿。

## 采样与不成功记录

examples/live/attempts/v2_natural_duration保存7次有限开发采样，包含简洁/故事风格及low/medium推理配置，摘要为summary.json。所有尝试保留，不只留下成功样本；不把这些不同配置算成受控成功率。

失败包括：偏短后误判缺资料、修改版本遗漏、规则修改后漏做新版估时、故事风格过长或压缩过短后结束。Chat接口另实际拒绝函数工具与low推理组合，已保留HTTP400记录并改用Responses。主记录选自plain_medium，其15.3→30.4→28.6秒完整轨迹没有门禁拒绝。

## 工程与独立复核

53项自动化测试通过，原始输出见 [test-results.txt](../examples/test-results.txt)。新增覆盖自由叙事、未引用数字/能力、引用不能覆盖额外宣传、否定声明、跨镜引用、偏短失败、自然问句，以及Responses原始上下文与真实观察回传。上限、版本失效、错误重检等仍有测试；Mock只证明流程。

运行 `python3 -m examples.live.verify_results` 不联网，重新计算时长和规则，核对最终版本/哈希、各镜与总时长、引用确实来自本轮检索、顶层来源去重、无素材改写、错误恢复，以及自然超时路径没有GUARD_REJECTED。结果见 [verification.json](../examples/live/verification.json)。当前5份live及6份Mock输出均通过JSON Schema校验；该额外QA使用本地已有jsonschema，应用运行不依赖它。

独立交付副本复核命令和结果见 [delivery-check.txt](../examples/delivery-check.txt)，不产生额外模型调用。当前工具演示见examples/tools/actual-results.json，不是模型生成证据。

## 历史文案人工核对与边界

正常稿对短视频创作者说话，涉及封面、转场、口播、教程/日常记录和互动提问，画面是纸卡、手机支架和提纲，属于可拍的创意安排。唯一产品事实为“支持字幕”，有P01-F1引用；没有自动识别、多语言、效率数据或产品按钮流程。提纲建议、提问及虚构创作者口吻属于非产品事实叙事，不伪装成真实用户证言或产品效果数据。

28.6秒来自3镜11.3+5.3+12.0秒；节奏偏口播，后续仍可细化剪辑点。工具恢复稿21.6秒、4镜，同样只引用“支持字幕”。词法检查会漏掉隐含宣传，也可能误报一般叙事中的数字/比较，不是通用语义事实证明。时长未以真实配音或成片验证。

其他限制：少量开发采样不代表稳定成功率；未做盲评、跨模型性能比较或用户可用性研究。个人贡献已记录在04-ai-usage.md；实际投入时间仍需按事实补充。

## 第二轮检查器漏检修复（规则2.2）

按 Claude 评审中构造的10句复现：每句放在含有效P01/P01-F1引用的分镜中，字幕保留“支持字幕”，将编造声明放入旁白。修复前实际放过7/10，证实合法引用不能替额外能力或效果声明背书。

| 声明 | 规则2.1实际结果 | 规则2.2实际结果 |
| --- | --- | --- |
| 用它做字幕，剪辑时间直接减半 | 漏检 | 拦截 |
| 字幕会跟着语音同步出现 | 漏检 | 拦截 |
| 字幕样式有几十种可选 | 漏检 | 拦截 |
| 它能帮你把字幕对齐时间轴 | 漏检 | 拦截 |
| 字幕可以批量修改 | 漏检 | 拦截 |
| 字幕不再需要手动打 | 漏检 | 拦截 |
| 做出爆款视频 | 漏检 | 拦截 |
| 支持字幕，还能识别方言 | 拦截 | 拦截 |
| 不支持字幕 | 拦截 | 拦截 |
| 打开产品界面点击字幕按钮 | 拦截 | 拦截 |

修改包括：减半、翻倍、耗时等时间效果；同步、对齐、批量、样式、模板等功能细节；中文数量表达；爆款/涨粉等效果；与“产品/它/字幕”等主语组合的“能、可以、会、帮你、不再”。不将所有模态词全局禁用，避免误伤“你可以先写提纲”等创作建议，也避免把“功能”中的“能”误识别为能力动词。

固定回归集10句全部拦截，6条正常叙事对照全部通过。此前真实成功脚本已用新规则离线复核，仍通过；本轮没有重新调用模型，也没有改写历史Trace的规则版本或检查结果。

证据：[修复前实际输出](../examples/checker/baseline-v2.1.json)、[修复后16条实际输出](../examples/checker/current-results.json)、[固定输入](../data/evaluation_claims.json)。复现命令：`python3 -m examples.checker.run_regression`。

这只是已报告漏检的词法修补，不是通用事实准确率评估。

## 第三轮：留出集评估与语义复核

规则2.2调词后，Claude 另写了一批未参与调词的句子作为留出集（12句编造声明、6句正常叙事、2句正确引用），与原16句一起放入 [data/eval/claim_eval.json](../data/eval/claim_eval.json)。每句放入已有有效P01-F1引用的分镜旁白。为保持留出性质，后续不得根据留出集结果修改词表或判定提示词。

词法层实际结果（离线，`python3 -m examples.checker.run_claim_eval`，输出 [claim-eval-lexical.json](../examples/checker/claim-eval-lexical.json)）：

| 子集 | 预期 | 词法层符合预期 |
| --- | --- | --- |
| 开发集编造声明 | 拦截 | 10/10 |
| 开发集正常叙事 | 放行 | 6/6 |
| 留出集编造声明 | 拦截 | 1/12 |
| 留出集正常叙事 | 放行 | 1/6 |
| 留出集正确引用 | 放行 | 2/2 |

开发集全对而留出集几乎失效，说明规则2.2是对已报告句子的过拟合。据此新增模型语义复核层（设计见02-solution.md）。

36句固定评估集的真实语义判定实验已执行一次，使用gpt-5.4-mini-2026-03-17、Responses、medium，36次真实调用，无工具/判定错误。未根据结果修改词表、判定提示词或标签，也未重跑筛选结果。复现命令（每句一次模型调用，共36次）：

```sh
python3 -m examples.checker.run_claim_eval --judge live --env-file .env --api responses --reasoning-effort medium --timeout 60
```

实际汇总与逐句判定见 [claim-eval-live.json](../examples/checker/claim-eval-live.json)，36条完整工具输入、返回及时间戳见 [claim-eval-live.trace.jsonl](../examples/checker/claim-eval-live.trace.jsonl)。每条成功返回均为judge_mode=live，不是离线Mock。仅为评估脚本增加进度、逐条落盘与运行元数据，没有修改审核业务逻辑。

| 子集 | 词法层符合预期 | 语义层符合预期 | 最终检查符合预期 |
| --- | --- | --- | --- |
| 开发集编造声明 | 10/10 | 9/10 | 9/10 |
| 开发集正常叙事 | 6/6 | 6/6 | 6/6 |
| 留出集编造声明 | 1/12 | 12/12 | 12/12 |
| 留出集正常叙事 | 1/6 | 6/6 | 6/6 |
| 留出集正确引用 | 2/2 | 2/2 | 2/2 |
| 合计 | 20/36 | 35/36 | 35/36 |

语义层目标句检出21/22条编造声明，14/14条正常叙事或正确引用被放行。留出集本次20/20符合预期，样本量小且仅运行一次，不代表通用准确率或重复运行稳定性。

**真实失败：开发集“做出爆款视频”漏检。** 该条目标旁白没有被列出产品声明；语义判定反而以“未被事实直接完整表达”为由误拦共用标题“字幕功能介绍”。因此semantic/final均为flagged_elsewhere：整份脚本检查虽失败，目标句仍属于漏检，不能把整体失败算成目标声明检出。其余35条没有出现该标题误报。此次最终层与语义层指标一致，说明有判定模型时词法风险信号降为提示，没有兜住这一目标句。上述标题误报单独记录，不混入14条应放行目标用例的误报率。

核对结果见 [claim-eval-live.verification.json](../examples/checker/claim-eval-live.verification.json)：数据集哈希、36条顺序/输入、live模式、各层统计和原始Trace逐项对应。该次评估运行没有更新压缩包；本次交付已另行重新生成dist/submission.zip。

### 新Trace对应的代码版本

固定评估的代码内容版本为 `8a11784b006e66353ec70616724d4afe42d1ecdfae3572c8cc7e5e957ba52522`（SHA-256）。[版本清单](../examples/checker/claim-eval-live.runtime-manifest.json)将36条Trace、结果与原核对文件的哈希，绑定到src/data/schemas、依赖文件及两个评估脚本的文件哈希；对应的完整文件保存在 [源码快照](../examples/checker/code-versions/8a11784b006e66353ec70616724d4afe42d1ecdfae3572c8cc7e5e957ba52522/)。清单还记录本次模型、API、reasoning effort、运行时间、复现命令，以及补录时的Git HEAD与dirty状态。该HEAD只是上下文，**不是此次执行的完整代码版本**，工作区未提交内容由源码快照固定。

这份清单在运行后补录，明确标记retrospective；不能声称它是在运行开始时自动采集，也不能只靠事后哈希独立证明历史执行。补录前后没有改动此次运行的业务代码、数据或评估入口。与此前正常场景的运行时清单交叉比较，共15个src/data/schemas文件全部一致。原始Trace和结果保持原样，未为补版本信息重新调用模型。

可复制的离线核对命令：

```sh
python3 -m examples.checker.verify_claim_eval
```

实际通过：源码快照与当前文件一致，Trace及输出未变，36条输入、live判定、各层结论和统计均对应，见[版本核对结果](../examples/checker/claim-eval-live.version-verification.json)。额外用临时清单分别篡改代码版本、Trace哈希、模型配置，三种均被拒绝。将来代码发生变化时，默认核对会报出差异；仅复核历史快照可用`--snapshot-only`，不会将历史结果归到新代码上。哈希用于对应与完整性核对，不是数字签名。后续若Git提交，应记录新提交对该清单的包含关系，不将新SHA冒充当时运行SHA。

此前五组Agent记录早于语义层。当前normal、duration_revision、tool_failure已用最新版独立重跑并更新；missing_info和no_material保留历史记录，不据此宣称它们经过新版语义判定。旧的三条记录已移至examples/history/pre-semantic-rerun。


## 最新版重跑：真实语义复核已核对

本轮不修改Agent、工具、提示词或判定器业务逻辑，仅运行最新版CLI，增加脱敏HTTP记录与离线审计脚本。生成模型和语义判定模型均为gpt-5.4-mini-2026-03-17，Responses、medium配置。

| 独立场景 | 真实过程/总时长 | 最终版本 | 最终句段数 | checks.semantic |
| --- | --- | --- | --- | --- |
| 正常 | 24.1秒，4镜 | 1 | 15 | passed，真实live判定 |
| 超时修正 | 36.2 → 20.1秒，4镜 | 2 | 13 | passed，真实live判定 |
| 工具失败 | 检索注入临时错误 → 模型重试 → 22.8秒，4镜 | 1 | 13 | passed，真实live判定 |

三条均无GUARD_REJECTED。时长场景共4次普通30秒请求：第一次18.8→29.9秒，第二次25.6秒，第三次36.2→20.1秒，第四次28.2秒；仅第三次属于超时修正，全部保留。正常和工具失败各一次，因此共6次新运行，未复用旧Trace或共享一次执行。

每次保存input/output/trace、api-audit.json及runtime-manifest.json。API审计记录真实HTTP返回中的结构化语义判定，不保存密钥或内部推理；未替换任何返回值。离线审计逐项确认：最终草稿payload与真实判定请求一致、判定覆盖全部句段、来源有效、版本与哈希一致、原始判定重放仍通过、估时与输出相同；三个最终判定的响应ID各不相同。

证据与复现见 [重跑说明](../examples/live/semantic-rerun/README.md)，完整核对结果为 [verification.json](../examples/live/semantic-rerun/verification.json)。`python3 -m examples.live.verify_semantic_runs` 不联网复核这些记录；重放明确标记replay，不冒充新的live调用。真实判定通过仍不等于语义判定器绝不误判。上述端到端重跑与36句固定评估是两次独立实验，后者的实际结果及失败见本页“第三轮”。
