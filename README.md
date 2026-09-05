# t2i-prompt-pipeline

这个工具把文生图内容分成共享 Foundation 和两层具体画面事实：

- `StyleConstraints`：只保存 brief 明示且逐字复制的风格、媒介、技法、时代和地域短语。
- `CastPlan`：从 brief 解析出的共享人物名册，只保存人物顺序、性别和明确身份，
  不保存外貌或服饰。
- `Theme`：主题、场景、完整视觉风格、人物稳定外貌和基础服饰。
- `Frame`：当前镜头、视角、构图、环境、表情、动作和细节。

每个事实只有一个所有者。renderer 只按固定顺序展开这些事实，不推断内容，也不补写光线、接触、服饰或位置。

`StyleConstraints.required_phrases` 不解释风格，也不补写 brief 没有提到的时代、
地域、媒介或视觉特征。例如 brief 只有“韦斯安德森风格”时，Foundation 只保存
这段原文。每个 `Theme.style` 必须逐字包含这些约束，再根据自身场景生成完整且
不同的媒介、画面调度、配色、光线和质感。最终提示词只展开当前 `Theme.style`。

## 生成流程

一次 run 有三类模型调用：

1. 一次 `Foundation` 调用生成共享 `StyleConstraints`、`CastPlan` 和语义文件名。
2. `Theme` 按小批次生成，默认每批 5 个，并在同一次调用中直接生成各自的完整 `style`。
3. 所有 `Theme` 完整生成后才执行可选的全量相似度审计；未齐时不会提前生成任何
  `Frame`。
4. 所有 `Theme` 通过审计后，每个 `Theme` 一次 Frame 调用，生成该主题当前缺失
  的全部 `Frame`。

因此 5 个主题、每个主题 5 个镜头的基础调用数是 7 次；100 个主题、
每个主题 6 个镜头、Theme batch size 为 5 时，基础调用数是 121 次。
自适应 `Theme.style` 复用原有 Theme 调用，不增加模型调用次数，也不需要预生成
风格候选、候选 ID、额外选择调用或选择理由。Frame 请求不再重复发送全局风格
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

项目可以在根目录的 `rules/` 下使用同样的可选目录结构添加用户规则，也可以用
`--rules-dir PATH` 显式指定目录。缺失的用户规则文件会跳过；显式指定的目录
不存在时会报错。每个阶段按以下固定顺序编译：

1. 系统 common、stage、当前 content level，以及 Frame 的当前 mode；
2. 用户 common、stage、当前 content level，以及 Frame 的当前 mode；
3. 运行时生成的输出语言要求，以及 Theme 的无名人物标签要求。

因此每次只把当前选择的 content level 和 frame mode 发送给模型，不会发送另外
两套等级，既避免规则冲突，也减少输入 token。当前系统规则要求：

- 创作先保留 brief 明示事实与 stage ownership，再满足单帧物理和可见性，之后才
  追求差异与装饰细节。规则中的条件示例不会给其他 brief 添加地点或服饰限制；
- 先为全部请求 ID 生成最简有效候选，再补可选细节；优先简化画面，确实无法形成
  有效候选时才省略该 ID。Theme 的 scene 用名词短语列活动位置、工具与对象、
  材质、固定布景及光源，style 默认一句；Frame 的 action
  用一个短句（中文40字或英文25词），details 默认至多两项可选细节（中文共30字或
  英文20词）；这些是指令侧长度要求，不做运行时截断，brief 必需事实、人物、路线
  与因果信息仍须完整保留；
- Frame 指令包含通过当前 schema 验证的完整短输出示例，示范完整面部和仅手部
  两种取景；示例只用于学习写法，实际 ID、场景与动作来自当前请求，检查过程
  不写入生成字段；
- 美学级仍要求至少两项可见形体表达；brief 固定服饰或日常活动时，通过相容的
  姿态与光影满足下限，不改变原服饰或活动；原有成年、互动及尺度上限保持不变；
- 使用自然、流利、简练且语言一致的描述，返回前消除病句和残句；中文自然语言
  创作字段不得夹杂英文标签、服饰名或状态词，schema 规定的机器标识字段除外；
- StyleConstraints 只逐字提取 brief 明示的视觉、时代和地域短语，不翻译、改写、
  总结或推断；brief 没有时代线索时不会默认补写“当代”，也不会根据创作者姓名
  固定一套所谓代表性配色、构图或年代；
- CastPlan 忠实保留 brief 明确写出的人物和身份；`role` 必须能在 brief 中找到
  明确身份原词，无身份原词时使用 JSON null，不能根据地点、任务或道具猜测职业；
  可选 CLI 人数只补足 brief
  没有明确的性别或人数，不能覆盖 brief，也不授权创造职业；
- Theme 在逐字保留 required_phrases 的前提下生成一个简练的完整 style，补充
  当前场景的摄影或摄像工艺、抽象构图与空间组织倾向、配色、光线和材质；最终媒介必须
  是摄影或摄像，不使用水彩、素描、版画、插画、动画或三维渲染；具体景别、相机
  位置、数值角度、焦距和镜头运动由 Frame 定义。Theme 同时拥有稳定外貌和动作发生前的基础服饰；scene 确定稳定的空间
  结构、固定布景和关键道具身份、材质；可移动道具的当前位置与持握由 Frame 描述，
  brief 明示的起点仍须保留。单地点活动不编造到达路线；scene 不复述 style，也不会在首个 Frame 前提前
  完成 brief 中的寻找、发现或取得等目标；brief 要求故事性或互动时，scene 还要
  提供能承载互动的可见信息或关键道具；
