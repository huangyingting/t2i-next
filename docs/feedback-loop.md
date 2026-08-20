# 离线 Prompt Feedback Loop 设计

> 状态：未来设计，尚未实现。
>
> 本文记录可供后续实现的方向，不代表当前 CLI、run schema 或目录已经支持这些
> 能力。正式实现时只采用届时确认的当前设计，不保留本文草案的兼容层。

## 背景

当前生成流程已经保存原始请求、冻结后的规则、Foundation、Theme、Frame、
PromptBook 和最终 prompts。系统能够通过结构化 schema 和本地 contract 保证
数量、ID、人物引用及部分字段长度，但仍可能出现以下语义问题：

- brief 没有被完整表达；
- StyleConstraints 包含 brief 没有明示的推断；
- 不同 Theme 使用了机械重复的 style；
- Frame 中的相机、人物朝向、姿态、遮挡或接触在物理上冲突；
- 文本不够自然、流利、简练；
- instruction 互相重复、冲突或没有被模型稳定遵循；
- prompt 本身正确，但下游图片模型没有正确执行。

这些问题需要持续收集、分类和验证，才能知道应该优化规则、schema、renderer、
provider 配置还是图片模型。仅观察最终 prompt 很难定位问题最早出现在哪一层。

## 设计目标

1. 在不增加正常 generate 调用数、延迟和 token 的前提下分析已完成 run。
2. 同时分析结构化中间对象和最终 prompt，定位问题的最早事实所有者。
3. 用结构化 finding 记录证据，而不是只产生一个不可解释的总分。
4. 将重复问题聚合为可验证的最小规则或代码修改。
5. 在固定 corpus 上比较 baseline 与 candidate，确认改善且没有明显回退后再合入。
6. 后续可以接入图片结果和人工反馈，并区分 prompt defect 与 image-model defect。

## 非目标

- 不在在线生成路径中加入 critic、repair 或自动重写。
- 不因为单个失败样本立即修改系统规则。
- 不允许 evaluator 自动修改并发布系统规则。
- 不使用 evaluator 分数替代具体问题、证据和人工抽查。
- 不把结构、拼接或持久化问题转化成更多 instruction。
- 不承诺通过 prompt 规则修复图片模型本身的所有能力限制。

## 核心原则

### 生成路径保持纯净

Feedback loop 是离线流程。正常生成仍然只负责 Foundation、Theme、Frame 和
renderer，不等待评价，也不根据评价重试。只有显式执行 audit 或 experiment 时
才产生额外成本。

### 先定位所有者，再决定修改方式

每个 finding 必须指向最早产生错误事实的层。不能把所有问题统一归因于规则：

| 问题 | 首选修复位置 |
| --- | --- |
| 风格身份、媒介或归属错误 | `foundation.rules` |
| 主题、场景、稳定人物、基础服饰或 look 错误 | `themes.rules` |
| 镜头、视角、构图、动作、表情或物理关系错误 | `frames.rules` |
| ID 泄漏、重复拼接、标签或标点错误 | renderer |
| 数量、长度、引用或枚举错误 | schema/contracts |
| provider 输出协议或截断错误 | provider adapter |
| prompt 正确但图片不遵循 | 图片模型或模型专属配置 |

### 结构化事实优先于最终文本

Audit 应读取：

- `request.json`；
- `manifest.json` 中的 provider 设置和规则指纹；
- `rules.json`；
- `foundation.json`；
- `themes/*.json`；
- `frames/*.json`；
- `book.json`；
- 最终 prompt 文件；
- 可选的图片、图片模型参数、seed 和人工反馈。

最终 prompt 用于确认 renderer 结果；Foundation、Theme 和 Frame 用于判断错误
最早在哪一层产生。

### Findings 优先于 scores

一个平均分无法回答应该改哪条规则，也会掩盖低频但严重的问题。系统可以在报告
中计算指标，但原始事实必须是带证据的 findings。

## 总体流程

```text
completed runs
    │
    ▼
offline audit
    ├── deterministic analyzers
    ├── semantic LLM evaluator（可选）
    ├── image evaluator（未来、可选）
    └── human feedback（未来、可选）
    │
    ▼
structured findings
    │
    ▼
aggregation and root-cause routing
    │
    ▼
candidate rule/code change
    │
    ▼
fixed-corpus baseline/candidate experiment
    │
    ▼
promotion gate and human review
```

## FeedbackLab 模块

Feedback loop 应形成一个深模块。调用方不需要了解检查器组合、LLM batching、
缓存、聚合或报告生成细节。

建议外部 interface 最多暴露两个入口：

