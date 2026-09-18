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
document_path = Path("story-inputs/recipes/multi-view.yaml")
resolved = resolve_story_input(
    load_story_document(document_path),
    run_configuration=load_run_configuration(Path("story-run.json")),
    source_path=document_path,
)
settings = StoryRunSettings(
    provider=provider_settings,
    **resolved.runtime.model_dump(),
    quality=resolved.quality,
)
completed = await StoryStudio(model, store, settings).run(resolved)
```

恢复时使用同一个 runs 目录和 manifest 中冻结的 settings：

```python
snapshot = LocalStoryRunStore(Path("runs")).inspect(run_id)
completed = await StoryStudio(
    model,
    LocalStoryRunStore(Path("runs")),
    snapshot.manifest.settings,
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
| `inputs/` | 分别严格加载视觉 YAML 与外部运行 JSON，解析适用性、模块、阶段规则和确定性槽位计划 |
| `models.py` | 请求、模型草稿、最终对象、阶段创作和质量策略 |
| `authoring_rules.py` / `prompts.py` | 冻结系统与视觉指令、序列化阶段上下文及适用的输出目标，不传递检查模式或重试策略 |
| `provider.py` | 结构化或文本传输、transport 重试、截断与 usage，不判断故事质量 |
| `frame_batches.py` / `quality_validation.py` | 纯文本边界解析与纯函数检查，不进行 I/O 或模型调用 |
| `studio.py` | 编排两个固定阶段，分配 ID，决定接受、缺失帧重试和完成 |
| `run_store.py` / `persistence.py` / `storage.py` | 原子 checkpoint、锁、恢复完整性验证与发布 |

结构化 Theme 与文本 Frame 使用各自明确的接受逻辑，共享 attempt 记录及错误反馈
机制；Theme 通过 async iterator 交付已保存主题，不引入业务 validator 回调或
通用 workflow 框架。创作、验证和执行设置互不冒充。
公共接口不接收无法冻结的 validator 回调；额外检查统一来自声明式质量策略。
仅保存当前目录和数据结构，不提供旧整组 JSON checkpoint 或旧输出模式的回退路径。
旧模式字段即使填入当前路径对应的值也会被拒绝；不存在自动转换模型生成 ID、
旧配置或旧 checkpoint 的步骤。Theme 的 schema 错误属于结构化响应处理，
Frame 只处理文本传输、标签边界和逐帧检查，不再保留 Frame schema 响应分支。

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

系统规则是等级定义的唯一来源。配方和模块只能补充题材相关、与该等级相容的要求，
不能替换等级定义或削弱其下限与上限。等级选择仍遵循
显式 CLI `--content-level` > 外部运行配置的 `generation.content_level` > 默认 `aesthetic`。
声明三个等级的细化分支不等于同时启用三个等级。

这里有四个不同职责，不是四套等级定义：运行配置的 `generation.content_level` 选择等级，
`requirements.content_levels` 限制配方可用等级，系统等级文件定义边界，
`authoring.level_refinements` 细化题材的实现。通用成年、自愿参与等安全边界由系统
`safety.rules` 单独拥有，通用叙事和输出约束由 `common.rules` 负责；
等级特有年龄下限、可见证据与禁止范围仍留在对应等级文件，
不能为了去重扩展成所有等级的共同限制。

## 人物数量约束

`StoryRequest.female_count` 和 `male_count` 是可选人物数量约束，分别接受 0 至 8。
两者都提供时，每个 Narrative Theme 及其每个 Narrative Frame 必须恰好使用该
阵容，不得省略、替换或增加其他人物。只提供一项时，该性别人数必须精确匹配，
另一性别人数遵循 Story Description 明示事实；两项都省略时，人物人数和性别
完全遵循 Story Description。两项不能同时为 0，已指定人数之和不能超过 8。

约束通过两个阶段的 `input_context` 传递，包括作用域、固定额外人物以及所选槽位
的人数条件；不再同时发送缺少作用域的第二份人数对象。

专属配方通过 `requirements` 限制视觉阵容、人物数量和内容等级，不配置执行次数或
输出语言。外部运行配置本身必须合法，最终有效请求还必须满足配方适用性；
这些检查不能被 quality off 关闭。
显式人数作用域使用 `cast.scope` 与 `fixed_roles`；有一名固定额外角色时，
请求组最多七人，请求组与固定角色合计最多八人。固定角色可由 Theme 选择性别并在该 Theme
内保持一致，不以编号奇偶强制分配。
确实包含背景人群的配方需另外声明 `cast.background_counts`，以有界、
不重叠的 `{min, max}` 区间表达允许数量，且使用明确的主角作用域。背景人群仍是
成年人并计入画面总人数范围，不能冒充未计数物件。主角容量八人不等于画面总人数
八人；运动模糊配方的四档背景人数被保留，不擅自删掉16–30人的背景场景。
没有背景声明的输入不能从正文推断并添加这一人数扩展。
字母表配方禁止运行级男女数量（显式0也不允许），各主题从目录项获得自己的总人数
与最低男女数量要求。同一人物的多个视图不重复计数。

## 人物国籍与地点缺省值

这些缺省偏好由命名的包内 `standard-story` 策略负责，而不是不可变核心契约。
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
未配置输出长度时，篇幅由人物和画面复杂度决定；字数与字符数目标只来自外部运行配置。

系统没有模型评审、关键词评分、相似度 gate 或 revision 阶段。默认不选择任何
额外质量检查，因此仍只执行基础结构契约。运行配置可以显式选择本地 Theme／Frame
证据检查；这些检查不保证叙事语义正确，也不代替画面定义与系统安全约束。

## Story Document

文件输入只接受 UTF-8 `.yaml`，不保留 TXT 解析或旧 CLI 入口。正文仍是自然语言，
不是字段化视觉规格。最小文档只需要 `id` 和 `description`：

```yaml
id: rainy-station
description: |
  1930年代秋夜，两名成年旅人在旧车站重逢。
  用克制的现实主义摄影描绘他们辨认彼此的瞬间。

cast:
  female_count: 1
  male_count: 1

authoring:
  level_refinements:
    aesthetic:
      shared:
        - 旅人的服装保持完整穿着，以衣物轮廓和站台光线承载画面。
      themes:
        - 确定与旅人身份相符的服装组合和色彩。
      frames:
        - 通过当前姿势和站台光线呈现选定的服装轮廓。
  themes:
    common:
      - 主题差异来自事件与人物关系，而不是仅更换色调。
  frames:
    common:
      - 每帧独立描述景别、视角和焦点或景深。

```

YAML 只定义视觉内容：人物构成、外观、关系、动作、媒介、布局、光线、物件、
画内文字，以及明确的视觉资产分配。`cast` 的作用域、额外角色与背景人群是画面
事实；不是执行次数。画内区域／视图数量也不是 `frames_per_theme`。

配方不再接受 `generation`、`runtime`、`validation`、`policy`，即使为空也会报错。
正文不承载安全声明、词数门槛、精确句式、协议标签、检查／重写流程或运行参数。
不可关闭的安全底线由系统统一提供；具体的支撑几何、人物外观年龄和画内文案仍是
视觉事实，不能为了清理控制指令而删除。

`id` 只接受小写字母、数字及单个分隔用的 `-`、`_`，长度不超过 120。
它作为 `source_prompt_stem` 冻结到请求，文件改名不改变发布名称。
`description` 去除首尾空白，保留 YAML 多行字符串解析后的内部换行；建议使用 `|`。
所有未知字段、非法枚举、重复键、anchors、aliases、merge keys、多个 YAML 文档、
非标准对象标签、错误数值类型和越界参数都会在加载 provider 配置前明确报错。

### 外部运行配置

生成数量、描述语言、等级选择、并发、重试、token 预算与质量策略放在独立的 JSON
运行配置中，而不是为每份配方维护另一份隐式控制表。例如 `story-run.json`：

```json
{
  "generation": {
    "theme_count": 12,
    "frames_per_theme": 3,
    "content_level": "aesthetic",
    "output_language": "chinese"
  },
  "runtime": {
    "concurrency": 8,
    "generation_retries": 2,
    "theme_batch_size": 3,
    "theme_output_tokens": 12000,
    "frame_output_tokens": 32768
  },
  "validation": {
    "themes": {
      "mode": "report",
      "checks": [
        {"type": "text_length", "field": "premise", "min_chars": 80, "max_chars": 500}
      ]
    },
    "frames": {
      "mode": "report",
      "checks": [
        {"type": "camera_evidence"},
        {"type": "prose_length", "min_chars": 100, "max_chars": 2000}
      ]
    }
  }
}
```

```bash
uv run t2i-story generate --input story-inputs/recipes/motion-blur-photography.yaml \
  --run-config story-run.json --frames 4
uv run t2i-story explain --input story-inputs/recipes/motion-blur-photography.yaml \
  --run-config story-run.json --frame-min-chars 500 --frame-max-chars 2500 --format json
```

JSON 使用 UTF-8，拒绝重复键、未知字段与非法类型。优先级为：程序默认值 <
运行配置 < **显式** CLI 参数；视觉配方的阵容是未显式覆盖人数时的基础。
只覆盖已传入的字段，包括数值 `0`。视觉文档与运行配置自身都须有效，不能靠 CLI
修补非法输入。最终请求还须满足视觉适用性、非零阵容与槽位分配契约。

缺省值：1 个主题、每主题 6 帧、aesthetic、chinese、不限定男女数量、8 个并发、
2 次额外 generation retries。不从文件名或历史配方配置猜测预算；固定槽位目录等
视觉分配要求必须由兼容的显式请求满足，例如百姿目录需要 `--themes 100`。

`--frame-min-words`／`--frame-max-words` 使用现有的空白分词计数；
中文长度通常应使用 `--frame-min-chars`／`--frame-max-chars`。外部配置中的
`when_language` 保留语言适用性。CLI 只覆盖给出的长度边界，保留已有检查的另一侧
边界与语言条件；新增检查默认不限语言，合并后上下限冲突会明确报错。
声明的长度、必含／禁用文本等输出要求由同一套
策略生成写作约束并执行检查，不再在配方正文重复维护。`off` 关闭质量检查与相关
重试，不删除已声明的输出目标，更不能关闭安全、结构或槽位约束。

有效运行配置随 resolved input 冻结。续跑不重新读取配置文件，也不接受旧版
包含执行控制字段的配方快照；旧输入与旧快照不提供兼容读取或自动迁移。

### 输入子目录与受控模块

当前配方位于 `story-inputs/recipes/`，共享模块位于相邻 `_modules/`，目录数据位于
`_catalogs/`。资产根默认相对 YAML 文档，`--assets-dir` 可显式覆盖。不再按当前
工作目录发现 `rules/`；不存在旧 `documents.py` 或 Story `--rules-dir` 入口。

配方、模块、目录和包内策略的 YAML 自然语言内容统一使用中文，包括描述、创作
规则、目录事实和注释。字段名、ID、枚举、文件名与真正画内文字的
原文保持不变；需要保留的英文原文以引用形式嵌入中文说明。
输入规则的书写语言不决定生成语言，外部运行配置的 `generation.output_language`
与 CLI `--language` 控制描述语言。画内文案的语言和字符集是视觉设计的一部分，
不要求描述整幅画面的提示词也使用同一种语言或字符集。

配方与模块只有一个等级细化入口，不再分别在三个位置维护等级映射：

| 位置 | 职责 |
|---|---|
| 系统 `content_levels/*.rules` | 定义等级的通用边界；配方不再重复定义 |
| `authoring.level_refinements.<level>.shared` | 两阶段共用的题材特有细化，只维护一份 |
| `authoring.level_refinements.<level>.themes` | 只适用于该等级的主题规划任务 |
| `authoring.level_refinements.<level>.frames` | 只适用于该等级的画面执行任务 |
| `authoring.<stage>.common` | 该阶段不随等级变化的创作规则 |

每个等级的三种职责集中在同一个块中。每阶段的配方规则按
`阶段 common + 当前等级 shared + 当前等级对应阶段` 选择；
系统当前等级规则始终保留。这是细化而非覆盖，不提供 `replace` 或“后写覆盖前写”
语义。模块使用同一结构。其他等级和另一阶段专属指令不会进入本阶段请求。
共享细化仍直接交给 Frame，而不是假设生成的 Theme 已完整复述所有约束。
仅供 Theme 选择的参考池、仅供 Frame 使用的具体画面细节不应搬进共享等级分支。

等级键负责选择，正文只写选择完成后的具体要求：既不要混写其他等级，也不要反复
写“在情色级级别”等当前等级前缀。等级标识保留在配置、适用性检查和冻结快照中，
不作为 `content_level` 字段或等级自报口令发送给模型。将共同适用的条件分别写入
各自等级，并保留各自的具体边界；`shared` 只表示当前等级的两阶段共享，
不表示跨等级共享。
`description` 和阶段 `common` 不承载按等级分流的行为条件；例如只适用于部分
等级的公共场所拍摄要求，应放入这些等级的 `frames`。不要要求输出等级证明、
合规回执或服装锁定口令；应直接规定人物、服装、动作与可见证据。画面中确实需要
出现的文字仍是画面事实；摄影和媒介事实也须保留，但不再绑定固定开场句式、
措辞锁或段落位置。协议、篇幅和检查流程不属于视觉配方。
仓库回归测试检查已收录规则及实际选中指令中的等级标签和分流，
但不是通用的自然语言语义验证器。

精简以同一次请求中的重复为准。相同硬约束分别交给 Theme 和 Frame，可能是两个
独立阶段各自必需的输入，不能假定生成的 Theme 能无损转述它们。系统通用契约只
维护一处；配方保留外观年龄、人数、位置、可见性和物理关系。移除检查表时仍保留
其中独有的视觉要求和摄影参数，不以减少字数为由丢失画面事实。评估使用相同输入与
相同既有 Theme 样本，分别比较编译后的请求长度、约束保留和阶段／等级适用性；
字符数下降不等于已验证模型生成质量改善。

加载时拒绝同一条等级规则在 Theme／Frame 重复、在共享与阶段块重复，或与该阶段
`common` 重复；无规则的等级或职责分支可以省略。旧的 `authoring.content_levels`
及 `authoring.themes/frames.content_levels` 即使为空也被拒绝，没有别名或兼容读取。
这些检查识别的是完全相同的规则，
不是自然语言语义冲突检测，也不证明模型输出符合内容边界。
清理通用等级定义时以系统规则为准；配方独有的更严格服装要求、构图与可见性要求
继续保留，不能以去重为由丢失。媒体共性只由显式模块提供，独有内容继续留在配方。
模块是数据而非插件，不能加载其他模块、执行代码或使用任意模板表达式。
模块与目录同样拒绝未知字段、重复键、锚点、远程/越界路径、重复ID及悬空引用。

`requirements` 可以声明 `allowed_casts`、男女人数的 `{min, max}` 边界、
`content_levels`，或用 `cast_constraints: unspecified` 禁止
运行级男女人数。这些条件不会自动更改用户设置，也不受可选质量模式影响。
项目中的两份 miniature 配方分别命名为 `miniature-open-composition` 与
`miniature-giant-encounter`，保留各自语义，删除旧名称而非添加兼容别名。

### 确定性目录分配

`allocation` 选择 `fixed_slots`、`alphabet_coverage` 或 `cyclic_slots`，并指定一个目录ID。
固定姿态目录明确列出全部槽位的项目ID；任何缺项或重复会在模型初始化前报错。
字母目录包含每个字母的创作事实及人数条件：总数26时严格A–Z，小于26时使用目录中
人工审定的多样性顺序，大于26时完整覆盖后循环，不按模型批次重新计数。
小于26的具体顺序是明确的数据选择，不宣称数学意义的多样性最优。

`cyclic_slots` 按整个运行的绝对Theme位置循环目录显式的槽位顺序，不执行正文
中的算式。受限空间的姿态/情绪使用30槽循环，年龄/视角组合使用12槽循环，
近未来的类别/种子使用30槽循环。原先以“本次返回列表”计数的文字统一为运行级，
不随provider批大小重置。想在一次运行中覆盖多个姿态家族时，由调用方显式选择
足够的 Theme 数量，配方不再暗中设置执行次数。
原情绪余数规则未定义零/一偏移；当前目录明确以首项对应T001、第十项对应T010，
T011回到首项。这是公开的确定化选择，不声称原文已经规定该偏移。
未定义确定顺序的创作多样性仍由视觉规则表达，不宣称已经机器验证。

目录项可携带有界的 `frame_assignment`，声明完整、唯一的Frame槽位规则，
适用帧数由 `slots` 长度推导，不重复存储执行数量。只有实际帧数匹配时才应用；
重试F02只携带原F02的规则，
不把第二个视角当成第一槽位重新分配。此类Frame事实不会进入Theme请求。

```yaml
id: studio-views
entries:
  - id: neutral
    themes:
      - 固定同一个摄影棚场景。
    frames:
      - 保留该主题已确定的布光。
    frame_assignment:
      slots:
        - frame_id: F01
          rules:
            - 从正面拍摄。
        - frame_id: F02
          rules:
            - 从背面拍摄。
slots:
  - neutral
```

配方通过 `allocation: {type: cyclic_slots, catalog: studio-views}` 引用该目录。
`frame_assignment.slots` 必须按序完整覆盖 `F01` 至 `Fnn`，不能漏项、
重复或使用空规则。其他帧数仍使用目录通用Frame事实与配方规则，不伪造槽位分配。
目录不是通用规则引擎，不接受轴、条件表达式、任意公式或嵌套执行步骤。
这不是可执行模板、任意条件表达式或新增生成阶段。

每个Theme都有预先冻结的计划，消息只包含本批选中项目及对应阶段的事实。
批大小、Frame局部重试和resume不会重排计划；所选姿态/字母的画面实现是否正确
仍不是目录完整性检查能够证明的。

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

外部 JSON 运行配置中的 `validation.themes` 与 `validation.frames` 分别声明本阶段的
`mode` 和 `checks`，不再从视觉 YAML 读取。
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
- `word_count`：`min_words`（默认1）与可选 `max_words`；按 `len(prose.split())`
  计算空白分隔单元，不做语言学分词，不以字符数代替词数。边界含端点；
  不提供 `max_words` 就没有额外词数上限。配方不再隐含700词等门槛；
  需要长度目标时由运行配置或 `--frame-min-words` / `--frame-max-words` 显式设置。
- `ascii`：检查整段prose是否全为ASCII，只有明确要求整个输出如此的输入才启用。
  画内英文文案不意味着中文叙事段落也必须ASCII；此检查不识别图内文字槽位。
- `ascii` 和 `word_count` 可声明 `when_language: english` 或 `chinese`；
  仅对匹配的运行输出语言执行，省略时对所有语言执行。不提供任意表达式条件。
  若该阶段全部检查都因语言条件不适用，报告为 `skipped` 而不是 `passed`。
- `required_text`：非空 `values` 列表，要求每帧逐字包含每一项，区分大小写。
- `forbidden_text`：非空 `values` 列表，要求每帧不包含任一项，区分大小写。

例如 `checks: [{type: required_text, values: [车站时钟]}]`。这些通用检查不识别
输入文件名，不加载 Film 的来源、人物或作品专属检查，也不提供关闭安全要求或
绕过 provider 限制的能力。

CLI 的 `--theme-quality-mode` 和 `--frame-quality-mode` 分别覆盖对应阶段的模式，
不改变检查器列表或另一阶段的设置；不保留旧 `--quality-mode`。
API 通过 `StoryRunConfiguration.validation.themes` / `.frames` 解析同一策略，再将
`resolved.quality` 与 `resolved.runtime` 写入 `StoryRunSettings`；store拒绝不一致的副本。
两阶段策略
完整冻结在 manifest 中，resume 不读当前 YAML、运行配置或规则文件，也不接受切换策略。

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
├── resolved-input.json
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
theme/frame token 上限、完整质量策略和发布目录，并保存解析输入的指纹。
`resolved-input.json` 保存模块、目录、来源、有效请求、有效运行配置及完整槽位计划。
读取时校验指纹和请求/规则/运行设置的一致性；缺少该快照的旧run直接拒绝。
resume不重新读取原YAML、外部JSON配置或当前资产文件，不运行隐式迁移。
每个成功 Theme 和每个 Frame
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
   可通过外部运行配置和显式 CLI 参数配置。
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
  --input story-inputs/recipes/motion-blur-photography.yaml \
  --themes 100 \
  --frames 6 \
  --content-level erotic \
  --concurrency 8
```

故事位置参数与 `--input` 互斥，并且必须提供其中一个。空文件、目录、不可读文件
和非 UTF-8 文件会在 provider 调用前报错。输入错误退出码为 2；已创建但未完成
的 run（包括强制质量检查耗尽）退出码为 1，并打印 resume 命令。批量脚本因此
能区分共享输入无效与某个阵容生成失败。
批量脚本先通过选定CLI的 `explain` 检查全部五组请求；任意一组不兼容时整批
退出2且没有生成调用。不再使用独立Python预检或静默跳过不兼容阵容。

```bash
uv run t2i-story explain \
  --input story-inputs/recipes/human-typography.yaml --themes 26 --format json
```

`explain` 与 `generate` 共享同一个解析器及覆盖模型，不读取provider配置、不创建run。
JSON结果为 `{"status":"valid","fingerprint":"...","input":{...}}`；
配置错误为 `{"status":"invalid","error":"..."}`，退出2。
`--format text` 可输出简短摘要。显式 `--female-count 0` 仍违反该字母配方的
“不提供运行级男女数量”条件。

主要选项：

```text
--input PATH           读取 UTF-8 YAML Story Document
--run-config PATH      读取独立 UTF-8 JSON 运行配置
--assets-dir PATH      显式模块/目录资产根，默认相对输入文件
--themes INTEGER       主题数量，1 至 100
--frames INTEGER       每个主题的画面数，1 至 6
--female-count INTEGER 可选女性人数约束，0 至 8
--male-count INTEGER   可选男性人数约束，0 至 8
--concurrency INTEGER  Theme/Frame 共用并发上限，1 至 32
--generation-retries INTEGER 每个生成单元额外重试次数，0 至 5
--theme-batch-size INTEGER 每批 Theme 数量，1 至 10
--theme-output-tokens INTEGER Theme 批次初始预算，512 至 65536
--frame-output-tokens INTEGER Frame 批次初始预算，512 至 65536
--theme-quality-mode TEXT Theme 的 off、report 或 enforce
--frame-quality-mode TEXT Frame 的 off、report 或 enforce
--frame-min-words INTEGER 帧正文的空白分隔词数下限
--frame-max-words INTEGER 帧正文的空白分隔词数上限
--frame-min-chars INTEGER 帧正文的 Unicode 字符数下限
--frame-max-chars INTEGER 帧正文的 Unicode 字符数上限
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
