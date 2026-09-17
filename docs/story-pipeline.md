# 极简叙事提示词生成器

`t2i_story_pipeline` 直接把 Story Description 生成最终可用于文生图的长段落。
它不复用旧 `t2i_prompt_pipeline`，也没有 Story Blueprint、字段化 Scene、
renderer、provider review 或 revision 阶段。

## Interface

调用者只需要一个可恢复的 seam：

```python
store = LocalStoryRunStore(
    Path("runs"),
    Path("prompts"),
)
request = StoryRequest(
    story="故事要求",
    theme_count=100,
    frames_per_theme=6,
    female_count=1,
    male_count=1,
    content_level=ContentLevel.AESTHETIC,
)
settings = StoryRunSettings(provider=provider_settings)
rules = resolve_story_rules(request)
completed = await StoryStudio(model, store, settings, rules).run(
    request
)
```

恢复时使用同一个 runs 目录和 manifest 中冻结的 settings：

```python
snapshot = LocalStoryRunStore(Path("runs")).inspect(run_id)
completed = await StoryStudio(
    model,
    LocalStoryRunStore(Path("runs")),
    snapshot.manifest.settings,
    snapshot.rules,
).resume(run_id)
```

结果按 Narrative Theme 分组；每个 Narrative Frame 只有：

- `frame_id`：`F01` 至请求数量；
- `prose`：一段无换行、无字段标签的最终叙事提示词。

## 生成流程

1. `themes`：每批最多十个，结构化返回 `semantic_name` 及每个主题的 `title`、
   `premise`、`style`，不提交 ID。程序按响应顺序分配连续 `T001` 等 ID。
   premise 建立足够完整的稳定事实，style 提供适合当前媒介的可执行视觉方向，
   不再机械限制成两句前提或一句风格。更具体的 Story Description 要求优先。
2. `frames`：一次请求当前主题所有缺失帧，模型仅返回对应数量的
   `<FRAME>完整单段正文</FRAME>` 文本块。程序按请求槽位顺序分配 `F01` 等 ID、
   去除传输标签并构造领域对象；模型不提交 Frame JSON 或工具参数。
   不存在本地正文拼接或二次 renderer。

100 themes × 6 frames 的基础调用量是十次 theme batch 加一百次 frame batch，
共 110 次 provider 调用（默认 Theme batch size 为 10）。
`StoryStudio` 使用一个顺序 Theme producer、有界 Frame queue 和固定数量的
Frame workers。每批 Theme 保存后立即入队，Frame 生成与后续 Theme 批次重叠，
不等待全部 Theme 完成。两类调用共用 `concurrency` 信号量，默认合计最多八个
在途生成操作；队列容量也等于该值。

Theme producer 始终看到之前已保存的完整主题列表，保持语义名称、ID 和去重上下文
顺序稳定。后续 Theme 批次失败不会放弃已排队的 Frame 工作。resume 优先排队已有
主题的缺失帧，同时补齐缺失 Theme；全部请求内容完成后才发布。

批量文本保持 110 次无错误基础调用，不采用逐帧调用所需的 610 次请求。
这只是请求数量对比，不等于模型质量、实际 token 或费用评测。
批次必须返回准确数量，且标签外不能有正文、标签不能嵌套；数量或边界不明确时
拒绝整个批次，不猜测段落对应哪个槽位。边界明确后逐帧执行结构契约和所选质量检查。

## 架构边界

Story 只有一条当前执行路径，不通过 output-mode 开关维护多套生成实现，
也不通过 YAML 声明任意步骤、可执行代码或插件：

| 层 | 职责 |
|---|---|
| `documents.py` / `models.py` | 严格解析文档和定义请求、模型草稿、最终对象、质量策略 |
| `authoring_rules.py` / `prompts.py` | 冻结创作指令、序列化阶段上下文，不混入执行策略 |
| `provider.py` | 结构化或文本传输、transport 重试、截断与 usage，不判断故事质量 |
| `frame_batches.py` / `quality_validation.py` | 纯文本边界解析与纯函数检查，不进行 I/O 或模型调用 |
| `studio.py` | 编排两个固定阶段，分配 ID，决定接受、缺失帧重试和完成 |
| `run_store.py` / `persistence.py` / `storage.py` | 原子 checkpoint、锁、恢复完整性验证与发布 |

