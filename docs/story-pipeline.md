# 独立故事生成器

`t2i_story_pipeline` 是一条独立的 story-first 实现。它不导入或调用
`t2i_prompt_pipeline`，也不使用旧实现的 Foundation、Theme、Frame、规则、
checkpoint 或 renderer。

## 输入

唯一创作输入是一段 Story Description。建议直接包含：

- 故事发生的时间和地点；
- 所有入画人物，并明确为二十一岁以上成年人；
- 人物关系、互动、当前动作与可见回应；
- 情绪变化和整体氛围；
- 可见环境、关键物件和动作结果；
- 希望采用的拍摄角度、景别或镜头感；
- 光源、方向、色温和明暗关系。

亲密互动必须明确双方自愿、回应或可以随时停止。不支持未成年人、
年龄模糊人物、性胁迫或性暴力。

## Narrative Mode

每个 Narrative Scene 根据主要叙事动力选择一种模式：

| Mode | 用途 |
| --- | --- |
| `tableau` | 单幅姿态、材质反馈和明确视觉焦点 |
| `atmospheric` | 环境痕迹、人物内心和时间感 |
| `dramatic` | 有原文证据的前因、冲突动作和可见结果 |

所有模式都只能通过逐字来自原文的 `source_context` 表达前因、
关系与风险；自由生成字段不能另行补写人物经历。
Story Blueprint 中的 `source_relationship` 和 `source_action` 采用同一规则。
Studio 会验证这些来源片段确实存在于 Story Description。

每个 Scene 始终是一张静态画面中的一个决定性瞬间，不是多镜头段落。
`camera_composition` 只描述当前机位、景别、焦点和空间关系；不得包含切镜、
推镜、镜头运动或连续时间推进。环境证据、物理反馈和感官证据各最多四项，
动作必须恰好一项，以避免单帧变成连续动作或细节清单。

## Creative Intent 与 Narrative Theme

Story Blueprint 只保存所有主题共享的故事事实。每个 Narrative Theme 再定义：

- `emotional_core`：观众最终感受到的单一核心情绪；
- `narrative_tension`：画面中相互拉扯的两种力量或状态；
- `decisive_moment`：为什么选择这一瞬间；
- `visual_motif`：从当前人物、动作、道具或环境中产生的视觉母题；
- `motif_progression`：母题如何跨连续画面发生可见变化；
- `restraint`：主动舍弃哪些漂亮但无助于故事的细节。

主题按每批最多十个生成，并携带此前主题的精简 ledger，避免跨批次重复。
系统会移除数字和标点后检查标题及“决定性瞬间 + 视觉母题”组合，拒绝
只增加编号的伪变化。生成完成后还会拒绝同一主题内重复画面，以及不同主题
拥有相同画面序列的结果。

## 生成与反馈闭环

生成流程使用以下结构化模型调用：

1. `interpret`：把 Story Description 编译为一个共享 Story Blueprint，
   包含人物、关系、有序 Story Beats、环境、氛围与整组摄影意图。
2. `themes`：分批产生指定数量且彼此实质不同的 Narrative Themes。
3. `scenes`：针对每个 Narrative Theme 生成指定数量的 Narrative Scenes。
4. `review`：逐主题、逐场景评估十个质量维度。

`interpret`、`themes` 和 `scenes` 若违反来源、语言、静态画面或可成像契约，
Studio 会把具体问题反馈给 provider 并执行有界重试；连续违规才会失败关闭。

十个评审维度是时空落地、环境叙事、因果动作、物理反馈、摄影叙事整合、
感官视觉化、主题收束、语言连贯、创意统一性和故事独有性。
每项满分 5 分，4 分为发布标准。
任何低于 4 分的维度必须产生包含 `problem` 和 `required_change` 的 typed issue。

系统把当前 Narrative Sequence 和 issues 发送给 `revise`，要求只修正低分部分，
然后重新执行 `review`。默认最多修订两次；仍未达标则失败，不发布低质量结果。

本地 renderer 按固定顺序生成两种输出：

- 连续 prose：时空开场 → 环境证据 → 人物进入与前因 → 动作和反馈 →
  材质物理 → 摄影光线 → 感官证据 → 主题收束；
- 结构化 prompt：创意主线、时间地点、人物、调度、互动动作、情绪主题、
  环境、摄影和光线。

画面中的招牌、信件、屏幕或海报文字使用结构化 `visible_text` 保存。
`content` 必须逐字保留，renderer 会用英文双引号括起文字，并同时输出其
承载物、画面位置以及字体或材质；没有画面文字时使用空列表。

## 配置

在 `.env` 中设置：

```dotenv
STORY_OPENAI_MODEL=gpt-4.1-mini
STORY_OPENAI_BASE_URL=https://api.openai.com/v1
STORY_OPENAI_API_KEY_ENV=OPENAI_API_KEY
STORY_OPENAI_AUTH_MODE=bearer
STORY_OPENAI_REASONING_EFFORT=none
STORY_OPENAI_TEMPERATURE=0.5
STORY_OPENAI_OUTPUT_TOKEN_LIMIT=12000
STORY_OPENAI_TIMEOUT_SECONDS=180
STORY_OPENAI_TRANSPORT_RETRIES=2
```

`STORY_OPENAI_REASONING_EFFORT` 与 `STORY_OPENAI_THINKING_MODE` 只能设置一个。
启用任一 reasoning control 时不会发送 `temperature`。十维 review 使用较大的
输出预算，但 `problem` 和 `required_change` 有严格长度上限，避免评审写成长文。

`STORY_OPENAI_API_KEY_ENV` 的值是实际保存密钥的环境变量名。默认使用
`OPENAI_API_KEY`。

## 使用

```bash
uv run t2i-story generate "完整故事描述" --themes 100 --frames 6
```

可选参数：

```text
--themes INTEGER            创意主题数量，1 至 100，默认 1
--frames INTEGER            每个主题的连续画面数，1 至 6，默认 6
--language chinese|english  自然语言输出，默认 chinese
--max-revisions INTEGER     最大评审修订次数，0 至 5，默认 2
--output-dir DIRECTORY      输出目录，默认 story-prompts
```

成功后生成：

```text
story-prompts/
├── story-<run-id>.json
├── story-<run-id>.prose.txt
└── story-<run-id>.prompt.txt
```

JSON 保存 Story Blueprint、Narrative Scenes、评审反馈、修订次数、
两种最终输出和 token usage。Prose TXT 每行保存一段连续电影化叙事；
Prompt TXT 每行保存一条可独立提交给文生图模型的提示词。使用
`--themes 100 --frames 6` 时，两个 TXT 文件都固定包含 600 行，
顺序为 T001/S01 至 T100/S06；JSON 保留完整主题与场景身份。

## 开发验证

```bash
uv run ruff check src/t2i_story_pipeline tests/story_factories.py \
  tests/test_story_*.py
uv run python -m pytest tests/test_story_*.py
```
