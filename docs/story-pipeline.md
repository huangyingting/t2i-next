# 极简叙事提示词生成器

`t2i_story_pipeline` 直接把 Story Description 生成最终可用于文生图的长段落。
它不复用旧 `t2i_prompt_pipeline`，也没有 Story Blueprint、字段化 Scene、
renderer、provider review 或 revision 阶段。

## Interface

调用者只需要一个可恢复的 seam：

```python
store = LocalStoryRunStore(
    Path("story-runs"),
    Path("story-prompts"),
)
settings = StoryRunSettings(provider=provider_settings)
completed = await StoryStudio(model, store, settings).run(
    StoryRequest(
        story="故事要求",
        theme_count=100,
        frames_per_theme=6,
        female_count=1,
        male_count=1,
        content_level=ContentLevel.EROTIC,
    )
)
```

恢复时使用同一个 runs 目录和 manifest 中冻结的 settings：

```python
snapshot = LocalStoryRunStore(Path("story-runs")).inspect(run_id)
completed = await StoryStudio(
    model,
    LocalStoryRunStore(Path("story-runs")),
    snapshot.manifest.settings,
).resume(run_id)
```

结果按 Narrative Theme 分组；每个 Narrative Frame 只有：

- `frame_id`：`F01` 至请求数量；
- `prose`：一段无换行、无字段标签的最终叙事提示词。

## 生成流程

1. `themes`：每批最多十个，生成 `title`、最多三百字的 `premise` 和简短
   `style`。差异必须来自事件、人物互动和决定性瞬间，不是道具、色调或镜头替换。
2. `frames`：每个主题一次生成完整的一至六帧 Narrative Sequence。
   不存在本地拼接或二次 renderer。

100 themes × 6 frames 的基础调用量是十次 theme batch 加一百次 frame sequence，
共 110 次 provider 调用。`StoryStudio` 默认最多并发生成八个 frame sequences。
resume 只调用缺失的 Theme batch 和 Frame Sequence。

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

系统没有本地叙事质量门、关键词评分、相似度 gate、review 或 revision。provider
第一次看到的就是完整创作方向；输出只经过结构契约，不因文风或词语触发额外
生成调用。

## 运行记录与恢复

每个 run 在首次 provider 调用前分配 ID，并写入独立目录：

```text
story-runs/<run-id>/
├── request.json
├── manifest.json
├── attempts/
│   └── <operation>-<attempt>.json
├── themes/
│   └── T001.json
├── frames/
│   └── T001.json
└── result.json
```

`manifest.json` 冻结 provider、并发数、generation retry、theme batch size、
theme/frame token 上限和发布目录。每个成功 Theme 和每个 Theme 的完整 Frame
Sequence 都独立原子写入并 fsync；attempt 文件保存结果、错误和 token usage。
checkpoint 文件名、内容 ID、顺序、数量或 schema 不一致时会明确报告损坏，不会
静默跳过。

同一 run 执行期间持有非阻塞文件锁，避免两个进程同时恢复。失败会保留全部成功
checkpoint；`resume` 扫描它们，只生成缺失部分，并把上次同一 operation 的错误
反馈给模型。全部 checkpoint 完成后才写入 `result.json` 并发布 JSON/TXT。
已完成 run 的 `resume` 直接返回已发布结果，不调用 provider。

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

因此 100 themes × 6 frames 在没有 provider/schema 错误时始终保持
110 次基础调用。

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
  --runs-dir story-runs
```

或者从 UTF-8 文本文件读取完整 Story Description：

```bash
uv run t2i-story generate \
  --prompt-file story.txt \
  --themes 100 \
  --frames 6 \
  --content-level erotic \
  --concurrency 8
```

故事位置参数与 `--prompt-file` 互斥，并且必须提供其中一个。文件首尾空白会被
移除，内部换行会保留。空文件、目录、不可读文件和非 UTF-8 文件会在 provider
调用前报错。

主要选项：

```text
--prompt-file PATH     从 UTF-8 文本文件读取完整故事描述
--themes INTEGER       主题数量，1 至 100
--frames INTEGER       每个主题的画面数，1 至 6
--female-count INTEGER 可选女性人数约束，0 至 8
--male-count INTEGER   可选男性人数约束，0 至 8
--concurrency INTEGER  frame sequence 并发数，1 至 32
--content-level TEXT   aesthetic、erotic 或 hardcore
--language TEXT        chinese 或 english
--output-dir DIRECTORY 输出目录
--runs-dir DIRECTORY   增量 checkpoint 和运行记录目录
```

查看和恢复 run：

```bash
uv run t2i-story runs --runs-dir story-runs
uv run t2i-story resume RUN_ID --runs-dir story-runs
```

## 输出

```text
story-prompts/
├── story-<run-id>.json
└── story-<run-id>.txt
```

TXT 每帧一行，内容就是最终 prose，不含主题标题或 frame ID。
每条 prose 最多 32,768 个字符；frame sequence 请求和 provider 缺省输出上限
也都是 32,768 tokens。该 token 上限由同一次调用中的全部 frames 和 JSON
结构共同使用，不是每帧单独分配。

Provider 使用独立的 `STORY_OPENAI_*` 环境变量。凭证只从配置的环境变量读取，
不会写入产物或日志。
