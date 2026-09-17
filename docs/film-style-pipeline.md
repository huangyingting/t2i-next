# 作品集合电影风格编译器

`t2i_film_style_pipeline` 是一个独立的一站式子模块。它接收导演署名、一个或多个
具体作品及可选的场景方向，通过一次结构化模型调用生成可复用视觉档案，再用包内
导演 Profile/Theme/Frame workflow 生成最终提示词。模型、消息、checkpoint、发布器、
错误类型和规则解析都由 `t2i_film_style_pipeline` 自己实现，不 import 或调用其他
生成 pipeline，也不加载外部 `film.txt` 或 `story-inputs/rules/`。

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
  `OPENAI_REASONING_EFFORT`、`OPENAI_TEMPERATURE`、
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

## CLI

```bash
uv run t2i-film-style generate "张艺谋" \
  --work "大红灯笼高高挂 (1991)" \
  --scene "颂莲与卓云在陈府院落点灯后相遇" \
  --filename-stem Zhang_Yimou \
  --themes 8 \
  --frames 1 \
  --female-count 1 \
  --male-count 1 \
  --content-level aesthetic \
  --concurrency 8 \
  --language chinese \
  --prompts-dir prompts \
  --runs-dir runs/film-style
```

`--work` 可以重复，支持 `TITLE` 和 `TITLE (YEAR)` 两种格式。`--scene` 是可选
的原作人物与场景方向；省略时，系统从 Profile 提取的锚点中自动选择。输入多部
作品时，每个 Theme 只能选择其中一部，Frame 必须延续相同人物与场景，不能跨片混合。
`--filename-stem` 可单独指定英文输出文件名前缀，不改变导演署名、作品来源句或
原作锚点；只允许 ASCII 字母、数字、下划线和连字符。

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

三个内容等级都采用相同结构：先定义视觉目标与每帧必须达到的可见下限，再规定
增强皮肤、接触、材质、姿态、表情和环境触觉的具体方法，最后给出不可越过的上限
以及成年人、自愿、清醒和可退出要求。美学级以人体造型和克制接触为上限；极致
情色级把裸露和非露骨亲密互动推到最高强度；赤裸明确级要求当前画面直接呈现明确
性行为，同时继续保留完整的电影空间、人物关系和导演作品视觉特征。
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

每个 Frame 都是完全独立的自然语言提示词，必须重新描述完整场景与全部人物，并用
一句普通来源说明开头，例如“这是一个基于张艺谋导演的《大红灯笼高高挂》（1991）
原作人物与场景重新构图的电影画面。”随后使用角色 canonical_name 和场景
canonical_name，依次描述环境、人物、动作与互动、镜头、光线和成片质感。
摄影部分必须明确景别、摄影机相对主要人物的方位与距离、机位高度、水平角度、
俯仰角度、镜头或焦段、透视效果、主焦点与次级清晰区域、景深，以及前景遮挡或
框景关系。空间轴线和人物朝向采用不同参照分别表述，避免“正面机位的三分之二
角度”等参照不明的组合。摄影机运动只有在当前静帧中产生可见结果时才写。
时代一致性覆盖灯具的燃料或电气结构、服装版型和材料、器物制造方式，以及天气、
温度、裸露程度和皮肤状态之间的直接因果。
最终提示词不输出母风格、Theme 风格、视觉档案等内部术语，也不输出由 App 决定的
画幅比例、分辨率或横竖方向。

Theme 和 Frame 在保存 checkpoint 前会经过 film-style 专用语义验证。拒绝或无法协助
文本、缺失或重复的指定来源句、内容等级越界或降级、画幅与尺寸信息都会被拒绝，并
通过 film 自有的有界重试把具体问题反馈给模型。Frame 缺少上述任一强制摄影
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

如果 profile、Theme 批次或单个 Frame 已保存，恢复时不会重新生成。只有通过结构
与语义验证的结果才会保存 checkpoint；重试耗尽后会保留已通过的 Frame、失败记录
并打印可直接执行的命令：

```bash
uv run t2i-film-style resume RUN_ID --runs-dir runs/film-style
```

恢复使用 run 中冻结的 provider 配置、并发设置和 film-style rules；当前 provider 配置
不一致时会明确拒绝继续，避免同一 run 混用生成条件。发布文件使用导演署名和安全
递增序号，因此重复使用同一基础 brief 与作品集合不会覆盖既有结果。