结构化 Theme 与文本 Frame 使用各自明确的接受逻辑，共享 attempt 记录及错误反馈
机制；Theme 通过 async iterator 交付已保存主题，不引入业务 validator 回调或
通用 workflow 框架。创作、验证和执行设置互不冒充。
公共接口不接收无法冻结的 validator 回调；额外检查统一来自声明式质量策略。
仅保存当前目录和数据结构，不提供旧整组 JSON checkpoint 或旧输出模式的回退路径。

## Content Level

`StoryRequest.content_level` 是故事分支自己的正式输入，不依赖旧管线规则。支持：

- `aesthetic`（默认）：故事、人物和构图优先，不主动增加裸露或性接触；原故事
  已要求成人亲密内容时只作非露骨呈现；
- `erotic`：每帧直接呈现与故事相容的成人裸露、非露骨亲密接触、姿态张力和
  表情回应，不以气氛或“即将发生”替代；
- `hardcore`：每帧直接呈现与故事相容的明确成人性行为，可以客观写明相关身体
  与接触，但仍服从单一静态动作、完整人物、故事因果、镜头和光线要求。

只把当前选择等级的指令编译进 theme 与 frame prompt；不会同时发送另外两级规则。
等级名称和合规说明不得出现在生成的 `title`、`premise` 或 `prose` 中。

## 人物数量约束

`StoryRequest.female_count` 和 `male_count` 是可选人物数量约束，分别接受 0 至 8。
两者都提供时，每个 Narrative Theme 及其每个 Narrative Frame 必须恰好使用该
阵容，不得省略、替换或增加其他人物。只提供一项时，该性别人数必须精确匹配，
另一性别人数遵循 Story Description 明示事实；两项都省略时，人物人数和性别
完全遵循 Story Description。两项不能同时为 0，已指定人数之和不能超过 8。

约束会同时编译进 theme 和 frame 的 system prompt，并以 `cast_constraints`
写入两个阶段的 provider request。

## 人物国籍与地点缺省值

Story Description 明确说明某个人物国籍时，Theme 和 Frame 忠实沿用。未明确
说明时，该人物缺省为中国籍。故事地点、姓名、语言、肤色和外貌不作为其他国籍
的推断依据。

Story Description 明确说明故事发生国家，或给出可确定国家的地点时，Theme 和
Frame 忠实沿用；两者都没有时，场景缺省位于中国，不得自行改到其他国家。每个
Theme premise 和每个最终 Frame 都必须逐人明确写出国籍，并明确写出故事发生
国家；英文输出用 `Chinese` 明示默认人物国籍。

## 叙事方式

每帧是一段自然流动的故事画面，而不是视觉规格表。整体通顺、画面成立和人物关系
优先于逐项填表。段落需要自然点明风格，并在前部让年代、地点和当前时刻成立；
每帧重新完整描写所有可见人物的明确成年身份、稳定外貌、发型、服装、表情、视线
和当前姿态。环境、最重要的动作或接触、直接物理结果、镜头和光线应按自然观察顺序
融入同一段 prose。

每个 Narrative Frame 都能脱离前后文独立理解，但不再强制“触发—目标—期限—
失败后果”、固定的“此刻”动作句、倒数第二句摄影或最后一句光线。只有故事真正需要
时才写期限和后果，不为制造戏剧性虚构委托、验收、倒计时和抽象风险。多帧像从同一
微型故事中选出的不同静止画面，不机械套用建立、加压、发现、结果、余波六阶段。
篇幅由人物和画面复杂度决定，不设目标字数。

系统没有模型评审、关键词评分、相似度 gate 或 revision 阶段。默认不选择任何
额外质量检查，因此仍只执行基础结构契约。Story Document 可以显式选择本地
Frame 证据检查；这些检查不保证叙事语义正确，也不代替创作规则。

## Story Document

文件输入只接受 UTF-8 `.yaml`，不保留 TXT 解析或旧 CLI 入口。正文仍是自然语言，
不是字段化视觉规格。最小文档只需要 `id` 和 `description`：

