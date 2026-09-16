# 作品集合电影风格编译器

`t2i_film_style_pipeline` 是一个独立子模块。它接收导演署名、一个或多个具体作品
以及现行 Story Description，通过一次结构化模型调用生成可复用视觉档案，再把档案
编译为可直接传给 `t2i_story_pipeline` 的完整文本。

结构化档案同时包含：

- 每部输入电影各自的一句风格总结，顺序与 `--work` 一致；
- 跨全部输入作品合成的一句母风格总结；
- 母风格名称；
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
  --brief-file story-inputs/classic-film-erotic-reinterpretation.txt \
  --language chinese \
  --output-dir film-style-inputs \
  --runs-dir runs/film-style
```

`--work` 可以重复。支持 `TITLE` 和 `TITLE (YEAR)` 两种格式。基础文件必须以
`BRIEF` 和一个空行开始，模块不支持旧 Story Description 格式。

完成后 CLI 输出：

- run ID；
- `runs/film-style/<run-id>/profile.json`；
- `film-style-inputs/<brief>__<director>__film_style__<run-id>.txt`。

## 与 story pipeline 串联

将 CLI 返回的 Story Description 路径直接传给 story pipeline：

```bash
uv run t2i-story generate \
  --prompt-file film-style-inputs/COMPILED_FILE.txt \
  --themes 8 \
  --frames 1 \
  --female-count 1 \
  --male-count 1 \
  --content-level erotic \
  --language chinese
```

编译器保留原始 `BRIEF` 头，并在基础描述之前注入
`WORK-SPECIFIC FILM STYLE PROFILE`。Theme 必须创建自己的精确原创风格名称；
Frame 必须明确写出导演、电影、母风格名称、母风格总结和 Theme 风格名称，并通过
至少五项可见特征证明风格。

## 持久化

每次运行创建独立目录：

```text
runs/film-style/<run-id>/
├── request.json
├── profile.json
└── result.json
```

发布文件名包含 run ID，因此重复使用同一基础 brief 与导演不会覆盖既有结果。
