# 作品集合电影风格编译器

`t2i_film_style_pipeline` 是一个独立的一站式子模块。它接收导演署名、一个或多个
具体作品及可选的场景方向，通过一次结构化模型调用生成可复用视觉档案，再用包内
导演 Profile/Theme/Frame workflow 生成最终提示词。模型、消息、checkpoint、发布器、
错误类型和规则解析都由 `t2i_film_style_pipeline` 自己实现，不 import 或调用其他
生成 pipeline，也不加载 Story 的视觉配方或外部 `film.txt`。

模型配置只从仓库根目录的 `.env.film` 加载：
`T2I_MODEL_BACKEND=openai` 使用直接
OpenAI-compatible HTTP，`T2I_MODEL_BACKEND=copilot` 使用 GitHub Copilot SDK。
该文件只保留 film 所需的后端、模型、认证变量名、推理级别、token 上限、超时和
重试配置，不读取通用 `.env`。顶层 run 同时冻结 Profile 与 Theme/Frame 两组
provider 配置。

`.env.film` 只应包含当前后端实际需要的以下变量：

- 通用：`T2I_MODEL_BACKEND`；
- Copilot：`COPILOT_MODEL`、`COPILOT_REASONING_EFFORT`、
  `COPILOT_OUTPUT_TOKEN_LIMIT`、`COPILOT_TIMEOUT_SECONDS`，以及实际使用的
  `COPILOT_GITHUB_TOKEN`、`GH_TOKEN` 或 `GITHUB_TOKEN`；
- OpenAI-compatible：`OPENAI_BASE_URL`、`OPENAI_API_KEY_ENV`、
  `OPENAI_AUTH_MODE`、`OPENAI_MODEL`、`OPENAI_THINKING_MODE`、
  `OPENAI_REASONING_EFFORT`、`OPENAI_THEME_TEMPERATURE`、
  `OPENAI_FRAME_TEMPERATURE`、
  `OPENAI_OUTPUT_TOKEN_LIMIT`、`OPENAI_TIMEOUT_SECONDS`、
  `OPENAI_TRANSPORT_RETRIES`，以及 `OPENAI_API_KEY_ENV` 指向的认证变量。

结构化档案同时包含：

- 每部输入电影各自的一句风格总结，顺序与 `--work` 一致；
- 每部电影中可用的原作成年人物、原作服装、实际场景、环境特征及场景道具锚点；
- 跨全部输入作品合成的一句直接、可见的视觉概述；
- 色彩、构图、调度、镜头、光线、运动、美术、材质与成片规则。

## 设计边界

- 来源必须是调用者明确提供的具体作品集合。
- 输出描述作品中可观察、可摄影控制的色彩、构图、调度、镜头、光线、运动、
  场景、美术、材质和成片特征。
- 来源署名不能代替视觉描述。
- Profile 和最终提示词都不得包含画幅比例、图像方向、分辨率或尺寸。
- 不生成导演个人风格的泛化标签。
- Theme 和 Frame 必须使用同一部电影的原作成年人物与实际场景。
- 不使用演员姓名代替角色，不跨片拼接，不虚构原作身份或地点，也不逐镜复制具体镜头。
- 人物之间的当前关系与互动可以按照 `--scene` 和内容等级重新创作，不要求忠于原作关系。
- 每名入画人物必须复用至少一个原作服装短语；每个场景必须复用至少两个环境短语和一个该场景道具短语。
- Python 不按导演名或作品名增加分支；差异全部来自请求与结构化视觉档案。

### 姿态与可见性边界

Frame 规则区分场地方向、人物自身的解剖左右和画面左右，要求接触两端的部位、
人物及左右侧与各自朝向一致。同一接触从双方描述时，位置与发力、受力关系必须
对应，高度差和距离必须在既定姿态下可达，不能靠未写出的转身、伸长肢体或
反向关节补足。承重描述必须来自同一份支撑安排；支撑物还须
说明相对位置、高度、接触面积和肢体所需空隙。靠墙后撑、抱膝坐与蹲姿、侧卧
头部与下侧手臂均须消除空间歧义。

站姿允许双脚承重，也允许单脚主要承重、另一脚轻触，但实际支点必须稳定。
肢体用途要求相互兼容，不机械限制为一个动作：手掌撑桌同时手指抓紧同一处桌沿
可以成立，同一只手撑桌又伸到别处拿杯则不成立。正文集中说明一次位置、朝向、
支点和肢体用途，后面的摄影、表情及材质描写不得暗中改变身体安排。

