# 作品集合电影风格编译器

`t2i_film_style_pipeline` 是一个独立的一站式子模块。它接收导演署名、一个或多个
具体作品及可选的场景方向，通过一次结构化模型调用生成可复用视觉档案，再用包内
导演 Profile/Theme/Frame workflow 生成最终提示词。它不依赖外部 `film.txt`，也不加载
`t2i_story_pipeline` 或 `story-inputs/rules/` 的规则。

模型调用遵循仓库统一配置：`T2I_MODEL_BACKEND=openai` 使用直接
OpenAI-compatible HTTP，`T2I_MODEL_BACKEND=copilot` 使用 GitHub Copilot SDK。
顶层 run 同时冻结 film-style 与 story 两个阶段的 backend 配置。

结构化档案同时包含：

- 每部输入电影各自的一句风格总结，顺序与 `--work` 一致；
- 跨全部输入作品合成的一句直接、可见的视觉概述；
- 色彩、构图、调度、镜头、光线、运动、美术、材质与成片规则。

## 设计边界

- 来源必须是调用者明确提供的具体作品集合。
- 输出描述作品中可观察、可摄影控制的色彩、构图、调度、镜头、光线、运动、
  场景、美术、材质和成片特征。
- 来源署名不能代替视觉描述。
- 不生成导演个人风格的泛化标签。
- 不复制角色、演员外貌、对白、剧情、标志性服装、独特道具或具体镜头。
- Python 不按导演名或作品名增加分支；差异全部来自请求与结构化视觉档案。

## CLI

```bash
uv run t2i-film-style generate "张艺谋" \
  --work "英雄 (2002)" \
  --work "十面埋伏 (2004)" \
  --scene "雨夜室内，两名成年人隔着长桌交谈" \
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
场景方向；省略时，系统会为每个 Theme 自动创作不同的原创电影场景。

完成后 CLI 输出：

- 顶层 film-style run ID；
- 结构化视觉档案路径；
- 最终叙事提示词路径。

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
- `models.py`：只定义输入、输出和 `FilmStyleRuleSet` 的结构与硬验证约束。
- `pipeline.py`：只负责阶段编排、checkpoint 和恢复。顶层 `rules.json` 同时冻结
  Profile、Theme、Frame 三组规则；Story child run 只接收执行 Theme/Frame 所需
  的两组规则。

三个内容等级都采用相同结构：先定义视觉目标与每帧必须达到的可见下限，再规定
增强皮肤、接触、材质、姿态、表情和环境触觉的具体方法，最后给出不可越过的上限
以及成年人、自愿、清醒和可退出要求。美学级以人体造型和克制接触为上限；极致
情色级把裸露和非露骨亲密互动推到最高强度；赤裸明确级要求当前画面直接呈现明确
性行为，同时继续保留完整的电影空间、人物关系和导演作品视觉特征。

Theme 不再压缩成一句风格总结。`premise` 通常使用三至五句完整说明稳定的人物、
地点、关系、事件和关键环境；`style` 通常使用四至八句，把作品级证据转化为当前
场景专属的视觉执行方案，并至少覆盖色彩、构图、调度、镜头、光线、美术、材质、
运动和成片质感中的六项。复杂场景可以继续展开，不设固定字数上限。film-style
的 Theme 批次输出预算为 12,000 tokens。

每个 Frame 都是完全独立的自然语言提示词，必须重新描述完整场景与全部人物，并用
一句普通来源说明开头，例如“这是一个采用张艺谋导演的《英雄》和《十面埋伏》视觉
风格的原创电影场景。”随后依次描述环境、人物、动作与互动、镜头、光线和成片质感。
最终提示词不输出母风格、Theme 风格、视觉档案等内部术语，也不输出由 App 决定的
画幅比例、分辨率或横竖方向。

## Checkpoint 与恢复

顶层 run 在第一次模型调用之前创建。每次运行使用一个对用户可见的 run ID，并在
其下保存 profile 与 story 两个子运行：

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
│       ├── compiled-story.txt
│       └── result.json
└── story-runs/
    └── <story-run-id>/
        ├── request.json
        ├── rules.json
        ├── manifest.json
        ├── themes/
        ├── frames/
        └── attempts/
```

顶层 `rules.json` 包含 `profile`、`themes` 和 `frames` 三个字段。Profile 尚未生成
时发生中断，resume 也会继续使用创建 run 时冻结的 Profile 规则，不会重新读取
后来修改的规则文件。

如果 profile、Theme 批次或某个 Theme 的 Frame Sequence 已保存，恢复时不会重新
生成。失败输出会打印可直接执行的命令：

```bash
uv run t2i-film-style resume RUN_ID --runs-dir runs/film-style
```

恢复使用 run 中冻结的 provider 配置、并发设置和 film-style rules；当前 provider 配置
不一致时会明确拒绝继续，避免同一 run 混用生成条件。发布文件名包含子运行 ID，
因此重复使用同一基础 brief 与作品集合不会覆盖既有结果。