```yaml
id: rainy-station
description: |
  1930年代秋夜，两名成年旅人在旧车站重逢。
  用克制的现实主义摄影描绘他们辨认彼此的瞬间。

generation:
  theme_count: 12
  frames_per_theme: 3
  content_level: aesthetic
  output_language: chinese
  cast:
    female_count: 1
    male_count: 1

authoring:
  themes:
    - 主题差异来自事件与人物关系，而不是仅更换色调。
  frames:
    - 每帧独立描述景别、视角和焦点或景深。

validation:
  themes:
    mode: report
    checks:
      - type: required_text
        field: premise
        values: [旧车站]
  frames:
    mode: report
    checks:
      - type: camera_evidence
      - type: prose_length
        min_chars: 100
        max_chars: 2000

runtime:
  concurrency: 8
  generation_retries: 2
  theme_batch_size: 3
  theme_output_tokens: 12000
  frame_output_tokens: 32768
```

`id` 只接受小写字母、数字及单个分隔用的 `-`、`_`，长度不超过 120。
它作为 `source_prompt_stem` 冻结到请求，文件改名不改变发布名称。
`description` 去除首尾空白，保留 YAML 多行字符串解析后的内部换行；建议使用 `|`。
所有未知字段、非法枚举、重复键、anchors、aliases、merge keys、多个 YAML 文档、
非标准对象标签、错误数值类型和越界参数都会在加载 provider 配置前明确报错。

优先级为：程序默认值 < 文档配置 < **显式** CLI 参数。只覆盖已传入的字段，
包括数值 `0`；未传的另一侧人物数仍采用文档配置。文档自身必须有效，不能靠 CLI
修补非法文档。人数最终仍经过 StoryRequest 的总人数与非零阵容契约。

缺省值：1 个主题、每主题 6 帧、aesthetic、chinese、不限定男女数量、8 个并发、
2 次额外 generation retries。`authoring.themes` 和 `authoring.frames` 是逐条
单行创作指令，按阶段追加到用户规则之后、输出语言规则之前。运行参数与质量策略
不会被当成初始创作指令发给模型；若要求模型包含指定内容，也应在正文或 authoring
中明确表达，而不是只配置检查器。

### 批次与输出预算

`runtime` 的整数配置与运行 API 共用 `StoryRuntime`，只保留一份默认值和边界：

| 字段 | 默认值 | 范围 |
|---|---|---|
| `concurrency` | 8 | 1–32，Theme 与 Frame 共用 |
| `generation_retries` | 2 | 0–5 次额外生成重试 |
| `theme_batch_size` | 10 | 1–10 |
| `theme_output_tokens` | 6000 | 512–65536 |
| `frame_output_tokens` | 32768 | 512–65536 |

输出预算针对整个批次，不是每个 Theme 或 Frame。实际初始请求使用配置预算与
provider 上限的较小值；不会改写 manifest 中冻结的配置。截断后按既有机制提升到
冻结的 provider 上限。较复杂的主题可以显式选用更小批次和更高预算，不自动扩大
所有请求。无错误调用量为 `ceil(theme_count / theme_batch_size) + theme_count`。

## 可选质量检查

`validation.themes` 与 `validation.frames` 分别声明本阶段的 `mode` 和 `checks`。
两者默认均为 `report`、空检查列表；可以只启用一个阶段，也可以使用不同模式。
不保留旧 `validation.quality`、扁平策略或旧报告结构的解析入口。

| 模式 | 行为 |
|---|---|
| `off` | 跳过可选检查；仍验证配置、schema、数量、ID、非空单段正文和存储契约 |
| `report` | 记录告警并发布，不因质量问题重试 |
| `enforce` | 拒绝有问题的输出，反馈具体问题并有界重试；耗尽后保留 checkpoint，不发布 |

某阶段的 `checks` 为空或模式为 `off` 时，该阶段状态是 `skipped`，不宣称通过
了质量验证。每个检查用带 `type` 的对象声明；未知类型即使在 `off` 下也会报错。

Theme 检查必须显式指定 `field: title | premise | style`，只检查该字段，不拼接
其他字段来凑证据。同一种类型可以用于不同字段，但同一字段不能重复配置：