摄影描述区分可见接触边界和自然遮住的接触面，不要求暴露被身体压住的底面。
进入路径必须空间可达，但不要求从镜头全程可见；群像动态消息也允许自然遮挡，
不再要求全部支撑面无遮挡。指定人数、身份和内容等级要求不变，在此前提下依次
保证支撑与关节合理、接触可达、摄影与自然遮挡协调，最后考虑姿态变化与装饰。
构图不合适先调整机位，动作不成立则重新安排姿态或删减辅助动作，并同步修正
相关描述；不能减少人物、暗加支点或强扭身体来补救。
表情可读性同时依赖对焦、无遮挡和照明，不能同时要求面部细节与完全逆光剪影。
这些是模型创作规则，不是人体坐标、受力、可达性或遮挡求解器；规则加载测试
仅证明约束传入模型，不证明生成正文或最终图像已经满足它们。此模块仍不导入
spatial 的姿态库，不新增模型评审调用或验证阶段；已有输出不会因此被重写或自动认证。

## CLI

```bash
uv run t2i-film-style generate "张艺谋" \
  --work "大红灯笼高高挂 (1991)" \
  --scene "颂莲与卓云在陈府院落点灯后相遇" \
  --filename-stem Zhang_Yimou \
  --female-count 2 \
  --male-count 0 \
  --themes 8 \
  --frames 1 \
  --content-level aesthetic \
  --concurrency 8 \
  --theme-batch-size 5 \
  --language chinese \
  --prompts-dir prompts \
  --runs-dir runs/film-style
```

`--work` 可以重复，支持 `TITLE` 和 `TITLE (YEAR)` 两种格式。`--scene` 是可选
的原作人物与场景方向；省略时，系统从 Profile 提取的锚点中自动选择。输入多部
作品时，每个 Theme 只能选择其中一部，Frame 必须延续相同人物与场景，不能跨片混合。
`--filename-stem` 可单独指定英文输出文件名前缀，不改变导演署名、作品来源句或
原作锚点；只允许 ASCII 字母、数字、下划线和连字符。
`--theme-batch-size` 控制单次 Theme 模型调用批量返回的独立 Theme 数，范围为
1–10，默认 5；`--concurrency` 是 Theme 批次与 Frame 调用共同遵守的全局并发
上限。

电影流程支持 `--female-count`、`--male-count`，对应 API 字段为 `female_count`、
`male_count`。它们完全决定每个 Theme 和 Frame 的男女数量：

- 默认一女零男；只指定一项时，另一项保留默认值，不随机补足。
- `--female-count 3 --male-count 0`：每个 Theme 固定三女零男。
- `--female-count 0 --male-count 5`：每个 Theme 固定零女五男。
- 两项均为非负整数，不设人数上限，也不要求至少一名女性；不能同时为零。
- 不合法的参数在模型调用前拒绝；原作成年人物不足仍不能虚构身份。

男女数量冻结在顶层与 prompt 子运行的请求中，不再保存随机人数计划。每次 Theme 调用的
`current_batch_cast_requirements` 按输出位置传递精确人数，Frame 调用通过
`theme_cast_requirement` 重申同一人数。Theme 和 Frame 的人数要求都包含精确的
`female_count` 与 `male_count`；零女性或零男性必须原样执行。模型只选择对应数量的原作
成年人物，不能改动总人数或已确定的男女组合，不能自行改回二人。
所有 Theme、重试、分批、并发和 resume 均采用请求中的同一组数量。
Profile 尽量完整提取可确认的成年人物，不能只列一对主角或按固定人数截断；
人数不足不能虚构身份、跨片拼接或把未成年人改成年。
每个 Theme 的全部 Frame 保持同一组人物，不为凑人数复制角色，也不引入额外的
原作/原创角色选择协议。
此改动不修改任何 content-level 规则。阵容要求交给模型执行，不把姓名出现次数
当作人数校验，也不宣称能证明自由文本中的实际身体数量。
旧的额外阵容字段或随机人数计划不迁移或静默转换；
需要按当前格式新建运行。已有输出不会自动修改。
输出文件名也不再自动拼接固定人数后缀，显式文件名前缀仍照常保留。
内容语义校验默认关闭；确有需要时才使用 `--validate-themes` / `--validate-frames`。
schema、批次数量、ID、单段正文、checkpoint 和发布完整性检查保留。

完成后 CLI 输出：

- 顶层 film-style run ID；
- 结构化视觉档案路径；
- 最终电影提示词路径。

