# 极简叙事提示词生成器

`t2i_story_pipeline` 直接把 Story Description 生成最终可用于文生图的长段落。
它不复用旧 `t2i_prompt_pipeline`，也没有 Story Blueprint、字段化 Scene、
renderer、provider review 或 revision 阶段。

## Interface

调用者只需要一个 seam：

```python
result = await StoryStudio(model).generate(
    StoryRequest(
        story="故事要求",
        theme_count=100,
        frames_per_theme=6,
        content_level=ContentLevel.EROTIC,
    )
)
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
共 110 次 provider 调用。`StoryStudio` 默认最多并发生成十个 frame sequences。

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

`erotic` 和 `hardcore` 会让 Story Description 必须显式声明参与者清醒、自愿、
持续回应或可以停止，否则在任何 provider 调用前失败。所有等级都继续执行相同的
硬安全契约：人物必须二十一岁以上，禁止未成年人、性胁迫、性暴力和无法退出的
亲密互动。`hardcore` 不会放宽这些规则。

## 叙事方式

质量要求全部写在 frame prompt 中。每帧是一段自然流动的故事，而不是视觉规格表：

1. 以该主题选择的简短风格开头，再落定年代、地点和当前时刻；
2. 用一句静态因果句明确写出谁与谁是什么身份或关系、触发事实、当前目标、
   必须现在完成的原因、阻力与失败后果，再用至少一个物件证明这些事实；
3. 每帧重新交代所有人物的身份、明确成年年龄、性别、稳定长相、发型、穿戴、
   单一静止姿态，以及各自不同且与动机相连的表情和视线；
4. 以“此刻”开头的唯一动作句描写一个决定性动作，并在同一句写完方向、
   对象、接触点、力度、静态回应和可见结果；动作必须使线索、风险、
   人物判断或关系至少一项发生变化；
5. 倒数第二句以“镜头采用”开头，明确景别、角度、机位、构图、焦点、
   前中后景和景深；
6. 最后一句以“光线”开头，明确光源、方向、软硬、明暗、色调，并以可见
   细节收束氛围与人物关系。

不能以“三名成年人正在寻找”“私密行迹隐约可见”等泛化句替代故事因果，
也不能把帝王、妃嫔、学生、记者等已知身份降格成无身份的男性或女性。
镜头与光线需要同时容纳故事动作和人物表情，而不是只展示手、衣料或装饰。
六帧还需要拥有不同的动作、发现和情绪转折，不能在同一接触点反复寻找或触摸。
静态因果句不能复述连续动作、对话或提前泄露当前帧结果；新线索与关系变化只能
发生在唯一动作句中。

这些是 prompt 指导，不是会触发整组重新生成的本地质量 gate。场景需要时可以写得
很长，但不能使用“主题：”“人物：”“环境：”“摄影：”等字段标签。人物不能在
单帧内改变姿态，正文也不引用上一帧或用推进词串联连续动作。

可由程序判定的质量要求只有一份定义：推进词、人物段姿态变化词、次动作词、
动作串联词、来源敏感词、景别和角度词表同时用于初始 provider prompt 与本地
评估。模型在第一次生成前即可看到评估标准。评估发现的问题写入
`StoryResult.quality_feedback`，不拒绝 Narrative Theme 或 Narrative Frame，
不触发修正调用，也不阻止最终 prose 发布。反馈用于观察真实输出、评估 prompt
效果并指导下一版初始 prompt，而不是建立 review/revision 阶段。

一组六帧应形成建立局面、增加压力、改变关系、抵达决定性瞬间、呈现后果和留下
余波的微型故事。每帧同时必须能够独立理解和生成。

## 时间、地点与时代一致性

Narrative Theme 必须建立“谁、何时何地”的故事种子；每个 Narrative Frame
仍需独立重写年代、具体地点和当前时刻，不能依赖前帧补足。

theme 与 frame 的初始 prompt 同时要求建筑、室内陈设、家具、器物、材料、服装、
发型、交通工具、武器、通信与照明技术、社会称谓和人物用语符合 Story Description
给定的时代、地域、季节、时辰与社会环境。服装冷暖、植物和取暖方式必须符合季节，
天然光与人工光源必须符合时辰，官职、礼仪和称谓必须属于正确朝代。不确定史实时
使用时代成立的通用描述，不猜测品牌、型号、精确年代或专名。

对于具有古代、朝代、民国或 1989 年以前年份锚点的故事，prompt 会同步列出一组
高置信度现代技术词，输出命中时写入非阻断 `quality_feedback`，不会触发额外
provider 调用。Story Description 自己明确指定的物件不视为错误；明确写明穿越、
架空、时代错置、历史混搭、蒸汽朋克或赛博朋克时则允许有意的时代冲突。

## 硬契约与质量反馈

以下规则是会阻断结果并进行有界 provider 重试的硬契约：

- Pydantic typed schema；
- 精确主题数、帧数和连续 ID；
- 非空单段 prose；
- 所有人物明确二十一岁以上；
- 情色或亲密互动必须清醒、自愿、持续回应且可以停止；
- 拒绝未成年人、性胁迫、性暴力和无法退出的亲密互动；
- provider 结构错误的有界重试和 token usage 统计。

以下规则只产生非阻断 `quality_feedback`：

- 中文主题和 prose 不混入 Story Description 之外的英文词；
- `aesthetic` 不越级呈现明确性行为，`erotic` 与 `hardcore` 达到各自要求的
  可见内容下限；
- 历史故事不混入 Story Description 未指定的高置信度现代技术与物件；
- 不虚构 Story Description 未提供的等级、年号、御赐经历、关系史或伤痕；
- prose 以主题风格开头，只含一个以“此刻，”开头且使用“正”或“正在”的
  决定性动作句；
- 人物描述不含姿态变化和次动作，动作句不含推进词或动作链；
- 倒数第二句是含景别与角度的镜头句，最后一句是光线句；
- 同一 Narrative Sequence 的动作句不重复。

因此 100 themes × 6 frames 在没有 provider/schema/安全错误时始终保持
110 次基础调用；质量反馈本身不增加 token 成本。

## CLI

```bash
uv run t2i-story generate \
  "1930年代秋夜，两名三十岁的成年人在旧车站重逢。他们双方自愿拥抱，彼此回应且任何一方都可以停止。" \
  --themes 100 \
  --frames 6 \
  --content-level erotic \
  --concurrency 10
```

主要选项：

```text
--themes INTEGER       主题数量，1 至 100
--frames INTEGER       每个主题的画面数，1 至 6
--concurrency INTEGER  frame sequence 并发数，1 至 32
--content-level TEXT   aesthetic、erotic 或 hardcore
--language TEXT        chinese 或 english
--output-dir DIRECTORY 输出目录
```

## 输出

```text
story-prompts/
├── story-<run-id>.json
└── story-<run-id>.txt
```

TXT 每帧一行，内容就是最终 prose，不含主题标题或 frame ID。
JSON 额外包含 `quality_feedback`；每项记录阶段、`item_id` 和问题列表。

Provider 使用独立的 `STORY_OPENAI_*` 环境变量。凭证只从配置的环境变量读取，
不会写入产物或日志。