- `required_text`：`values` 中每项必须逐字出现在指定字段，区分大小写。
- `forbidden_text`：指定字段不能包含 `values` 中任一原文，区分大小写。
- `text_length`：指定字段的 Unicode 字符长度必须位于 `min_chars` / `max_chars`
  闭区间，默认 1 / 32768；检查参数范围为 1–32768，不改变 Theme 基础 schema。

Theme 批次在 checkpoint 和 Frame 入队之前执行检查。`enforce` 失败时有界重试
整个 Theme 批次，不生成该批次的 Frame；`report` 保存告警后继续。之前批次已经
通过的 Theme 和 Frame 不受后续主题拒绝影响。

Frame 检查只针对最终 `prose`，同一种类型只能出现一次：

- `camera_evidence`：按输出语言检查景别、视角、焦点或景深的文字证据。中文匹配
  “中景”“平视”“焦点”等词；英文匹配 `medium shot`、`eye-level`、`focus`
  等表达。这只是启发式检查，不验证摄影方案是否物理成立，不建议对插画等题材
  无差别启用。
- `prose_length`：`min_chars` / `max_chars`（默认 1 / 32768）的闭区间；
  按 Python Unicode 字符数计算，包含标点和空格，不是字节数、汉字数或 token 数。
- `required_text`：非空 `values` 列表，要求每帧逐字包含每一项，区分大小写。
- `forbidden_text`：非空 `values` 列表，要求每帧不包含任一项，区分大小写。

例如 `checks: [{type: required_text, values: [车站时钟]}]`。这些通用检查不识别
输入文件名，不加载 Film 的来源、人物或作品专属检查，也不提供关闭安全要求或
绕过 provider 限制的能力。

CLI 的 `--theme-quality-mode` 和 `--frame-quality-mode` 分别覆盖对应阶段的模式，
不改变检查器列表或另一阶段的设置；不保留旧 `--quality-mode`。
API 通过 `StoryRunSettings.quality.themes` / `.frames` 设置同一策略。两阶段策略
完整冻结在 manifest 中，resume 不读当前 YAML 或规则文件，也不接受切换策略。

检查问题以 `stage`、`theme_id`、`frame_id`、`field`、`check`、`message` 保存到
attempt 的 `quality_issues`。Theme 问题的 `frame_id` 为 null，Frame 问题指向
具体 Frame ID 和 `prose` 字段。强制拒绝进入现有错误反馈与重试链。
最终 `result.json` 的 `quality.themes` 和 `quality.frames` 分别包含
`mode`、`status`、`issues`，只汇总已接受结果，不复制历史拒绝问题。
发布和读取完成结果时都会按冻结策略重新计算两阶段报告并核验一致性。
CLI 分别输出两阶段的 `skipped` / `passed` / `warnings` 和报告路径；
`report` 告警也出现在进度输出中。最终 TXT 保持每帧一行纯正文，不混入报告。

每个 Frame 独立接受与保存。一个批次只有部分帧违反结构或 `enforce` 质量检查时，
通过的帧立即保留，下一次请求只包含失败槽位，并携带已经保存的帧作为上下文。
`report` 的告警帧仍会被接受，不引起额外调用。单次执行中，每个主题的 attempt
次数仍有界，不会因为每次有部分进展而重置重试预算。显式 resume 会获得新一轮
冻结配置允许的重试机会，attempt 编号继续递增。不新增 Profile 或模型评审调用。

## 运行记录与恢复

每个 run 在首次 provider 调用前分配 ID，并写入独立目录：

```text
runs/<run-id>/
├── request.json
├── rules.json
├── manifest.json
├── attempts/
│   └── <operation>-<attempt>.json
├── themes/
│   └── T001.json
├── frames/
│   └── T001/
│       ├── F01.json
│       └── F03.json
└── result.json
```