最终提示词保存在内容等级目录中，文件名只使用清理后的导演署名和递增序号，例如
`prompts/2026-09-17/hardcore/张艺谋_0001.txt`。内容等级、人物数量和
`film_style` 等信息不再重复拼入文件名；完整请求仍保存在 run checkpoint 中。

动态作品证据只作为 run 内部上下文保存。film-style 自己拥有完整规则集：

```text
src/t2i_film_style_pipeline/rule_packs/system/
├── profile.rules
├── common.rules
├── themes.rules
├── frames.rules
└── content_levels/
    ├── aesthetic.rules
    ├── erotic.rules
    └── hardcore.rules
```

Profile 阶段加载 `profile.rules`；Theme 和 Frame 阶段按
`common → 当前阶段 → 所选 content level → 可选用户规则 → 输出语言` 加载。
不传 `--rules-dir` 时只使用上述包内规则；显式传入时，用户目录也采用相同布局，
其中 `profile.rules`、阶段规则或内容等级规则缺失时会跳过。包内规则和动态输出
语言指令统一使用中文书写。

## 模块职责

- `rule_packs/system/*.rules`：保存所有静态创作政策和阶段行为，任何会改变模型如何
  分析或创作的长期指令都必须放在这里。
- `rules.py`：只负责读取、选择和合并 Profile、Theme、Frame 规则，不包含
  导演或作品特例。
- `profile_messages.py`：只把导演、作品和输出语言序列化为 Profile 请求消息，不保存业务
  规则，也不重复描述任务。
- `compiler.py`：把已经生成的结构化视觉档案与可选场景方向编译为当前 run 的动态
  电影场景上下文；中英文模板属于输出数据格式，不属于模型行为规则。
- `models.py`：定义输入、输出、每部作品的人物与场景锚点，以及 `FilmStyleRuleSet`
  的结构与硬验证约束。
- `content_validation.py`：验证拒绝文本、来源句、内容等级和图像几何禁项；只定义
  可确定判断的发布门槛，不承担创作规则。
- `pipeline.py`：负责阶段编排、checkpoint 和恢复。顶层 `rules.json` 同时冻结
  Profile、Theme、Frame 三组规则；film prompt 子运行只接收执行 Theme/Frame 所需
  的两组规则。
- `prompt_models.py`、`prompt_messages.py`、`prompt_provider.py`、
  `prompt_run_store.py` 和 `prompt_studio.py`：film 自有的 Theme/Frame 生成核心，
  不复用其他 pipeline 的模型、provider、storage 或 studio。

模型输出边界按阶段区分：Profile 的人物、服装、场景、环境和道具档案继续使用严格
结构化提交；Theme 只提交 `semantic_name`、`title`、`premise` 和 `style`，不再让
模型生成 `theme_id`；Frame 不提交 JSON 或工具参数。每个 Theme 只调用模型一次，
使用 `<FRAME>...</FRAME>` 标签批量返回该 Theme 的全部纯自然语言正文；程序拆分
批次、按顺序分配 `F01`、`F02` 等 Frame ID、构造 Pydantic 领域对象并写入
checkpoint。每个纯文本 Frame 仍须通过全部语义发布门槛；任一 Frame 失败时重试
时立即逐帧 checkpoint 同批次中已通过的画面，只把失败槽位组成较小批次重新生成；
run 中断后恢复也只请求尚未通过的槽位。

Theme 与 Frame 使用流式 producer/consumer 调度，而不是两个完全分离的阶段。
单个 Theme producer 按 `theme_batch_size` 顺序批量生成 Theme，使下一批可以看到
此前已保存的 Theme 并避免重复；每个批次返回并 checkpoint 后，其中每个 Theme
立即作为独立工作项进入有界 Frame queue。Frame workers 可以处理上一批 Theme，
同时 producer 生成下一批，二者共享 `concurrency` 信号量，因此实际模型调用不会
超过全局并发上限。保留单一 Theme producer 也保证 `semantic_name`、Theme ID 与
checkpoint 顺序稳定。若 Theme 总数不超过一个批次，模型会在一次调用中返回全部
Theme，随后并发生成各自的 Frame。

