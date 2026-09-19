# t2i-prompt-pipeline

## 模型后端

所有现行 pipeline 使用同一个后端选择变量。默认直接调用 OpenAI-compatible
endpoint：

```dotenv
T2I_MODEL_BACKEND=openai
OPENAI_MODEL=gpt-4.1-mini
OPENAI_API_KEY=...
```

切换到 GitHub Copilot SDK：

```dotenv
T2I_MODEL_BACKEND=copilot
COPILOT_MODEL=auto
COPILOT_REASONING_EFFORT=high
COPILOT_OUTPUT_TOKEN_LIMIT=16384
COPILOT_TIMEOUT_SECONDS=180
```

Copilot 模式使用已登录的 GitHub Copilot 用户，也支持 SDK 识别的
`COPILOT_GITHUB_TOKEN`、`GH_TOKEN` 或 `GITHUB_TOKEN`。每个结构化阶段只开放一个
终端提交工具，不开放文件、终端或网络工具；工具参数沿用当前 Pydantic schema。
run 会冻结 backend 和模型配置，恢复时不能混用另一个 backend。

Theme 相似度检查仍使用 embeddings API。Copilot 模式若同时设置
`OPENAI_EMBEDDING_MODEL`，还需保留对应的 `OPENAI_BASE_URL`、凭据与认证配置；
未启用相似度检查时不需要这些 OpenAI 配置。

## 原地润色文本文件

`scripts/refine-text-file.py` 使用 `.env` 中共享的 `OPENAI_*` 模型配置，把
`--instruction` 原样作为 system prompt，并把指定 UTF-8 文件的完整内容作为 user
消息。模型成功返回非空结果后，脚本会原子替换原文件；调用失败时原文件保持不变。

```bash
uv run python scripts/refine-text-file.py \
  --instruction "Improve clarity while preserving all requirements and structure." \
  draft.txt
```

## 作品集合电影风格编译器

`t2i_film_style_pipeline` 从一名导演的明确作品集合提炼结构化、可摄影执行的
视觉档案，并在同一命令中生成最终提示词。它自带完整、独立的 Profile、common、
Theme、Frame、模型、provider、checkpoint 和发布实现，不 import 或调用
`t2i_story_pipeline`，也不依赖 `recipes/` 中的视觉配方。
它只加载仓库根目录的 `.env.film`，不会读取通用 `.env`。该配置文件仅保留 film
所需的后端、模型、认证、推理、token、超时和重试项。它为每部输入电影提取原作成年人物
与实际场景锚点，Theme 和 Frame 必须使用同一部电影的原作人物与场景，不得跨片
拼接或使用演员姓名代替角色。每个 Frame 还必须命中所选人物的原作服装短语，以及
所选场景的环境与道具短语；人物之间的当前关系与互动可以按场景方向和内容等级
重新创作，不要求忠于原作关系。

```bash
uv run t2i-film-style generate "张艺谋" \
  --work "大红灯笼高高挂 (1991)" \
  --scene "颂莲与卓云在陈府院落点灯后相遇" \
  --filename-stem Zhang_Yimou \
  --themes 8 \
  --frames 1 \
  --theme-batch-size 4 \
  --concurrency 8 \
  --content-level aesthetic
```

`--scene` 可省略，省略时自动选择原作成年人物与实际场景。顶层进度、结构化档案、内部动态
视觉上下文及 Theme/Frame checkpoint 全部写入 `runs/film-style/<run-id>/`；
最终提示词写入 `prompts/`。不再创建 `film-style-inputs/`。
`--filename-stem` 可指定仅含 ASCII 字母、数字、下划线和连字符的英文文件名前缀，
且不会改变中文导演署名和作品锚点。中断后只需顶层 run ID：

```bash
uv run t2i-film-style resume RUN_ID
```

恢复时复用已经完成的视觉档案、Theme 和 Frame，不重新生成已有 checkpoint。
电影流程不再接受固定男女数量的 CLI/API 参数。每个 Theme 由模型自行选择
**1–4 名不同的成年人，至少一名女性**，组合可随 Theme 变化；同一 Theme 的
Frame 保持选定人物一致，不能复制一个身份来凑人数。此选择规则对现有所有内容
等级一致适用，不改变任何等级的定义或要求。恢复简单的原作人物与场景上下文，
不再使用额外的原作/原创人物选择协议和强制阵容语义校验。
保留 schema、批次数量、ID、checkpoint 与发布完整性检查；内容校验仍是可选项，
默认不启用，可显式使用 `--validate-themes` 和 `--validate-frames`。
Profile 保持严格结构化输出；Theme 只返回不含 ID 的轻量结构，由程序分配
`theme_id`。Theme producer 每次批量生成 `--theme-batch-size` 个 Theme；批次
checkpoint 后，每个 Theme 独立进入有界 Frame queue，producer 随即生成下一批，
因此上一批的 Frame 与下一批 Theme 可以并行。二者共同遵守 `--concurrency`
全局模型调用上限；默认 Theme 批次大小为 5，可在 1–10 之间调整。
后续 Theme 批次使用紧凑的全局多样性账本，而不是重复传入全部既有 Theme 全文；
账本保留已用标题、premise/style 短摘要、来源锚点使用次数和高层覆盖计数。每个
新 Theme 必须区别于全部历史和本批其他 Theme；仅改标题、措辞、人数或小道具
不能算新主题。这个写作要求不冒充完整的语义去重证明。每个
当前输出位置获得一份稳定、可恢复的高层 diversity contract，平衡内容路径、关系
张力、空间、摄影和光线，但不固定动作、姿态、动作发起者或接触链。模型在同一次
调用内避开已用的作品场景、人物组合、内容路径、空间调度和摄影光线骨架，因此
不需要额外的多样性验证调用。
OpenAI-compatible 后端默认对 Theme 使用 `0.85` temperature、Frame 使用 `0.6`，
可用 `OPENAI_THEME_TEMPERATURE` 和 `OPENAI_FRAME_TEMPERATURE` 分别调整；
Copilot SDK 当前不支持逐调用 temperature。
每个 Theme 的全部 Frame 在一次纯文本调用中批量返回，由程序拆分并分配
`frame_id`，避免逐帧调用开销以及 JSON wrapper 或工具提交失败。批次中验证通过的
Frame 会被保留，后续只重新生成失败槽位。
每个待生成的 Frame slot 还会获得一份确定性的内容路径合同。不同 Theme 分配不同
路径，同一 Theme 的所有 Frame 继承 Theme 已锁定的同一路径，避免 Theme 与 Frame
互相矛盾；合同要求正文同时落实对应路径的全部可见证据，并要求同 Theme 画面至少
改变姿态、核心互动、景别和机位中的三项，但不固定具体姿势或身体拓扑。Theme 实际选中的 canonical
人物与场景同时冻结为 required anchors，其他上下文锚点作为 forbidden anchors，
并只在固定来源首句之后的画面正文中禁止，防止漏写场景或混入另一部作品，同时
避免作品标题中的同名人物造成误判。选择性重试继续使用原槽位的同一合同。
程序在模型返回后、写入 Frame checkpoint 前，把 Theme 的 canonical 人物和场景
组成一条自然语言锚点句，确定性插入固定来源首句之后。该句保证 exact anchor，不
替代模型的实际人物描写；报告会排除程序句，再逐人物检查服装／外貌与支撑描述、
两项面部状态、视线落点和独立支撑。
人数统一由上述 1–4 人规则选择，不再按等级固定为一人或两人。
极致情色级每帧必须同时包含明显裸露
或半解服装、实际非生殖器接触、具体欲望或愉悦表情以及皮肤或材质触觉。
任意三人及以上的 N 人阵容中，`group_frame_contracts` 只根据 Theme
实际选中的人物建立通用参与合同，不预设核心二人组、观察者、回应者、外围人物、
固定角色、配对数量、接触顺序或空间站位。模型根据人数、场景和身体拓扑自行设计
适合当前画面的互动网络，不使用程序提供的结构菜单；每个人都必须通过具体可见且
不可删除的动作直接参与同一个共同互动事件，并保持自己的闭合承重链。
Hardcore 多人 Frame 的 `hardcore_group_realization` 同样不按性别或名单顺序分配
角色，只要求全部人物直接进入当前内容路径，逐人写清动作主客体、接触或器具、受力、
支撑与主动反应，并让所有参与者属于同一个可追踪互动网络。
通过验证的 Frame 会立即单独写入 checkpoint，因此中断恢复也不会重做已通过画面。
完成的 prompt 子运行还会写出 `diversity-report.json`，本地统计 Theme/Frame
重复度、最近邻相似度、同 Theme Frame 差异、各高层变化轴覆盖情况、当前内容级别
证据完整度和 Frame 锚点一致性；景别统计只包含远景、全景、中景、中近景、近景与
特写，并记录衣袖堆在手臂或完全赤裸仍穿衣物等衣物状态冲突。报告不调用模型，也
不会触发拒绝或重试。
多人诊断还分别记录 character/scene anchor 完整帧数，以及逐人物描述、面部、视线、
支撑的完成槽位数；因此程序锚点句不会掩盖正文中漏写人物细节的问题。
每个 Frame 还要求为每名入画人物分别写出具体可见表情，以至少两项面部状态和明确
视线落点落实，不能使用群体共同表情或抽象情绪标签。
为减少肢体错乱，Frame 按支撑面、躯干朝向、四肢唯一职责、明确接触链和衣物最终
状态的固定顺序构造；每帧只保留一个核心互动，每人最多一个辅助接触，并禁止无承重
悬空、贴合与夹手冲突、遮脸与表情冲突以及互斥衣物状态。
Theme 只锁定人物、场景、关系与内容方向；每个 Frame 自由设计姿态和核心接触链，并
闭合自身的承重、四肢和衣物拓扑。批次同时变化姿态类别、高低关系、核心接触与摄影
方案，冲突时优先删除辅助动作和服装花样。
Hardcore Frame 只保留一条核心互动链，可以是明确性行为，也可以是无插入但具有
同等可见强度的 BDSM 支配互动。BDSM 路径必须写清控制者、器具两端、牵引方向、
被控制者主动维持的姿态、承重链和具体欲望表情；项圈、牵引链、腕带或绳索不能
承担体重或压迫气道。画面描述动作完成后的静态受力结果，避免连续运动、袖口束缚
和面部遮挡；Theme 不提前固定动作主客体。
Erotic 与 Hardcore 的皮肤、表情、呼吸、材质和重量感都保持最高强度；Erotic
停留在非生殖器亲密接触，不能形成完整器具控制链或命令式色情展示，Hardcore
则必须形成明确性行为、器具支配链或命令式开放展示中的一种不可误读的色情事实。
每帧还需为核心接触保留可见进入路径，保持头颈与胸骨方向一致，并从完整穿着、前开
上衣加腰部固定下装、完全脱衣三种互斥衣物状态中选择一种。
姿态不使用固定菜单或模板分配；站、坐、跪、蹲和卧姿均可使用，只要求每个人的承重
链闭合且重心落在自己的支撑多边形内。
Theme 与 Frame 语义发布验证默认关闭；分别使用 `--validate-themes` 和
`--validate-frames` 启用。启用后会验证指定来源句、内容等级、拒绝文本和图像几何
禁项；不合格 Theme 或 Frame 进入有界重试，不会作为成功结果写入 checkpoint。
每个 Theme 必须建立可执行的
镜头策略；每个 Frame 还必须明确景别、机位方位与距离、高度、水平与俯仰角度、
镜头或焦段、透视、焦点、景深及前景框景关系。时代一致性同时约束灯具技术、
服装材料、天气、温度、裸露与身体状态；安全边界必须用可见动作表达，不得写成
合规说明。
最终提示词使用简短导演署名作为文件名，例如 `张艺谋_0001.txt`；内容等级由父目录
表示，不在文件名中重复。
详细接口见
[`docs/film-style-pipeline.md`](docs/film-style-pipeline.md)。