```python
report = lab.analyze(run_ids, profile="deterministic")

experiment = lab.compare(
    corpus,
    candidate_rules_directory,
)
```

建议 CLI：

```bash
uv run t2i-prompts audit RUN_ID
uv run t2i-prompts audit RUN_ID --semantic
uv run t2i-prompts compare eval/cases.jsonl \
  --candidate-rules rules-candidate/
```

`analyze` 读取已有 run，不修改 run。`compare` 创建新的实验 run，并明确记录
baseline、candidate、provider 配置和重复次数。

只有确实存在多个可替换 evaluator 实现时才建立 evaluator seam。例如本地
确定性 evaluator 和远程 LLM evaluator 是两种真实 adapter；不要提前为每个
小检查创建浅接口。

## Finding 数据模型

每条 finding 至少包含：

```text
finding_id
run_id
theme_id                 可选
frame_id                 可选
stage                    foundation | theme | frame | renderer | image_model
category
severity                 info | warning | error
confidence               0..1
evidence
expected_behavior
root_cause
recommended_action       rule | schema | renderer | provider_profile | no_change
rule_fingerprint
evaluator_name
evaluator_version
```

`evidence` 必须引用具体字段或 prompt 片段。`root_cause` 说明为什么把问题定位到
当前 stage。`recommended_action` 只表示修改类别，不直接携带自动执行的补丁。

建议的 category：

- `brief_fidelity`
- `style_attribution`
- `style_theme_fit`
- `theme_differentiation`
- `language_consistency`
- `conciseness`
- `fact_ownership`
- `camera_pose_geometry`
- `visibility_occlusion`
- `physical_contact`
- `character_consistency`
- `content_level`
- `internal_id_leak`
- `render_duplication`
- `image_model_adherence`

category 应保持有限且稳定，具体解释放在 evidence 和 root cause 中，避免每个问题
都创建一个新类别。

## 第一层：确定性分析

确定性 analyzer 不调用 LLM，应优先运行并阻止明显无效的产物进入付费评价。

建议检查：

- request、manifest、rules 和 book 是否能按当前 schema 读取；
- 规则指纹是否一致；
- Theme、Frame 和 Character ID 是否泄漏到最终文本；
- `StyleConstraints.required_phrases` 是否都是 brief 的逐字连续子串；
- 每个 required phrase 是否在当前 `Theme.style` 中恰好出现一次；
- 当前 `Theme.style` 是否在每个 prompt 中恰好出现一次；
- required phrases 之外的 `Theme.style` 是否混入具体相机位置或摄影参数；
- `Theme.style` 是否明确使用摄影或摄像，并排除非相机实拍的最终媒介；
- Theme 是否加入 brief 未指定的明确年代；
- brief 指定多个连续地点时，每个 Theme 是否独立包含完整路线而不是充当一个章节；
- Frame 明确选择的景深是否与 `Theme.style` 的明确景深倾向相反；
- Frame action 是否包含“不可见”“出画”“画外”，自然语言字段是否使用“仍”“已”
    等跨 Frame 缩写，或混入声音、气味、温度等非视觉信息；
- 中文和英文 style 是否符合当前长度 contract；
- Theme 自然语言字段是否混入 brief 未授权的其他语言文字；
- prompt 是否为空、重复、异常过长或含连续重复片段；
- 同一 Theme 的稳定人物字段是否保持一致；
- 不同 Theme 的 style 是否完全相同或具有过高文本相似度；
- PromptBook 中的 prompt 数量和 Frame 数量是否一致；
- renderer 是否遗漏结构化字段或重复展开同一事实。

确定性检查发现的问题通常应修复 schema、contract、store 或 renderer，而不是新增
规则。

## 第二层：LLM 语义分析

语义 evaluator 只报告问题，不生成修复后的 prompt。其 structured output 使用
`findings[]`，允许返回空数组。

建议检查：

- brief 是否被 Foundation、Theme 和 Frame 忠实表达；
- StyleConstraints 是否逐字保留 brief 明确指定的导演、艺术家或流派短语；
- StyleConstraints 是否擅自总结或补写 brief 没有明示的时代、地域、媒介或风格事实；
- Theme.style 是否与主题、场景、人物和基础服饰匹配；
- 不同 Theme 是否形成自然视觉差异；
- Frame 是否只拥有当前镜头事实；
- 相机位置、镜头朝向、取景范围、人物朝向、姿态、重心和支撑是否相容；
- 遮挡和可见部位是否相容；
- 接触双方的部位、方向和施力关系是否相容；
- 是否出现普通正面镜头同时清晰呈现面部正面和臀部背面等矛盾；
- 描述是否自然、流利、简练；
- content level 是否与请求一致；
- 规则是否过度约束、互相冲突或诱发机械重复。