三个内容等级都采用相同结构：先定义视觉目标与每帧必须达到的可见下限，再规定
增强皮肤、接触、材质、姿态、表情和环境触觉的具体方法，最后给出不可越过的上限
以及成年人、自愿、清醒和可退出要求。美学级以人体造型和克制接触为上限；极致
情色级与赤裸明确级都把皮肤、表情、呼吸、材质、身体重量和空间触觉推到最高
感官强度。情色级的核心仍是非生殖器亲密接触，不得形成完整的器具控制链或
命令式色情展示；赤裸明确级则要求当前画面直接呈现明确性行为，或无插入但具有
同等可见强度的器具支配、命令展示与臣服互动，同时继续保留完整的电影空间、
人物关系和导演作品视觉特征。
Theme 阶段必须把当前等级的核心互动类别、参与关系和发生状态确立为稳定事实；
Frame 阶段只能具体化姿态、肢体分工、接触细节和摄影方案，不得降低、替换或升级
Theme 的核心互动。

美学级每个 Frame 必须满足五项感官证据中的至少四项，并强制包含皮肤或贴身轮廓
以及身体明暗塑形。人物的成年、清醒、主动回应和可退出边界只能通过准确年龄、
主动回握、回应式视线、双向施力和各自稳定支撑等可见事实表达，不得写成“平等而
自愿”“可随时退出”或其他结论式合规话术。

Theme 不再压缩成一句风格总结。`premise` 通常使用三至五句完整说明稳定的人物、
地点、关系、事件和关键环境；`style` 通常使用四至八句，把作品级证据转化为当前
场景专属的视觉执行方案。镜头策略与透视倾向是不可省略的必选项；除此之外还须
覆盖色彩、构图、调度、光线、美术、材质、运动和成片质感中的至少五项。复杂场景
可以继续展开，不设固定字数上限。film-style 的 Theme 批次输出预算为
12,000 tokens。

跨 Theme 批次的避重恢复完整历史：`existing_themes` 包含此前每个已接受 Theme 的
ID、标题、完整 premise 与 style，不截断、不摘要、不只保留最近两个。resume
从同一批完整 checkpoint 重建历史。模型必须比较全部历史及当前批次内部候选，
不能只换标题、措辞、小道具或机位就把相同情境与视觉组织当作新 Theme。
程序额外拦截规范化后 premise/style 完全重复的主题，不依赖可选内容校验，
使用已有的有界生成重试；没有新增语义评审调用或相似度拒绝阈值。
这一检查不保证识别换词后的语义重复；完整历史的输入 token 成本高于短摘要。
当前批次每个输出位置仍会
得到一个 `current_batch_diversity_contracts` 条目，以请求上下文哈希和 Theme 顺序
稳定分配内容路径重点、关系张力、空间策略、摄影策略、光线策略和两个优先变化维度。
合同只指定高层变化轴，不分配具体作品、动作、姿态、动作发起者、接触链或精确镜头。
这些高层方向不能代替完整历史比较，也不能把自由阵容固化成主题编号对应的菜单。

OpenAI-compatible prompt provider 默认对 Theme 使用 `0.85` temperature，对 Frame
使用 `0.6`；可分别通过 `OPENAI_THEME_TEMPERATURE` 和
`OPENAI_FRAME_TEMPERATURE` 调整。启用实际 reasoning/thinking 模式时不发送
temperature；`reasoning_effort=none` 仍允许使用分阶段 temperature。Copilot SDK
当前不暴露逐调用 temperature，因此这两个设置只影响 OpenAI-compatible 后端。