`manifest.json` 冻结 provider、并发数、generation retry、theme batch size、
theme/frame token 上限、完整质量策略和发布目录。每个成功 Theme 和每个 Frame
都独立原子写入并 fsync；例如只有 F02 失败时，上图的 F01 和 F03 保留，恢复只请求 F02。
attempt 在对应 Frame checkpoint 之前保存接受/拒绝信息与 usage。若在多帧落盘
期间中断，以已经完成原子写入的 Frame 文件为恢复依据，不把未落盘的 accepted ID
当作已完成内容。
checkpoint 文件名、内容 ID、顺序、数量或 schema 不一致时会明确报告损坏，不会
静默跳过。

同一 run 执行期间持有非阻塞文件锁，避免两个进程同时恢复。失败会保留全部成功
checkpoint；`resume` 扫描它们，只生成缺失部分，并把上次同一 operation 的错误
反馈给模型。全部 checkpoint 完成后才写入 `result.json` 并发布 TXT。
已完成 run 的 `resume` 直接返回已发布结果，不调用 provider。

## 错误分类与重试

错误恢复分为两层：

1. provider transport 层默认额外重试两次。timeout、transport error、HTTP 429
   和 5xx 使用有界退避；429 优先遵循 `Retry-After`。401/403 立即报告认证错误。
2. generation 层对每个 Theme batch 或单主题的缺失 Frame batch 默认额外重试两次。
   空响应和不支持的 provider 响应记录为 provider error；Theme JSON/schema 或质量错误、
   Frame 文本边界错误或逐帧拒绝记录为 rejected。文本响应若
   `finish_reason=length`，不把可能截断的内容作为成功批次；无效的截断 Theme
   同样记录为 truncated。下一次 attempt 提升到 manifest 冻结的 provider 上限；
   Theme 默认初始预算为 6,000 tokens，Frame batch 为 32,768 tokens，
   可通过文档和显式 CLI 参数配置。
   truncated outcome 会持久化，因此进程重启后的第一次 resume attempt
   也直接使用提升后的预算。

每个 attempt 保存 stage、operation、requested IDs、accepted IDs、具体 issues、
实际请求 token 上限、耗时和 token usage。当前进程内的下一次 attempt，以及进程
重启后的 resume，都会读取最近一次与当前 requested IDs 相交的 attempt，并把最多
三条 issues 反馈给模型。认证失败和 transport 层耗尽后的不可恢复 provider error
不会在 generation 层盲目循环。

Theme batch 要求完整的结构化响应；Frame batch 在文本边界明确后允许部分接受。
缺失帧集合只能缩小，不会重新请求已保存的帧，也没有无限 salvage/no-progress 循环。
取消运行或发生未预期异常时，会取消并等待 Theme producer 与所有 Frame workers，
包括正在等待队列空间或并发额度的任务。已落盘 checkpoint 保留，run 锁释放，
manifest 保持可 resume，不留下继续调用模型的后台任务。

## 时间、地点与时代一致性

Narrative Theme 必须建立“谁、何时何地”的故事种子；每个 Narrative Frame
仍需独立重写年代、具体地点和当前时刻，不能依赖前帧补足。

theme 与 frame 的初始 prompt 同时要求建筑、室内陈设、家具、器物、材料、服装、
发型、交通工具、武器、通信与照明技术、社会称谓和人物用语符合 Story Description
给定的时代、地域、季节、时辰与社会环境。服装冷暖、植物和取暖方式必须符合季节，
天然光与人工光源必须符合时辰，官职、礼仪和称谓必须属于正确朝代。不确定史实时
使用时代成立的通用描述，不猜测品牌、型号、精确年代或专名。

时代一致性以整体创作规则表达，不维护不断扩张的违禁物件词表。Story Description
自己明确指定穿越、架空或时代错置时，允许有意的时代冲突。

## 基础契约

以下规则是会阻断结果并进行有界 provider 重试的硬契约：

- Pydantic typed schema；
- 精确主题数、帧数和连续 ID；
- 非空单段 prose；
- provider 结构错误的有界重试和 token usage 统计。

因此默认 Theme batch size 10 下，100 themes × 6 frames 在没有 provider/schema
错误或强制质量拒绝时保持 110 次基础调用；`report` 不增加质量重试调用。

## CLI