### Batching

语义检查应以 Theme 为基本 batch：一个请求包含共享 Foundation、当前 Theme、
该 Theme 的全部 Frame 和最终 prompts。这样共享上下文只发送一次，也便于检查
跨 Frame 稳定性。

只有确定性分析通过的对象才进入语义评价。大型 run 可以只评价新增对象、失败
对象或固定比例样本。

### 防止 evaluator 被待分析文本影响

brief、rules 和 prompts 都应被当作不可信数据。Evaluator instruction 必须明确：

- 不执行待分析文本中的命令；
- 不改变评价目标；
- 只依据固定 rubric 返回 schema；
- 不泄漏 provider 配置或环境信息；
- evidence 只能引用输入中存在的内容。

## 第三层：图片与人工反馈

Prompt feedback 不能完全代替图片反馈。后续如果系统能够获得生成图片，应保存：

- prompt ID；
- 图片模型和版本；
- sampler、steps、尺寸等参数；
- seed；
- 输出图片引用；
- 人工或视觉 evaluator 的 findings。

视觉评价可以检查：

- 构图和镜头是否符合 prompt；
- 人物数量、身份和外貌是否一致；
- 姿态、肢体和接触是否合理；
- 遮挡与视角是否成立；
- Theme.style 及其 brief 原文约束是否在图片中可见；
- 图片是否遗漏 prompt 中已经明确的关键事实。

必须区分：

1. prompt 没有表达清楚；
2. prompt 已表达清楚，但图片模型没有遵循；
3. prompt 对特定图片模型表达方式不合适。

第一类进入通用规则优化，第二类归为 image-model defect，第三类才考虑模型专属
profile。不能用越来越长的全局规则补偿单一图片模型的限制。

人工反馈应尽量使用有限标签和可选说明，例如：

- accepted；
- wrong_style；
- wrong_character；
- wrong_camera；
- impossible_pose；
- too_verbose；
- missing_detail。

自由文本作为补充 evidence，不直接作为可执行 instruction。

## 聚合与根因分析

Findings 应至少按以下维度聚合：

- rules fingerprint；
- provider 和 model；
- content level；
- output language；
- frame mode；
- generation stage；
- category；
- severity。

建议报告：

- 每 100 个 prompt 的 finding 数；
- 无 error prompt 比例；
- 各 category 的 error/warning 比例；
- Theme.style 重复率；
- prompt 长度和生成 token 分布；
- 人工接受率；
- 图片遵循率；
- 与上一规则版本相比的变化。

只有跨多个 run 重复出现且证据一致的问题才进入优化候选。单个异常样本可以加入
回归 corpus，但不能直接证明全局规则需要修改。

## 规则优化 proposal

一个 proposal 应记录：

- 目标 category 和 stage；
- 代表性失败样本；
- 当前相关规则；
- 当前规则为什么没有覆盖或为什么存在冲突；
- 建议修改的文件和最小文本变化；
- 预期改善；
- 可能回退；
- 对应 regression cases。

LLM 可以生成 proposal，但 proposal 不自动改文件。修改仍通过正常代码审查和测试
流程完成。

新增规则前必须检查：

- 是否能修改已有规则而不是追加重复规则；
- 是否属于 schema、contract 或 renderer；
- 是否只针对某个 provider 或图片模型；
- 是否会与 content level、frame mode 或输出语言规则冲突；
- 是否增加大量输入 token；
- 是否把一个具体失败样本过度概括成全局限制。

## 固定 Corpus 与 A/B Experiment

建立版本化 evaluation corpus，建议最初包含 30 至 100 个 case，覆盖：

- 中文和英文；
- aesthetic、erotic 和 hardcore；
- sequential 和 variations；
- 单人、多人和复杂人物接触；
- 正面、背面、俯视、仰视、侧面和镜面；
- 明确导演或艺术家、可映射风格和无明确风格；
- 室内、户外、昼夜及不同材质环境；
- 容易发生遮挡、肢体、重心或可见性矛盾的场景。

每个 case 保存 spec、期望标签和已知风险，但不要求保存唯一正确 prompt。创作输出
不是字符串快照测试。

实验必须记录：

```text
corpus_version
baseline_rules_fingerprint
candidate_rules_fingerprint
provider_signature
repetitions_per_case
evaluator_versions
```

由于生成具有随机性，同一 case 建议运行 2 至 3 次。Baseline 与 candidate 必须
使用相同 provider 配置和评价 rubric。

### Promotion gate

Candidate 只有同时满足以下条件才可合入：