- 本地 contract 会拒绝中文 Theme 中 brief 未授权的拉丁文字，也会拒绝
  required_phrases 之外混入 Theme.style 的具体景别、机位、快门、焦距或镜头运动，
  以及 brief 未指定的明确年代；批次中的其他有效 Theme 会保留，只定向补全被拒绝的 ID；
- 基础服饰必须同时符合 brief 明示的时代地域和 scene 的地点、场合、季节与天气；
  道具、器物、家具、照明、载具、建筑构件和织物都要写出该时代的具体形制与材质，
  例如写“陶油灯”“木格窗”“麻布直裾”而不是“灯”“窗”“衣服”，避免笼统名词
  被文生图模型默认渲染成当代工业制品；时代早于当代时不得出现电灯、塑料、拉链、
  机制印刷品、机动车等该时代不存在的物件，Frame 的 details 也沿用同一时代形制；
- 同一批 Theme 必须形成不同的完整方案，不能复制 title、scene 和稳定事实后只
  替换 style；差异只来自 brief 未固定的布局、布景、障碍、路线和 style，不能移动
  brief 已指定的起点、核心物体、目标地点或其他不变量；涉及楼层或高度变化时，
  scene 必须提供能承载人物和核心物体的可执行垂直路线；brief 指定多个连续地点时，
  每个 Theme 都包含全部地点及连接关系，并由自己的 Frames 独立完成整条故事线，
  不能把不同 Theme 当成同一故事的连续章节；相似度反馈要求新方案时，也只调整
  brief 未固定的部分；
- Frame 是可独立渲染的当前画面，不引用 Frame ID 或前序帧元叙事；contract 会拒绝
  action 中的“不可见”“出画”“画外”、依赖其他 Frame 的“仍”“已”等缩写，以及
  声音、气味、温度等非视觉信息；
- Frame 的现有字段需要覆盖取景与透视、景深与焦点、视觉重点、人物调度、
  前中后景、姿态与视线，以及当前环境光效和道具状态；只写与画面相关的信息，
  不机械罗列摄影术语，并把 Theme 的抽象构图、透视和景深倾向转成具体 camera
  选择；承担核心互动或故事推进的道具必须已经存在于 Theme.scene
  或人物稳定服饰配件中，Frame 不临时发明新的核心道具；Theme.style 明确浅景深
  或深景深倾向时，Frame 不得选择相反景深；
- Frame 只包含当前画面实际可见的人物；完全出画的人物不进入结构化 Frame，也不
  会由 renderer 重复写入最终 prompt。先确定取景边界，再写可见部位、动作和细节；
  眼神仅在眼部可见时描述，仅下半脸可见时描述嘴角或下颌，面部不可见时 expression
  为 null。手部默认一个主要任务，身体和容器内部细节均服从实际取景；
- 默认选择完整面部或仅手部与物体的明确取景，brief 要求局部面部时才选局部；
  只见背面时 expression 为 null。variations 的人物焦点只用已有工具，不额外
  要求记录工具；细节焦点在 brief 允许时使用手部取景，并保留核心动作的可见结果；
- brief 的空间关系需要由实际活动位置体现，而不只是背景里出现相关物体；服饰
  材质要求同时约束 Frame 的光照与 details，不透明衣料不因逆光描写而变为透明。
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
  --rules-dir rules \
  --runs-dir runs \
  --prompts-dir prompts
```

`--frame-mode variations` 会让同一主题的镜头成为互不依赖的完整候选画面。
每个候选仍继承相同的 Theme 稳定事实并保留 brief 核心活动，优先改变取景、机位和
构图，再选择自然姿态。三项差异是满足明确约束后的目标，不以改变核心活动或复杂
手势凑足差异。五个或更多候选在这些约束内尽可能覆盖多种取景范围、机位和构图。
本地会按 Theme ID 生成并轮换一个很小的
`variation_plan`，随原有 Frame 请求指定每个 ID 的主要变化焦点，不增加模型调用，
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
5 个 run 和 3,000 条提示词。第三个可选参数可以指定另一个规则目录；未传时使用
项目根目录的 `rules/`。
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

该命令固定使用 `aesthetic` 和 `variations`，并加载
`rules/batches/safe_avant_garde/` 的隔离规则，要求所有人物 25 岁以上、
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
上限仍重复时 run 会停止并保留最后一份报告。embedding provider 失败仍只记录在
报告中并继续生成；未配置 embedding 模型时不发起该调用。拒绝决定会先持久化，
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
启用 Theme 相似度诊断的 run 还要求 embedding 模型、dimensions 和两个阈值与
manifest 一致。已保存且无候选的 `theme-similarity.json` 在 resume 时不会重复
调用 embedding；已保存的候选报告会继续执行定向 Theme 重生成。
`RunIncompleteError` 表示最近一个完整补全 pass 没有新增任何 Theme 或 Frame；
在此之前有进展的 pass 已由同一次命令自动继续。

提示词文件位于 `prompts/YYYY-MM-DD/<content-level>/`，每个 Frame 占一行，
行与行之间没有空行，也不包含 `[T01-F01]`
之类的 Frame 标题。人物 `label` 有真实姓名时使用姓名；没有姓名时，女性
在中文模式依次使用 `女1、女2`、男性使用 `男1、男2`；英文模式使用
`Woman 1、Woman 2` 和 `Man 1、Man 2`。完整或简写的内部 Theme、Frame、
Character ID 都不会写入最终提示词文本。每行只展开一次所属 Theme 的完整
`style`；Foundation 的原文约束已包含在该 style 中，不再另行重复。

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
| `THEME_SIMILARITY_SCENE_THRESHOLD` | `0.86` |
| `THEME_SIMILARITY_STYLE_THRESHOLD` | `0.815` |

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