## 独立故事生成器

`t2i_story_pipeline` 是完全独立的极简叙事生成器。它不复用下文旧管线的
Foundation、字段化 Theme/Frame、规则或 renderer，而是从一段故事描述直接生成
彼此不同的微型故事主题，以及每个主题一至六段最终叙事提示词。它使用独立的
`runs/` 保存增量 checkpoint 和运行记录：

```bash
uv run t2i-story generate \
  "秋夜，两名三十多岁的成年人在旧车站重逢。他们确认彼此身份后一起寻找遗失的行李，气氛由警惕转为释然。湿润月台反射暖色站灯，使用平视中景和侧后方灯光。" \
  --themes 100 \
  --frames 6 \
  --female-count 1 \
  --male-count 1 \
  --content-level erotic \
  --concurrency 8
```

也可以把画面描述保存为 UTF-8 YAML Story Document，执行配置单独放在 JSON 中：

```bash
uv run t2i-story generate \
  --input recipes/motion-blur-photography.yaml \
  --themes 100 \
  --frames 6 \
  --content-level erotic
```

故事位置参数与 `--input` 必须且只能提供一个；不再支持 TXT 文件输入。
最小文档包含 `id` 和多行 `description`，还可声明 `cast`、`authoring`、
`requirements`、`modules` 和 `allocation`；只表达人物、构图、媒介和可见内容。
`--run-config story-run.json` 加载严格 JSON 执行配置，优先级为
程序默认值 < 外部 JSON < 显式 CLI 参数；数值 `0` 也能正确覆盖。
统一默认是1个 Theme、每主题6帧、中文、`aesthetic`；未被外部覆盖的人数来自视觉 `cast`。
配置本身必须合法，最终请求还必须满足视觉适用性，程序不按配方推断或修补执行参数。
例如固定100槽的目录必须显式请求100个 Theme，非默认等级也须显式选择。
`--female-count` 和 `--male-count` 可以分别约束每个主题及每帧的人数。

```yaml
id: station-reunion
description: |
  秋夜，两名成年旅人在旧车站重逢。
authoring:
  frames:
    common:
      - 每帧明确描述景别、视角和焦点。
```

外部运行配置示例：

```json
{
  "generation": {"theme_count": 12, "frames_per_theme": 3},
  "runtime": {"concurrency": 8, "theme_batch_size": 3},
  "validation": {
    "themes": {
      "mode": "report",
      "checks": [{"type": "required_text", "field": "premise", "values": ["旧车站"]}]
    },
    "frames": {
      "mode": "report",
      "checks": [{"type": "prose_length", "min_chars": 100, "max_chars": 2000}]
    }
  }
}
```

```bash
uv run t2i-story generate --input recipes/motion-blur-photography.yaml \
  --run-config story-run.json
```

质量模式支持 `off`（跳过可选检查）、`report`（记录告警但不重试）和 `enforce`
（拒绝并有界重试）；两阶段分别用 `--theme-quality-mode`、`--frame-quality-mode`
覆盖。缺省策略对两个阶段使用 `enforce`：Theme 的 `title`、`premise`、`style`
分别要求 4–48、160–520、100–360 个 Unicode 字符，Frame 正文要求 450–950
个字符（中文）；英文起始范围分别为 4–96、320–1040、200–720 和 900–1900。
每个 Theme 单独按核心人物数量扩展：超过两人后，中文 `premise`、`style` 和
Frame 上下限每人增加 60、30、100；英文增加 120、60、200。人数不完全指定时
采用已知核心人物下限，计入固定角色但不计背景人群。Theme 在通过检查后才保存并开始生成 Frame。
Frame 可选检查包括摄影文字证据、字符长度、空白分隔词数、ASCII、必含和禁止原文；它们不是模型
评审，也不保证叙事语义或摄影物理正确。配置的写作目标也会进入对应阶段的提示词；
`off` 只关闭检查与质量重试，不删除目标。`--frame-min-words` / `--frame-max-words`
和 `--frame-min-chars` / `--frame-max-chars` 可覆盖帧长度目标；
词数按空白分隔，中文通常用字符数。
运行配置只提供模式时保留缺省检查；显式提供某阶段的 `checks` 时完整替换该阶段
缺省列表。用户长度检查默认固定，CLI 显式覆盖任一字符边界也使该检查固定，
即使数字与默认值相同；不再按数值猜测配置来源。每个 Theme 的有效范围冻结后
统一用于写作目标、检查、发布及 resume。
长正文另以有效字符范围的整数中点作为建议写作目标，帮助模型规划内容；这不是
新的接受阈值，原有闭区间和重试条件不变，标题与精确长度不强制取中点。
结构与安全契约不受开关影响。
质量策略随 run 冻结；告警写入 attempts 和完整结果，CLI 分阶段显示检查状态。
批次和预算可分别用 `--theme-batch-size`、`--theme-output-tokens`、
`--frame-output-tokens` 覆盖；预算针对整个批次，实际请求受 provider 上限约束。
完整字段与示例见 [Story pipeline 文档](docs/story-pipeline.md)。

Theme 去重上下文不再反复传输所有完整正文：保留全部历史主题的标题和四维差异摘要，
加上最近两个完整 Theme；完整 checkpoint 仍用于 Frame 生成。相同摘要或相同
premise/style 组合会拒绝，同一 Theme 中完全重复的 Frame 也会拒绝；这不等于
识别所有语义重复。Frame 重试会带上所有失败槽位的问题及有界的上一版正文。
Theme 必须明确具体事件或静态视觉命题，Frame 在其人物、地点和时间边界内变化，
不能另开无关任务。肢体占用和衣物结构的静默自检属于写作要求，不冒充本地语义
或物理正确性证明，实际内容质量仍须通过真实输出抽查。
可用 `uv run t2i-story diagnostics <run-id> --format json` 查看首轮接受率、
重试、失败类别和已记录 token，用量缺失不被当作免费调用。

story 流水线的可复用作者规则使用独立的 `StoryRuleSet`，不在运行时加载
`t2i_prompt_pipeline` 的规则。Story 的通用安全契约集中在系统 `safety.rules`，
公共叙事和输出约束由 `common.rules` 负责，
三个 content-level 文件只保留等级特有的边界与可见要求；规则组织不再依赖与
另一条流水线逐字相同。story 内置规则位于
`src/t2i_story_pipeline/rule_packs/system/`，只描述通用 Theme/Frame 阶段职责、
schema、人物一致性和内容等级。媒介、版式、区域、视图、比例关系及其他特定视觉
行为由配方描述及其显式模块定义，Python 不识别具体 `recipes/*.yaml`
类型。

视觉配方位于仓库根目录的 `recipes/`，输入编译器位于 `src/t2i_story_pipeline/inputs/`：

```text
recipes/
├── multi-view.yaml
├── human-typography.yaml
├── miniature-open-composition.yaml
├── miniature-giant-encounter.yaml
├── ...                         # 48 份当前配方
├── _modules/                   # 多视图、画内文案、绢本媒介
└── _catalogs/                  # 字母表、固定姿态及有界循环槽位
```

全部配方、模块、目录和包内策略的 YAML 自然语言使用中文；字段名、ID、枚举、
文件名与真正画内文字的原文不变。中文输入规则不意味着只能生成中文；
画内文案语言也不强制整段描述使用同一种语言。

系统拥有不可变格式与安全契约，`standard-story` 命名策略拥有中国籍/中国地点的
项目缺省偏好。输入只选择需要的模块；独有创作留在 description 和对应阶段
`authoring.<stage>.common`。系统独占内容等级定义；配方只通过
`authoring.level_refinements.<level>` 细化，在该块内用 `shared`、`themes`、
`frames` 区分共同约束与阶段任务，不再保留三个分散的等级映射入口。
只编译当前等级，细化不替换系统边界；同一等级规则的重复归属会明确报错。
等级标识留在配置与冻结快照中，不重复传入模型请求。规则正文直接描述所需内容，
不使用等级自报、合规证明或服装锁定口令。人数、支撑几何、媒介及画内文字等视觉
事实保留；字数、固定句式、格式协议、检查与重写流程不属于配方。
安全由系统始终施加，不通过删除 YAML 中的重复声明来关闭。
字母/姿态由本地计划分配到 Theme 槽位，每批只发送所选项目，不让模型自行续数。
小于26个字母时使用目录明确的多样性顺序，26个时A–Z，大于26个时覆盖全部再复用。
其他已有编号规则用有界循环目录表达；条件Frame分配仅对匹配的帧数生效，
局部重试仍使用原槽位规则，不执行正文中的编号算式。
图内六区域不等于六Frame，指定组人数与固定额外角色合计最多八人。
明确需要背景人群的配方使用有界人数区间另行声明，预览展示包含背景的总人数范围，
不会为了套用主角容量而删除原有拥挤场景。

