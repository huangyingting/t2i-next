# 作品集合电影风格编译器

`t2i_film_style_pipeline` 是一个独立的一站式子模块。它接收导演署名、一个或多个
具体作品及可选的场景方向，通过一次结构化模型调用生成可复用视觉档案，再用包内
导演 Theme/Frame workflow 生成最终提示词。它不依赖外部 `film.txt`。

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

动态作品证据只作为 run 内部上下文保存。Theme 系统规则位于
`src/t2i_film_style_pipeline/rule_packs/system/themes.rules`，Frame 系统规则位于
`src/t2i_film_style_pipeline/rule_packs/system/frames.rules`。Theme 只保存一句
直接描述可见选择的视觉方案，不创建风格名称。每个 Frame 都是完全独立的自然语言
提示词，必须重新描述完整场景与全部人物，并用一句普通来源说明开头，例如“这是
一个采用张艺谋导演的《英雄》和《十面埋伏》视觉风格的原创电影场景。”随后依次
描述环境、人物、动作与互动、镜头、光线和成片质感。最终提示词不输出母风格、
Theme 风格、视觉档案等内部术语，也不输出由 App 决定的画幅比例、分辨率或横竖
方向。

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

如果 profile、Theme 批次或某个 Theme 的 Frame Sequence 已保存，恢复时不会重新
生成。失败输出会打印可直接执行的命令：

```bash
uv run t2i-film-style resume RUN_ID --runs-dir runs/film-style
```

恢复使用 run 中冻结的 provider 配置、并发设置和 story rules；当前 provider 配置
不一致时会明确拒绝继续，避免同一 run 混用生成条件。发布文件名包含子运行 ID，
因此重复使用同一基础 brief 与作品集合不会覆盖既有结果。