每个 Frame 都是完全独立的自然语言提示词，必须重新描述完整场景与全部人物，并用
一句普通来源说明开头，例如“这是一个基于张艺谋导演的《大红灯笼高高挂》（1991）
原作人物与场景重新构图的电影画面。”随后使用角色 canonical_name 和场景
canonical_name，依次描述环境、人物、动作与互动、镜头、光线和成片质感。
Frame payload 中的 `theme_anchor_contract` 把 Theme 实际采用的人物与场景列为
`required_exact_terms`，并把上下文内其他 canonical anchor 列为
`forbidden_other_anchor_terms_in_body`。每帧必须在固定来源首句后的画面正文中
逐字复用全部 required anchors，且不能出现任何 forbidden anchor；来源首句中的
作品标题即使包含同名人物字样也不计入禁止项。
模型返回后，程序在写入 checkpoint 前将 `deterministic_anchor_sentence` 幂等地
放到固定来源首句之后。该自然语言句由 `required_characters` 与 `required_scene`
构造，不消耗模型 token，也不触发重试。它只保证 canonical 字符串存在；逐人物
诊断会先移除该句，再检查模型正文是否真正描述了每个人。
`current_frame_diversity_contracts` 按 `frame_slot` 重申 Theme 已锁定的内容路径及其
必须同时可见的证据。不同 Theme 按确定性合同分配不同路径，同一 Theme 的全部
Frame 使用同一路径，只在姿态、核心互动链、动作发起者、景别、机位和光线中变化。
Hardcore 的四条路径为明确性行为、器具形成的无插入 BDSM 控制链、命令式开放展示
和外部器具或受控自我刺激。合同只约束高层证据，不固定人物姿势或身体拓扑；同一
F-ID 在选择性重试和恢复后保持不变。
各等级均使用同一组请求参数指定的男女数量，没有按等级设置的固定人数。
极致情色级的
Frame 合同要求明显裸露或半解服装、实际非生殖器接触、具体欲望或愉悦表情，以及
皮肤或材质触觉四项同时出现。
Theme 采用三人及以上阵容时，`participant_frame_contracts` 为每个人建立
独立描述义务，并按每个 F-ID 生成通用 `group_frame_contracts`。合同只携带
Theme 实际选中的 `required_active_participants` 及逐人
参与要求，不预设核心二人组、观察者、回应者、外围人物、固定角色、配对数量、
接触顺序或空间站位。
模型根据人数、场景与身体拓扑自行设计适合当前画面的互动网络，不从程序提供的
固定结构菜单中选择；每个人都必须通过具体可见且不可删除的动作直接参与同一个
共同事件，成为至少一条动作或接触链的明确端点，并分别闭合支撑、四肢职责和
进入路径。
Hardcore 且 N 人阵容不少于三人时，`hardcore_group_realization` 仍只提供通用约束：
模型自行决定全部人物的动作、对象与双向关系，不按性别或名单顺序分配角色；每个人
都必须直接进入当前内容路径，逐人写清动作主客体、接触或器具、受力、支撑与主动
反应，并让所有参与者属于同一个可追踪互动网络。`no_euphemism` 禁止将当前路径
软化为协商、游戏、普通亲密姿态或画外暗示。
每个入画人物必须分别具有一个与当前动作一致的具体可见表情，以至少两项眉眼、
眼睑、嘴角、嘴唇、下颌、面颊或额头状态落实，并明确视线落点；不得用群体共同
表情或“神情复杂”等抽象结论代替。
为降低肢体错乱，Frame 在写正文前按固定顺序解决身体拓扑：先确定每人的支撑面和
承重部位，再确定骨盆、躯干与头部朝向，然后为四肢确定相互兼容的用途，
写清双方叙述一致且空间可达的接触链，最后固定每件衣物的唯一状态。
每帧围绕一个共同互动事件组织必要动作，并禁止悬空但无直接承重、完全贴合却把手放在身体
之间、面部完全遮挡却要求完整表情、完全赤裸却仍穿着衣物等冲突组合。
Theme 只锁定人物、地点、关系、内容方向和视觉原则；每个 Frame 自由设计站、坐、跪、
蹲或卧姿，独立选择动作发起者和一条核心接触链，并重新闭合承重、四肢和衣物拓扑。
批次同时变化姿态类别、高低关系、核心接触与机位、景别、前景、焦点和光线，冲突时
删掉辅助动作。
Hardcore Frame 只允许一条核心互动链，可以选择明确性行为路径，也可以选择无插入
但完整可见的 BDSM 路径。后者必须同时写清控制者、器具连接、握持或牵引方向、
被控制者主动维持的开放姿态、闭合承重链和具体欲望表情；项圈、牵引链、腕带和
绳索不得承担身体重量或压迫气道。画面把动作写成完成后的静态受力结果，禁用持续、
反复、来回和起伏等跨时刻措辞。上衣只能完整穿袖并从前方敞开或完全脱下，每张脸的
眼、鼻、嘴必须从可辨角度直接可见。可选 Theme 验证不要求 Theme 提前达到逐帧的明确
接触粒度；明确行为下限在 Frame 验证中执行。
每个核心接触还必须具有空间可达的进入路径和足够空间；侧卧时明确同向或相向且双腿不穿插，
坐姿不混用地面与座椅承重。未参与核心动作的手臂回到自身或支撑面，衣物从三种完整
状态中选一，避免“完全赤裸”与仍穿衣、脚踝堆衣等冲突。
姿态不使用模板分配，只要求每人的承重链闭合；仅靠地面支撑时重心投影须落在实际
支撑范围内，靠墙或扶桌另行交代支撑位置与受力。禁止无承托的悬空骨盆、
无支点深度俯折、抬举和单点承受另一人全身重量。
摄影部分必须明确景别、摄影机相对主要人物的方位与距离、机位高度、水平角度、
俯仰角度、镜头或焦段、透视效果、主焦点与次级清晰区域、景深，以及前景遮挡或
框景关系。空间轴线和人物朝向采用不同参照分别表述，避免“正面机位的三分之二
角度”等参照不明的组合。摄影机运动只有在当前静帧中产生可见结果时才写。
时代一致性覆盖灯具的燃料或电气结构、服装版型和材料、器物制造方式，以及天气、
温度、裸露程度和皮肤状态之间的直接因果。
最终提示词不输出母风格、Theme 风格、视觉档案等内部术语，也不输出由 App 决定的
画幅比例、分辨率或横竖方向。