资产根默认相对输入文件，可用 `--assets-dir` 显式指定；不存在工作目录规则发现、
模块递归 include、远程资源或可执行模板。缺失、冲突和未知字段明确报错。
旧顶层文件、旧名称别名、Story 的 `--rules-dir` 与旧 authoring 数组格式已删除。
旧配方的 `generation`、`runtime`、`validation`、`policy` 即使为空也被拒绝，
不提供旧字段读取、自动迁移或按配方文件名查询的影子运行配置。
多个 Frame 始终是同一 Theme 的平行视觉方案，媒介与题材不新增 pipeline。

可以在加载模型配置前离线检查最终输入、规则来源和全部槽位：

```bash
uv run t2i-story explain --input recipes/human-typography.yaml --themes 26
```

默认输出 JSON，`--format text` 输出摘要；无效输入退出2，不创建run或调用模型。

Story 使用唯一的当前输出路径：Theme 返回不含 ID 的结构化草稿，Frame 按主题
批量返回 `<FRAME>...</FRAME>` 纯文本块，所有 ID 由程序分配。正常的
100 themes × 6 frames 在默认 Theme batch size 10 下仍为 110 次基础调用，
不增加逐帧模型调用。一个顺序 Theme producer 每保存一批主题就交付给有界
Frame queue，固定数量的 workers 与后续主题生成重叠执行；两阶段共用一个
并发上限。恢复时先排队已有主题的缺失帧，同时继续生成缺失主题。
每个 run 在首次 provider 调用前创建。每个 Theme 和每个 Frame 都会原子保存；
同一批次部分帧失败时保留成功帧，重试或进程退出后的恢复只请求缺失槽位：

```bash
uv run t2i-story runs --runs-dir runs
uv run t2i-story resume RUN_ID --runs-dir runs
```

`resolved-input.json` 冻结所选模块、目录、来源、有效运行配置与完整槽位计划，并校验其指纹。
resume 不重新读取原输入、外部JSON配置或资产；旧格式快照明确拒绝，不做迁移或回退。
`request.json`、provider/并发/retry/token/质量配置、generation attempts 和 token
usage 都随 run 保存。已完成 run 的 `resume` 是幂等的，不会再次调用 provider。
网络 timeout、transport error、429 和 5xx 默认在 provider 层额外重试两次；
空响应、schema 错误和截断输出在 generation 层分类记录并进行有界重试。截断
Theme 或 Frame batch 输出会把下一次请求预算提升到 run 冻结的 provider token 上限，并在
resume 后保持该预算。attempt
记录保存请求/接受 ID、具体 issues、耗时和 usage；Frame 重试及 resume 会带上
当前失败槽位的全部问题，以及每帧最多 2000 字符的上一版失败正文（截短会标记）。
已接受的 Frame 不会重新生成。认证错误不会盲目重试。

批量针对一个 Story Description 文件生成固定的 hardcore English 人物组合
（1男1女、2女、3女、1男2女、2男1女），每组 100 themes × 6 frames：

```bash
./scripts/generate-story-cast-matrix.sh recipes/motion-blur-photography.yaml
```

最终 TXT 默认统一写入 `prompts/YYYY-MM-DD/hardcore/`，所有可恢复 run 记录在
`runs/`。也可以把第二、第三个位置参数分别用于覆盖
prompts root 和 runs directory。
可选第四参数或 `T2I_STORY_RUN_CONFIG` 指定外部 JSON；提供后不再强制上述
100 themes / 6 frames / hardcore / English，而由 JSON 与程序默认决定，
脚本仅覆盖这五组人数。
脚本先用同一 CLI 的 `explain` 对全部五组最终请求预检；任何一组不兼容就整批退出，
没有生成调用，不默认跳过。字母表、固定双人/单人等配方不能套用这套阵容矩阵。
视觉配方的 authoring 与外部运行配置的并发、重试和质量策略分别生效。

输出按 `prompts/YYYY-MM-DD/aesthetic|erotic|hardcore/` 分类：

- 使用 `--input` 时：
  `<prompt-stem>_<content-level>_<female-count>_<male-count>_NNNN.txt`，例如
  `3-view_hardcore_1_woman_0_men_0001.txt`。`prompt-stem` 来自文档显式 `id`，
  不受 YAML 文件改名影响；女性、男性人数和四位冲突序号始终明确写出。
- 直接传入 Story Description 时：
  `<semantic-name>_<cast-slug>_NNNN.txt`，继续使用模型生成的小写英文 snake_case
  语义名称和现有 cast slug。
- 每行是一段可独立渲染的最终故事画面。

`prompts/` 中只保存最终 TXT；恢复所需的结构化 JSON 只保存在 `runs/`。

每个 Narrative Frame 只有 `frame_id` 和一段无换行的 `prose`。每帧自然点明风格、
年代、地点和当前时刻，重新完整描写所有可见人物，并将当前静态关系、环境证据、
镜头与光线融为一个通顺段落。本地始终校验 typed schema、精确数量、连续 ID 和
存储契约；可选质量检查只来自外部运行配置。系统安全指令始终加载，
但这些文本检查并不证明模型输出或生成图像的语义安全。叙事规则以整体画面是否自然、
人物空间是否成立和段落能否直接用于文生图为准，不要求固定句首或六段填表结构。
每帧必须重新交代年代、地点与当前时刻；建筑、陈设、器物、材料、服装、发型、
交通、通信、照明、社会称谓和人物用语必须符合该时代与地域。不确定时采用保守的
时代通用描述。Story Description 明确要求穿越、架空或时代错置时允许有意混搭。
服装冷暖、植物与取暖方式还必须
符合季节，光源必须符合时辰，官职、礼仪和称谓必须属于正确朝代。

独立故事分支支持 `--content-level aesthetic|erotic|hardcore`。默认
`aesthetic` 以故事和构图为主，不主动增加性内容；`erotic` 要求可见但非露骨的
成人裸露与双方主动亲密接触；`hardcore` 要求直接呈现明确的成人性行为。
通用成年、自愿、清醒、持续回应和可随时停止要求由系统安全规则施加，
不要求配方重复声明。等级特有边界仍由相应系统等级规则负责。

Provider 直接复用共享的 `OPENAI_*` 环境变量；完整说明见
[独立故事生成器](docs/story-pipeline.md)。
Story Description 未明确人物国籍时，该人物缺省为中国籍；未明确故事发生国家
或可确定国家的地点时，场景缺省位于中国。Theme premise 和每个最终 Frame 都会
明确写出人物国籍与故事发生国家。

## 独立空间提示词生成器

`t2i_spatial_pipeline` 是独立于 story 和旧 prompt pipeline 的约束求解流水线。它先
把任意语言的自然语言主题规范化为 ASCII English，再通过有界 LLM 阶段推导
Character、World、Style 和 Presentation 蓝图，最后由本地 catalog 和几何编译器
确定人物数量、姿势、接触、支撑面、肢体归属、表情与镜头。CharacterBlueprint
只为当前 cast 实际使用的 F1、F2、F3、
M1、M2 角色分别设计成年年龄、身高体重、体型比例、肤色、脸型五官、发型发色、
私密特征和体毛；PresentationBlueprint 再为这些角色分别设计协调但不同的服装、
鞋履、配饰与妆容或仪容。cast roles 和场景数量同时进入蓝图缓存键。每批可以通过
`--count` 生成 1 至 20 个相互不同的场景，并只使用二十一岁以上成年人。

覆盖状态同样按角色推导，而不是整场共用一个开关。每个角色可以独立采用
`selective_access` 或 `styled_nude`；因此同一场景可以全员裸体、全员局部穿着，
也可以混合呈现。hardcore 批次没有固定裸体数量或比例，裸体角色仍分别保留鞋履、
配饰以及妆容或仪容设计。

```bash
uv run t2i-spatial generate \
  "午夜魔王城中的奢华仪式空间，高对比暗色奇幻摄影" \
  --female-count 1 \
  --male-count 1 \
  --count 20 \
  --seed 42 \
  --prompts-dir prompts \
  --runs-dir runs/spatial
```

模块入口使用相同的显式子命令：

```bash
uv run python -m t2i_spatial_pipeline generate \
  "午夜魔王城中的奢华仪式空间，高对比暗色奇幻摄影" \
  --female-count 1 \
  --male-count 1
```

`--female-count` 和 `--male-count` 与 story 流水线采用相同的人数参数形式。
当前生成器支持 catalog 中全部 `1女0男`、`1女1男`、`1女2男`、`2女0男` 和
`3女0男` cast，以及每类全部32种 activity 和24个姿势族。完整支持集合与符号
验证元数据集中定义在 `src/t2i_spatial_pipeline/safety.py`。
相同主题和 seed 会复用内容寻址的 Creative
Blueprint 缓存；场景数量不同时会使用不同缓存。使用
`--refresh-blueprint` 可以强制重新推导。

多人审计区分正常表面接触、画面遮挡与不合理的实体穿透，不要求人物轮廓完全
分开。当前主流水线仍是 `symbolic_only`：检查姿势、肢体任务与支撑描述的一致性，
不证明三维接触、软组织形变或承重平衡。手持工具角色的站跪姿态必须与支撑一致；
双人托举占用的角色不能同时控制手持工具，但不因此占用第三人的手。
竖直抬起的腿不再计入双脚支撑；侧卧时按解剖左右区分上侧、下侧手，先保留姿势
固定的手和明确指定的握持手，再分配未指定左右的接触任务。
现有几何代理无法表达的解剖或形变情况仍属未验证，不能靠放宽碰撞阈值放行。