```bash
uv run t2i-story generate \
  "1930年代秋夜，两名三十岁的成年人在旧车站重逢。他们双方自愿拥抱，彼此回应且任何一方都可以停止。" \
  --themes 100 \
  --frames 6 \
  --female-count 1 \
  --male-count 1 \
  --content-level erotic \
  --concurrency 8 \
  --runs-dir runs
```

或者读取 Story Document：

```bash
uv run t2i-story generate \
  --input story-inputs/motion-blur-photography.yaml \
  --themes 100 \
  --frames 6 \
  --content-level erotic \
  --concurrency 8
```

故事位置参数与 `--input` 互斥，并且必须提供其中一个。空文件、目录、不可读文件
和非 UTF-8 文件会在 provider 调用前报错。输入错误退出码为 2；已创建但未完成
的 run（包括强制质量检查耗尽）退出码为 1，并打印 resume 命令。批量脚本因此
能区分共享输入无效与某个阵容生成失败。
批量脚本的文档预检只使用仓库 `.venv/bin/python` 或仓库目录下的 `uv run python`，
不会退回到可能缺少项目依赖的 PATH Python；两者都不可用时明确失败。

主要选项：

```text
--input PATH           读取 UTF-8 YAML Story Document
--themes INTEGER       主题数量，1 至 100
--frames INTEGER       每个主题的画面数，1 至 6
--female-count INTEGER 可选女性人数约束，0 至 8
--male-count INTEGER   可选男性人数约束，0 至 8
---concurrency INTEGER  Theme/Frame 共用并发上限，1 至 32
--generation-retries INTEGER 每个生成单元额外重试次数，0 至 5
--theme-batch-size INTEGER 每批 Theme 数量，1 至 10
--theme-output-tokens INTEGER Theme 批次初始预算，512 至 65536
--frame-output-tokens INTEGER Frame 批次初始预算，512 至 65536
--theme-quality-mode TEXT Theme 的 off、report 或 enforce
--frame-quality-mode TEXT Frame 的 off、report 或 enforce
--content-level TEXT   aesthetic、erotic 或 hardcore
--language TEXT        chinese 或 english
--prompts-dir DIRECTORY 按日期保存最终 TXT 的根目录
--runs-dir DIRECTORY   增量 checkpoint 和运行记录目录
```

查看和恢复 run：

```bash
uv run t2i-story runs --runs-dir runs
uv run t2i-story resume RUN_ID --runs-dir runs
```

## 输出

```text
prompts/
└── YYYY-MM-DD/
    ├── aesthetic/
    │   └── <prompt-stem>_aesthetic_<female-count>_<male-count>_0001.txt
    ├── erotic/
    │   └── <prompt-stem>_erotic_<female-count>_<male-count>_0001.txt
    └── hardcore/
        └── <prompt-stem>_hardcore_<female-count>_<male-count>_0001.txt
```

TXT 每帧一行，内容就是最终 prose，不含主题标题或 frame ID。
`prompts/` 中只发布最终 TXT。用于恢复的 request、manifest、Theme、Frame、
attempt 和完整 result JSON 只保存在 `runs/`，不会复制到 `prompts/`。
使用 `--input` 时，`prompt-stem` 来自文档显式 `id`；
随后依次写入 content level、数字女性人数、数字男性人数和
序号，例如 `3-view_hardcore_1_woman_0_men_0001.txt`。只约束一侧或未约束
人数时，未知部分使用 `unspecified_women` 或 `unspecified_men`，不根据模型正文
猜测。

直接传入 Story Description 时没有 `prompt-stem`，继续使用
`<semantic-name>_<cast-slug>_NNNN.txt`。`semantic-name` 由模型用简短的小写
英文 snake_case 概括整个 Story Description；现有 `cast-slug` 使用
`one_woman_one_man` 等英文数量形式。

同一天、同一 content level 下完整名称重名时，序号按 `_0001`、`_0002` 递增
分配。
每条 prose 最多 32,768 个字符；frame batch 请求和 provider 缺省输出上限
也都是 32,768 tokens。该 token 上限由同一次调用中的全部缺失 frames 与传输标签
共同使用，不是每帧单独分配。

Provider 使用共享的 `OPENAI_*` 环境变量。凭证只从配置的环境变量读取，
不会写入产物或日志。