Theme 和 Frame 的 film-style 专用语义验证默认关闭。使用 `--validate-themes`
启用 Theme 验证，使用 `--validate-frames` 启用 Frame 验证；开关状态写入顶层
run settings，resume 保持创建 run 时的选择。启用后，拒绝或无法协助文本、缺失或
重复的指定来源句、内容等级越界或降级、画幅与尺寸信息都会被拒绝，并通过 film
自有的有界重试把具体问题反馈给模型。Frame 缺少上述任一强制摄影
证据、美学级感官证据不足或出现结论式合规话术时同样拒绝。Theme 必须选择一部
作品中的人物和一个场景；Frame 若切换作品、人物或场景，缺少任一入画人物的
costume_features、少于两个 environment_features，或没有 canonical_props，也会被
拒绝。中文 Frame 通常控制在六百至一千二百个中文字符，共同国籍、成年身份和关系
只写一次组级说明。

## Checkpoint 与恢复

顶层 run 在第一次模型调用之前创建。每次运行使用一个对用户可见的 run ID，并在
其下保存 profile 与 prompt 两个子运行：

```text
runs/film-style/<run-id>/
├── request.json
├── settings.json
├── rules.json
├── manifest.json
├── profile-runs/
│   └── <profile-run-id>/
│       ├── request.json
│       ├── profile.json
│       ├── compiled-context.txt
│       └── result.json
└── prompt-runs/
    └── <prompt-run-id>/
        ├── request.json
        ├── rules.json
        ├── manifest.json
        ├── diversity-report.json
        ├── themes/
        ├── frames/
        │   └── T001/
        │       ├── F01.json
        │       └── F02.json
        └── attempts/
```

顶层 `rules.json` 包含 `profile`、`themes` 和 `frames` 三个字段。Profile 尚未生成
时发生中断，resume 也会继续使用创建 run 时冻结的 Profile 规则，不会重新读取
后来修改的规则文件。

如果 profile、Theme 批次或单个 Frame 已保存，恢复时不会重新生成。已有但 Frame
尚不完整的 Theme 会先进入 Frame queue，同时 Theme producer 继续补齐缺失 Theme。
只有通过结构
与语义验证的结果才会保存 checkpoint；重试耗尽后会保留已通过的 Frame、失败记录
并打印可直接执行的命令：

```bash
uv run t2i-film-style resume RUN_ID --runs-dir runs/film-style
```

恢复使用 run 中冻结的 provider 配置、并发设置和 film-style rules；当前 provider 配置
不一致时会明确拒绝继续，避免同一 run 混用生成条件。发布文件使用导演署名和安全
递增序号，因此重复使用同一基础 brief 与作品集合不会覆盖既有结果。
完成时程序本地计算 `diversity-report.json`，记录标题唯一数、Theme/Frame 精确重复、
字符三元组余弦相似度、同 Theme Frame 相似度，以及内容路径、来源锚点、空间、景别、
姿态和光线覆盖计数。所有内容级别都记录自身证据完整与不完整 Frame 数量，并记录
Frame 是否完整继承 Theme 的 required anchors、是否出现其他作品的 forbidden
anchors；景别只统计远景、全景、中景、中近景、近景与特写，不混入摄影机方向或
高度，并单独记录衣袖堆在手臂或“完全赤裸”仍穿衣物等衣物状态冲突。报告不调用
模型、不拒绝结果，也不会触发重试。
报告额外拆分 `character_anchor_complete_frames` 与
`scene_anchor_complete_frames`，并记录 `participant_slot_count`、逐人物完整描述、
面部、视线和支撑完成槽位。逐人物统计排除程序插入的锚点句，避免 exact anchor
成功掩盖模型正文中的人物遗漏。