六种 cast 的大批量生成使用 `bulk`。省略 `--seed` 时命令会先输出新的基础 seed；
每种 cast 共享一套 CreativeBlueprint，再通过独立空间 seed 分批编译，避免为
每20条重复调用模型。每批完成后更新 `bulk-report.json`，使用相同 seed 和参数
再次执行即可续跑。续跑记录同时绑定拓扑与编译审计版本；规则变化后必须使用
新的运行目录，不迁移或混用旧批次。完成后每种 cast 发布一个聚合 TXT：

六种 cast 各自使用独立的构图语法。单人强调独立轮廓；两种双人配置分别使用
异性双轴和女性横向交错；三种三人配置分别使用前后包围三角、女皇与侧翼分层
三角、女性放射/链式构图。它们保留相同的24个基础姿势族和32项 activity，但
角色左右位置、前中后景和宏观接触轴不会再共用同一模板。

```bash
uv run t2i-spatial bulk \
  "1930年代中国原创社会讽刺，成熟的女性作家与男性大学讲师，民国电影摄影质感" \
  --count-per-category 600 \
  --runs-dir runs/spatial \
  --prompts-dir prompts
```

Provider 与其他流水线一样直接复用现有 `.env` 中的 `OPENAI_*`。至少需要设置
`OPENAI_MODEL`；API 密钥由 `OPENAI_API_KEY_ENV` 指向。最终提示词与其他流水线
一样保存到 `prompts/YYYY-MM-DD/hardcore/`，文件名包含世界语义名、内容等级、
人数和四位冲突序号。每行是一条可独立渲染的提示词。

结构化运行资料保存在 `runs/spatial/`：

- `blueprint.json`：本次采用的 CreativeBlueprint 与 token usage。
- `layers.json`：每个场景解析后的角色、环境、风格和呈现层。
- `selections.json`：pose、activity、镜头及各层指纹。
- `report.json`：最终 TXT 路径、多样性阈值和本地约束校验结果。
- `blueprint-cache/`：按主题、seed、模型配置和 schema 寻址的缓存。

空间模块拥有自己的 CLI、catalog、配置、审计与运行目录，不导入 story、旧 prompt
或 film pipeline；仅共享底层 `t2i_model_provider` 接入组件。Film 的多样性账本和
诊断思路不构成运行时依赖。独立入口为 `t2i-spatial` 或
`python -m t2i_spatial_pipeline`。

### 非露骨人物姿态参考库

#### 几何工具选型

静态几何检查采用本地 NumPy、SciPy 和 python-fcl，不需要云端模型、GPU 或
下载人体权重。FCL 负责有体积形状的碰撞查询，SciPy 负责有边界的接触求解；
人体尺寸、关节范围、接触语义和验收仍由项目明确建模，不能由库的“成功”返回值
代替。具体版本由 `uv.lock` 固定。

已比较的现成方案：