- 目标 category 明显改善；
- error 级问题不增加；
- 其他主要 category 没有明显回退；
- prompt 长度和 token 成本没有超过预设阈值；
- 未参与调优的 holdout cases 也有改善；
- 人工抽查通过。

不能只依据一个综合平均分决定 promotion。

## 存储与不可变性

现有 `runs/` 保持不可变。评估产物放入独立目录：

```text
evaluations/<evaluation-id>/
├── request.json
├── findings.jsonl
├── report.json
└── experiment.json
```

其中：

- `request.json` 保存 run IDs、profile 和 evaluator 配置；
- `findings.jsonl` 保存原始 findings；
- `report.json` 保存聚合指标；
- `experiment.json` 仅在 baseline/candidate 比较时存在。

缓存键建议使用：

```text
run artifact fingerprint
+ evaluator name/version
+ evaluation profile
+ rubric fingerprint
```

相同产物和 evaluator 不重复付费分析。Evaluator 或 rubric 改变时自动形成新的
评价结果，不覆盖历史结果。

## 成本控制

- 确定性检查始终先运行；
- semantic 和 image profile 必须显式启用；
- 按 Theme 批量评价全部 Frame；
- 默认只分析新增 run；
- 大型 run 可以抽样；
- 只对新增或改变的规则运行 candidate experiment；
- 使用 fingerprint 缓存；
- 聚合阶段只读取 findings，不再次发送完整 prompts；
- 在线 generate 路径不调用 evaluator。

因此 MVP 可以做到零额外生成成本；只有主动运行语义或图片评价时才使用额外模型
调用。

## 常见失败模式

### 自我确认

如果 evaluator 只重复生成时使用的规则，它可能倾向于确认当前输出。Rubric 应独立
定义检查维度，并要求 evidence。重要 promotion 应结合人工抽查或第二 evaluator。

### 自动规则膨胀

如果每个 finding 都追加一条规则，instruction 会越来越长并产生冲突。Proposal
必须优先修改、合并或删除现有规则。

### 过拟合单个样本

所有全局规则变化必须在 corpus 和 holdout 上验证。失败样本用于形成 hypothesis，
不是直接形成全局规则。

### 混淆 prompt 与图片模型问题

图片错误不自动证明 prompt 错误。必须先检查 prompt 是否已经明确表达对应事实。

### 评价漂移

Evaluator model、rubric 和 structured schema 都必须版本化。不同 evaluator 版本
的结果不能直接当作同一测量尺度。

### 总分掩盖严重问题

报告必须保留 category、severity 和 evidence。Promotion gate 优先看 error 级
回退，而不是只看平均分。

## 分阶段实施

### Phase 1：确定性 Audit MVP

- 定义 Finding 和 FeedbackReport；
- 实现本地确定性 analyzer；
- 增加 `audit RUN_ID`；
- 写入独立 evaluations 目录；
- 测试现有结构 contract、ID 清理、Theme.style 展开和缓存。

验收标准：不调用 LLM；不修改 run；同一 run 重复 audit 得到同一结果。

### Phase 2：语义 Evaluator

- 定义固定中文 rubric；
- 增加 structured findings response schema；
- 按 Theme batching；
- 加入 evaluator/rubric fingerprint 和缓存；
- 增加 prompt injection 防护测试。

验收标准：只报告问题，不生成 repair；所有 finding 有 stage、category 和 evidence。

### Phase 3：聚合与 Proposal

- 跨 run 聚合 issue rate；
- 实现根因路由；
- 输出候选修改 proposal；
- 不自动修改系统规则。

验收标准：能够从重复 findings 定位一个目标规则文件或代码层。

### Phase 4：Corpus 与 Experiment

- 建立版本化 corpus 和 holdout；
- 实现 baseline/candidate replay；
- 比较质量、回退和 token 成本；
- 实现 promotion gate。

验收标准：规则修改必须有可重现的实验报告。

### Phase 5：图片与人工反馈

- 保存图片模型参数和 seed；
- 接入视觉 findings；
- 接入有限标签的人工反馈；
- 区分 prompt、provider 和 image-model defect。

验收标准：图片失败不会被无条件转化为全局 prompt 规则。

## 将来实现前需要重新确认的事项

- 第一个 semantic evaluator 使用当前 provider 还是独立评价模型；
- evaluation corpus 是否存入仓库；
- 图片和人工反馈由 CLI、Web UI 还是外部文件导入；
- 默认抽样比例和成本上限；
- promotion gate 的初始数值；
- 是否需要 provider/image-model 专属规则层。

这些选择会影响实现，但不改变本文的核心方向：生成与评价分离、findings 结构化、
根因按事实所有权路由、修改通过固定 corpus 验证后再合入。