| 方案 | 本项目取舍 |
|---|---|
| [python-fcl](https://github.com/BerkeleyAutomation/python-fcl) + [SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) | 采用；适合显式逐对检查和静态接触求解，两者使用 BSD 许可证 |
| [MuJoCo](https://github.com/google-deepmind/mujoco) | 提供运动学和 Apache-2.0 人形模型，但默认碰撞过滤不能直接作为完整自碰撞验收 |
| [Drake](https://drake.mit.edu/) | 有成熟的约束逆运动学；对当前有限姿势目录而言引入的模型和求解设施较重 |
| [MyoSim](https://github.com/MyoHub/myo_sim) | 有 Apache-2.0 解剖模型，但仍需编写具体接触规则，不是现成的姿势有效性判定器 |

这里使用自建的简化人体代理，不复制上述人体资产。几何通过仅适用于这个代理及
其显式参数，不代表医学安全、衣物不穿插、动态平衡或最终生成图像已经正确。

#### 姿态定义与几何验收

`t2i-spatial poses` 是空间模块内的独立离线工具，用于全身着装、成年人物的日常
造型和美术参考。它不调用模型、不依赖 story/film，不组合 activity，也不修改
`generate`/`bulk` 原有的成人活动 catalog。两者用途不同：原有24族目录继续服务
既有生成命令；这里提供的是新增的非露骨参考配方，不是该目录的兼容层或替代入口。

当前参考库为 **16 个姿态族 × 3 个完整配方 = 48 个姿态**：

- 站立：平行站姿、偏重心站姿、前后错步、靠墙、扶桌、单脚踏台阶、交流手势。
- 坐姿：端坐、前倾坐、靠背坐、侧向坐、垫上屈膝坐。
- 低位：直身跪姿、单膝跪姿、手部辅助蹲姿、侧卧休息。

配方显式定义身体高度、脊柱状态、骨盆与胸口朝向、头部相对胸口的朝向、轮廓、
重心偏向、侧卧的下侧、腿部排列、左右手职责、视线和支撑接触。
骨盆、胸口与机位使用固定房间方向；左右肢体和支撑物相对位置使用人物自身的
解剖方向；留白使用画面方向，视线相对头部描述，不再把这些参照混用。
`balance_bias` 只表示左右偏重，不列承重部位；全部承重及轻触描述直接来自
`supports`，不再维护独立的 `weight_distribution`。扶桌/辅助蹲姿的双手版本
明确保留两手承重。直身跪姿采用膝部与鞋头接触垫面、脚跟抬起的配置，不强行
要求单块脚模型在超出踝关节范围时仍把脚背压平。垫坐采用骨盆及双脚落垫、
双膝屈起的定义；侧卧有独立头垫，下侧手掌放到躯干前方，肘部离垫留空，
不把手臂压在身体下又要求它可见。跨前臂接触时，另一只手可明确放在身体前方，
不能仍描述为垂在体侧却要求对侧手够到它。

不做腿部/手臂的无条件笛卡尔组合。加载时校验承重、左右膝足归属、台阶/地面
支撑、手的接触与手势冲突、躯干与靠背冲突、头部对齐、支撑位置、结构去重和
镜头引用。侧卧只接受稍高且兼顾支撑的机位；头部已向外转时排除脸背向机位的
方向组合。这层离散规则之后还必须通过独立的三维几何检查，不能替代它。

`t2i_pose_geometry` 是独立内核，不导入任何 pipeline 或 provider：

- 固定骨长的正向运动学从关节角计算世界坐标；单位为米，世界轴为右/前/上。
- 胶囊体、椭球及有方向的盒体表示肢段、躯干、头和手脚；家具包含实体厚度。
- 有界双骨段解析候选覆盖不同肘部方向和掌面方向，必要时再用有边界的局部
  数值求解；候选数量和求解次数有限，不保证为任意约束找到解。
- 独立检查关节范围、指定接触面的边界及法线、自碰撞、人与家具及多个人体
  之间的碰撞。声明接触不会豁免碰撞；相邻肢段也不整对跳过，只允许内核定义
  的局部关节连接重叠。
- 优化器收敛不等于通过。候选在几何检查失败后不能渲染为参考提示词，也不能
  通过缩短骨长、缩小身体或放宽容差自动补救。

参考人物的 `body_scale` 是显式编写的合成人体比例，不根据年龄、性别或外貌
推断。均匀缩放可从参考解按相似变换产生候选，但每个尺寸实例都重新计算和
检查几何，不能复用另一个体型的通过结论。非均匀尺寸可通过内核 API 单独定义
并检查；当前参考人物预设只使用均匀缩放。

这些检查验证的是简化刚体代理，不是医学安全、软组织或衣物碰撞、手指细节、
受力平衡或舒适度。原有 `generate`/`bulk` 和 film 的自由文本输出没有因此
自动获得三维认证，最终图像仍须单独检查。

#### 显式多人场景的三维审计

内核的 `solve_scene` 会在同一次有界优化中求解全部人物的接触，而不是逐人移动
后复用旧的目标坐标。每次迭代重新计算所有身体接触的两端；人体尺寸、骨长、
家具和接触定义保持不变。最终独立重建全部碰撞体，连未参与接触的第三人也检查。
接触误差收敛但发生实体穿透的候选不能通过；搜索失败也不等于证明姿势不可能。

```bash
uv run t2i-spatial audit-geometry scene-request.json \
  --output scene-evidence.json --preview scene-geometry.svg
```

输入采用 `t2i_pose_geometry.SceneSolveRequest` 的当前 JSON 格式：`scene`
包含所有人物的 `ActorPose`、实体家具、支撑面接触和人体表面接触；
`variables_by_actor` 必须列出每个人，空数组表示固定，非空数组使用
`root_position`、`root_z`、`torso_yaw` 等已有求解变量。没有接触约束的可动角色、
未知部位和未知家具会明确报错，不替换为默认接触点。`max_nfev`、移动边界及
`tolerances` 也随输入和求解结果保存。SVG 按相同容差重新验收；失败候选同样输出
诊断资料，并以非零状态退出。

这个命令只验收显式给出的静态代理场景。原有活动目录尚无完整的多人三维姿态、
家具尺寸和接触端点映射，不能把目录标签自动转换成上述输入，也不能用一个
中性示例的通过结论为目录组合背书。未建模的解剖结构与形变保持未验证状态。

参考库还包含 **5 套完整摄影配方、4 个成年人物档案和5套环境视觉配方**：
摄影配方把镜头类型、透视、拍摄空间需求、焦点、景深、留白和前景关系作为
一致的组合，不独立随机拼接焦距与距离。所有配方保留全身构图、脸和关键
手部及可见支撑边界的可读性，前景框景不得遮住身体轮廓；不为面向镜头而改变
姿态。允许交叠腿部及接触底面的自然遮挡，不要求全部手脚和接触面都无遮挡。
要求表情细节时保留面部补光，不以“对焦清楚”代替照明。
人物的年龄、外观和完整不透视着装在同批次内固定，且每条描述独立完整重述。
人物文字一致不等于渲染身份已得到保证。
摄影兼容性仍是定性视角筛选，不是经过标定的相机遮挡或光学求解。

环境配方分别声明地点、色彩、可见光源及光线处理、成片质感、拍摄空间和真实
支撑物。每个 surface 必须映射到具体物体，并声明高度档位、接触空间和水平/
垂直朝向；`support_layout` 指定它相对身体的位置。扶桌使用髋高、可容纳双掌
及前臂的水平面，并置于身体前方前臂可及的位置；台阶低于站姿膝部并容纳整脚；
座面位于坐姿膝高，头垫位于垫上并使头颈对齐。高度、面积或方向不符合配方的
物体，即使名称正确，也不能用于该姿态。档位先筛选环境，再根据人体和姿态
落实具体家具尺寸、位置和接触坐标。当前是标准化家具配方，不能把通过结论
套到任意现实桌椅。同一把椅子的座面与靠背必须属于同一个 object；头垫
必须与地垫同时提供。较长拍摄距离只在扩展空间环境中使用。`poses list`
同时列出摄影、人物和环境 ID 及完整定义。

```bash
# 列出完整类型化目录，或仅列出一个姿态族
uv run t2i-spatial poses list
uv run t2i-spatial poses list --family half_kneeling

# 按 seed 选取16个姿态，输出结构、参考描述和统计
uv run t2i-spatial poses sample --count 16 --seed 42

# 指定同批人物与环境；只从该环境能实现的姿态和镜头中选择
uv run t2i-spatial poses sample --count 16 --seed 42 \
  --subject mara --presentation daylight_atelier

# 导出每行一条的着装人物参考描述；目标文件必须不存在
uv run t2i-spatial poses sample --count 16 --seed 42 \
  --format text --output runs/spatial/pose-references/sample.txt

# 检查结构覆盖和所有兼容姿态/摄影/环境组合的描述编译
uv run python -m t2i_spatial_pipeline poses audit

# 导出正面/侧面/俯视的几何诊断 SVG，不是 AI 出图
uv run t2i-spatial poses preview table_supported_both \
  --subject mara --presentation daylight_atelier \
  --output runs/spatial/pose-references/table.svg
```

采样先固定人物并求解/检查候选几何，再依次优先选择当前批次使用最少的姿态族、
历史使用次数较少的姿态，以及
“与已选姿态的最小结构距离”最大的配方；seed 决定同分时的稳定顺序。
不筛选环境时，16条每族各一条，完整库最多可取48条；`--family` 筛选后最多
3条，超量会报错，不重复凑数。指定 `--presentation` 会先过滤支撑或拍摄空间
不兼容的姿态/镜头，数量上限与可覆盖姿态族随之缩小。几何不合格的候选会拒绝，
原因保存在 `geometry_rejections`，CLI 同时通知；剩余有效数量不足时明确报错，
不重复凑数，也不退回未经检查的文本版本。
姿态选定后，从兼容的摄影/环境组合中依次优先选择历史组合重复少、环境使用
少、镜头使用少的方案。摄影和环境变化不计作新增姿势。

结构距离是8组字段的等权不同比例：身体高度、脊柱、骨盆/胸口/头部朝向、
轮廓、重心偏向/侧卧下侧、腿部、
左右手配置和支撑接触集合。ID、姿态族名称、视线和镜头不参与距离计算。
这只是确定性的结构选择启发式，不是感知相似度或经过标定的视觉质量分数。
JSON 报告包含族/高度/脊柱/重心偏向覆盖、声明的承重接触次数、场景对数、最小和平均结构距离；
以及摄影、环境、人物覆盖次数、已在历史中出现的姿态数和完整组合数。单场景
没有场景对，距离为 `null`，不伪造“完全不同”的分数。

每个场景还包含 `geometry`（体型、关节角、实体与接触约束）、
`geometry_joints`（世界坐标）、`geometry_report` 和 `geometry_tolerances`。
加载场景时会检查这些数据是否仍与当前配方、正向运动学及验收结果一致，不能
把通过报告或关节坐标替换成另一份数据。几何对象使用规范 surface ID；环境
中的同名 surface 映射提供对应的具体器物描述。数值容差不是实际人体的测量精度。

跨批次历史使用**不可变 JSON 快照链**，不维护会被并发命令覆盖的全局计数文件：

```bash
uv run t2i-spatial poses sample --count 16 --seed 42 \
  --output runs/spatial/pose-references/first.json
uv run t2i-spatial poses sample --count 16 --seed 42 \
  --history runs/spatial/pose-references/first.json \
  --output runs/spatial/pose-references/second.json
```

后一批从前一批的 `history_after` 继续，并记录自己的 `history_before` 与
`history_after`；前一批文件不会被修改。默认沿用前一批人物，显式 `--subject`
可以为新批次更换人物。相同 seed、目录定义、历史快照、人物和筛选参数得到
相同结果；历史改变时，相同 seed 可以有不同选择。在全部48个配方均通过当前
体型检查且没有额外筛选时，连续取三批16条，每批每族一条，先用完48个姿态，
再重复使用。姿态用尽后仍会尽量选用较少使用
的摄影/环境组合，但不承诺无限不重复。

计数按 pose、camera、presentation 和三者组合保存，不把新 scene ID 或换人物
算成新的几何/摄影/环境组合。JSON 同时记录目录指纹、筛选参数、算法及 renderer
版本；目录、摄影、人物、环境、几何内核或数值依赖版本变更时拒绝使用不匹配
的历史，不静默重置。
传入同一个历史文件的多次命令是独立分支；要连续累计，应传入最新批次的 JSON。
文本导出不含历史快照，不能作为 `--history`。

`list`、`sample`、`audit` 均可通过 `--output` 保存 JSON；`sample --format text`
输出一行一条的英文参考描述，固定为全身、非露骨、日常不透视着装。目标文件
已存在时拒绝覆盖。当前参考库和批次 schema 为 `4.0`，采样算法标识为
`geometry_gated_family_maximin_v4`，renderer 版本为4；不兼容或迁移旧 schema。
姿态定义位于 `src/t2i_spatial_pipeline/pose_reference_catalog.py`，视觉配方位于
`src/t2i_spatial_pipeline/pose_reference_presentation.py`，不维护第二份打包 JSON。
`poses audit` 输出目录指纹、姿态统计、摄影/人物/环境数量、兼容组合数量、
几何检查数量、容差及拒绝原因。它会检查每个兼容组合和人物的几何，再编译并
校验描述；出现几何拒绝时以非零状态退出。外层 `evidence` 同时声明静态代理
几何与结构证据，内部 `pose_report` 的距离和覆盖统计仍只属于符号结构证据。
`poses preview` 重新验证具体场景，绘制实际碰撞体、关节和接触点的三视图，
并标红失败部位；无效候选可以作为失败诊断导出，但命令返回非零且不能用于
参考描述生成。它不是人体渲染器或出图验收工具。
目录和报告显式保留 `physical_validation: false`、`visual_validation: false`
及 `requires_render_review: true`；通过的 `geometry_report` 只证明当前静态
代理满足明确的关节/接触/碰撞规则，不代表完整物理验证。当前模块没有图像
生成接口；需要将导出的
参考描述送入实际图像生成流程，再检查关节、承重、遮挡和面部可读性，不能用
编译成功或测试数量替代这一步。

### 原有生成目录的离线审计

姿势 catalog 和场景分配器可以完全在本地审核，不读取模型配置，也不调用 LLM：

```bash
uv run t2i-spatial audit \
  --seed-count 100 \
  --count 20 \
  --runs-dir runs/spatial
```

审核先比较六份打包 JSON 与代码生成的 catalog 定义，按解析后的完整数据比较，
不受 JSON 缩进影响；定义漂移或进程内 catalog 缓存过期会显式报错，不自动改写
目录。然后穷举检查所有保留的 pose/activity 拓扑，对全部六种 cast 运行连续随机
种子的场景分配压力测试。每个 seed 用相同参数分配两次并验证结果完全一致，
再编译、复核每条抽样几何 Prompt。只有整组检查成功才将该 seed 的计数和结构
统计一并原子保存到
`runs/spatial/audit-progress.json`；命令中断后使用相同参数再次执行即可从下一个
未完成 seed 继续，不会重复累计已完成样本。checkpoint 同时绑定打包 catalog
内容、代码生成的定义、拓扑规则、Prompt 审核规则、分配算法版本和显式安全策略
版本。当前审计 schema 为 `1.3`，旧 schema 不迁移；参数、规则或 catalog 改变时
也会拒绝误续跑。确认变更后显式传入 `--restart` 开始新的审核。

每种 cast 的审计结果包括 `catalog_matches_definition`、`definition_hash`、
`reproducibility_checks` 和 `structural_diagnostics`。结构诊断累计报告姿势条目、
姿势结构、宏观结构、完整选择的重复，以及姿势族、身体高度、躯干/骨盆方向、
支撑面、机位和景别的使用次数。宏观结构指纹由 catalog 中的身体高度、躯干/骨盆
方向、支撑面/支撑点和人物布局构成；姿势结构还包含腿部、手臂配置和肢体职责。
条目名称、scene ID 和支撑点列举顺序不算结构差异。完整选择的重复按 cast、
family、variant、activity、viewpoint 和 shot scale 统计，不把新 scene ID
视为新选择。

`within_batch_pairs` 和 `same_macro_structure_pairs` 仅累计每个 seed 批次内部
的场景对，不计算跨批次两两距离；`minimum_distinct_macro_structures` 记录单批
最少覆盖的宏观结构数。跨批次重复通过累计的 coverage 和
`exact_selection_repeats` 查看。同 seed 重放仅用于检查，不重复计入样本。
这些统计固定标记为 `symbolic_structure_only`、`visual_validation: false`：
它们不计算文本相似度、图像感知距离或主观视觉质量，也没有未经验证的“多样性
达标”阈值，不改变现有生成选择器。

Spatial 的 `passed: true` 只表示 schema、catalog、接触端点、支撑和 Prompt
一致性通过本地符号审核。输出中的 `validation_status` 固定为 `symbolic_only`，
`visual_validation` 固定为 `false`，且 `requires_render_review` 为 `true`。
它不证明真实图片人数、脸、躯干、手脚或接触方向正确。全部 activity 和姿势族
虽然都可生成，但复杂构图仍必须实际渲染并经过人工或图像姿态检测；不得把本地
audit 结果当作视觉验收。

这个工具把文生图内容分成共享 Foundation 和两层具体画面事实：

- `StyleConstraints`：保存 brief 明示且逐字复制的作品或虚构世界、导演、艺术家、
  流派与风格、媒介、技法、时代和地域 reference phrase。
- `CastPlan`：从 brief 解析出的共享人物名册，只保存人物顺序、性别和明确身份，
  以及 brief 明示的人物姓名，不保存外貌或服饰。只有作品名时不会猜测角色。
- `Theme`：多个 Frame 共用的最小稳定视觉上下文，只保存结构化 `Setting`
  （明确时间、具体地点、固定元素、候选光源、背景人口与视觉氛围）、
  `StoryPlan`（单一即时目标、可见触发与可见结果）、人物稳定外貌和基础服饰。
- `Frame`：当前非入画摄影参数、结构化景深与光线，以及人物可见外观、受光、表情和动作。

每个事实只有一个所有者。作品或虚构世界、导演、艺术家和风格名称由 Foundation
逐字保存，例如“笑傲江湖的武侠世界”，并进入每条最终 Prompt；不把它们改写成长篇
社会背景。Theme 从 brief 推导稳定时间和具体地点：若 brief 只给作品世界或题材，
使用可信时期并把地点落实为可见物理场所。renderer 只按固定顺序展开这些事实。
人物稳定事实用于生成 Frame；Theme 的候选光源列表不展开，最终只写本帧实际光源。
若 Cast Plan 含 brief 明示的 `display_name`，renderer 使用姓名作为人物标签；否则
按性别和出现顺序使用 `女1/男1` 或 `Woman 1/Man 1`。姓名只影响显示，Theme 和
Frame 内部仍以稳定 Character ID 关联人物。

`StyleConstraints.required_phrases` 不解释风格，也不补写 brief 没有提到的时代、
地域、媒介或视觉特征。创作者与紧邻的作品名保存为一个自然 reference，并可插入
准确的作品类型关系词，例如“张爱玲小说《沉香屑·第一炉香》”；其他内容保持原文。
renderer 直接展开 `PromptBook.style_constraints` 中的 reference，
不额外添加“实拍摄影”等媒介或风格前缀；Theme 不再重复保存或改写风格。

## 生成流程

一次 run 有三类模型调用：

1. 一次 `Foundation` 调用生成共享 `StyleConstraints`、`CastPlan` 和语义文件名。
2. `Theme` 按小批次生成，默认每批 5 个，并生成各自的结构化 `setting`、
  `story_plan` 与稳定人物事实。
3. 所有 `Theme` 完整生成后才执行可选的全量相似度审计；未齐时不会提前生成任何
  `Frame`。每一行最终 Prompt 都展开 reference phrase、所属 Theme 的时间与地点。
4. 所有 `Theme` 通过审计后，每个 `Theme` 一次 Frame 调用，生成该主题当前缺失
  的全部 `Frame`。

因此 5 个主题、每个主题 5 个镜头的基础调用数是 7 次；100 个主题、
每个主题 6 个镜头、Theme batch size 为 5 时，基础调用数是 121 次。
Theme 变化计划按 ID 稳定规划场景空间、材质、人群、氛围，以及各人物的发型、
整体配色，以及各人物的发型、服装颜色材质、鞋履和配饰；Frame 视觉计划稳定规划
景别、机位、人物空间编排、身体动态、景深、实际光源与光位；每个 Frame 槽位
还携带 story requirement，要求落实所属 Theme 的同一故事计划。
各轴先覆盖十个明显不同的方向，后续轮次重新交叉组合，不会每十项原样重复；
鱼眼等强风格镜头保持低频。
两类计划都复用原有调用，不增加模型调用次数。Frame 请求不再重复发送全局风格
摘要，最终 prompt 也不再叠加全局 anchor，因此还能减少重复输入和输出 token。

管线只检查人数约束、数量、ID、CastPlan 对应关系和人物引用。没有 Outline 状态链、
critic 或语义 repair。
每个 Foundation、Theme 和 Frame 成功后立即原子保存；结构错误、输出截断
或数量不足时，只重新请求当前缺失 ID。批次中若只有部分对象通过本地 schema
校验，系统会立即保存这些有效对象，不向模型发起 repair；下一次只请求无效或
缺失的 ID。只要一个完整补全 pass 新增了 checkpoint，流水线就会自动继续下一
pass；只有整轮零进展时才返回可 resume 的未完成错误。checkpoint 写入失败会立即
停止并发调用，避免继续产生无法持久化的付费结果。最终提示词仍只在全部完成后发布。

每次模型调用都会追加记录到 run 的 `attempts.jsonl`，包含 stage、请求与接受的
ID、outcome、校验问题、耗时、token usage 和输出预算。Theme embedding 审计也以
独立的 `theme_similarity` stage 记录 usage，并用 operation ID 防止 resume 重复记账。该日志同时让后续 pass
或进程重启后的 resume 继续向模型提供最近一次相关校验反馈，而不是重新从空白
重试。

模型创作规则由 `authoring_rules.py` 这个深 module 统一加载和编译，template
只负责组装请求数据。系统规则位于：

```text
src/t2i_prompt_pipeline/rule_packs/system/
├── common.rules
├── foundation.rules
├── themes.rules
├── frames.rules
├── content_levels/
│   ├── aesthetic.rules
│   ├── erotic.rules
│   └── hardcore.rules
└── frame_modes/
    ├── sequential.rules
    └── variations.rules
```

规则格式刻意保持简单：UTF-8 文件中的每个非空、非注释行就是一条完整中文
instruction；去除前导空格后以 `#` 开头的行是注释。没有 TOML/YAML、
priority、replace、disable、模板变量或条件 DSL，行顺序就是规则顺序。

规则只从上述包内系统目录加载，不发现工作目录文件，也没有用户规则覆盖入口。
每个阶段按以下固定顺序编译：

1. 系统 common、stage、当前 content level，以及 Frame 的当前 mode；
2. 运行时生成的输出语言要求，以及 Theme 的无名人物标签要求。

因此每次只把当前选择的 content level 和 frame mode 发送给模型，不会发送另外
两套等级，既避免规则冲突，也减少输入 token。当前系统规则要求：

- 创作先保留 brief 明示事实与 stage ownership，再满足单帧物理和可见性，之后才
  满足叙事可读性，之后才追求差异与装饰细节。规则中的条件示例不会给其他 brief
  添加地点或服饰限制；
- 先为全部请求 ID 生成最简有效候选，再补可选细节；优先简化画面，确实无法形成
  有效候选时才省略该 ID。Theme 的 `setting` 分别保存地点、固定布景与设备、
  可用光源和背景人口约束；Frame 的 action
  用一个短句（中文45字或英文25词）；Frame 以结构化 lighting 明确光源、
  光位、光色和场景明暗，并为每个人物分别描述亮部与阴影；
  这些是指令侧长度要求，不做运行时截断，brief 必需事实、人物、路线
  与因果信息仍须完整保留；
- Frame 指令包含通过当前 schema 验证的完整短输出示例，示范所有人物以躯干或
  身体主体入画；示例只用于学习写法，实际 ID、场景与动作来自当前请求，检查过程
  不写入生成字段；
- 美学级仍要求至少两项可见形体表达；brief 固定服饰或日常活动时，通过相容的
  姿态与光影满足下限，不改变原服饰或活动；原有成年、互动及尺度上限保持不变；
- 使用自然、流利、简练且语言一致的描述，返回前消除病句和残句；中文自然语言
  字段只允许保留 brief 原文中的外文姓名和专有术语，其他英文混入会触发当前对象
  重试；英文输出同样拒绝 brief 未明示的中文混入；
- StyleConstraints 只逐字提取 brief 明示的视觉、时代和地域短语，不翻译、改写、
  总结或推断；brief 没有时代线索时不会默认补写“当代”，也不会根据创作者姓名
  固定一套所谓代表性配色、构图或年代；
- CastPlan 忠实保留 brief 明确写出的人物和身份；`role` 必须能在 brief 中找到
  明确身份原词，无身份原词时使用 JSON null，不能根据地点、任务或道具猜测职业；
  可选 CLI 人数只补足 brief
  没有明确的性别或人数，不能覆盖 brief，也不授权创造职业；
- Theme 不保存 title 或 style；全局媒介和 brief 风格原词由 Foundation 拥有并由
  renderer 确定性展开。Theme 拥有稳定外貌和完整穿戴：
  appearance 明确发型、脸型及至少两项眉眼、鼻唇、肤色、颧骨或下颌特征；outfit 明确合乎
  场景的上下装或连体装、鞋、关键材质及零至一件配饰。每个未固定项
  选择一个具体值而不是列出备选，并在不同 Theme 间形成协调变化；brief 明示的数量、
  否定、服饰类型与遮盖、颜色和材质必须直接写出，其中服饰修饰原词复制到 outfit，
  不能用常识或材质暗示替代。`setting.location` 保留地点关系；
  `fixed_elements` 保存固定布景、设备与关键道具；`available_light_sources`
  只列现场存在的固定光源；`background_population` 只保存非名册背景人物约束；
  `atmosphere` 用色温、明暗或人群密度加一个情绪词表达稳定视觉氛围。
  `story_plan` 保存所有 Frame 共用的单一即时目标、可见触发和动作造成的可见结果；
  brief 没有动作时只推导不改变人物身份或背景事实的现场微型目标。它是 Frame 的
  生成计划，不作为解释性 prose 直接进入最终 Prompt。
  Theme 不写人物位置、动作、持握、构图或受光，也不会在首个 Frame 前提前完成
  brief 中的寻找、发现或取得等目标；
- 本地 contract 保护 schema、ID、人物集合与引用、framing 联动，以及头部入画时
  对脸型和至少两项面部特征的覆盖，
  required_phrases、路线、输出语言、结构化残片和内部字段泄漏等确定性约束；
  开放式自然语言质量仍由生成规则负责，不使用宽泛质量词表打分；
- 基础服饰必须同时符合 brief 明示的时代地域和 scene 的地点、场合、季节与天气；
  道具、器物、家具、照明、载具、建筑构件和织物都要写出该时代的具体形制与材质，
  例如写“陶油灯”“木格窗”“麻布直裾”而不是“灯”“窗”“衣服”，避免笼统名词
  被文生图模型默认渲染成当代工业制品；时代早于当代时不得出现电灯、塑料、拉链、
  机制印刷品、机动车等该时代不存在的物件，Frame 的 environment 也沿用同一时代形制；
- 同一批 Theme 必须形成不同的完整方案，不能复制 setting 和稳定人物事实后只
  替换颜色；差异只来自 brief 未固定的布局、布景、障碍、路线、发型、服装轮廓、
  鞋履和配饰，不能移动
  brief 已指定的起点、核心物体、目标地点或其他不变量；涉及楼层或高度变化时，
  setting 必须提供能承载人物和核心物体的可执行垂直路线；brief 指定多个连续地点时，
  每个 Theme 都包含全部地点及连接关系，并由自己的 Frames 独立完成整条故事线，
  不能把不同 Theme 当成同一故事的连续章节；相似度反馈要求新方案时，也只调整
  brief 未固定的部分；
- Frame 是可独立渲染的当前画面，不引用 Frame ID 或前序帧元叙事；contract 会拒绝
  action 中的“不可见”“出画”“画外”和明确跨 Frame 引用，但不对一般自然语言做
  视觉质量词法评分；
- 每个 Frame 以正在发生的动作、明确对象和可见反馈形成可辨认的故事瞬间。
  variations 的每个候选独立落实同一 `story_plan`，只改变决定性瞬间与视觉组织；
  sequential 则从可见触发逐帧推进到可见结果。单纯站立、凝视、摆姿或无状态变化
  的轻触不能替代故事动作；
- Frame 不再生成自由文本 `camera.composition` 或通用 `details`。每个人分别拥有
  `framing`、`placement`、`facing`、可见外观、受光、表情与动作；相机拥有
  结构化 `lens_profile`、`shot_scale`、`height`、`direction`、
  `depth_of_field` 和 `lighting`。这些字段只描述画面外的拍摄方式，不代表场景中
  存在相机或镜头；只有 brief 明确要求摄影器材入画时，器材才属于 setting 或 action。
  renderer 按人物 ID 确定性合成统一构图并替换为
  女1、男1等显示名，因此人物身份、位置和入画范围不会由两套自由文本分别描述；
- Frame 的现有字段需要覆盖取景与透视、景深与焦点、视觉重点、人物调度、
  前中后景、姿态与视线，以及当前环境光效和道具状态；只写与画面相关的信息，
  不机械罗列摄影术语。`depth_of_field` 明确 shallow、moderate 或 deep、对焦目标
  和背景呈现；承担核心互动或故事推进的道具必须已经存在于
  `Theme.setting.fixed_elements` 或人物稳定服饰配件中，Frame 不临时发明新的核心道具；
- Frame 按 Theme 顺序包含全部人物，并选择能容纳所有人身体主体的景别。`framing`
  只允许头部与躯干、全身或裁头躯干三种值，不提供局部肢体选项；裁头时 expression
  必须为 null，其他取景必须提供表情；中景和特写不得使用全身 framing，`facing`
  必须是以明确朝向动词开头并指向人物 ID 或镜头的完整短语。执行核心动作时，
  action 直接写出 brief 对动作、工具、对象、颜色、
  图案、数量和结果的修饰；手部默认一个主要任务，身体和容器内部细节均服从实际取景；
- 不使用单独的手、腿、脚代替人物；允许有明确躯干和姿态的无头裁切。variations
  的人物和锚点焦点仍让全部人物以身体主体入画，只用已有工具，不额外要求记录工具；每个候选
  独立呈现 brief 的全部可视事实，核心动作的工具、对象、颜色、图案、数量和结果
  不能拆散到其他 Frame；
- brief 的空间关系需要由实际活动位置体现，而不只是背景里出现相关物体；服饰
  材质要求同时约束 Frame 的光照与可见外观，不透明衣料不因逆光描写而变为透明。
  Theme 的 appearance 只写稳定形态，当前眼神、表情与朝向留给 Frame；
- sequential 镜头围绕 brief 的核心行动或关键道具形成可见推进，人物与道具状态
  只能通过画面内成立的动作改变；最后一个 Frame 必须在 brief 核心动词的语义
  上限内呈现可见终态，例如“检查”不能升级为“修复”，“寻找”不能升级为
  “取得”；起终点存在高度差时，中间镜头必须呈现垂直通过过程，终帧必须给出
  到达目标高度的空间证据；
- 单一镜头下的相机、朝向、姿态、关节、支撑、遮挡、深度与接触必须在物理上
  同时成立，只描述该视角真正可见的部位。

## 安装

```bash
cp .env.example .env
uv sync --extra dev
```

至少设置：

```dotenv
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

## 使用

```bash
uv run t2i-prompts generate \
  "一名成年女性和一名成年男性在酒店大堂重逢" \
  --theme-count 5 \
  --frames-per-theme 5 \
  --content-level aesthetic \
  --frame-mode sequential \
  --output-language chinese \
  --concurrency 8 \
  --theme-batch-size 5 \
  --generation-retries 2 \
  --runs-dir runs \
  --prompts-dir prompts
```

`--frame-mode variations` 会让同一主题的镜头成为互不依赖的完整候选画面。
每个候选仍继承相同的 Theme 稳定事实并保留 brief 核心活动，优先改变焦段、景别、
机位、方向和构图，再选择自然姿态。差异是满足明确约束后的目标，不以改变核心活动
或复杂手势凑足。五个或更多候选尽可能覆盖超广角、广角、标准、长焦和少量鱼眼，
以及多种取景范围与机位。
本地会按 Theme ID 生成并轮换一个很小的
`frame_visual_plan`，随原有 Frame 请求指定每个 ID 的摄影与光线参数，不增加模型调用，
避免所有 Theme 都从相同广角槽位开始；每帧必须明确写出 brief 的视觉锚点，也不
使用没有实际相机、笔记本或工具的“虚握”动作制造伪变化。

### 五组人物矩阵

交互式脚本接收一个不含人数的共享 brief，然后依次生成一女、两女、三女、
一女一男、两女一男五组提示词。每组固定为 100 个 Theme、每个 Theme 6 个连续
Frame。未指定 content level 时依次运行 `erotic` 和 `hardcore`，共生成 10 个
run 和 6,000 条提示词：

```bash
./scripts/generate-cast-matrix.sh
```

也可以直接传入 brief，并使用相同的双尺度默认值：

```bash
./scripts/generate-cast-matrix.sh \
  "盛唐河西敦煌壁画启发的现实乐舞电影摄影"
```

第二个参数显式指定 `aesthetic`、`erotic` 或 `hardcore` 时只运行该尺度，共生成
5 个 run 和 3,000 条提示词。
脚本会为每组 brief 补充明确成年的人物配置，因此共享 brief 不应自行指定人数。
批次状态按 brief、content level 和规则自动写入 `runs/cast-matrix-*.json`。
单次生成暂时没有进展时会在批次预算内自动继续同一 run；Theme 相似度重生成耗尽时
会在预算内建立替代 run。中断后执行相同命令会验证并跳过已有提示词，只继续未完成
的组。预算耗尽会明确暂停，不会无限续跑或无限创建替代 run。

### 安全先锋艺术固定批次

以下命令按 24 位先锋艺术家逐一生成三种明确成年群像配置：一女一男、
两女一男和三女。每种配置固定生成 100 个 Theme，每个 Theme 生成 6 个
独立变化 Frame，共 72 个 run 和 43,200 个 Frame：

```bash
uv run t2i-prompts generate-safe-avant-garde
```

该命令固定使用 `aesthetic` 和 `variations`；任务 brief 要求所有人物 25 岁以上、
全程穿着不透明且完整覆盖的服装，不生成裸露、性行为或性化接触。
批次进度默认写入 `runs/safe-avant-garde-batch.json`；命令中断后执行同一
命令，会跳过已完成任务并通过现有 run checkpoint 继续当前任务。

### 共享批次执行与预算

两种批次共用 `batch.py` 的执行、持久化、完成校验和预算逻辑，任务定义只保留各自
的人物与主题配置。人物矩阵在预算内自动续跑并替换相似度耗尽的 run；安全先锋艺术
批次仍在一次 run 未完成时暂停，等待用户再次执行同一批次命令。

新批次默认限制：

- 每个任务最多 10 次 run 执行尝试，包含首次执行、手动恢复、自动续跑和替代 run；
- 每个任务最多 2 个替代 run，仅人物矩阵的自动恢复策略使用；
- 从批次创建起最多 86,400 秒，包含重试等待、进程中断和离线时间。

这些是 **run 执行次数与总时间预算，不是精确的模型请求数、token 或金额上限**。
一次 run 尝试内部仍使用已有阶段重试与并发设置。超时会取消本批次正在等待的任务，
但不能保证供应商停止处理或不计费；已成功写入的 checkpoint 会保留。

预算和累计尝试在模型调用前保存，重新启动不能清零。省略预算参数时保留已保存的
上限；需要继续耗尽的批次时，可显式提高相应上限，其他预算保持不变：

```bash
uv run t2i-prompts generate-cast-matrix "共享视觉 brief" \
  --content-level aesthetic \
  --batch-max-attempts 15 \
  --batch-max-replacements 3 \
  --batch-timeout-seconds 172800
```

`generate-safe-avant-garde` 同样支持 `--batch-max-attempts` 和
`--batch-timeout-seconds`。上限只能提高，不能重置计数；改变 brief、规则、恢复
策略或批次目录会明确报错。已有 run 使用冻结的运行设置，新建替代 run 和尚未开始
的任务也沿用批次最初的设置。

批次状态采用统一的 `bounded-batch-v1` 格式，保存所有历史 run ID、累计尝试、
创建时间、预算和暂停原因；不读取或迁移旧的专用批次状态格式，也不覆盖旧文件。
状态文件和 run checkpoint 使用相同的原子替换及文件、目录 fsync。执行期间持有
状态文件旁的 `.lock` 排他锁，第二个进程不能同时执行同一批次。锁文件保留在磁盘，
进程退出后系统释放锁，不需要删除锁文件。该锁不限制用户单独执行 `resume RUN_ID`；
批次运行期间不要另行恢复其 run。

如果 run 已发布但批次完成记录尚未写入便中断，下次执行会先核对并补记完成状态，
不消耗新的尝试次数，也不重新调用模型；即使预算已到期也能完成这一步。

Foundation 默认直接从 brief 解析人物。`--female-count` 和 `--male-count`
是可选 Cast Constraint，只用于 brief 没有明确性别或人数的情况，例如 brief
只写“三名成年人”时可传 `--female-count 2 --male-count 1`。如果 brief 已明确
写出“两名女性和一名男性”，参数可以省略；若显式参数与 brief 冲突，系统会在
生成任何 Theme 前失败并指出冲突，不会静默覆盖、合并或删除人物。两项参数都
省略且 brief 也没有确定人物时，Cast Default 为一名成年女性；brief 已确定人数
但没有确定部分人物性别时，未确定者也默认设为女性。这个默认值不会覆盖 brief
明确写出的男性或其他人物事实。

`--output-language`（别名 `--language`）支持 `chinese`（默认）和
`english`。选择 `english` 时，即使 brief 使用中文，Foundation、Theme、
Frame 的自然语言创作字段以及最终提示词也会使用英文；内部 ID 和 schema
枚举不受影响。所有系统 instruction 始终使用中文，`output_language` 只控制
生成内容的语言。该选项保存在 `request.json` 中，resume 会继续使用原语言。

`--content-level` 支持 `aesthetic`、`erotic` 和 `hardcore`。它只作为
Foundation、Theme 和 Frame 的创作尺度提示传给模型，不触发等级矩阵、内容校验、
critic 或 repair。三个等级分别定义在系统规则目录的
`content_levels/aesthetic.rules`、`erotic.rules` 和 `hardcore.rules` 中，
每次只加载选择的文件。

每次生成的输入和运行策略只来自命令行并冻结到 run：`--theme-count`、
`--frames-per-theme`、`--female-count`、`--male-count`、`--content-level`、
`--frame-mode`、`--output-language`、`--concurrency`（默认 8）、
`--theme-batch-size`（默认 5）和 `--generation-retries`（默认 2）。
`.env` 不提供这些参数的隐式默认值，因此同一条命令不会因机器上的旧 T2I 环境
变量而改变语义。

成功后生成：

```text
runs/<run-id>/
├── request.json
├── manifest.json
├── rules.json
├── foundation.json
├── themes/
├── frames/
└── book.json

prompts/
└── YYYY-MM-DD/
    ├── aesthetic/
    │   └── semantic_name_0001.txt
    ├── erotic/
    │   └── semantic_name_0001.txt
    └── hardcore/
        └── semantic_name_0001.txt
```

每个 run 只会在其创建日期和 `content_level` 对应的目录中发布提示词。日期使用
run 的 UTC 创建日期，因此跨日 resume 仍发布到原创建日期。文件序号按日期、
`content_level` 和 `semantic_name` 独立分配；resume 会复用 manifest 中已冻结的
文件路径，不会重复生成提示词文件。

`rules.json` 保存本次 run 已解析完成的 Foundation、Theme 和 Frame 规则；
manifest 保存它的 SHA-256 指纹。Foundation 会生成安全的英文 `snake_case`
语义名。同一语义名再次生成时使用
`_0002`、`_0003`，依次递增。提示词只在全部内容生成完成后发布。这个版本
只支持当前 schema；开发阶段不会保留旧格式的迁移或 fallback。

配置 `OPENAI_EMBEDDING_MODEL` 后，每次全量 Theme 被接受时会增加一次批量
embedding 调用，分别比较 `scene` 和移除 `required_phrases` 后的 `style`。无重复
的 run 只调用一次；每轮自动重生成后会再审计一次。只有两个字段都达到阈值的
Theme 对才标记为候选重复，结果保存在 run 的
`theme-similarity.json`。命中后保留 ID 较早的 Theme，拒绝并只重新生成 ID 较后
的 Theme，然后再次执行全量相似度审计；通过后才开始生成 Frame。候选 pair 会按
Theme ID 顺序构造保留集：只拒绝与已保留 Theme 重复的后续 Theme，被拒 Theme
不会继续连带淘汰其他 Theme。自动重生成最多执行 `GENERATION_RETRIES` 轮，达到
上限仍重复时会保留当前 Theme 和最后一份报告，并继续生成 Frame；embedding
相似度是诊断信号，不会最终阻断 run。embedding provider 失败同样只记录在报告中
并继续生成；未配置 embedding 模型时不发起该调用。拒绝决定会先持久化，
再幂等删除目标 Theme 及其 Frame checkpoint；进程在两步之间退出时，resume 会
完成同一操作而不会额外消耗重生成轮次。重生成反馈按 Theme ID 传给对应批次。

如果 CLI brief 明确写出某位导演、艺术家或流派，Foundation 会把对应原文短语
逐字保存在 `StyleConstraints.required_phrases` 中，Theme 也必须逐字使用。系统
不会把一组视觉线索隐式映射为 brief 没有写出的姓名，也不会把模型对创作者的
概括提升为整次 run 的事实。

如果进程退出、VM 重启或部分模型调用失败，使用：

```bash
uv run t2i-prompts resume RUN_ID --runs-dir runs
```

忘记 RUN_ID 时先列出现有 run：

```bash
uv run t2i-prompts runs --runs-dir runs
```

`runs` 只读取每个 run 的 `manifest.json` 和 `request.json`，不加载 checkpoint，
也不需要 provider 配置。输出按创建时间倒序，给出状态、主题×镜头规模、brief
摘要，已完成 run 显示提示词文件路径，未完成 run 直接给出可复制的 resume 命令。
manifest 或 request 损坏的 run 会单独列在末尾而不是被静默跳过。

resume 会扫描 checkpoint 文件，只请求缺失的 Theme 和 Frame，并始终使用
run 内冻结的 `rules.json`，所以 VM 重启后即使系统或用户规则文件已修改或删除，
同一 run 也不会混用规则。run 缺少 `rules.json`、规则指纹不一致或 manifest
不属于当前 run 时会直接报 checkpoint 损坏。原始 spec、batch size、retry 次数、
并发设置和输出 token 硬上限都从 run manifest 恢复，避免一个 run 混用不同生成
设置。已完成 run 的 resume 是幂等的，不会重复生成 prompt 文件，也不需要加载
provider 配置。未完成 run 会校验当前 provider 的 endpoint、模型、
structured-output 模式、reasoning/thinking 设置和 temperature；当前
`OPENAI_OUTPUT_TOKEN_LIMIT` 可以更大，但不能小于 manifest 记录的硬上限。
启用 Theme 相似度诊断的 run 还要求 embedding 模型、dimensions 和 setting 阈值与
manifest 一致。已保存且无候选的 `theme-similarity.json` 在 resume 时不会重复
调用 embedding；已保存的候选报告会继续执行定向 Theme 重生成。
`RunIncompleteError` 表示最近一个完整补全 pass 没有新增任何 Theme 或 Frame；
在此之前有进展的 pass 已由同一次命令自动继续。

提示词文件位于 `prompts/YYYY-MM-DD/<content-level>/`，每个 Frame 占一行，
行与行之间没有空行，也不包含 `[T01-F01]`
之类的 Frame 标题。人物显示名由 `CastPlan` 的性别和顺序确定：女性
在中文模式依次使用 `女1、女2`，男性使用 `男1、男2`；英文模式使用
`Woman 1、Woman 2` 和 `Man 1、Man 2`。完整或简写的内部 Theme、Frame、
Character ID 都不会写入最终提示词文本。每行先展开 Foundation 保存的 brief
reference 原词；没有 reference 时直接从 Theme 开始，不添加媒介前缀。随后展开
所属 Theme 的场所、必要固定布景、背景人口，以及 Frame
当前真正可见的人物、景深、构图与光线。

## 配置

Provider 配置来自 `.env`：

| 变量 | 默认值 |
| --- | --- |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| `OPENAI_API_KEY_ENV` | `OPENAI_API_KEY` |
| `OPENAI_AUTH_MODE` | `bearer` |
| `OPENAI_STRUCTURED_OUTPUT_MODE` | `json_schema` |
| `OPENAI_TEMPERATURE` | `0.6` |
| `OPENAI_OUTPUT_TOKEN_LIMIT` | `16384` |
| `OPENAI_TIMEOUT_SECONDS` | `180` |
| `OPENAI_TRANSPORT_RETRIES` | `2` |
| `OPENAI_EMBEDDING_MODEL` | 未设置，关闭 Theme 相似度诊断 |
| `OPENAI_EMBEDDING_DIMENSIONS` | provider 模型默认维度 |
| `THEME_SIMILARITY_SETTING_THRESHOLD` | `0.86` |

`OPENAI_MODEL` 没有默认值，必须设置。只配置模型支持的 reasoning 控制：`OPENAI_REASONING_EFFORT` 或 `OPENAI_THINKING_MODE`，不要同时设置。

每次调用的输出窗口由 Foundation、当前 Theme batch 大小或当前缺失 Frame
数量动态估算，并保留 130% 余量。`OPENAI_OUTPUT_TOKEN_LIMIT` 不是固定请求
预算，而是当前 Provider/模型允许的输出 token 硬上限；动态估算不会超过它。
如果 provider 返回 `finish_reason=length`，下一次尝试直接提高到该硬上限。

## 未来设计

- [离线 Prompt Feedback Loop](docs/feedback-loop.md)：记录如何在不增加正常
  generate 成本和延迟的前提下分析 runs、聚合问题、验证规则优化，并在未来接入
  图片和人工反馈。该功能尚未实现。

## 测试

```bash
uv run ruff check src tests
uv run python -m pytest
```

推送和 PR 会在 Python 3.12 与 3.13 上自动执行同样的检查。
