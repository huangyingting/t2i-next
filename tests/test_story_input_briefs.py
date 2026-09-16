from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_story_inputs_use_only_the_current_authoring_contract() -> None:
    story_inputs = sorted((REPOSITORY_ROOT / "story-inputs").glob("*.txt"))

    assert story_inputs
    assert not (REPOSITORY_ROOT / "story-inputs" / "multi-view-scenes.txt").exists()

    for story_input in story_inputs:
        brief = story_input.read_text(encoding="utf-8")

        assert brief.startswith("BRIEF\n\n"), story_input.name
        assert "Theme" in brief, story_input.name
        assert "Frame" in brief, story_input.name
        assert "CLI" not in brief, story_input.name
        assert "Generate exactly the Theme count" not in brief, story_input.name
        assert "Generate exactly the Theme and Frames-per-Theme counts" not in brief, (
            story_input.name
        )
        assert "cast as a creative seed" not in brief, story_input.name
        assert "time advances through causally connected beats" not in brief, (
            story_input.name
        )


def test_lifestyle_story_is_social_photography_not_ui() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "lifestyle-story.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "RUN-LEVEL ROUTING: Read request.content_level before creation" in normalized
    assert "that value is immutable across every Theme and Frame in the batch" in normalized
    assert "If it is erotic, ignore every hardcore permission and never output oral sex" in normalized
    assert "If it is hardcore, ignore erotic limits and require one explicit direct act in every Theme and Frame" in normalized
    assert "Reject the whole batch if an item uses inactive branch" in normalized
    assert "Themes and Frames are incoming parameters, not fixed lists" in normalized
    assert "Instagram and Xiaohongshu" in normalized
    assert "not a literal screen capture of either application" in normalized
    assert "INSTAGRAM EDITORIAL" in brief
    assert "XIAOHONGSHU LIFESTYLE" in brief
    assert "HYBRID SOCIAL EDITORIAL" in brief
    assert "outfit-of-the-day" in normalized
    assert "cafe visit, city walk, weekend trip" in normalized
    assert "Use exactly the requested number of adult women and adult men" in normalized
    assert "Every person is unmistakably twenty-five or older" in normalized
    assert "every woman is Chinese" in normalized
    assert "every Frame must identify her naturally as a Chinese woman" in normalized
    assert "Apply the same Chinese nationality default independently to every man" in normalized
    assert "Never infer another nationality from a foreign-inspired outfit" in normalized
    assert "set every Theme in China" in normalized
    assert "without changing the cast's default Chinese nationality" in normalized
    assert "When the requested cast is one woman and zero men" in normalized
    assert "Use an arm's-length selfie, mirror selfie, timer, tripod, or fixed camera" in normalized
    assert "Do not invent a nearby friend, companion, photographer, lover" in normalized
    assert "one concrete occasion per Theme" in normalized
    assert "The location and activity must provide concrete evidence" in normalized
    assert "FASHION, BEAUTY, AND GROOMING" in brief
    assert "nearby-friend handheld portrait" in normalized
    assert "only when that friend is part of the requested visible cast" in normalized
    assert "only when that companion is part of the requested visible cast" in normalized
    assert "mirror selfie with one physically coherent reflection" in normalized
    assert "timer or fixed-camera full-body outfit portrait" in normalized
    assert "For one woman and zero men, choose only an arm's-length selfie" in normalized
    assert "Never call the view nearby-friend, companion-taken" in normalized
    assert "credible modern phone-camera or compact-camera optics" in normalized
    assert "ANATOMY AND BODY CONTINUITY" in brief
    assert (
        "Every visible arm or leg must trace continuously from its shoulder or hip"
        in normalized
    )
    assert (
        "Never create a detached, source-less, repeated, fused, or extra limb"
        in normalized
    )
    assert "describe the left and right legs separately" in normalized
    assert 'a collective phrase such as "her legs are parted" is not enough' in normalized
    assert (
        "Do not combine raised knees, crossed legs, a projecting foreground leg"
        in normalized
    )
    assert (
        "never hide the connecting joint while showing an isolated lower limb or foot"
        in normalized
    )
    assert (
        "Avoid body-crossing foreground limbs, extreme low foot-side angles"
        in normalized
    )
    assert "simplify the pose or move the camera" in normalized
    assert "small signs of lived reality" in normalized
    assert "CONTENT LEVEL" in brief
    assert "Aesthetic:" in brief
    assert "Erotic:" in brief
    assert "Hardcore:" in brief
    assert "Hardcore must contain an unmistakable explicit adult act already in progress" in normalized
    assert "touching an inner thigh" in normalized
    assert "For one woman and zero men, show solitary masturbation already in progress" in normalized
    assert "directly stimulates her external genitals" in normalized
    assert "Add no partner, assisting hand, mouth, reflected person" in normalized
    assert "never add a participant to intensify the action" in normalized
    assert "Every Hardcore Frame must directly name the active hand or toy" in normalized
    assert "the contacted genital structure such as the clitoris, vulva" in normalized
    assert "Wet fingers, arousal, parted legs, pubic hair" in normalized
    assert "parallel finished alternatives rather than chronological steps" in normalized
    assert "silently reject and rewrite it if any visible limb" in normalized
    assert "separate left-leg and right-leg descriptions establish exactly two" in normalized
    assert 'literal phrases "left leg" and "right leg"' in normalized
    assert "naming only the feet, knees, thighs, or collective legs" in normalized
    assert "if the camera method contradicts itself" in normalized
    assert "When English is requested, use English-only ASCII prose" in normalized
    assert "replacement glyphs, non-English script, and translated fragments" in normalized
    assert "The words Instagram and Xiaohongshu are invisible art direction only" in normalized
    assert "Never write the words Instagram or Xiaohongshu in a Theme title" in normalized
    assert "Translate the selected direction into visible photography" in normalized
    assert "without platform names in generated fields" in normalized
    assert "Target 220-300 words for every English Frame" in normalized
    assert "between 180 and 360 words, with 360 as an absolute hard ceiling" in normalized
    assert "count its words and rewrite it if the total falls outside the hard range" in normalized
    for forbidden in (
        "app interface",
        "profile page",
        "username",
        "hashtag",
        "like count",
        "comment",
        "carousel dot",
        "platform logo",
        "watermark",
        "QR code",
    ):
        assert forbidden in normalized


def test_intimate_liquid_editorial_uses_open_ended_scene_grammar() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "intimate-liquid-editorial.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert not (
        REPOSITORY_ROOT
        / "story-inputs"
        / "overhead-radial-splash-fashion.txt"
    ).exists()
    assert not (
        REPOSITORY_ROOT
        / "story-inputs"
        / "overhead-intimate-liquid-editorial.txt"
    ).exists()
    assert not (
        REPOSITORY_ROOT
        / "story-inputs"
        / "high-angle-intimate-liquid-editorial.txt"
    ).exists()
    assert "成人亲密液体动势时尚编辑摄影" in normalized
    assert "多样且符合场景的拍摄视点" in normalized
    assert "固定 high-angle 俯拍" in normalized
    assert "EDITORIAL STYLE LOCK" in brief
    assert "高预算、经过完整造型与美术指导的成人 时尚编辑摄影" in normalized
    assert "露骨动作只是画面事件，不得取代时尚叙事" in normalized
    assert "一件 hero garment 或一个 hero accessory" in normalized
    assert "Hardcore 即使下身赤裸" in normalized
    assert "不能只剩 裸体、性玩具和液体" in normalized
    assert "高端成人时尚杂志、奢华美妆大片" in normalized
    assert "amateur porn screenshot" in normalized
    assert "不能使用 clinical、medical、forensic" in normalized
    assert "时尚感必须在缩略图尺度仍然成立" in normalized
    assert "一个强造型焦点、两个辅助 材质或色彩关系和一项精致美容细节" in normalized
    assert "这是开放式生成语法，不是封闭场景清单" in normalized
    assert "可扩展的创作种子，不是穷举" in normalized
    assert "就可以自由发明未列出的 场景" in normalized
    assert "不把作品限制在固定摄影棚、白色床垫" in normalized
    assert "开放场景生成器" in brief
    assert "可控摄影空间" in normalized
    assert "建筑室内" in normalized
    assert "文化与休闲空间" in normalized
    assert "静止交通空间" in normalized
    assert "户外受控场地" in normalized
    assert "水边与浅水空间" in normalized
    assert "物理搭建的幻想空间" in normalized
    assert "场景—液体因果锁" in brief
    assert "液体不是为了制造喷射效果而额外塞入画面的装饰" in normalized
    assert "优先使用 场所原生且用途明确的来源" in normalized
    assert "器具若不属于该地点的正常设施，就必须改用更合理的器具或更换 地点" in normalized
    assert "不能在温室、街道、屋顶、住宅、雪地、交通工具或文化空间中凭空增加工业雨淋管" in normalized
    assert "只有摄影棚、特效测试间、舞台后场或明确封闭拍摄的布景" in normalized
    assert "储水、低压供水、固定支架、操作或触发方式、防滑承载面和排水路径" in normalized
    assert "如果主要液体来自人物身体或储液式成人玩具，就不要再叠加无关的环境喷水" in normalized
    assert "不要求每张图都有巨大喷射装置或爆炸水冠" in normalized
    assert "自然呈现液体从出现到消失的完整流程" in normalized
    assert "场所用途说明液体为何 存在" in normalized
    assert "合理的私密性、清洁条件和可退出性" in normalized
    assert "不能用“艺术装置”“时尚拍摄”或“定时释放” 作为万能借口" in normalized
    assert "液体来源—地点适配矩阵" in brief
    assert "默认只选择私人浴室、酒店浴室、独立湿房、私人 水疗套间" in normalized
    assert "完整防水保护层和吸水护理垫的私人卧室床、酒店套房床" in normalized
    assert "此处是严格地点白名单" in normalized
    assert "不得放在中庭、温室、开放广场、街道、稻田或农地、普通屋顶" in normalized
    assert "添加 private、locked、secluded、exclusive、closed" in normalized
    assert "不能使其合规" in normalized
    assert "只使用该地点正常存在的一套供水系统" in normalized
    assert "不得让水枪、喷头、 水桶、倾倒板或实验器皿仅因造型新奇" in normalized
    assert "不得在自然场景中加入水枪式成人道具来制造额外喷射" in normalized
    assert "自然雨只能直接落在露天空间、无顶庭院、开启的天窗或明确敞开的屋面缺口下" in normalized
    assert "完整 玻璃顶、封闭车顶、实体屋檐或密闭窗户外侧的雨水" in normalized
    assert "不能同时穿过 屏障落到室内人物或地面" in normalized
    assert "液体的实际落点必须连接到画面可见的地漏" in normalized
    assert "只有普通洗手间而没有地漏时，不能让大量液体在地面聚集" in normalized
    assert "床上人物体液场景必须直接显示一套普通且可信的床面保护" in normalized
    assert "完整包住床垫的防水床笠或 医用级防水保护罩" in normalized
    assert "一至两块大尺寸吸水护理垫、厚浴巾或可清洗防水毯" in normalized
    assert "不得让未保护的床垫、 普通羽绒被、枕头或地毯承接大量液体" in normalized
    assert "不能在床头、床垫或天花凭空安装地漏、喷头阵列" in normalized
    assert "床上的精液只有 在运行请求包含至少一名可见成年男性时才能出现" in normalized
    assert "零男性请求绝不生成精液、画外男性或无来源白色液体" in normalized
    assert "可以在真实来源基础上形成夸张、醒目的弧线" in normalized
    assert "可以跨过受保护床面的较大部分" in normalized
    assert "不能射向天花、越过保护层落到 无关区域" in normalized
    assert "床上可使用手指或一件常规成人玩具完成主要 动作，但不增加喷水器具" in normalized
    assert "第一步固定一个不可更改的“来源—地点”配对" in normalized
    assert "不得先选其他地点再写成 改造、租用、封闭、清空或临时布置后的湿景棚" in normalized
    assert "不能由装卸区、仓库、中庭、温室、舞蹈室、屋顶、 交通工具或其他空间改名而来" in normalized
    assert "任何不在白名单中的地点都必须改选场所原生环境水或 日常清水工具" in normalized
    assert "身体液体允许现实基础上的编辑摄影夸张" in normalized
    assert "更高但仍受重力控制的弧线、密集冻结液滴" in normalized
    assert "dramatic、 forceful、high-arc、dense、radiating、burst" in normalized
    assert "STYLIZED BODY-FLUID LOCK:" in normalized
    assert "Heighten the arc, droplet density, frozen timing, radial shape" in normalized
    assert "Never turn body fluid into pressurized plumbing" in normalized
    assert "夸张重点放在喷射形态、液滴分离、姿势、表情、镜头角度、灯光" in normalized
    assert "人体液体可以承担径向构图的主要视觉动势" in normalized
    assert "不能穿过身体或物体、逆重力改变方向" in normalized
    assert "不得解释自己如何满足 brief" in normalized
    assert "不得输出 自检、幕后安排、拍摄后清理计划或规则术语" in normalized
    assert "第一句必须直接从具体地点、人物或相机视点开始" in normalized
    assert "不得先写衣着锁、Theme 编号、Frame 编号、标题、许可声明" in normalized
    assert "衣着锁放在自然摄影描述之后" in normalized
    assert "Hardcore 的主要动作与接触点必须直接可见" in normalized
    assert "不能 被衣摆、身体、手掌、阴影、水花、道具或构图遮住" in normalized
    assert "不得用手臂紧张、衣物下的动作、 水面波纹、表情或文字声明间接暗示" in normalized
    assert "中央水冠、离体高弧、径向 burst 或明确 jet 只用于从两腿之间正确生殖器开口" in normalized
    assert "人物不必躺在床上" in normalized
    assert "构图、视点与镜头" in brief
    assert "拍摄角度是开放变化轴" in normalized
    assert "不把 high-angle、overhead 或正俯拍设为默认" in normalized
    assert "垂直高度、俯仰角、绕人物方位、拍摄距离、焦段、裁切尺度和主体落点" in normalized
    assert "70–90 度 overhead 或顶视" in normalized
    assert "25–65 度 elevated oblique 高位斜拍" in normalized
    assert "接近水平的 eye-level 平视" in normalized
    assert "low-angle 低机位" in normalized
    assert "profile 侧面、front three-quarter 前侧三分之四" in normalized
    assert "近距离 beauty、material 或 action detail" in normalized
    assert "场景—姿势—机位匹配矩阵" in brief
    assert "受保护床面：轮换对角仰卧桥式" in normalized
    assert "不能每次都仰卧张腿" in normalized
    assert "浴缸与水疗床：轮换沿椭圆长轴半躺" in normalized
    assert "必须避开高缸壁 对动作区域的遮挡" in normalized
    assert "淋浴间与独立湿房：轮换墙面单手支撑的站立弓步" in normalized
    assert "湿滑地面禁止无支撑单脚站立" in normalized
    assert "私人泳池与浅水区：轮换仰漂星形" in normalized
    assert "不得让水面反光遮没脸和动作起点" in normalized
    assert "原生湿景棚与透明平台：轮换透明台上的非对称 X 形" in normalized
    assert "不固定为 50mm 正俯拍" in normalized
    assert "100 种高感官刺激姿势库" in normalized
    pose_ids = [
        token
        for token in brief.split()
        if len(token) == 4 and token.startswith("P") and token[1:].isdigit()
    ]
    assert pose_ids == [f"P{index:03d}" for index in range(1, 101)]
    assert "P001 正面宽腿站姿" in normalized
    assert "P050 侧卧镜面姿势" in normalized
    assert "P081 背后环抱站姿" in normalized
    assert "P100 床面非对称环抱构图" in normalized
    assert "每个 Frame 只选择一个主姿势" in normalized
    assert "跨 Theme 轮换六大姿势家族" in normalized
    assert "相邻 Theme 不得重复同一姿势家族" in normalized
    assert "不得连续生成深蹲、仰卧张腿、跪姿后仰或 站立后弯" in normalized
    assert "机位在 overhead 顶视、elevated oblique 高位斜拍、eye-level 平视" in normalized
    assert "low-angle 低机位、 profile 侧面" in normalized
    assert "waterline 水面高度和近距离 detail" in normalized
    assert "24–35mm 环境广景、40–55mm 全身中景、60–85mm 紧凑人像与动作研究" in normalized
    assert "85–105mm beauty 或材质细节" in normalized
    assert "不能隔着大腿、缸壁、床头、手臂、水花或反光拍摄" in normalized
    assert "不强制双腿形成固定 V 形" in normalized
    assert "不强制双臂水平展开" in normalized
    assert "不强制人物仰卧" in normalized
    assert "每个 Theme 只选择一个主要液体来源家族" in normalized
    assert "环境清水：自然雨水、向下落水、瀑布薄幕" in normalized
    assert "手持清水工具：只用于向下流动或倾倒的低压软水管" in normalized
    assert "储液式成人玩具" in normalized
    assert "女性排尿" in normalized
    assert "从可见尿道口开始" in normalized
    assert "不得把尿液写成来自阴道" in normalized
    assert "女性阴道液体" in normalized
    assert "从可见阴道口或外阴区域开始" in normalized
    assert "主视觉喷射起点锁" in normalized
    assert "喷射起点就必须在镜头中清楚位于该人物两腿之间 的生殖器部位" in normalized
    assert "从可见的正确解剖开口连续连接到液柱或液滴" in normalized
    assert "被闭合、 交叉双腿遮住的位置发出" in normalized
    assert "相机、姿势、水花和道具都不得遮挡这个起点" in normalized
    assert "环境清水、 手持清水工具和储液式成人玩具只能形成下落" in normalized
    assert "不得形成主要 jet、spray、high arc 或 burst" in normalized
    assert "任何人体液体喷射都从镜头中清楚可见、位于两腿之间的正确生殖器解剖开口开始" in normalized
    assert "男性精液" in normalized
    assert "运行请求包含至少一名可见成年男性" in normalized
    assert "从该男性可见生殖器开始" in normalized
    assert "液体形态在 Theme 和 Frame 间轮换" in normalized
    assert "软水管或手持喷头可在 Erotic 或 Hardcore 中作为自愿外部自慰工具" in normalized
    assert "不得把高压水流、硬质喷嘴或软管插入身体" in normalized
    assert "性玩具设计、动作与场景适配" in brief
    assert "性玩具是可选变化轴，不是每个 Theme 的强制道具" in normalized
    assert "一件主要性玩具或由多个不可分离部件组成的一套单一系统" in normalized
    assert "不能只写 generic sex toy" in normalized
    assert "掌心 bullet vibrator、短柄 wand vibrator、指套 vibrator" in normalized
    assert "直形或弯形 silicone dildo" in normalized
    assert "带宽大限位底座的 anal plug" in normalized
    assert "suction-base dildo" in normalized
    assert "单件 strap-on" in normalized
    assert "具有可见透明储液腔、挤压球、短导管和明确出液口" in normalized
    assert "只在出液口附近流出或滴落" in normalized
    assert "带可见拉环或回收绳的 vibrating egg" in normalized
    assert "不得整批重复透明 dildo、银色 bullet 或黑色 wand" in normalized
    assert "性玩具—场景匹配" in brief
    assert "吸盘不能直接粘在柔软床垫、床单或枕头上" in normalized
    assert "不得让市电电线、插线板、充电器或非防水 遥控器接触潮湿区域" in normalized
    assert "浴缸、泳池和浅水区只使用整体防水" in normalized
    assert "全部部件必须属于一个可追踪系统" in normalized
    assert "性玩具—姿势—机位匹配" in brief
    assert "持玩具的手、 玩具头和外部接触点三者必须同时可见" in normalized
    assert "必须显示玩具底座、进入方向和解剖接触边界" in normalized
    assert "同时显示 吸盘、刚性固定面、玩具轴线、身体承重点和单一接触位置" in normalized
    assert "同时看见储液腔、导管或内部通路、出液口、手部触发和液体落点" in normalized
    assert "不能只靠文字 声明体内藏有看不见的玩具" in normalized
    assert "普通 vibrator、dildo、plug、wand 或 wearable toy 不会自行喷液" in normalized
    assert "普通玩具表面的 润滑剂只能形成贴附薄层、拉丝或滴落" in normalized
    assert "禁止尿道插入、宫颈穿透" in normalized
    assert "肛门玩具必须有清楚可见且大于插入部分的限位底座" in normalized
    assert "Aesthetic 不出现可识别性玩具" in normalized
    assert "Erotic 最多使用一件仅作外部接触的玩具" in normalized
    assert "Hardcore 可从外部刺激、单一阴道或肛门插入" in normalized
    assert "连续十个包含 性玩具的 Theme 至少覆盖五个玩具家族" in normalized
    assert "相邻玩具 Theme 不得重复玩具家族、材质、颜色、固定方式和姿势组合" in normalized
    assert "灯光服从场景而不是固定 5500K" in normalized
    assert "色温可在约 2800–7500K 范围内变化" in normalized
    assert "CONTENT LEVEL" in brief
    assert "Aesthetic：" in brief
    assert "Erotic：" in brief
    assert "Hardcore：" in brief
    assert "AESTHETIC WARDROBE LOCK:" in normalized
    assert "opaque fabric fully covers all nipples, external genitals, pubic hair, and anus" in normalized
    assert "EROTIC WARDROBE LOCK:" in normalized
    assert "visibly retains one or two sheer, translucent, open, wet-clinging, lifted, or partially lowered" in normalized
    assert "HARDCORE WARDROBE LOCK:" in normalized
    assert "The featured adult woman's lower body is bare" in normalized
    assert "only one minimal upper garment plus zero to four accessories" in normalized
    assert "主表演者必须实际保留一至两件透明、半透明、湿贴、敞开、撩起或 半褪下" in normalized
    assert "主表演者下身必须完全赤裸" in normalized
    assert "当前 content level 唯一正确且逐字输出的衣着锁" in normalized
    assert "每个 Frame 必须表现明确成人裸露和一个清楚可见的主要露骨动作" in normalized
    assert "裸体、湿衣或 挑逗姿势代替 Hardcore 动作" in normalized
    assert "外部自慰、一至两根手指的单一插入" in normalized
    assert "本身也可以独立作为该 Frame 唯一的主要 Hardcore 液体动作" in normalized
    assert "环境清水、普通倾倒清水和其他安全舞台液本身绝不能替代 Hardcore 动作" in normalized
    assert "必须同时清楚显示上述外部自慰、单一插入或单一成人接触之一" in normalized
    assert "仅把玩具靠近身体、让液体流过裸体不算 Hardcore 动作" in normalized
    assert "同一解剖中心可有与主要动作直接相关的辅助 手部接触" in normalized
    assert "HARDCORE 液体严格单选" in normalized
    assert "整张 Frame 只描述这一类别的流动" in normalized
    assert "不得同时滴落、喷射、飞溅、形成涟漪或与主要液体混合" in normalized
    assert "不得在 同一 Frame 同时出现尿流与阴道液体" in normalized
    assert "不能用 private、 locked、secluded 或 closed 修饰温室" in normalized
    assert "禁止冷冻舱、冷库、桑拿、高温房、干冰、液氮" in normalized
    assert "各自唯一且前后一致的精确整数年龄" in normalized
    assert "同一 Frame 出现两个不同年龄" in normalized
    assert "人物年龄统一保持在 25–34 岁的年轻成年人范围" in normalized
    assert "轮换 25–29 岁和 30–34 岁两个子段" in normalized
    assert "连续十个 Theme 至少覆盖六个不同整数年龄" in normalized
    assert "年轻不等于幼态" in normalized
    assert "娇小纤细、修长瘦削、柔软丰满、圆润丰腴" in normalized
    assert "不得默认所有成年人拥有平坦腹部、 细腰、长腿和年轻紧致皮肤" in normalized
    assert "脸部设计轮换椭圆脸、圆脸、方脸、长脸、心形脸" in normalized
    assert "发型必须同时轮换长度、纹理、结构和颜色" in normalized
    assert "不得让每个 Theme 都使用黑色波波头" in normalized
    assert "妆容按人物肤色、脸型、服装和地点独立设计" in normalized
    assert "不能只生成 bodysuit、leotard 或泳装" in normalized
    assert "每连续十个 Theme 至少覆盖六个不同整数年龄、六种体型" in normalized
    assert "发现整套造型相似时，优先改换年龄段、体型、 脸型和发型" in normalized
    assert "相邻 Theme 至少改变人物造型档案、地点家族、承载面" in normalized
    assert "只有以场所原生环境水为主的 Aesthetic 或 Erotic 批次才要求覆盖五个广义地点家族" in normalized
    assert "Hardcore 或任何人物身体液体、玩具储液批次" in normalized
    assert "白名单内至少四种兼容空间子型" in normalized
    assert "受保护私人卧室床和 受保护酒店套房床" in normalized
    assert "允许多个 Theme 属于 同一广义湿区家族" in normalized
    assert "人体液体不承担 六种水型配额" in normalized
    assert "不得为 满足多样性配额牺牲地点功能" in normalized
    assert "至少覆盖六种姿势家族、五种视点家族、五种绕人物方位、四档焦段" in normalized
    assert "同一视点家族最多出现两次" in normalized
    assert "规则优先级从高到低依次为：场景功能与物理逻辑" in normalized
    assert "必须舍弃更奇怪的地点、器具、水型或构图" in normalized
    assert "FINAL SCENE-LIQUID GATE" in brief
    assert "只有一个活动液体来源，且地点本来就适合该来源" in normalized
    assert "ONE-SOURCE LOCK: Exactly one visible jet, stream, spray, pour, or moving-fluid event" in normalized
    assert "Never combine, cross, merge, unite, or synchronize liquid from two sources" in normalized
    assert "every showerhead, hose, faucet, environmental spray, and reservoir toy is visibly off" in normalized
    assert "完整防水床面和吸水层清楚可见时才属于白名单" in normalized
    assert "人体液体可以有强烈、夸张、径向的编辑摄影表现" in normalized
    assert "不变成管道级、工业级或房间级水量" in normalized
    assert "环境水或储液玩具液体单独不能构成 Hardcore" in normalized
    assert "仅让储液玩具向裸体流液、让液体落在身体上" in normalized
    assert "必须重写" in normalized
    assert "场景合理性高于地点、水型、器具和构图多样性" in normalized
    assert "宁可重复兼容湿区，也不创造古怪组合" in normalized
    assert "只在正文结尾逐字输出当前 content level 的一条衣着锁" in normalized
    assert "CONTENT LOCK: Copy the runtime content level exactly" in normalized
    assert "A Hardcore request must end with only the HARDCORE WARDROBE LOCK" in normalized
    assert "never the AESTHETIC WARDROBE LOCK or EROTIC WARDROBE LOCK" in normalized
    assert "相邻 Theme 不重复姿势 家族、双腿关系、支撑手和相机方位" in normalized
    assert "轮换 overhead、elevated、eye-level、low-angle、profile、three-quarter" in normalized
    assert "不把每张 图都拍成 high-angle、50mm、人物居中的俯拍全身照" in normalized
    assert "只保留一件主要玩具或一套不可分离系统" in normalized
    assert "普通玩具不主动喷液" in normalized
    assert "湿区玩具防水且 无市电连接" in normalized
    assert "任何玩具都不进行尿道插入" in normalized
    assert "画面都保持高预算成人时尚编辑摄影" in normalized
    assert "不输出临床、医疗、法证、 偷拍、webcam、CCTV、自拍或普通色情记录美学" in normalized
    assert "CAST LOCK: Copy the requested female and male counts exactly" in normalized
    assert "one woman and zero men means exactly one visible adult woman" in normalized
    assert "no off-camera partner, no implied male, and no semen" in normalized
    assert "Never add a partner to enable a toy, action, fluid source, pose, or camera composition" in normalized
    assert "PRESENCE LOCK: Requested cast counts are exact required presences" in normalized
    assert "Every requested adult must be physically visible in every Frame" in normalized
    assert "one woman and one man means exactly one visible adult woman and exactly one visible adult man" in normalized
    assert "never omit either person, move either person off-camera" in normalized
    assert "多样性退化为同一白色平台上的换装" in normalized
    assert "把喷嘴、软管、控制器、纸钞、粉色腕带、白色服装" in normalized
    assert "每个 Theme 的必选物" in normalized


def test_indoor_pure_desire_editorial_has_complete_pose_library() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "indoor-pure-desire-editorial.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "室内纯欲成人时尚摄影 Theme" in normalized
    assert "纯欲不是幼态，也不是只使用白色内衣" in normalized
    assert "所有场景必须位于真实、封闭、可进入且可安全退出的室内" in normalized
    assert "服装、服饰、妆容、打扮和发型均为自由变化轴" in normalized
    assert "不把纯欲固定为白色" in normalized
    assert "建议姿势库" in brief

    pose_ids = [
        token
        for token in brief.split()
        if len(token) == 5
        and token.startswith("PD")
        and token[2:].isdigit()
    ]
    assert pose_ids == [f"PD{index:03d}" for index in range(1, 101)]
    assert "PD001 Lying flat on the back with knees bent" in normalized
    assert "PD050 Squatting in a deep position" in normalized
    assert "PD100 Standing with the torso upright" in normalized
    assert "每个 Frame 只选择一个主姿势" in normalized
    assert "构图与视角锁" in brief
    assert "front view 正面" in normalized
    assert "side view 纯侧面" in normalized
    assert "rear view 正后方" in normalized
    assert "front three-quarter 前侧三分之四" in normalized
    assert "rear three-quarter 后侧三分之四" in normalized
    assert "overhead/top-down 顶视" in normalized
    assert "elevated oblique 高位斜拍" in normalized
    assert "eye-level 平视" in normalized
    assert "low-angle 低机位" in normalized
    assert "beauty/action detail 近景" in normalized
    assert "Dutch angle/canted angle 荷兰角" in normalized
    assert "相机绕镜头轴有意倾斜约 5–20 度" in normalized
    assert "不得超过约 25 度" in normalized
    assert "over-the-shoulder 肩后视角" in normalized
    assert "head-side/foot-side axial 头侧或脚侧轴线视角" in normalized
    assert "floor-reflection 地面反射构图" in normalized
    assert "mirror-within-frame 镜中框构图" in normalized
    assert "foreground veil 前景柔性遮幅" in normalized
    assert "environmental wide portrait 室内环境广景" in normalized
    assert "telephoto compression 长焦压缩" in normalized
    assert "profile silhouette 侧面轮廓剪影" in normalized
    assert "centered vanishing-point 中央消失点" in normalized
    assert "high-low layered composition 高低层构图" in normalized
    assert "cropped editorial tension 编辑式裁切" in normalized
    assert "人物必须回头、转为可读侧脸或借可信镜面显示表情" in normalized
    assert "十个 Theme 的批次必须至少各出现一次 front view、side view、rear view" in normalized
    assert "任一视角家族最多出现 两次" in normalized
    assert "十个 Theme 还必须至少包含一次 Dutch angle、over-the-shoulder" in normalized
    assert "正中对称、偏心三分法、对角线、S 曲线、X 形、C 形" in normalized
    assert "Aesthetic：" in brief
    assert "Erotic：" in brief
    assert "Hardcore：" in brief
    assert "准确运行人数" in normalized
    assert "运行请求的人数是精确人数，不是上限" in normalized
    assert "每个最终 Frame 输出为请求语言的一段自然、连续" in normalized
    assert "不输出标题、Theme 编号、Frame 编号、 姿势编号" in normalized


def test_restroom_brief_requires_forward_leaning_deep_squat() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "piss.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "骨盆居中、双腿紧凑且趋于并拢但不互相接触的低位蹲姿" in normalized
    assert "双膝内缘和双鞋内缘之间形成等宽、狭窄、连续的竖直空隙" in normalized
    assert "躯干从髋关节整体向前折叠到胸腹近乎平行地面" in normalized
    assert "胸腹自然压在大腿上方" in normalized
    assert "肩膀在三维位置中越过膝盖" in normalized
    assert "不能仅低头、弯颈、把头伸向视点或单独伸出手机来假装前倾" in normalized
    assert "禁止抬高臀部变成站立俯身" in normalized
    assert "人物上身直立、后仰或只弯颈低头" in normalized
    assert "GROUND-LEVEL VIEWPOINT LOCK:" in normalized
    assert "SQUAT-TOILET LOCK:" in normalized
    assert "just outside the corresponding rim of a Chinese porcelain squat toilet" in normalized
    assert "aimed upward through a rectilinear 35mm perspective" in normalized
    assert "anatomically correct adult proportions" in normalized
    assert "physically plausible low-angle foreshortening" in normalized
    assert "a head visibly smaller than the shoulder span and torso" in normalized
    assert "FORWARD-FOLDED SQUAT LOCK:" in normalized
    assert "STYLE CONTINUITY LOCK:" in normalized
    assert "torso nearly horizontal to the floor" in normalized
    assert "the pelvis centered over the midpoint between the feet" in normalized
    assert "both upper thighs anatomically distinct and closely paired" in normalized
    assert "the thighs descending almost parallel with only a slight medial taper" in normalized
    assert "the inner knee gap and inner shoe gap equal" in normalized
    assert "no wider than one forefoot width" in normalized
    assert "each forward-facing kneecap centered directly above the second toe" in normalized
    assert "both shins forming close vertical parallel columns" in normalized
    assert "with a narrow straight gap between them" in normalized
    assert "both shoe centerlines aimed straight forward and parallel to one another" in normalized
    assert "to the toilet's front-to-rear axis" in normalized
    assert "toe spacing exactly equal to heel spacing" in normalized
    assert "neutral anatomical rotation from hips through ankles" in normalized
    assert "shoulders ahead of the knees" in normalized
    assert "head aligned naturally with the folded spine" in normalized
    assert "without thrusting toward it" in normalized
    assert "the viewpoint is visually absent and leaves the composition unobstructed" in normalized
    assert "禁止写 unseen camera、hidden camera、floor camera" in normalized
    assert "the same adult keeps the exact age, body build, hairstyle, makeup" in normalized
    assert "upper garments, fully lowered lower garments, accessories" in normalized
    assert "matching pair of shoes" in normalized
    assert "and squat-toilet design" in normalized
    assert "胸腹近乎平行地面" in normalized
    assert "骨盆中心位于双脚中点正上方" in normalized
    assert "双腿紧凑、趋于并拢但不互相接触" in normalized
    assert "两条大腿从髋部向下几乎平行" in normalized
    assert "双膝内缘之间与双鞋内缘之间保留同一条狭窄空隙" in normalized
    assert "两条小腿形成彼此靠近的垂直平行柱及窄直缝" in normalized
    assert "每侧髌骨中心必须位于对应鞋第二脚趾正上方" in normalized
    assert "两只鞋的纵向中心线笔直朝前、彼此平行并平行于蹲便器长轴" in normalized
    assert "脚尖间距等于脚跟间距" in normalized
    assert "髋关节、膝关节和踝关节保持中立旋转" in normalized
    assert "英文 Frame 不得复述这些错误姿势名称" in normalized
    assert "删除 M-shaped legs、frog squat、diamond-shaped legs、wide squat" in normalized
    assert "pigeon-toed、inward-pointing toes、turned-in feet 与 toe-in stance" in normalized
    assert "头发、项链、上衣下摆和松散布料受重力垂向地面视点" in normalized
    assert "正常成人头身比、肩宽、躯干长度及四肢比例" in normalized
    assert "使用 35 mm 等效直线投影，保持自然低角度透视" in normalized
    assert "鞋脚和小腿比臀胯、大腿适度显大" in normalized
    assert "肩膀和胸腹或背部保持主体体量" in normalized
    assert "透视只改变各部位的合理投影大小" in normalized
    assert "正确的视觉层级是下方鞋脚略大" in normalized
    assert "鞋脚占据大半画面、腿异常粗长、躯干塌成短块" in normalized
    assert "真实头高约为完整身高的七分之一至八分之一" in normalized
    assert "投影宽度必须小于可见肩宽和躯干宽度" in normalized
    assert "双肩、胸腹和骨盆必须清楚可见" in normalized
    assert "头部不是距离视点最近的物体" in normalized
    assert "头宽达到或超过肩宽、头遮挡身体、头大身小" in normalized
    assert "年龄按 Theme 编号使用确定性四段循环" in normalized
    assert "余 1 时选择 25–34 岁的年轻成年人" in normalized
    assert "余 2 时选择 35–49 岁的成熟成年人" in normalized
    assert "余 3 时选择 50–64 岁的年长成年人" in normalized
    assert "余 0 时选择 65–79 岁的老年成年人" in normalized
    assert "每个 Theme 必须在对应范围内给出一个明确整数年龄" in normalized
    assert "50 岁以上人物必须显示与具体年龄相符的面部细纹" in normalized
    assert "不得让整批年龄集中在 25–39 岁" in normalized


def test_restroom_brief_varies_interactions_and_uses_ground_camera() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "piss.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "手机不是必需品" in normalized
    assert "已经褪下的裤子、内裤或裙子是静止衣物" in normalized
    assert "低头并用一只手撩起上衣" in normalized
    assert "从卷筒抽取厕纸" in normalized
    assert "进行明确擦拭" in normalized
    assert "整理、梳开或轻拉阴毛" in normalized
    assert "一至两根清楚归属同一只手的手指" in normalized
    assert "进行可见外部自慰" in normalized
    assert "视点位于中国式蹲便器对应外缘的地面高度" in normalized
    assert "从地面向上倾斜 35–55 度" in normalized
    assert "画面底缘必须出现紧邻视点的陶瓷蹲便器边缘" in normalized
    assert "禁止手持、自拍、腰部高度、膝盖高度、眼平、俯拍" in (
        normalized
    )
    assert "画面任何位置都不得出现相机机身、镜头、手机拍摄设备" in normalized
    assert "摄影机遥控器、三脚架或任何会暗示拍摄设备进入画面的道具" in normalized
    assert "所有裤子、短裤、内裤和裙子都必须已经完全离开腰部" in normalized
    assert "统一褪到膝盖以下、小腿或脚踝处并清楚可见" in normalized
    assert "不得只解开、掀起或停留在大腿中段" in normalized
    assert "这些下装保持静止并与双手分离" in normalized
    assert "不得被手提回膝盖或大腿" in normalized
    assert "季节至少轮换盛夏、春秋和寒冬" in normalized
    assert "场合至少轮换都市日常、办公室通勤、正式晚宴、夜店派对" in normalized
    assert "服装颜色不得默认黑色或连续重复单色" in normalized
    assert "每个 Theme 写清主色、辅色和材质" in normalized
    assert "发型至少轮换精灵短发、齐耳短发、直长发、自然卷" in normalized
    assert "妆容至少轮换素颜、透明自然妆、办公室柔和妆、复古红唇" in normalized
    assert "表情至少轮换专注、从容、自信、调皮、轻笑、惊喜" in normalized
    assert "鞋履至少轮换平底凉鞋、细带高跟凉鞋、经典尖头高跟鞋" in normalized
    assert "配饰每人选择一至三件" in normalized
    assert "相邻 Theme 不得重复相同视角方向、季节、场合、服装类别、主色" in normalized
    assert "不得在 Frame 末尾追加以 No、Without、Neither 或 Absent 开头" in normalized
    assert "发布每个英文 Frame 前逐字扫描" in normalized
    assert "确认成对鞋履均穿在双脚上" in normalized
    assert "嵌入地面的中国式陶瓷蹲便器" in normalized
    assert "中央椭圆便池与排污口清楚可见" in normalized
    assert "左右各有带防滑纹的承重脚踏区" in normalized
    assert "不得替换成西式坐便器、独立地漏或长排水沟" in normalized
    assert "左右脚或鞋分别完整踩在中国式蹲便器左右防滑脚踏区" in normalized
    assert "落入正下方中国式蹲便器的中央陶瓷便池和排污口" in normalized
    assert "central oval bowl, visible waste outlet, rear flush channel" in normalized
    assert "two anti-slip foot platforms supporting the complete matching left and right shoes" in normalized
    assert "蹲便器相关内容只使用以下英文词汇" in normalized
    assert "正面、左侧、右侧、背面或三分之四方向中明确选择一个" in normalized
    assert "左侧或右侧视角位于蹲便器对应侧缘 80–100 度" in normalized
    assert "背面视角位于蹲便器后缘和脚跟后方 160–180 度" in normalized
    assert "不得在同一 Frame 混合正面、侧面和背面" in normalized
    assert "整批必须均衡覆盖 front view、left side view、right side view" in normalized
    assert "rear view、front three-quarter view 和 rear three-quarter view" in normalized
    assert "VIEW DIRECTION LOCK: front view from the squat toilet's front rim" in normalized
    assert "VIEW DIRECTION LOCK: left side view from the squat toilet's left rim" in normalized
    assert "VIEW DIRECTION LOCK: right side view from the squat toilet's right rim" in normalized
    assert "VIEW DIRECTION LOCK: rear view from the squat toilet's rear rim" in normalized
    assert "VIEW DIRECTION LOCK: front three-quarter view" in normalized
    assert "VIEW DIRECTION LOCK: rear three-quarter view" in normalized
    assert "生成两帧 Theme 时按 Theme 编号使用确定性视角对" in normalized
    assert "Theme 编号除以 3 余 1 时" in normalized
    assert "余 2 时，Frame 1 使用 right side view、Frame 2 使用 rear view" in normalized
    assert "余 0 时，Frame 1 使用 front three-quarter view" in normalized
    assert "必须读取当前 Theme 编号决定视角对" in normalized
    assert "最后一句必须正面描述可见的蹲便器陶瓷、脚踏纹、地砖、顶灯" in normalized


def test_confined_exhibition_fantasy_has_safe_scene_catalog() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "confined-exhibition-fantasy.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())
    scenes = [
        line
        for line in brief.splitlines()
        if len(line) > 5 and line[:3].isdigit() and line[3:5] == ". "
    ]

    assert len(scenes) == 100
    assert len(set(scenes)) == 100
    assert [int(scene[:3]) for scene in scenes] == list(range(1, 101))
    assert all("围观者" in scene for scene in scenes)
    assert all(
        any(
            pose in scene
            for pose in (
                "折叠",
                "对折",
                "卷曲",
                "收膝",
                "折膝",
                "前倾",
                "翘臀",
                "抬臀",
                "臀部",
                "大字型",
                "四点支撑",
                "四角支撑",
                "四肢撑向",
                "四角伸展",
                "四肢伸展",
            )
        )
        for scene in scenes
    )
    assert "TOTAL PEOPLE = female_count + male_count 为 4–8" in normalized
    assert "female_count 至少为 2、male_count 至少为 1" in normalized
    assert "SPECTATORS = TOTAL PEOPLE - 1，因此围观者为 3–7 人" in normalized
    assert "WOMEN SPECTATORS = female_count - 1" in normalized
    assert "MEN SPECTATORS = male_count" in normalized
    assert "保证围观群众同时有女性和男性" in normalized
    assert "不得增加请求之外的人物、背景脸、身体、手脚、镜中人物" in normalized
    assert "站在空间开口或安全边界之外" in normalized
    assert "静止、通风、照明充分且出口保持开启" in normalized
    assert "车辆必须停稳、熄火、钥匙移除" in normalized
    assert "任何箱体、柜体、舱室或隔间都不得上锁" in normalized
    assert "真实摄影师在可控私人场地中拍到的一次高预算编辑摄影" in normalized
    assert "皮肤、织物、金属、木材和软垫各有真实质感" in normalized
    assert "不是不可能的关节、复制粘贴式表情、过度锐化、塑料皮肤或堆砌提示词" in normalized
    assert "HIGHEST PRIORITY OUTPUT" in brief
    assert "400–680 个英文单词" in normalized
    assert "四人场景优先控制在 420–540 个单词" in normalized
    assert "每增加一人最多增加 30 个单词" in normalized
    assert "不得使用 the same、identical、again、remains unchanged" in normalized
    assert "提交前逐词扫描这些禁用短语" in normalized
    assert "with no backward pointer or reference to another Frame" in normalized
    assert "每个围观者最多使用一个简洁句子" in normalized
    assert "不输出 `LOCK`、schema、公式、检查步骤" in normalized
    assert "把人数算术留在内部规划中" in normalized
    assert "前两句自然写明准确总人数" in normalized
    assert "WARDROBE, COLOR, ACCESSORIES, AND EXPRESSION" in brief
    assert "逐项写出：上身单品、下身单品或其明确缺席" in normalized
    assert "主色、辅色、材质、鞋履以及一至四件配件" in normalized
    assert "不得连续使用同一件黑色蕾丝内衣" in normalized
    assert "材质轮换哑光棉、丝绸、缎面、雪纺、薄纱、网眼、蕾丝" in normalized
    assert "相邻 Theme 的主色、辅色、材质和服装类别均不得重复" in normalized
    assert "细框眼镜、粗框眼镜、无度数彩色镜片、窄丝巾、长丝巾" in normalized
    assert "丝巾只能松系在颈部、头发、手腕或腰侧" in normalized
    assert "至少包含五项同时可见的线索" in normalized
    assert "左右略不对称的眉形" in normalized
    assert "清晰瞳孔和视线目标" in normalized
    assert "不使用风格化啊嘿颜、完全上翻眼睛、失焦瞳孔" in normalized
    assert "只有环境温度低于 10°C 时才能写可见呼气" in normalized
    assert "衣服数量较少但保持关键部位完全不透明遮盖" in normalized
    assert "一件贴身连体衣，或两至三件组成的极简性感造型" in normalized
    assert "必须保留一至两件透明、半透明、湿贴、敞开或半褪下" in normalized
    assert "必须清楚写出衣物停留位置" in normalized
    assert "表情保持清醒、主动、聚焦和解剖自然" in normalized
    assert "两膝与两前臂形成宽而稳定的四点支撑" in normalized
    assert "骨盆明显高于肩线约半个躯干厚度" in normalized
    assert "肘膝保留自然轻屈" in normalized
    assert "不要求达到关节极限或同时触及最远角点" in normalized
    assert "当前返回 Theme 列表中的顺序使用确定性三项循环" in normalized
    assert "英文 title 以 `FOLDED - ` 开头" in normalized
    assert "title 以 `RAISED HIPS - ` 开头" in normalized
    assert "title 以 `SPREAD EAGLE - ` 开头" in normalized
    assert "不在正文输出前缀解释或姿势锁" in normalized
    assert "实际距离必须适合所选地点，不写固定米数" in normalized
    assert "3 人可用 2+1 或 1+2" in normalized
    assert "4 人可用 2+2 或 1+2+1" in normalized
    assert "5 人可用 2+2+1" in normalized
    assert "6 人可用 2+2+2 或 3+2+1" in normalized
    assert "7 人可用 3+2+2" in normalized
    assert "PORTAL AND SILHOUETTE SEPARATION" in brief
    assert "每个 Frame 的前 180 个英文单词内" in normalized
    assert "完整开口内只出现主表演者、承重垫和内部表面" in normalized
    assert "开口中央、主表演者正后方和四肢间负空间保持为清楚可见的空内部背景" in normalized
    assert "不得只写 spectators are outside、safe distance 或 visible gaps" in normalized
    assert "主表演者及其承重垫完整位于开口平面内侧" in normalized
    assert "全部围观者的头、肩、躯干、手臂和双脚完整位于开口平面外侧" in normalized
    assert "不能在投影上出现在黑暗舱体、柜体或箱体内部" in normalized
    assert "一条连续、无遮挡的外部地面或走道隔离带" in normalized
    assert "其投影高度约占画面高度的 8–15%" in normalized
    assert "每名围观者占用一个独立轮廓槽位" in normalized
    assert "头部与相邻头部之间至少保留一个可见头宽" in normalized
    assert "背景包围其轮廓三侧" in normalized
    assert "采用开口外侧 35–45 度的斜向视点" in normalized
    assert "不得把任何围观者安排在主表演者正后方" in normalized
    assert "若所选场景无法在 35–50 mm 视角中同时容纳请求人数" in normalized
    assert "每个 Frame 最多一人指点、最多一人手拢嘴边" in normalized
    assert "不得让所有人同时瞪眼、张嘴或摆出相同手势" in normalized
    assert "主表演者占画面高度或宽度约 50–68%" in normalized
    assert "允许离焦随距离自然增加" in normalized
    assert "每名围观者拥有不同的脸、发型、服装辅色、站位" in normalized
    assert "多数视线落在主表演者" in normalized
    assert "允许在英文 Frame 中使用 camera、lens、aperture、shutter" in normalized
    assert "PHOTOGRAPHIC REALISM AND VISUAL IMPACT" in brief
    assert "一个主导实景光源、一个克制补光或反射来源" in normalized
    assert "35–50 mm 等效镜头、f/4–f/5.6 光圈" in normalized
    assert "第一层是主表演者的脸、眼神和完整姿势轮廓" in normalized
    assert "第二层是狭小空间边界、受压材质与开启出口" in normalized
    assert "第三层是较小、稍柔但仍可辨识的围观者" in normalized
    assert "细小毛孔、柔软汗毛、轻微色差、局部潮红" in normalized
    assert "高光随皮肤曲面缓慢滚落" in normalized
    assert "构图采用略微偏心的编辑摄影瞬间" in normalized
    assert "BODY, MATERIAL, AND SPACE CONTACT" in brief
    assert "每个 Frame 至少描写三项材质—身体—空间接触证据" in normalized
    assert "臀部使汽车座垫或床垫产生可信形变" in normalized
    assert "OUTPUT PREFLIGHT" in brief
    assert "Theme title 前缀与唯一姿势家族一致" in normalized
    assert "最终 Frame 只保留可渲染画面正文" in normalized
    assert "SCENE CATALOG" in brief
    assert "CONTENT LEVEL" in brief
    assert "VARIATION AND REJECTION RULES" in brief


def test_rebuilt_legacy_inputs_are_complete_story_descriptions() -> None:
    required_sections = (
        "BRIEF",
        "THEME CONTRACT",
        "FRAME CONTRACT",
        "VARIATION AND REJECTION RULES",
    )

    for filename in ("avantgarde.txt", "snofs.txt", "tentacle.txt"):
        brief = (REPOSITORY_ROOT / "story-inputs" / filename).read_text(
            encoding="utf-8"
        )

        assert all(section in brief for section in required_sections), filename
        assert "At aesthetic level" in brief, filename
        assert "At erotic level" in brief, filename
        assert "At hardcore level" in brief, filename


def test_story_inputs_do_not_override_run_level_cast_or_frame_semantics() -> None:
    film_post = (REPOSITORY_ROOT / "story-inputs" / "film-post.txt").read_text(
        encoding="utf-8"
    )
    zero_gravity = (
        REPOSITORY_ROOT / "story-inputs" / "zero-gravity-intimacy.txt"
    ).read_text(encoding="utf-8")

    assert "Use the exact requested cast and no additional people" in film_post
    assert "must appear clearly in every Theme premise and every poster" in film_post
    assert "At hardcore level" in zero_gravity
    assert "incompatible with hardcore" not in zero_gravity
    assert "Keep intimate actions non-graphic" not in zero_gravity


def test_intimate_lifestyle_portrait_matches_reference_photo_grammar() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "intimate-lifestyle-portrait.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert "Every Frame is one finished full-bleed photograph" in normalized
    assert "Aspect ratio and canvas dimensions are controlled outside this brief" in normalized
    assert "Do not declare, request, prefer, or reject any aspect ratio" in normalized
    assert "bright, polished East Asian social-media lifestyle-glamour aesthetic" in normalized
    assert "fresh, gentle, sunlit, colorful" in normalized
    assert (
        "bright high-key East Asian lifestyle beauty portrait, soft feminine "
        "social-media glamour, luminous ivory skin, clear large almond eyes, "
        "clean modern digital-camera realism"
    ) in normalized
    assert "Use exactly `female_count` adult women and exactly `male_count` adult men" in normalized
    assert "these run parameters are the sole authority for visible human count" in normalized
    assert "Never infer, add, remove, replace, or duplicate a person" in normalized
    assert "Every requested person is unmistakably 25 or older" in normalized
    assert "designate one requested woman as the primary beauty-portrait subject" in normalized
    assert "the requested companion is equally complete, identifiable, active" in normalized
    assert "Never copy, name, or closely resemble a real person" in normalized
    assert "coherent anatomy; the primary woman may have a curvy figure and naturally full bust" in normalized
    assert "minute visible pores, soft facial peach fuzz" in normalized
    assert "MAKEUP AND GROOMING" in normalized
    assert "Describe every woman's complete visible makeup design" in normalized
    assert "exact blush hue, placement, diffusion, and finish" in normalized
    assert "peach cream blush high on the cheekbones" in normalized
    assert "Rotate makeup families across Themes before repeating" in normalized
    assert "give each a visibly distinct but harmonious makeup design" in normalized
    assert "describe polished grooming" in normalized
    assert "ACCESSORIES AND HEADWEAR" in normalized
    assert "at least three coordinated accessories from different categories" in normalized
    assert "wide-brim straw hat, structured beret, silk headscarf" in normalized
    assert "cat-eye, slim oval, softly rectangular, rimless" in normalized
    assert "fine pendant, pearl strand, velvet choker, layered chain" in normalized
    assert "charm bracelet, slim bangle stack, cuff, polished watch" in normalized
    assert "Never hide the eyes behind dark opaque lenses" in normalized
    assert "build distinct accessory sets with different centerpiece categories" in normalized
    assert "For a requested man, specify two or more coherent accessories" in normalized
    assert "remain in the same position in both Frames of one Theme" in normalized
    assert "distinct location family" in normalized
    assert "bright neighborhood gym entrance" in normalized
    assert "sunlit independent cafe or bakery" in normalized
    assert "bright apartment art corner" in normalized
    assert "outdoor market lounge" in normalized
    assert "vintage tea room" in normalized
    assert "brick-walled garage" in normalized
    assert "Use original, unbranded designs" in normalized
    assert "At aesthetic level" in normalized
    assert "Wardrobe is a major visual attraction, not ordinary daywear" in normalized
    assert "at least three luxurious fashion materials or treatments" in normalized
    assert "Use at least three coordinated accessories" in normalized
    assert "ordinary plain sportswear or a basic top-and-shorts combination is insufficient" in normalized
    assert "embellished corset top, embroidered bustier, jeweled bodysuit" in normalized
    assert "Deep cleavage, side cutouts, open backs, bare shoulders" in normalized
    assert "opaque over nipples and genitals" in normalized
    assert "At erotic level" in normalized
    assert "At hardcore level" in normalized
    assert "Partial toplessness, bare breasts, and visible nipples are permitted" in normalized
    assert "an unmistakable, currently visible consensual adult sexual act" in normalized
    assert "A one-woman cast uses an explicit solo act" in normalized
    assert "a woman-and-man or two-woman cast uses an explicit mutually participatory act" in normalized
    assert "Do not add an unrequested partner, body part, hidden participant" in normalized
    assert "The run's requested content level is the sole authority" in normalized
    assert "Aesthetic has no visible nipples, genitals, or sex act" in normalized
    assert "one natural, visually legible activity tied to the selected place" in normalized
    assert "The activity supports the portrait instead of dominating it" in normalized
    assert "below roughly twenty percent of the frame" in normalized
    assert "FACE, BODY, AND POSE DIRECTION" in normalized
    assert "Treat face direction, torso direction, pelvis direction, and camera position as four separate choices" in normalized
    assert "clean left or right profile" in normalized
    assert "face turned back over one shoulder" in normalized
    assert "back mostly toward camera with the face looking over one shoulder" in normalized
    assert "shoulders and pelvis deliberately counter-rotated" in normalized
    assert "relaxed standing contrapposto" in normalized
    assert "floor sitting with one knee raised" in normalized
    assert "upright kneeling with grounded shins" in normalized
    assert "reclining diagonally on a sofa or chaise" in normalized
    assert "use at least four face directions, five body directions" in normalized
    assert "The eyes are the first focal priority in every Frame" in normalized
    assert "iris direction, degree of eye convergence" in normalized
    assert "natural wet lower-lid line, separated eyelashes, detailed irises" in normalized
    assert "wide, clear, softly attentive eyes" in normalized
    assert "never predatory, confrontational, or brooding" in normalized
    assert "Narrowed or half-lidded eyes are valid only when" in normalized
    assert "focused, luminous half-lidded gaze" in normalized
    assert "EXPRESSION AND EMOTION VARIATION POOL" in normalized
    assert "adult playful coquetry" in normalized
    assert "teasing invitation" in normalized
    assert "languid ease" in normalized
    assert "sensual contentment" in normalized
    assert "dreamy reverie" in normalized
    assert "private pride" in normalized
    assert "romantic anticipation" in normalized
    assert "self-aware glamour" in normalized
    assert "wistful tenderness" in normalized
    assert "At aesthetic level, favor approachable, playful, coy" in normalized
    assert "At erotic level, allow stronger teasing invitation" in normalized
    assert "Plan expression coverage across the whole batch" in normalized
    assert "COY AND COQUETTISH" in normalized
    assert "LANGUID AND SENSORY" in normalized
    assert "TEASING AND CONFIDENT" in normalized
    assert "WARM AND OPEN" in normalized
    assert "DREAMY AND TENDER" in normalized
    assert "FOCUSED AND PROUD" in normalized
    assert "Assign these lanes in a varied order rather than by Theme ID" in normalized
    assert "vary direct lens contact, phone-screen attention, mirror-eye contact" in normalized
    assert "at least four mutually consistent signals" in normalized
    assert "Replace vague words such as beautiful, sexy, seductive" in normalized
    assert "one primary emotion, one quieter secondary emotion" in normalized
    assert "one concrete trigger in the current scene" in normalized
    assert "Make the emotional chain visually causal" in normalized
    assert "A viewer should infer both emotions without a caption" in normalized
    assert "preserve the exact emotional baseline, trigger, appraisal" in normalized
    assert "Every Frame captures the identical emotional instant" in normalized
    assert "PAIR CONTINUITY — HIGHEST PRIORITY" in normalized
    assert "privately build one immutable subject block" in normalized
    assert "Copy that immutable subject block" in normalized
    assert "Pair variation is camera variation only" in normalized
    assert "Framing family and shooting method never change within a Theme" in normalized
    assert "Do not put down, raise, transfer, add, or remove a phone or camera" in normalized
    assert "Continuity outranks novelty" in normalized
    assert "Every Frame must stand alone" in normalized
    assert "Restate every stable fact as a present visible fact" in normalized
    assert "compare paired Frames field by field" in normalized
    assert "scan out every cross-Frame comparison word above" in normalized
    assert "Never echo instructions or state absences" in normalized
    assert "Delete negative checklist phrases before publishing" in normalized
    assert "do not emit Chinese characters" in normalized
    assert "Capture an action at its most informative fraction of a second" in normalized
    assert "one immediate physical consequence" in normalized
    assert "Every Frame must include a coherent micro-detail hierarchy" in normalized
    assert "Keep the eyes and action-driving hand as the sharpest details" in normalized
    assert "live-action photorealistic location portrait photography" in normalized
    assert "Do not prescribe a focal length" in normalized
    assert "do not use wide-angle, ultra-wide, fisheye" in normalized
    assert "Never write wide-angle, ultra-wide, fisheye, 0.5x" in normalized
    assert "A selfie must use a natural-perspective phone camera mode" in normalized
    assert "Variation comes from camera position, height, side, distance" in normalized
    assert "live-action photorealistic location portrait with natural undistorted perspective" in normalized
    assert "FULL BODY" in normalized
    assert "show every requested person completely from the top of the hair through both feet and footwear" in normalized
    assert "LARGE HALF BODY" in normalized
    assert "hips, and at least the upper thighs or knees" in normalized
    assert "alternate them across a batch before repeating" in normalized
    assert "Independently choose one distinct shooting method for every Theme" in normalized
    assert "arm's-length front-camera selfie" in normalized
    assert "always using LARGE HALF BODY framing" in normalized
    assert "mirror selfie showing the exact requested cast and only their corresponding reflections" in normalized
    assert "a timer photograph from a shelf, counter, windowsill" in normalized
    assert "Treat selfie, mirror selfie, friend-held camera, timer camera" in normalized
    assert "physically truthful gaze behavior" in normalized
    assert "front-camera selfie must never claim full-body framing" in normalized
    assert "For a batch of three or more Themes" in normalized
    assert "at least one front-camera selfie or mirror selfie" in normalized
    assert "at least one nearby-friend portrait" in normalized
    assert "at least one timer or fixed-camera portrait" in normalized
    assert "Every Theme premise must explicitly name its framing family and shooting method" in normalized
    assert "one framing family and one shooting method not yet used" in normalized
    assert "one expression family, gaze pattern, brow pattern" in normalized
    assert "one face direction, body direction, and pose family" in normalized
    assert "Compose three physical depth planes" in normalized
    assert "Keep the face high-key and readable" in normalized
    assert "Avoid low-key lighting, heavy chiaroscuro" in normalized
    assert "one dreamy but physically photographable atmosphere" in normalized
    assert "soft golden-hour backlight" in normalized
    assert "small prism refractions" in normalized
    assert "bright rain droplets, condensation, or misted glass" in normalized
    assert "candlelight or warm table lamps balanced by cool blue-hour window fill" in normalized
    assert "sunlit pollen, steam, or fine dust" in normalized
    assert "delicate practical fairy lights, cafe bulbs, or city lights" in normalized
    assert "The dreamy atmosphere must remain real-location photography" in normalized
    assert "Do not use magical particles, supernatural auras" in normalized
    assert "four consecutive information blocks" in normalized
    assert "Completeness and image-defining detail matter more than an arbitrary word count" in normalized
    assert "IDENTITY AND LOOK" in normalized
    assert "EYES AND EMOTION" in normalized
    assert "POSE AND ACTION" in normalized
    assert "CAMERA AND LIGHT" in normalized
    assert "write one explicit `MAKEUP —` sentence for each woman" in normalized
    assert "Write one `GROOMING —` sentence for each man" in normalized
    assert "These sentences and every person's accessories are mandatory in every Frame" in normalized
    assert "Spend most of the budget on the face, eyes, micro-expression" in normalized
    assert "THEME CONTRACT" in normalized
    assert "exactly `female_count` original adult women and `male_count` original adult men" in normalized
    assert "primary woman's exact blush hue and placement" in normalized
    assert "the exact parameter-controlled cast" in normalized
    assert "Do not add, remove, substitute, merge, or crop away a requested person" in normalized
    assert "FRAME CONTRACT" in normalized
    assert "VARIATION AND REJECTION RULES" in normalized


def test_miniature_fantasy_v2_scopes_cast_to_miniature_people() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "miniature-fantasy-v2.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert len(brief) < 9_500
    assert "仅用于 Erotic 和 Hardcore" in normalized
    assert "female_count 和 male_count 只约束微型人物" in normalized
    assert "每帧画面总人数严格等于 1 + female_count + male_count" in normalized
    assert "不得出现额外脸、头、躯干、肢体或局部人物" in normalized
    assert "系统为唯一巨大人物自动选择成年男人或成年女人" in normalized
    assert "该 Theme 全部 Frame 固定此选择" in normalized
    assert "所有人物均为自愿互动的多元东亚成年人" in normalized
    assert "真实成人身体多样性" in normalized
    assert "不是默认年轻、纤瘦、健美、对称、光滑和无瑕" in normalized
    assert "年轻成年、中年或老年年龄层" in normalized
    assert "肥胖厚重、柔软丰满、精瘦、宽壮或肌肉型体态" in normalized
    assert "巨大人物优先轮换明显不同的年龄和体型" in normalized
    assert "皱纹、松弛皮肤、腹部与腰侧脂肪褶皱" in normalized
    assert "下垂胸部、妊娠纹、橘皮组织" in normalized
    assert "静脉、疤痕、痣、色素差异或不对称" in normalized
    assert "年龄与肥胖是正常且可具吸引力的成人特征" in normalized
    assert "不得写成疾病、怪物化、羞辱理由" in normalized
    assert "巨大人物是环境尺度主体" in normalized
    assert "双方均可发起、回应或引导" in normalized
    assert "Theme 锁定发起方" in normalized
    assert "专为掌心成年居民建造的室内小人国" in normalized
    assert "真实成年原住民" in normalized
    assert "正常人类世界的成年访客" in normalized
    assert "身体与器官保持普通成人尺寸" in normalized
    assert "除总人数和镜头焦距外，不得输出比例" in normalized
    assert "人物或物体尺寸、长度单位" in normalized
    assert "每个 Frame 分开描述" in normalized
    assert "living miniature adult woman/man native" in normalized
    assert "normal-human-sized giant visitor" in normalized
    assert "不得把双方简称为同尺寸普通人物" in normalized
    assert "完全相同的头身比、肩宽尺度和四肢长度" in normalized
    assert "不得用高矮、娇小、修长或不同骨架区分" in normalized
    assert "不得让其中一人单独靠近镜头" in normalized
    assert "尺度是每帧最高优先级，必须同时出现三层证据" in normalized
    assert "完整身高短于巨大人物手腕至中指尖" in normalized
    assert "能站在其掌心" in normalized
    assert "头部小于其拇指末节" in normalized
    assert "与巨大手、脚或脸无遮挡并排" in normalized
    assert "广角透视只能强化、不能单独证明尺度" in normalized
    assert "接触处必须同时看见巨大身体、完整微型身体和建筑参照" in normalized
    assert "小人国门框匹配居民身高" in normalized
    assert "巨大访客手大于门洞" in normalized
    assert "身体跨越多个房间" in normalized
    assert "不能由单件小人国家具承托" in normalized
    assert "须由地面、墙体或多组结构支撑" in normalized
    assert "三层尺度证据" in normalized
    assert "铅笔" not in normalized
    assert "不得添加任何不参与主动作的松散小物" in normalized
    assert "所有微型人物投影身高相等" in normalized
    assert "只允许一具解剖连续的巨大成人身体" in normalized
    assert "只允许一个目标性器官可见" in normalized
    assert "目标器官在一个专门句子中只命名一次" in normalized
    assert "相对微型人物的巨大尺度、朝向、自然表面" in normalized
    assert "当前接触造成的可见压力或形变" in normalized
    assert "目标器官保持普通成年人自然尺寸" in normalized
    assert "不得放大成洞穴、房间或建筑" in normalized
    assert "penis 保持自然 shaft、glans 与根部" in normalized
    assert "vaginal opening 保持连续外部褶皱与入口" in normalized
    assert "anus 保持自然放射褶皱与入口" in normalized
    assert "每名微型人物必须从头顶到双脚全身可见" in normalized
    assert "始终完整位于巨大访客体外" in normalized
    assert "道具、衣物和液体不得遮断其头—躯干—四肢轮廓" in normalized
    assert "任何头、躯干、骨盆、手臂、腿或脚都不得进入体内" in normalized
    assert "独立闭合的头—颈—躯干—骨盆—四肢链" in normalized
    assert "人物轮廓不重叠、不融合、不共享肢体" in normalized
    assert "多个微型人物的头和躯干之间保留可见背景空隙" in normalized
    assert "不同空间槽位和支撑面" in normalized
    assert "每人只用一个固定英文称谓并在全文保持不变" in normalized
    assert "同性交互禁止 she、her、he、him、his 等代词" in normalized
    assert "不得把同一人改称 operator、worker、partner 或 figure" in normalized
    assert "仅有一名微型人物时，它只能二选一" in normalized
    assert "不得同时用身体接触又用手操作控制器" in normalized
    assert "每条手臂和腿只分配一次位置与动作" in normalized
    assert "接触点数量必须与列出的手脚一致" in normalized
    assert "工具只有一个作用面，只连接接触点" in normalized
    assert "每人只握一件工具或控制器" in normalized
    assert "流体仅从接触点流向导流器和单个容器" in normalized
    assert "禁止反向 toward the contact point" in normalized
    assert "不得成为第二接触对象或身体支撑" in normalized
    assert "inward、intrusion、insert、penetration、enter、inside" in normalized
    assert "微型人物性器官被服装遮住或位于画外" in normalized
    assert "显示目标部位到所属胸廓或骨盆" in normalized
    assert "巨大人物可以完整出现，也可以只出现" in normalized
    assert "与主要互动相关的局部身体" in normalized
    assert "所属骨盆及一段相连躯干、臀部或大腿" in normalized
    assert "裁切只在画框边缘" in normalized
    assert "全部性行为或性活动只发生在一名或多名微型人物" in normalized
    assert "与唯一巨大人物之间" in normalized
    assert "禁止微型人物彼此、巨大人物独自或第三方性活动" in normalized
    assert "每名微型人物须直接接触巨大人物" in normalized
    assert "或操作由工具、支撑或体液轨迹连接巨大人物的同一动作链" in normalized
    assert "不得旁观或另开动作" in normalized
    assert "每帧只有一个连续主要行为、目标器官和接触中心" in normalized
    assert "微型人物、巨大人物或双方均可发起" in normalized
    assert "须明确发起与回应" in normalized
    assert "除唯一接触点外，每个 Frame 只用一只手或一件工具" in normalized
    assert "让唯一接触点主动贴近微型人物" in normalized
    assert "巨大手指不得遮住微型人物头部" in normalized
    assert "非常规活动必须把体型反差转化为可见" in normalized
    assert "每个 Frame 只选一个主要行为" in normalized
    assert "围绕同一接触中心形成一条动作链" in normalized
    assert "成人之间明确自愿的暴露、窥视角色扮演" in normalized
    assert "每个人仍须表现出可辨认的发起、同意或回应" in normalized
    assert "并遵守非微距、完整空间和单一身体规则" in normalized
    assert "微型身体或工具压住唯一接触点并造成可见形变" in normalized
    assert "approaching、within reach、alignment、readiness" in normalized
    assert "waiting、traverse toward、approach" in normalized
    assert "画外行为、纯观看、纯展示或姿势暗示" in normalized
    assert "想象力与标志性机制" in normalized
    assert "先锁定一个 Signature Mechanism" in normalized
    assert "以下只作灵感参考，不是清单、配额或模板" in normalized
    assert "不得照抄例子或只替换道具名称" in normalized
    assert "空中探险" in normalized
    assert "流体工程" in normalized
    assert "重型机械" in normalized
    assert "巨大访客主动使用完整微型人物的外部身体工具" in normalized
    assert "在内部先构思至少三个候选" in normalized
    assert "交通、剧场、温室、浴场、实验室、厨房" in normalized
    assert "重力、浮力、杠杆、反重、振动、气流" in normalized
    assert "只有巨人—小人尺度差才能成立的角色反转" in normalized
    assert "不输出候选过程" in normalized
    assert "世界系统 + 物理原理 + 装置 + 发起方 + 房间 + 支撑面" in normalized
    assert "主动发起者可为巨大人物或微型人物" in normalized
    assert "机制必须占据清楚画面空间" in normalized
    assert "体液必须来自唯一可见的身体来源" in normalized
    assert "大量且清晰可见的精液、尿液喷射、阴道液体或灌肠喷射" in normalized
    assert "每帧只选一种主要体液效果" in normalized
    assert "Hardcore 可使用远大于微型人物体量的强烈喷流" in normalized
    assert "喷口、方向、受力表面、汇流路径" in normalized
    assert "束缚架、滑轮悬吊、束带、项圈、夹具、震动器、泵、扩张器" in normalized
    assert "自愿 BDSM 系统" in normalized
    assert "不得只作装饰、制造伤害、遮住微型完整身体或形成第二性行为" in (
        normalized
    )
    assert "巨大身体也可成为游乐设施地形" in normalized
    assert "环绕胸廓与肩背的安全束带在胸部前搭建秋千" in normalized
    assert "完整微型人物荡过一侧乳房、乳沟上方或躯干" in normalized
    assert "胸前摩天轮、乳沟上方索道或胸骨弹射台" in normalized
    assert "不得把乳头或柔软组织作为唯一锚点" in normalized
    assert "秋千座椅不得遮住微型人物头、躯干和四肢" in normalized
    assert "机械必须完整接地" in normalized
    assert "微型人物采用夸张、舞台化、从头到脚完整设计" in normalized
    assert "每人固定一个强烈轮廓特征" in normalized
    assert "和一个醒目发型、头饰或超大配饰" in normalized
    assert "同一 Theme 全部 Frame 一致" in normalized
    assert "Erotic 和 Hardcore 中，巨大人物每个 Theme 可选择裸体或部分穿着" in (
        normalized
    )
    assert "并在全部 Frame 保持一致" in normalized
    assert "部分穿着可保留一至两件衣物及一件配饰" in normalized
    assert "骨盆、目标部位及其与胸腹、臀部或大腿的连续关系" in normalized
    assert "显示自然可见的阴毛及其与皮肤、骨盆的连续边界" in normalized
    assert "衣物不得覆盖阴毛或接触点" in normalized
    assert "阴毛造型可作为创意和尺度证据" in normalized
    assert "局部修剪成几何边界、分区或渐变" in normalized
    assert "编成短辫，加入轻质环、珠、丝带或金属线" in normalized
    assert "体液形成湿润聚束和导流纹路" in normalized
    assert "每个 Theme 只选一种主造型并在全部 Frame 固定" in normalized
    assert "不得完全剃除、延伸成触手或额外肢体" in normalized
    assert "不得作为微型人物唯一承重支撑" in normalized
    assert "伪装成肢体或制造额外身体轮廓" in normalized
    assert "夸张造型不能改变人物身高、头身比、肩宽" in normalized
    assert "微型服装按小人国居民的共同尺寸裁制" in normalized
    assert "每名微型人物造型使用 20–30 个英文单词" in normalized
    assert "两种颜色、两种材质、一个轮廓和一个配饰" in normalized
    assert "organza" in normalized
    assert "硬纱" not in normalized
    assert "巨大人物用 12–20 词" in normalized
    assert "不得复制成额外肢体" in normalized
    assert "人物表情必须生动、具体并与发起或回应角色一致" in normalized
    assert "每个 Frame 分别为发起者和回应者指定一个简短表情" in normalized
    assert "不得让所有人共享相同的空洞、微笑或惊讶表情" in normalized
    assert "至少一个环境中景或全景必须显示发起者和回应者的脸" in normalized
    assert "Hardcore 表现极度性兴奋" in normalized
    assert "潮红面颊、张开的嘴唇、急促呼吸" in normalized
    assert "表情保留自然面部结构" in normalized
    assert "每人表情使用 10–15 个英文单词" in normalized
    assert "不得为表情放大人物、头部或改用贴脸特写" in normalized
    assert "不写导演姓名或模仿在世创作者" in normalized
    assert "采用原创形式主义电影美术" in normalized
    assert "正面中心构图、精确轴线" in normalized
    assert "受控色板选自灰粉、芥末黄、湖蓝、薄荷绿、奶油白与酒红" in normalized
    assert "每场三种主色与一种强调色" in normalized
    assert "家具、门框、壁纸和灯具采用整齐网格" in normalized
    assert "和小道具采用" not in normalized
    assert "对称只用于建筑、家具、灯光和道具" in normalized
    assert "不得镜像、复制或成对增加人物" in normalized
    assert "人物和唯一接触点可偏离中轴" in normalized
    assert "不能让形式化构图压平成无空间感的平面" in normalized
    assert "最多描述两个建筑特征和三个场景颜色" in normalized
    assert "采用哑光、不反射、不透明表面" in normalized
    assert "禁止微距摄影、微距镜头、极端特写" in normalized
    assert "强制使用 20–32 mm 等效广角" in normalized
    assert "明显但可信的近大远小、汇聚线和前后景拉伸" in normalized
    assert "不得消除透视变形" in normalized
    assert "禁止鱼眼、正交感、平视平拍" in normalized
    assert "room-scale wide establishing shot" in normalized
    assert "只有一个 Frame 时必须使用该景别" in normalized
    assert "巨大人物完整身体或大段连续身体" in normalized
    assert "贴近微型人物支撑面的低机位仰拍" in normalized
    assert "从巨大访客肩部以上向下的高机位俯拍" in normalized
    assert "不得使用平直眼平视角" in normalized
    assert "low-angle wide full shot" in normalized
    assert "high-angle oblique full shot" in normalized
    assert "partial-body wide environmental shot" in normalized
    assert "局部身体镜头可以让巨大人物超出画框" in normalized
    assert "两个以上 Theme 必须同时覆盖一次仰拍和一次俯拍" in normalized
    assert "前景空间锚点、中景互动和背景房间边界三层深度" in normalized
    assert "至少两条强烈汇聚的房间深度线" in normalized
    assert "中等至较深景深" in normalized
    assert "正常人类访客性别" in normalized
    assert "发起方与回应方" in normalized
    assert "多个 Frame 是同一个已经发生的主要行为" in normalized
    assert "不是前后发展的连续故事" in normalized
    assert "禁止接近、准备、开始攀爬、驶向、下降前往、等待" in normalized
    assert "每个 Frame 严格 700–850 个英文单词" in normalized
    assert "返回前计算词数" in normalized
    assert "超过 850 词删除重复与次要细节" in normalized
    assert "第二句独立以“The single penis...”" in normalized
    assert "只命名目标一次，写自然表面、骨盆连接、形变和动作" in normalized
    assert "后文只称“the contact point”" in normalized
    assert (
        "Exactly [total] separate adult bodies are visible in total inside a "
        "miniature kingdom built for palm-sized adult inhabitants"
    ) in normalized
    assert "total = 1 + female_count + male_count" in normalized
    assert "数字均用阿拉伯数字" in normalized
    assert (
        "[female_count] living miniature adult women natives and [male_count] "
        "living miniature adult men natives, plus one normal-human-sized giant "
        "[woman/man] visitor"
    ) in normalized
    assert (
        "each miniature adult's entire body is shorter than the giant visitor's hand "
        "from wrist to fingertip, and visible background space separates every miniature "
        "head and torso"
    ) in normalized
    assert (
        "the unmistakable cross-scale spectacle is [initiator] using "
        "[invented mechanism]"
    ) in normalized
    assert "[invented mechanism] to [active effect at the contact point]" in normalized
    assert "绝大多数篇幅用于三层尺度证据" in normalized
    assert "每句重复固定称谓；同性人物禁用人物代词" in normalized
    assert "只有一名微型人物时禁用 first/second 且只给一个操作动词" in normalized
    assert "from the contact point into [channel/container]" in normalized
    assert "造型、表情和场景美术合计不超过 140 个英文单词" in normalized
    assert "句子以“The camera uses a room-scale wide establishing shot”开头" in (
        normalized
    )
    assert "不得为达到 700 词而重复人数、身高、器官名" in normalized
    assert "禁止“previous frame”“as before”" in normalized
    assert "“next phase”等跨帧词" in normalized
    assert "“same”和“identical”仅说明共同尺度" in normalized
    assert "只用自然英文简单现在时" in normalized
    assert "只写画面肯定事实" in normalized
    assert "第三句起的 penis、vaginal opening、anus 替换为 the contact point" in normalized
    assert "逐字符删除 CJK" in normalized
    assert "删除 no、not、without、unseen、uninvolved" in normalized
    assert "替换 centimeter、inch、twentieth、pencil" in normalized
    assert "核对首句身份完整及镜头句精确开头" in normalized
    assert "不附自检报告" in normalized
    assert "总人数不等于 1 + female_count + male_count" in normalized
    assert "出现额外脸、头、躯干、肢体或不止一名巨大人物" in normalized
    assert "人物轮廓在接触点外重叠、融合或共享肢体" in normalized
    assert "出现第二个性器官、第二具骨盆、断开的器官" in normalized
    assert "性活动没有排他地发生在微型—巨大之间" in normalized
    assert "缺少标志性装置" in normalized
    assert "互动只是拥抱、依偎、摆姿与无装置触碰" in normalized
    assert "多个微型人物的实际或投影身高不一致" in normalized
    assert "场景不是小人国" in normalized
    assert "输出焦距外的尺寸单位" in normalized
    assert "Frame 少于 700 个英文单词、夹杂中文" in normalized
    assert "镜头句未按指定英文开头" in normalized
    assert "人物缺少夸张造型、造型跨 Frame 改变" in normalized
    assert "发起者或回应者没有可辨认表情" in normalized
    assert "微型身体或工具未压住接触点" in normalized
    assert "Frame 停在准备状态" in normalized
    assert "输出否定、自检与禁止句" in normalized
    assert "目标器官超出正常成人尺寸、名称出现超过一次" in normalized
    assert "没有显示微型人物完整独立轮廓" in normalized
    assert "单人使用 first/second、同一人换称谓" in normalized
    assert "同性用人物代词、一人多任务、肢体变位" in normalized
    assert "流体与支撑错误" in normalized
    assert "把双方简称为同尺寸普通人物" in normalized
    assert "任何微型肢体进入巨大访客体内" in normalized
    assert "1:12" not in normalized


def test_giant_country_fantasy_scopes_cast_to_visiting_people() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "giant-country-fantasy.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "female_count 和 male_count 只约束从正常人类世界来到巨人国的成年访客" in normalized
    assert "每帧画面总人数严格等于 1 + female_count + male_count" in normalized
    assert "加一名巨人国原住民" in normalized
    assert "finger-length miniature-scale normal-world adult woman/man visitor" in normalized
    assert "giant-country native giant woman/man" in normalized
    assert "禁止输出 normal-human-sized" in normalized
    assert "不得写成天生微型种族、玩偶、模型、克隆人或儿童" in normalized
    assert "巨人不得拥有年轻、健美、无瑕或模特化的完美身材" in normalized
    assert "肥胖并有自然腹部与皮肤褶皱" in normalized
    assert "苍老并有皱纹、松弛皮肤与老年斑" in normalized
    assert "瘦削并有突出的锁骨、肋骨与关节" in normalized
    assert "疤痕、静脉、妊娠纹、色斑和左右轻微不对称" in normalized
    assert "同一 Theme 全部 Frame 固定年龄层、体型和皮肤特征" in normalized
    assert "IMAGE-SCALE COMPOSITION GATE" in normalized
    assert "访客层" in normalized
    assert "食指层" in normalized
    assert "身体层" in normalized
    assert "世界层" in normalized
    assert "所有属于巨人国原住民、巨人国建筑或当地环境的可见物件都必须按巨人居民的统一日常比例制造" in normalized
    assert "常用容器、鞋、手机、工具、家具、机器、车辆和建筑构件必须至少达到访客完整身体的高度" in normalized
    assert "较小部件可以低于访客身高，但必须以异常厚度、宽度或重量继续显出巨人尺度" in normalized
    assert "英文名称前必须明确写“giant-scale”或“colossal giant-country”" in normalized
    assert "禁止只写普通 cup、chair、door、rope、lever、bucket 或 platform" in normalized
    assert "compact miniature visitor-built workbridge" in normalized
    assert "具体、普通、可实地拍摄的巨人国城市生活场景" in normalized
    assert "不得连续两个 Theme 使用同一场景类型" in normalized
    assert "人行道、后巷、十字路口、公交维修场、市场街、建筑工地" in normalized
    assert "城市公寓、社区洗衣店、健身房、办公室、诊所、便利店或超市后场" in normalized
    assert "画面的唯一异常是巨人国居民、建筑与物件相对正常人类访客的极端尺度" in normalized
    assert "环境本身必须像现实城市" in normalized
    assert "混凝土、沥青、瓷砖、排水沟、斑马线、交通灯、路牌、广告牌" in normalized
    assert "至少四种" in normalized
    assert "除指定访客与唯一巨人外不得出现路人、司机、乘客、店员" in normalized
    assert "互不重复的城市生活类别" in normalized
    assert "住宅与家务、零售与餐饮、办公室与医疗、交通与停车" in normalized
    assert "市政与公共休闲、建筑与工业、街道与社区服务" in normalized
    assert "即使只有两个 Theme，也必须来自两个不同类别" in normalized
    assert "例子只用于打开想象，不得照抄为固定清单" in normalized
    assert "FINGER-LENGTH VISITOR SCALE AND EVERYDAY OBJECT PROOF" in normalized
    assert "所有巨人国原生事物都巨大无比" in normalized
    assert "它们彼此保持普通现实世界中人与物的比例" in normalized
    assert "不能只有一个道具巨大而其余门、桌椅、设备和基础设施接近正常人尺寸" in normalized
    assert "只允许 travel mug、coffee mug、beverage can、beverage bottle、smartphone 或 remote control" in normalized
    assert "这是封闭列表" in normalized
    assert "禁止鞋、安全帽、衣物、梯子、椅子、手电筒、工具" in normalized
    assert "巨人一根完整食指是唯一访客身高锚点" in normalized
    assert "每名访客从脚底到头顶只等于该食指从 fingertip 到 base knuckle crease 的完整长度" in normalized
    assert "finger-length miniature-scale normal-world adult visitor" in normalized
    assert "食指竖直向下伸展" in normalized
    assert "脚底与 fingertip 水平对齐，头顶与 base knuckle crease 水平对齐" in normalized
    assert "The giant's fully connected [left or right] hand hangs naturally beside the workbridge at torso depth" in normalized
    assert "one standing visitor's feet align with the fingertip" in normalized
    assert "that visitor's head aligns with the base knuckle crease" in normalized
    assert "它只证明巨人国物件而不是人物身高" in normalized
    assert "finger-length miniature-scale 是整段最高频尺度词" in normalized
    assert "不得达到巨人的手掌、前臂、膝盖、大腿、腰、胸或肩部高度" in normalized
    assert "两只巨人手必须处于同一深度、具有相同自然尺寸并分别连续连接双肩" in normalized
    assert "禁止任何手掌朝镜头、伸向访客背后、单独放大、复制或断开" in normalized
    assert "巨人的头、双肩、胸腹、骨盆、双大腿、双膝和至少一只完整脚" in normalized
    assert "不能出现为普通人制造的椅子、梯子、控制台或平台" in normalized
    assert "ordinary stepladder、office chair、rolling chair、full-size ladder、full-size platform" in normalized
    assert "the finger-length miniature-scale normal-world adult visitors occupy one separated workbridge bay each" in normalized
    assert "不得让手、脚、器官、日用品或访客伸向镜头" in normalized
    assert "每名访客必须从头顶到双脚全身可见" in normalized
    assert "完整位于巨人身体外部" in normalized
    assert "访客的头部、胸廓、腹部和骨盆四周" in normalized
    assert "可见空气、背景空隙或刚性平台边界" in normalized
    assert "除一个明确命名的局部接触面外" in normalized
    assert "禁止整名访客横跨、趴伏或贴伏在巨人的胸部、腹部、阴阜、骨盆或大腿表面" in normalized
    assert "全部访客位于同一个 miniature visitor-built workbridge 的独立编号工位" in normalized
    assert "Erotic 只允许 Signature Mechanism 的单一软垫机械末端、气流、水流或织物束带到达接触点" in normalized
    assert "Hardcore 允许被明确分配的访客嘴、一只手或单一玩具直接到达同一目标器官" in normalized
    assert "a visible air gap separates the visitor's head, torso, abdomen, and pelvis from the giant's skin" in normalized
    assert "a visible air gap separates each visitor's torso, abdomen, pelvis, arms, and legs from the giant's skin, with only the assigned mouth, hand, or toy reaching the contact point" in normalized
    assert "禁止 visitor against giant torso" in normalized
    assert "禁止 full-body direct contact、body-weight contact" in normalized
    assert "penis 的根部固定在下腹之下的 pubic arch" in normalized
    assert "shaft 从根部到 glans 的连续轴线" in normalized
    assert "vaginal opening 位于 lower pelvis 正中" in normalized
    assert "pubic mound 下方和 perineum 前方" in normalized
    assert "anus 必须写位于臀沟正中、骶骨下方" in normalized
    assert "目标上方的下腹、左右两侧的 upper inner thighs" in normalized
    assert "the lower abdomen is visibly above the target" in normalized
    assert "both thighs continue toward the knees" in normalized
    assert "目标不得出现在胸部、上腹、肚脐或平坦躯干表面" in normalized
    assert "SILHOUETTE LIMB INVENTORY" in normalized
    assert "目标器官位于两条大腿之间，绝不能代替大腿、膝或脚形成第三条腿" in normalized
    assert "penis 或 vaginal opening 使用前侧三分之四视角" in normalized
    assert "anus 使用后侧三分之四视角" in normalized
    assert "禁止从正面通过裤门襟显示臀沟和 anus" in normalized
    assert "手臂不得从软管、控制器或另一人物躯干长出" in normalized
    assert "腿不得消失进椅子、梯子、平台或巨人皮肤" in normalized
    assert "访客不得互相搭肩、交叉躯干、共享扶手或用另一人的身体承重" in normalized
    assert "人物之间和每条肢体内侧至少保留一条可见背景缝隙" in normalized
    assert "Both giant shoulders visibly connect through two separate arms to two naturally equal-sized hands at one depth" in normalized
    assert "the contact point lies between rather than replacing the thighs" in normalized
    assert "every visitor has two independently traceable arms, hands, legs, and feet" in normalized
    assert "只写“continuous with the pelvis”不算定位完成" in normalized
    assert "禁止用 lower surface、one side、lower rim" in normalized
    assert "必须以巨人的耻骨、下腹、会阴、臀沟或大腿为参照" in normalized
    assert "全部性行为只发生在一个或多个正常人类访客" in normalized
    assert "与唯一巨人国原住民之间" in normalized
    assert "每个 Theme 必须先锁定一个 CONTENT-LEVEL CAUSAL PREMISE" in normalized
    assert "画面必须同时显示原因、访客协作、物理结果和巨人自愿回应" in normalized
    assert "原因必须逐字兼容 S5 已写出的巨人姿势、支撑和双手任务" in normalized
    assert "Because [visible temporary circumstance], the visitors coordinate to [perform the content-level action]" in normalized
    assert "IF AND ONLY IF request.content_level IS erotic：互动核心是挑逗、护理、清洁、按摩、角色扮演" in normalized
    assert "不得只是裸露程度变化" in normalized
    assert "IF AND ONLY IF request.content_level IS hardcore：互动核心必须是访客与巨人之间已经发生的直接露骨性行为" in normalized
    assert "从口交、手交、玩具插入、直接外阴刺激或自愿 BDSM 刺激中只选择一种" in normalized
    assert "若有两名或更多访客，至少一名访客必须直接参与主要性行为" in normalized
    assert "多人协作口交的主要行为名称只能是“cooperative oral stimulation”或“coordinated oral sex”" in normalized
    assert "一名访客在龟头或外阴接触中心使用嘴" in normalized
    assert "每名直接参与者只允许一种接触面" in normalized
    assert "禁止两颗头占据同一位置" in normalized
    assert "大量且清晰可见的精液、尿液喷射、阴道液体或灌肠喷射" in normalized
    assert "自愿 BDSM 系统" in normalized
    assert "可把城市洗衣、升降、清洁、通风、排水、交通维修或屋顶设施改成承重、定位、节奏或流体机制" in normalized
    assert "不得把乳头、阴毛或柔软组织作为唯一锚点" in normalized
    assert "显示自然阴毛及其与皮肤、骨盆的连续边界" in normalized
    assert "所有人物都必须穿衣或半裸露，不得全身裸体" in normalized
    assert "巨人国原住民穿着两至四件符合场景的正常衣物及一件配饰" in normalized
    assert "只局部打开当前动作所需区域" in normalized
    assert "visibly bunched around the upper thighs" in normalized
    assert "不得一边写穿裤子一边让下装从画面消失" in normalized
    assert "S4 写出的每件衣物、鞋履和头饰状态必须逐字约束 S5" in normalized
    assert "写了 shoes、boots 或 sandals 就必须保持穿在对应双脚" in normalized
    assert "miniature-scale visitors 各穿一种高对比纯色连体工作服和清楚鞋履" in normalized
    assert "衣物不得遮住肢体和接触点" in normalized
    assert "巨人需要完整人物造型" in normalized
    assert "miniature-scale visitors 不描述眼妆、唇色、首饰、面部微表情、精细材质或时装剪裁" in normalized
    assert "只写成年脸部存在、不同发型外轮廓、单一服装色和任务姿势" in normalized
    assert "巨人拥有与互动一致的明确表情和视线" in normalized
    assert "访客只以头部朝向和身体动作表达专注" in normalized
    assert "每人的动作必须是一个稳定、可拍摄的当前动作" in normalized
    assert "躯干朝向、重心、主要支撑面、双手唯一任务" in normalized
    assert "固定每人的造型、妆容、表情角色、动作、支撑与四肢位置" in normalized
    assert "巨人必须具有与年龄和体型一致的自然体毛" in normalized
    assert "胸毛、腹毛、腋毛、手臂毛、腿毛或背毛中的至少两处" in normalized
    assert "灰白变化和皮肤连接" in normalized
    assert "At [specific real-world urban giant-country setting]" in normalized
    assert "exactly [total] separate adult bodies are visible in total:" in normalized
    assert "不能只写 generic interior、street、city、outdoors 或 giant country" in normalized
    assert "plus one giant-country native giant [woman/man]" in normalized
    assert "像普通摄影师在真实地点使用真实相机完成的真人外景或室内拍摄" in normalized
    assert "live-action photorealistic location photography" in normalized
    assert "真实成年演员、真实皮肤毛孔与体毛" in normalized
    assert "可信镜头光学、自然曝光、物理景深和一致阴影" in normalized
    assert "高预算实拍比例特效、实体布景、外景摄影与无缝合成" in normalized
    assert "最终画面仍像未经夸张美术化的现场照片" in normalized
    assert "禁止 illustration、painting、anime、comic、CGI look、3D render" in normalized
    assert "塑料皮肤、蜡像人物和过度磨皮" in normalized
    assert "室内外环境必须具有使用、风化和维护痕迹" in normalized
    assert "不得像空布景或刚搭建的主题乐园" in normalized
    assert "不得默认哥特、腐朽、毒性、恐怖" in normalized
    assert "照明必须清楚显示完整访客、唯一接触点、体毛及全部尺度参照" in normalized
    assert "同一 Theme 的全部 Frame 锁定巨人的支撑姿势、骨盆旋转" in normalized
    assert "不能把站、坐、跪、躺互换" in normalized
    assert "不可变的 S2–S6 subject block" in normalized
    assert "再复制到全部 Frame" in normalized
    assert "配对 Frame 只改变相机方位和最终镜头句" in normalized
    assert "严格按以下物理句序写，任何顺序变化都重写" in normalized
    assert "S1 CAST + EARLY SCALE + INTERACTION + MECHANISM + CAMERA" in normalized
    assert "必须逐字套用以下单句骨架" in normalized
    assert "occupy one separated bay each on a single miniature visitor-built workbridge" in normalized
    assert "while the visitors carry out [one content-level interaction] using [colossal giant-country location-native Signature Mechanism]" in normalized
    assert "在 perspective 之前不得出现句号或分号" in normalized
    assert "S2 TARGET MAP" in normalized
    assert "两个短语缺少任意一个就重写整个 Frame" in normalized
    assert "S2 只写解剖定位，不得插入 Chinese、Asian、年龄、体型、身份、服装、表情" in normalized
    assert "S3 FOUR SCALE PROOFS" in normalized
    assert "Four simultaneous scale proofs share one clear focal plane:" in normalized
    assert "禁止把手掌作为尺度证明" in normalized
    assert "S3 必须以句号结束" in normalized
    assert "the selected giant-scale everyday anchor functions as an ordinary everyday object for the giant" in normalized
    assert "不得在 S3 使用 held、worn、lying、resting、remains 或其他位置状态词" in normalized
    assert "S3 必须明确包含一个最低台阶、门槛、路缘或支撑底座高过访客全身" in normalized
    assert "S3A FINGER-LENGTH HEIGHT" in normalized
    assert "不得省略 fully connected、torso depth、fingertip 或 base knuckle crease" in normalized
    assert "S3B EVERYDAY OBJECT PROOF" in normalized
    assert "clearly towers above the finger-length visitors as an ordinary object made for the giant" in normalized
    assert "Signature Mechanism 必须是当前地点本来就会安装、存放或使用的原生系统" in normalized
    assert "为什么这个装置会在这里" in normalized
    assert "所有锚点、滑轮、缆线、支架和承重结构都必须属于同一地点功能链" in normalized
    assert "Erotic 中，S1 命名的 Signature Mechanism 必须直接作用于接触点" in normalized
    assert "visitor-scale control input → giant-scale force transmission" in normalized
    assert "Hardcore 中，S1 命名的 Signature Mechanism 必须直接承托、定位、稳定、驱动节奏或承接体液" in normalized
    assert "assigned visitor mouth, hand, or toy at the contact point" in normalized
    assert "这属于装饰性假机制" in normalized
    assert "作业桥严格具有与访客人数相等的左到右编号工位" in normalized
    assert "每个工位只有一人并以栏杆和背景缝隙分隔" in normalized
    assert "U+2019 改为 ASCII apostrophe" in normalized
    assert "S4 CHARACTER DESIGN" in normalized
    assert "一个物理句子先详细写巨人造型" in normalized
    assert "S5 POSE AND ACTION" in normalized
    assert "S5A LIMB TOPOLOGY" in normalized
    assert "一个物理句子写巨人姿势和全部访客工位" in normalized
    assert "逐人写双臂、双手、双腿和双脚的无遮挡路径" in normalized
    assert "必须逐字复制 S3A 的“the giant's fully connected [side] hand hangs naturally beside the workbridge at torso depth" in normalized
    assert "参照手不得改成 raised、braced、busy、holding、pressing 或 gripping" in normalized
    assert "S6 CONTENT-LEVEL CAUSAL INTERACTION" in normalized
    assert "原因只能来自另一只手的任务或身体姿势" in normalized
    assert "不能写 both hands、hands are occupied" in normalized
    assert "S6 不得新增人物、工位或巨人动作" in normalized
    assert "物理第一句必须点名具体 real-world urban setting" in normalized
    assert "紧接句号后的物理第二句必须以" in normalized
    assert "任何人物介绍、服装、妆容、机制解释或环境句都不得出现在它之前" in normalized
    assert "live-action photorealistic location photography captured from a distance with a real 35–50 mm camera" in normalized
    assert "previous frame, same, identical, unchanged, still, again, now, remains, then, afterward, next, about to, will, normal-human-sized" in normalized
    assert "NEVER OUTPUT THESE TOKENS IN ANY CONTEXT" in normalized
    assert "U+2010、U+2011 和 U+2012 改为 ASCII hyphen" in normalized
    assert "The finger-length miniature-scale visitors are each only as long as one fully connected giant index finger" in normalized
    assert "both giant hands share one natural scale and depth" in normalized
    assert "The camera uses a distant environment-scale wide establishing shot" in normalized
    assert "live-action photorealistic location photography" in normalized
    assert "纪实摄影、生活方式摄影或克制的商业外景摄影观感" in normalized
    assert "不使用 fantasy、epic、mythic、enchanted、otherworldly" in normalized
    assert "真实材料的接缝、磨损、灰尘、湿气和受力" in normalized
    assert "可信地质、普通植物、天气方向" in normalized
    assert "风对头发和衣物的影响，以及自然大气透视" in normalized
    assert "绝对禁止 magic、spell、sorcery、enchantment、rune power、portal" in normalized
    assert "teleportation、levitation、floating island" in normalized
    assert "无支撑悬浮" in normalized
    assert "禁止满画面霓虹、自发光轮廓、无来源光、过饱和糖果色" in normalized
    assert "调色保持中性、自然、略微克制" in normalized
    assert "强制使用距离主体较远的 35–50 mm 等效正常视角" in normalized
    assert "镜头光轴近似垂直于食指与登记访客形成的并排平面" in normalized
    assert "巨人的头、双肩、双臂、两只自然等大的手、胸腹、骨盆、双腿和至少一只完整脚处于画框内" in normalized
    assert "urban indoor、urban outdoor 或 semi-open urban location" in normalized
    assert "不得包含乡村、荒野、魔法、天文奇观、发光森林、晶体宫殿或史诗化环境" in normalized
    assert "THEME CONTRACT" in brief
    assert "FRAME CONTRACT" in brief
    assert "VARIATION AND REJECTION RULES" in brief
    assert "1:15" not in normalized
    assert "11-centimeter" not in normalized
    assert "14-centimeter" not in normalized


def test_furry_mythic_interactions_uses_original_live_action_characters() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "furry-mythic-interactions.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert "DETERMINISTIC CAST ALLOCATION" in brief
    assert "total_count = female_count + male_count" in normalized
    assert "Set furry_count = 1 for every Theme" in normalized
    assert "human_count = total_count - 1" in normalized
    assert "the lower positive count supplies the furry slot" in normalized
    assert "If the two positive counts are equal, the male slot is furry" in normalized
    assert "two women and one man becomes two human women and one male furry" in (
        normalized
    )
    assert "one woman and two men becomes one female furry and two human men" in (
        normalized
    )
    assert "COMMON CAST EXACT OPENINGS" in brief
    assert "human_count = 2, furry_count = 1, zero other bodies" in normalized
    assert "two named human women and one named adult male anthropomorphic" in (
        normalized
    )
    assert "TWO-WOMEN-ONE-MAN ABSOLUTE LOCK" in brief
    assert "The phrases human man and female furry are forbidden" in normalized
    assert "name both human women and the male furry before stating the act" in (
        normalized
    )
    assert "give the second human woman direct contact with one of the other two" in (
        normalized
    )
    assert "The cast declaration must continue in that same sentence with" in normalized
    assert "the male furry's penis is inside the first human woman's vagina" in (
        normalized
    )
    assert "Preserve exactly female_count female slots and male_count male slots" in (
        normalized
    )
    assert "SINGLE-SLOT EXACT OPENING" in brief
    assert "exactly one requested adult woman and zero adult men, allocated as" in (
        normalized
    )
    assert "exactly one visible adult body" in normalized
    assert "with zero humans and zero other furry beings" in normalized
    assert "Never add a character outside those requested slots." in normalized
    assert "alert, intelligent, speaking or clearly reasoning adult" in normalized
    assert "FURRY GENDER CONTRACT" in brief
    assert "The furry character inherits the gender of the deterministically selected" in (
        normalized
    )
    assert (
        "If only female_count is nonzero, every furry being is female." in normalized
    )
    assert "If only male_count is nonzero, every furry being is male." in normalized
    assert "keep name, gender, pronouns, and sexual anatomy consistent" in normalized
    assert "FURRY GENDER OVERRIDES ACT SELECTION" in brief
    assert (
        "one woman and zero men means one female furry adult and zero humans"
        in normalized
    )
    assert "An all-female run contains no penis, scrotum, testicles" in normalized
    assert "choose only an act compatible with the locked anatomy" in normalized
    assert "ungendered presentation" not in normalized
    assert "photographed adult performer" in normalized
    assert "physically present cinematic creature" in normalized
    assert "FURRY WARDROBE FREEDOM" in brief
    assert "Every furry being wears at least one clearly visible" in normalized
    assert "Do not assign a fixed outfit or garment family" in normalized
    assert "never leave the furry being as an entirely unclothed fur-only body" in (
        normalized
    )
    assert "public-domain mythological" in normalized
    assert "Journey to the West figures" in normalized
    assert "The Eight Immortals" in normalized
    assert "completely original high-fantasy characters" in normalized
    assert "completely original heroic" in normalized
    assert "Do not reproduce a character" in brief
    assert "Warcraft" in brief
    assert "Marvel" in brief
    assert "Do not name, imitate, evoke, combine, or transpose the style" in normalized
    assert "Do not use the name, title, alias, face, biography" in normalized
    assert (
        "The requested themes and frames run parameters are the sole authority"
        in normalized
    )
    assert (
        "Do not assign T001, T002, or any other Theme ID to a predetermined source"
        in normalized
    )
    assert "When these Theme IDs exist" not in brief
    assert "- T001:" not in brief
    assert "visible, consequential decision that has already taken effect" in normalized
    assert 'Never write "must choose," "must decide,"' in normalized
    assert "End every Theme premise with two concise proof clauses" in normalized
    assert '"Decision: [protagonist name]' in normalized
    assert "The premise must end after the Immediate response clause." in brief
    assert "Put the visual style only in the separate Theme style value." in normalized
    assert (
        "At Aesthetic and Erotic levels, begin every Frame by independently naming "
        "the precise location"
    ) in normalized
    assert "with no backward pointer" in normalized
    assert "Restage one equivalent decisive instant" in normalized
    assert "F02 is not later than F01" in normalized
    assert "Every variation must read as a fresh staging" in normalized
    assert "the protagonist's completed decision" in normalized
    assert "must not displace the protagonist from narrative and optical priority" in (
        normalized
    )
    assert "Do not mention the brief, prompt, request, model, generator" in normalized
    assert '"the image reads first as," "only afterward,"' in normalized
    assert "use only ASCII code points U+0020 through U+007E" in normalized
    assert "Transliterate personal and place names" in normalized
    assert "scan every title, premise," in normalized
    assert "advances the fixed time window" in normalized
    assert "Do not use anime" in brief
    assert "At aesthetic level" in brief
    assert "At erotic level" in brief
    assert "At hardcore level" in brief
    assert "one explicit consensual adult sexual act already occurring" in normalized
    assert "Within the first one hundred English words" in normalized
    assert 'exact phrase "consensual and willing"' in normalized
    assert "For total_count equal to one, place the furry protagonist's explicit" in (
        normalized
    )
    assert "For larger casts, place every participant in the same direct" in (
        normalized
    )
    assert "whose penis is inside whose vagina or anus" in normalized
    assert "Vague phrases such as intimate contact" in normalized
    assert 'calling the image a "live-action fantasy photograph"' in normalized
    assert (
        "stating the exact requested adult gender totals, exact human_count, exact "
        "furry_count"
    ) in normalized
    assert "Put the direct anatomical contact in this same first sentence." in normalized
    assert "first sentence takes absolute priority" in normalized
    assert "All sexual anatomy is ordinary adult humanoid anatomy" in normalized
    assert "Never use a muzzle shape, beak, horn, claw, tail, wing, paw pad" in (
        normalized
    )
    assert "no adult merely watches from the background" in normalized
    assert "ALLOCATED BODY COUNT AND CONTACT LOCK" in brief
    assert "state the exact total number of visible adult bodies" in normalized
    assert "Name every human and furry being individually in the first sentence" in (
        normalized
    )
    assert (
        "the first two sentences must give every furry and human participant one "
        "current"
    ) in normalized
    assert "A second or later participant may not stand beside" in normalized
    assert "Self-touch may supplement but never replace contact with another" in (
        normalized
    )
    assert "one separate, unobscured body slot for each participant" in normalized
    assert "hard minimum of 600 whitespace-delimited words" in normalized
    assert "Target 750-950 words" in normalized
    assert "Never mention a word count or length check" in normalized
    assert "At Aesthetic and Erotic levels, begin every Frame" in normalized
    assert "At Hardcore level, use the mandatory cast-and-contact first" in normalized
    assert "HARDCORE POSE GEOMETRY" in brief
    assert "broad, dry, level, room-temperature, non-slip support" in normalized
    assert "Do not select from or repeat a fixed catalog of named poses." in brief
    assert "invent a new physically plausible pose" in normalized
    assert "There is no mandatory pose sequence, quota, or four-pose cycle." in (
        normalized
    )
    assert "Do not use standing penetration, a wall-pressed body" in normalized
    assert "pelvises to meet at incompatible heights" in normalized
    assert "complete a silent limb ledger for every participant" in normalized
    assert "left thigh, left knee, left lower leg, and left foot" in normalized
    assert "right thigh, right knee, right lower leg, and right foot" in normalized
    assert "within the first three hundred English words" in normalized
    assert 'Use the literal side labels "left arm", "left hand", "right arm"' in (
        normalized
    )
    assert "they never replace the side-specific map" in normalized
    assert "Immediately after the mandatory Hardcore cast-and-contact sentence" in (
        normalized
    )
    assert "the complete human limb map, then the complete furry limb map" in normalized
    assert "Do not insert face, hair, biography, mythology, wardrobe" in normalized
    assert "Keep human arms visually separate from furry forelimbs." in brief
    assert "NON-ORAL MOUTH SAFETY" in brief
    assert (
        "keep every hand, finger, forepaw, claw, object, garment edge, and tail "
        "outside the human and furry mouths"
    ) in normalized
    assert "Do not cradle, cover, press, pull, or stroke a face near the lips" in (
        normalized
    )
    assert "place supporting hands below the collarbones or on the shared support" in (
        normalized
    )
    assert "Every furry being has exactly two arms and two legs." in brief
    assert "Never add a third leg, duplicate a knee" in normalized
    assert "The tail is never load-bearing during intimacy." in brief
    assert "Do not coil it around architecture, furniture, a limb" in normalized
    assert "Match the sexual act to the visible head anatomy." in brief
    assert "with a beak, bill, rigid muzzle, tusks, large fangs" in normalized
    assert "never performs oral-genital contact" in normalized
    assert "Use a 35mm to 65mm three-quarter or full-body camera view" in normalized
    assert "camera obliquely enough to separate overlapping limbs" in normalized
    assert "Hardcore Frame without a clearly named adult sexual act" in normalized
    assert "uses \"explicit interaction\" for nonsexual ritual" in normalized
    assert "an English Frame below 600 whitespace-delimited words" in normalized
    assert "THEME CONTRACT" in brief
    assert "FRAME CONTRACT" in brief
    assert "VARIATION AND REJECTION RULES" in brief


def test_dress_board_region_names_are_layout_only() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "dress.txt").read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert "Do not render the Theme title or region names as visible text." in brief
    assert "Use region names only as internal layout references" in brief
    assert "Begin the scale at visibly sensual" in normalized
    assert "requires a cast of one woman and zero men" in normalized
    assert "zero or one visually restrained body-safe adult product" in normalized
    assert "adult product-and-wearable fashion system" in normalized
    assert (
        "Include one to three clearly designed body-safe adult products" in normalized
    )
    assert "EXAGGERATED BRIGHT CHARACTER STYLING" in normalized
    assert (
        "hairstyle, outfit design, worn styling, and visible facial expression"
        in normalized
    )
    assert "bright lighting alone" in normalized
    assert "DECISION ORDER" in normalized
    assert "A later choice must never weaken an earlier one" in normalized
    assert "limited high-chroma palette" in normalized
    assert "BDSM equipment-and-wardrobe design board" in normalized
    assert "Include three to six BDSM-specific designed elements" in normalized
    assert "BDSM EQUIPMENT SPECIFICATION" in normalized
    assert "at least two externally wearable pieces" in normalized
    assert "non-load-bearing, low-pressure, and visibly releasable" in normalized
    assert "HARDCORE VISUAL IMPACT GATE" in normalized
    assert "remains powerful at thumbnail scale" in normalized
    assert "Use at least three of these contrast axes" in normalized
    assert "one dominant statement, two secondary structures" in normalized
    assert "CURATED HARDCORE WARDROBE ARCHETYPES" in normalized
    assert "CURATED HARDCORE EQUIPMENT SYSTEMS" in normalized
    assert "CURATED EXPLICIT BDSM PRODUCT CATEGORIES" in normalized
    assert "SEX TOY PRODUCT SPECIFICATION" in normalized
    assert "CURATED SEX TOY PRODUCT CATEGORIES" in normalized
    assert "CURATED HARDCORE MATERIAL AND COLOR SYSTEMS" in normalized
    assert "nipple clamps" in normalized
    assert "ball gag" in normalized
    assert "bit gag" in normalized
    assert "open-center mouth gag" in normalized
    assert "Any selected hardcore product may appear worn" in normalized
    assert "visible low-tension limiter" in normalized
    assert "visible breathing path" in normalized
    assert "relaxed jaw" in normalized
    assert "chastity-inspired waist belt" in normalized
    assert "ventilated leather half-mask" in normalized
    assert "wide posture collar" in normalized
    assert "bondage mitts" in normalized
    assert "breast-framing leather harness" in normalized
    assert "lightweight padded spreader bar" in normalized
    assert "soft suede flogger" in normalized
    assert "broad padded leather paddle" in normalized
    assert "limited body area necessary" in normalized
    assert "External wearable sex toys may appear fitted" in normalized
    assert "Insertive product categories may be named and shown" in normalized
    assert "must remain completely outside the body" in normalized
    assert "full-size wand massager" in normalized
    assert "strap-on harness carrying a removable silicone dildo" in normalized
    assert "classic silicone dildo" in normalized
    assert "rabbit vibrator" in normalized
    assert "jeweled silicone butt plug" in normalized
    assert "graduated anal-bead set" in normalized
    assert "textured masturbation sleeve" in normalized
    assert "one to three sex toys in addition to its BDSM" in normalized
    assert "PRODUCT AUTHENTICITY GATE" in normalized
    assert "attach to the nipples" in normalized
    assert "attached to lace" in normalized
    assert "must not be called a nipple clamp" in normalized
    assert "CONSTRUCTION AND CONNECTION INTEGRITY" in normalized
    assert "collar seamlessly extends into gloves" in normalized
    assert "material flat lay must show two shoes, two gloves" in normalized
    assert "genuinely different presentation" in normalized
    assert "Change at least four of these" in normalized
    assert "Do not write the internal level names" in normalized
    assert "BDSM may appear at most once" in normalized
    assert "do not leak untranslated English workflow words" in normalized
    assert "Do not pad final prose with compliance-shaped negations" in normalized
    assert "does not satisfy product emphasis" in normalized
    assert "Do not use the words futuristic" in normalized
    assert "generic mid-gray walls" in normalized
    assert "flat, shadowless catalog lighting" in normalized
    assert "Every named product has its real shape and intended fit" in normalized
    assert "Every Frame differs from other Frames" in normalized
    assert "Final prose never states an internal content level" in normalized
    assert "cybernetic body parts" in normalized
    assert (
        "State shared identity, outfit, palette, and inventory facts once"
        in normalized
    )
    assert "technology-shaped costume components" in normalized
    assert "utilitarian futurism" not in normalized
    assert "Aesthetic is sensual lingerie-led fashion" in normalized
    assert "hardcore is a BDSM wardrobe-and-equipment system" in normalized
    assert "Present one complete, opaque, non-erotic outfit." not in brief
    assert "At aesthetic level, include none." not in brief

    wardrobe_pool = brief.split("\nCURATED HARDCORE WARDROBE ARCHETYPES\n", maxsplit=1)[
        1
    ].split("\nCURATED HARDCORE EQUIPMENT SYSTEMS\n", maxsplit=1)[0]
    equipment_pool = brief.split("\nCURATED HARDCORE EQUIPMENT SYSTEMS\n", maxsplit=1)[
        1
    ].split("\nCURATED EXPLICIT BDSM PRODUCT CATEGORIES\n", maxsplit=1)[0]
    product_pool = brief.split(
        "\nCURATED EXPLICIT BDSM PRODUCT CATEGORIES\n", maxsplit=1
    )[1].split("\nCURATED SEX TOY PRODUCT CATEGORIES\n", maxsplit=1)[0]
    sex_toy_pool = brief.split("\nCURATED SEX TOY PRODUCT CATEGORIES\n", maxsplit=1)[
        1
    ].split("\nCURATED HARDCORE MATERIAL AND COLOR SYSTEMS\n", maxsplit=1)[0]
    material_pool = brief.split(
        "\nCURATED HARDCORE MATERIAL AND COLOR SYSTEMS\n", maxsplit=1
    )[1].split("\nSIX-VIEW BOARD CONTRACT\n", maxsplit=1)[0]
    for pool in (
        wardrobe_pool,
        equipment_pool,
        product_pool,
        sex_toy_pool,
        material_pool,
    ):
        entries = [
            line.removeprefix("- ").strip()
            for line in pool.splitlines()
            if line.startswith("- ")
        ]
        assert len(entries) >= 8
        assert len(entries) == len(set(entries))

    explicit_product_entries = [
        line.removeprefix("- ").strip()
        for line in product_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(explicit_product_entries) >= 12
    sex_toy_entries = [
        line.removeprefix("- ").strip()
        for line in sex_toy_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(sex_toy_entries) >= 10

    assert (
        "The Theme title appears exactly once and the six region labels "
        "each appear once"
    ) not in brief


def test_post_layout_brief_builds_one_analog_collage_poster() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "post-layout.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "tactile mid-century cinematic photomontage" in normalized
    assert "REFERENCE EFFECT AND POSTER DNA" in normalized
    assert "one dominant monochrome photographic hero" in normalized
    assert "two to four smaller documentary" in normalized
    assert (
        "one oversized condensed headline assembled on a torn paper slab" in normalized
    )
    assert "overlapping torn paper with irregular deckled edges" in normalized
    assert "halftone dots, photocopy grain, coarse newsprint" in normalized
    assert "Deliberate collage is mandatory" in normalized
    assert "portrait 4:5 poster" in normalized
    assert "Repeated photographic crops of the same protagonist" in normalized
    assert "Do not drift into clean corporate minimalism" in normalized
    assert "The reference establishes this design grammar only" in normalized
    assert "ENGLISH-ONLY IMAGE TEXT GATE" in normalized
    assert "seven internal planning concerns" in normalized
    assert "not as a literal response format" in normalized
    assert "Do not print those concern names" in normalized
    assert "SEVEN-PART CONTENT STRUCTURE" in normalized
    assert "Their names are internal authoring cues" in normalized
    assert (
        "Write one compact, fluent paragraph rather than seven labeled lines"
        in normalized
    )
    assert (
        "dedicated image-text passage inside the natural prose is the sole "
        "source of visible image copy"
    ) in normalized
    assert "exact physical carrier, poster location" in normalized
    assert "add an ASCII colon" in normalized
    assert "end with an ASCII semicolon" in normalized
    assert "Never enclose copy in quotation marks" in normalized
    assert "zero Chinese characters" in normalized
    assert "do not authorize Chinese writing in the image" in normalized
    assert "no quotation mark surrounds visible copy" in normalized
    assert "If a word is not explicitly declared in that passage" in normalized
    assert "zero non-English glyphs appear anywhere" in normalized
    assert "Composition: one exact aspect ratio" not in normalized
    assert "Output: resolution matching" not in normalized
    assert "Composition and Output both specify portrait 4:5" not in normalized
    for label in (
        "Subject:",
        "Scene:",
        "Composition:",
        "Style:",
        "Text:",
        "Details:",
        "Output:",
    ):
        assert label not in brief
    assert "turn one finished design into a collage of proposals" not in normalized


def test_post_briefs_isolate_text_without_removing_poster_copy() -> None:
    film_post = (
        REPOSITORY_ROOT / "story-inputs" / "film-post.txt"
    ).read_text(encoding="utf-8")
    post_layout = (
        REPOSITORY_ROOT / "story-inputs" / "post-layout.txt"
    ).read_text(encoding="utf-8")

    for filename, brief in (
        ("film-post.txt", film_post),
        ("post-layout.txt", post_layout),
    ):
        normalized = " ".join(brief.split())

        assert "TEXT-LAYER ISOLATION LOCK" in normalized, filename
        assert "Frame prose must use English throughout" in normalized, filename
        assert "During Theme generation" in normalized, filename
        assert (
            "Every character in the complete Frame must be ASCII code point"
            in normalized
        ), filename
        assert "U+2018 and U+2019 with a straight apostrophe" in normalized, filename
        assert "dedicated image-text passage" in normalized, filename
        assert "add an ASCII colon" in normalized, filename
        assert "end with an ASCII semicolon" in normalized, filename
        assert "the literal characters `: `" in normalized, filename
        assert "never write the words colon or semicolon" in normalized, filename
        assert "The Frame's final character is `;`" in normalized, filename
        assert "gibberish" in normalized, filename
        assert "unreadable microtext" in normalized, filename
        assert "exactly three readable English strings" not in normalized, filename
        assert "exactly three controlled typography zones" not in normalized, filename

    film_normalized = " ".join(film_post.split())
    assert (
        "Keep the original theatrical copy package and typography freedom"
        in film_normalized
    )
    assert "title, tagline, release line, billing block, credits" in film_normalized
    assert "one original English tagline written for that design" in film_normalized
    assert "and a compact fictional English billing block" in film_normalized
    assert "evidence and archive: receipts, letters, maps" in film_normalized
    assert "handwritten evidence" in film_normalized

    layout_normalized = " ".join(post_layout.split())
    assert "Visible-copy serialization must not change the poster design" in (
        layout_normalized
    )
    assert (
        "Do not remove or simplify editorial fragments, credits, quotations, "
        "dates, venue details" in layout_normalized
    )
    assert (
        "a few short English editorial fragments, credits, quotation blocks, "
        "date or venue details" in layout_normalized
    )
    assert (
        "ticket, photograph edge, credit strip, badge, sign" in layout_normalized
    )


def test_jav_dvd_wrap_has_complete_ascii_packaging_contract() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "jav-dvd-wrap.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "back panel on the left, a narrow spine in the center" in normalized
    assert "ENGLISH-ONLY ASCII LOCK" in normalized
    assert "Every character in the complete Frame must be ASCII code point" in (
        normalized
    )
    assert "TEXT-LAYER ISOLATION LOCK" in normalized
    assert "The Frame's final character must be `;`" in normalized
    assert "43-46 percent of the width to the back panel" in normalized
    assert "6-8 percent to the spine" in normalized
    assert "47-50 percent to the front panel" in normalized
    assert "six to nine bordered inset stills" in normalized
    assert "No body, face, hand, limb, prop, fluid, or garment may cross" in (
        normalized
    )
    assert "Use the exact requested human cast and no additional people" in normalized
    assert "unmistakably mature Chinese adult" in normalized
    assert "When the requested cast is one woman and zero men" in normalized
    assert "every front, back, and inset photograph is strictly solitary" in normalized
    assert "off-camera participant, second body, extra hand, partial head" in normalized
    assert "premise must describe solo agency" in normalized
    assert "At aesthetic level" in normalized
    assert "At erotic level" in normalized
    assert "At hardcore level" in normalized
    assert "Every inserted object must be a body-safe sex toy" in normalized
    assert "Never insert a bottle, food, household object" in normalized
    assert "Frames are parallel campaign variants" in normalized
    assert "ADULTS 25+" in normalized
    assert "one exact invented 13-digit barcode number" in normalized
    assert "Target 700-1000 words" in normalized
    assert "absolute range of 500-1300 words" in normalized
    assert "each inset description under 40 words" in normalized
    assert "State shared lighting, identity, borders, and print behavior once" in normalized
    assert "Reject and rewrite any Frame below 500 words or above 1300 words" in normalized
    assert "final dedicated image-text passage is missing" in normalized
    assert "one complete flat sleeve" in normalized


def _legacy_everyday_social_caricature_contract() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "everyday-social-caricature.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert "EAST ASIAN CAST AND SETTING LOCK" in normalized
    assert "Every visible person is a fictional East Asian adult" in normalized
    assert (
        "mainland Chinese, Taiwanese, Hong Kong Chinese, Japanese, South Korean, "
        "and Singaporean Chinese"
        in normalized
    )
    assert "Set every Theme and Frame in mainland China, Taiwan, Hong Kong" in normalized
    assert "Use plausible local names in ASCII Latin letters" in normalized
    assert "Every Theme premise must explicitly identify each person's allowed identity" in (
        normalized
    )
    assert "Every Frame must identify every adult as an East Asian woman or East Asian man" in normalized
    assert "WOMAN-CENTERED AGENCY" in normalized
    assert "At least one adult woman is the unmistakable narrative" in normalized
    assert "Use exactly the requested cast and add no bystanders" in normalized
    assert "ENGLISH OUTPUT AND REAL-PERSON PHOTOMONTAGE LOCK" in normalized
    assert "complete Frame in English, regardless of the requested output language" in (
        normalized
    )
    assert "Use English-only ASCII characters" in normalized
    assert "Reject any code point outside ASCII U+0020 through U+007E" in normalized
    assert "Write personal names in normal Title Case" in normalized
    assert "reserve uppercase words exclusively for exact visible copy" in normalized
    assert (
        "Flat satirical photomontage assembled from photographs of real adult "
        "performers:"
        in normalized
    )
    assert "exact cast supplied by the generation request" in normalized
    assert "Exactly [requested total] East Asian adults fill the image" in normalized
    assert "Omit a gender phrase when its requested count is zero" in normalized
    assert "Never infer, default, or hard-code any count in this brief" in normalized
    assert "two East Asian women and one East Asian man" not in normalized
    assert "repeat the complete opening cast declaration verbatim" in normalized
    assert "final two-entry text passage" in normalized
    assert "Every visible person must remain unmistakably photographic and human" in (
        normalized
    )
    assert "Do not use illustration, drawing, painting" in normalized
    assert "anime, manga, chibi" in normalized
    assert "real photographic adult cutouts" in normalized
    assert "The final style sentence must positively restate" in normalized
    assert "LIFE AS THE SOURCE" in normalized
    assert "invisible domestic labor" in normalized
    assert "friendship rituals" in normalized
    assert "dating, courtship, commitment" in normalized
    assert "workplace meetings" in normalized
    assert "attention, imitation, approval, self-presentation" in normalized
    assert "CARICATURE AND CONTROLLED DISTORTION" in normalized
    assert "Exaggerate decisively" in normalized
    assert "SATIRICAL CARICATURE HARD GATE" in normalized
    assert "one controlled caricatural exaggeration" in normalized
    assert "thirty to forty percent of the image" in normalized
    assert "Exactly one physical supporting object" in normalized
    assert "CONTROLLED WHOLE-BODY EXAGGERATION" in normalized
    assert "Every adult appears as one intact photographic person" in normalized
    assert "Use no more than one anatomical or silhouette exaggeration" in normalized
    assert "Never cut, paste, duplicate, float, detach, fold, splice" in normalized
    assert "Do not exaggerate breasts, buttocks, genitals, tongue" in normalized
    assert "Do not use exact body-part canvas percentages" in normalized
    assert "Branch immediately after the cast sentence" in normalized
    assert "For hardcore, the second sentence must begin with the explicit act" in (
        normalized
    )
    assert "All requested adults are already joined in one consensual explicit act:" in (
        normalized
    )
    assert "This sentence contains only names, involved anatomy, present contact" in (
        normalized
    )
    assert "within the first eighty English words after the fixed opening phrase" in (
        normalized
    )
    assert "Only after this early content proof" in normalized
    assert "complete head-to-foot outfit" in normalized
    assert "including top, bottom or one-piece garment, and footwear" in normalized
    assert "describe each adult's remaining or displaced clothing" in normalized
    assert "Clothing must not cover or contradict required contact" in normalized
    assert "Immediately after the selected-level proof" in normalized
    assert "All figures are frontal whole-person photographic cutouts" in normalized
    assert "before faces, metaphor, setting, or props" in normalized
    assert "Never mention instructions, sentence numbers, requirements" in normalized
    assert "Exaggerate decisively, but select exactly one item" in normalized
    assert "Never assign a second item from the list to the same person" in normalized
    assert "These choices are mutually exclusive" in normalized
    assert "whole-body scaling leaves hair, garments, limbs, and face unaltered" in (
        normalized
    )
    assert "scaled between seventy and one hundred thirty percent" in normalized
    assert "without changing the size or shape of any facial organ" in normalized
    assert "Never resize or paste a face or isolated organ" in normalized
    assert "All faces must remain unmistakably mature" in normalized
    assert "Reject smooth doll faces, huge sparkling eyes" in normalized
    assert "DRAW FIRST, DESCRIBE SECOND" in normalized
    assert "silently draw at least three radically different thumbnail" in normalized
    assert "using only black shapes and one accent color" in normalized
    assert "silently assemble one complete final photomontage" in normalized
    assert "separately photographed real adult performers" in normalized
    assert "following the viewer's scan order from dominant icon" in normalized
    assert "If a symbol requires explanation, redesign it before writing" in normalized
    assert "fill thirty-five to fifty percent of the entire image area" in normalized
    assert "VISUAL LABEL AND POWER MAP" in normalized
    assert "Give each side a concrete visual label" in normalized
    assert "Use one blunt visual contest that survives without context" in normalized
    assert "If the scene can be mistaken for an ordinary lifestyle illustration" in (
        normalized
    )
    assert "METAPHOR AND SYMBOL SYSTEM" in normalized
    assert "Use an animal, object, garment, or emblem as a visual label" in normalized
    assert "Every symbol must have one clear referent" in normalized
    assert "ACTION-METAPHOR COUPLING GATE" in normalized
    assert "one closed causal force chain" in normalized
    assert "central woman's intimate movement applies one visible directional force" in (
        normalized
    )
    assert "another participant's body transmits that same force" in normalized
    assert "primary metaphor visibly changes mechanical state because of the bodies" in (
        normalized
    )
    assert "changed mechanism redirects pressure into every remaining participant" in (
        normalized
    )
    assert "At least two adults must directly touch, load, grip, brace, block" in normalized
    assert "If removing the explicit interaction leaves the metaphor unchanged" in (
        normalized
    )
    assert "Because [central woman] [physical verb]" in normalized
    assert "CONTENT-LEVEL INTEGRATION" in normalized
    assert "At aesthetic level" in normalized
    assert "name one complete opaque outfit for each adult" in normalized
    assert "Show no bare torso, transparent garment, lingerie" in normalized
    assert "At erotic level" in normalized
    assert "At hardcore level" in normalized
    assert "Every requested participant must make direct intimate physical contact" in (
        normalized
    )
    assert "through penetration, oral-genital contact, or direct genital stimulation" in (
        normalized
    )
    assert "Looking, kissing, touching shoulders or hips" in normalized
    assert "Include no clothed spectator or queued participant" in normalized
    assert "Do not pin, trap, force, dominate, restrain" in normalized
    assert "include no loose props or debris" in normalized
    assert "NON-NEGOTIABLE PRIORITY" in normalized
    assert "everyone awake, alert, willing" in normalized
    assert "PLANNED ENGLISH LABEL SYSTEM" in normalized
    assert "Every Theme must choose one meaningful pair of opposed English labels" in (
        normalized
    )
    assert "Each label contains one or two short words" in normalized
    assert "Lock the exact pair during Theme generation" in normalized
    assert "Locked image labels: FIRST LABEL | SECOND LABEL." in normalized
    assert "The Frame must preserve this exact pair" in normalized
    assert "Give each label one large, simple physical carrier" in normalized
    assert "No other readable or pseudo-readable content may appear" in normalized
    assert "The two clean label carriers are the only text-bearing surfaces" in (
        normalized
    )
    assert "LEXICAL TEXT-CARRIER BAN" in normalized
    assert "Do not use any of these English words or their plurals" in normalized
    assert "Replace any candidate containing one of these words" in normalized
    assert "microtext, card, pass, knife, cleaver, blade" in normalized
    assert "weapon, pin, pinned, trap, trapped, force, forced" in normalized
    assert "THEME CONTENT-PROOF GATE" in normalized
    assert "The Theme premise itself must contain the complete visible proof" in (
        normalized
    )
    assert "Do not substitute vague phrases such as sexual activity" in normalized
    assert "Hardcore does not imply BDSM" in normalized
    assert "one Theme sentence must account for every requested participant" in normalized
    assert "Touching only oneself, clothing, furniture, or a prop does not qualify" in (
        normalized
    )
    assert "Never describe any participant as preparing, approaching" in normalized
    assert "Every erotic Frame must include at least one" in normalized
    assert "Bare shoulders, cleavage, exposed thighs, sleepwear" in normalized
    assert "the explicit interaction is the sole ongoing human action" in normalized
    assert "No participant simultaneously reads, types, calculates" in normalized
    assert "The humor comes from desire, etiquette, attention" in normalized
    assert "DIRECT AND POPULAR LEGIBILITY" in normalized
    assert "understandable without text" in normalized
    assert "Use a poster-like hierarchy" in normalized
    assert "at least four fifths of the composition" in normalized
    assert "Photograph each real performer frontally or in a shallow side pose" in (
        normalized
    )
    assert "one exact orthographic poster plane" in normalized
    assert "must not resemble people photographed together in a real room" in normalized
    assert "single matte field with no floor line, wall corner, ceiling" in normalized
    assert "IMAGE-TEXT GATE" in normalized
    assert "Every Frame must visibly include the Theme's exact pair" in normalized
    assert "Every letter must be at least one twentieth of the image height" in (
        normalized
    )
    assert "each complete label must occupy at least one eighth" in normalized
    assert "inside the central eighty percent of the canvas" in normalized
    assert "minimum ten-percent safety margin" in normalized
    assert "inside ten-percent safety margin: WORK;" in normalized
    assert "Spell each locked label exactly twice in the complete Frame" in normalized
    assert "Repetition reinforces correct image rendering" in normalized
    assert "dedicated image-text passage at the absolute end" in normalized
    assert "Write exactly two entries" in normalized
    assert "minimum letter height, horizontal orientation, type weight" in normalized
    assert "Use the literal characters `: `" in normalized
    assert "Do not add an IMAGE-TEXT heading" in normalized
    assert "The Frame's final character" in normalized
    assert "Write this dedicated passage once only" in normalized
    assert "never restart or duplicate either carrier-copy entry" in normalized
    assert "Use this serialization grammar exactly" in normalized
    assert "After each colon, write only the exact locked label" in normalized
    assert "Every other surface must contain zero letters" in normalized
    assert "its entire visible typographic content must be one of the two" in normalized
    assert "If removing the words makes the satire unintelligible" in normalized
    assert "Do not use interpretive phrases such as symbolizes" in normalized
    assert "do not hard-code a sentence count" in normalized
    assert "one stable anchor sentence per adult when needed" in normalized
    assert "verbatim opening cast declaration" in normalized
    assert "The only supporting object is one [singular object]" in normalized
    assert "Name no other loose object, debris, food scatter" in normalized
    assert "Perform a final character scan on every Theme and Frame" in normalized
    assert "REAL-PERSON PHOTOMONTAGE LANGUAGE" in normalized
    assert "premium physical editorial photomontage" in normalized
    assert "full natural color and photographic tonal variation" in normalized
    assert "THEME CONTRACT" in normalized
    assert "FRAME CONTRACT" in normalized
    assert "WITHIN-THEME CONTINUITY LOCK" in normalized
    assert "names, allowed identities, ages, facial anchors, hair" in normalized
    assert "base garments, chosen exaggerations, primary metaphor, and label pair" in (
        normalized
    )
    assert "Clothing may shift only as required by the selected interaction" in normalized
    assert "requested women and men visually unambiguous" in normalized
    assert "No generic shocked open mouths" in normalized
    assert "VARIATION AND REJECTION RULES" in normalized


def test_everyday_social_caricature_centers_women_and_lived_interaction() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "everyday-social-caricature.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert len(brief.splitlines()) <= 150
    assert len(brief) <= 17_000
    assert brief.isascii()

    required_contract = (
        "Create original, woman-centered editorial caricatures",
        "humorous at first glance and bitter on reflection",
        "Satirize conduct and relationships, never identity itself",
        "PRIORITY",
        "exact requested cast",
        "action-metaphor causality",
        "CAST, SETTING, AND OUTPUT",
        "exactly the script-requested number of women and men",
        "Every visible person is a fictional, willing, alert East Asian adult",
        "mainland Chinese, Taiwanese, Hong Kong Chinese, Japanese",
        "Set the scene in mainland China, Taiwan, Hong Kong, Japan",
        "Give each exactly one identity phrase from this list verbatim",
        "Never add a second nationality, citizenship, diaspora",
        "State each person's gender explicitly",
        "never all-capital surnames",
        "English-only ASCII",
        "replace smart punctuation, multiplication signs, and non-English glyphs",
        "CONTENT LEVEL",
        "At aesthetic level",
        "At erotic level",
        "At hardcore level",
        "name every participant's anatomy-and-contact role",
        "holding unrelated items, directing a pose, or touching clothing does not count",
        "order the cast A > B > C and onward",
        "permit only adjacent-pair sexual contacts",
        "C never touches A",
        "one exclusive target",
        "the act is independently chosen recreation",
        "never evidence, payment, initiation, punishment, leverage",
        "No one demands, requires, forces, purchases, trades, rewards, or records the act",
        "WARDROBE AND CLEAN BACKGROUND",
        "striking head-to-foot editorial styling",
        "one bold clothing silhouette",
        "high-contrast color blocking",
        "without becoming another deformation, label, symbol, or metaphor",
        "Reject generic default officewear",
        "one broad matte color field plus at most two simple geometric cues",
        "Include no room inventory, decorative clutter",
        "The cast, primary structure, and paired motif dominate the image",
        "BITING PHYSICAL CARICATURE",
        "exactly two coordinated layers of deformation",
        "one coherent facial caricature combining at least two altered features",
        "elongated longitudinally, widened transversely, or enlarged uniformly",
        "two to four times ordinary scale",
        "shortened longitudinally, narrowed transversely, or reduced uniformly",
        "one-half to one-quarter ordinary scale",
        "Name both facial alterations explicitly",
        "exactly one allowed verb-axis pair and one numeric scale",
        "Never combine opposing size verbs or alter a second axis",
        "A general expression or unquantified adjective does not qualify",
        "The matching limb and adjacent parts remain ordinary",
        "never satisfy the required nonfacial layer",
        "may not invent, spread, intensify, or transfer a deformation",
        "Every other adult receives exactly one different secondary",
        "Choose either one facial cluster or one body or limb change, never both",
        "If body or limb is chosen, keep the face ordinary",
        "if face is chosen, keep all body proportions ordinary",
        "Scale changes stop cleanly at named joints",
        "The face, body, gesture, and action must communicate the same trait",
        "SHARED ACTION AND METAPHOR",
        "one closed reaction circuit",
        "thirty-five to fifty percent of the canvas",
        "State each contact point, force direction, immediate physical change",
        "Give every named adult one visible contact-force-result clause",
        "For hardcore scenes, the explicit act is the sole ongoing human action",
        "PHYSICAL STAGING",
        "Describe one frozen instant",
        "left-to-right and overlap position, facing, weight-bearing support",
        "Every contact must name two anatomically reachable surfaces",
        "Preserve one coherent occupancy map",
        "no limb passes through a body or structure",
        "no unsupported hovering",
        "No body may thread, loop, wrap, weave through, or be bisected",
        "Reflective props show abstract glare, never duplicated people or anatomy",
        "never attachment, balance, reach path, collision, or load transfer",
        "hard edges may touch only feet, knees, hands, or forearms",
        "A broad flat surface may support the back or seat without pressure",
        "no structure may press, wedge, trap, or bisect the head",
        "B must occupy the physical center and directly neighbor both endpoints",
        "Left-to-right order must be A-B-C or C-B-A",
        "No person or limb may reach across, behind, around, over, under, or through the third person",
        "If the tableau cannot be reconstructed physically",
        "establish the complete physical staging map before describing",
        "exactly one supporting motif represented by two related physical instances",
        "HYBRID NEWSPAPER PHOTOMONTAGE",
        "separately photographed real adult performers",
        "bold adult newspaper screen print",
        "photographic texture inside each deformed cutout",
        "exactly four dominant flat spot-color fields outside natural skin and hair",
        "Controlled graphic foreshortening",
        "impossible independently of camera proximity",
        "TEXT PAIR",
        "Locked image labels: FIRST LABEL | SECOND LABEL.",
        "each locked label exactly once and only in the terminal serialization",
        "Never choose an inherently text-bearing object as the primary structure",
        "COMPLIANCE GATE",
        "participant contact graph, occupancy map",
        "discard the whole draft and rebuild it",
        "THEME CONTRACT",
        '"Cast:" lists every Title Case name, age of at least twenty-five',
        '"Deformations:" lists CENTRAL NAME',
        "explicit woman or man",
        "feature plus alteration; feature plus alteration",
        "one nonfacial part, allowed verb-axis pair, and valid scale",
        '"Consent:" states that every adult freely chose recreation',
        '"Staging:" fixes A-B-C or C-B-A spatial order, B centered',
        '"Hardcore proof: Chain A > B > C.',
        "No other sexual contact.",
        "unified real-person newspaper photomontage medium",
        "FRAME CONTRACT",
        "Hybrid real-person newspaper photomontage with biting anatomical caricature:",
        "Exactly [requested total] East Asian adults fill the image",
        "Preserve every Theme age, identity, wardrobe, deformation, chain order",
        "VARIATION AND REJECTION",
        "mixed media",
        "interchangeable clothing",
        "cluttered background",
        "nonadjacent or repeated contact pair",
        "contact count other than cast-size-minus-one",
        "chain midpoint outside the spatial center",
        "contact reaching across the third adult",
        "shared anatomical target",
        "a supporting adult with both facial and bodily change",
        "opposing scale verbs",
        "deformation spreading to adjacent parts",
        "a body threaded through a structure",
        "hard edge against a core body part",
        "structure pressing or trapping a body",
        "non-ASCII glyph",
        "unsupported, intersecting, or irreconstructible staging",
    )
    for marker in required_contract:
        assert marker in normalized

    conflicting_contracts = (
        "Continue immediately with the complete dominant visual icon",
        "Do not use photographic",
        "Select a coherent original medium",
        "roughly one third of the image",
        "Choose one dominant deformation grammar per Theme",
        "both adults' different dominant deformations",
        "five to eight complete sentences",
        "premise of no more than two sentences",
        "foreground, middle ground, background",
        "forced perspective",
        "the viewpoint, distance, or perspective",
    )
    for conflict in conflicting_contracts:
        assert conflict not in normalized


def test_creative_brief_uses_open_ended_high_concept_ideation() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "creative.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "PLAN THE WHOLE BATCH FIRST" in normalized
    assert "at least twice as many candidate concepts as requested" in normalized
    assert "ONE-OBJECT AND MULTI-OBJECT MODES" in normalized
    assert "visible mix of single-object and multi-object ensemble Themes" in normalized
    assert "aiming for roughly half of each" in normalized
    assert "coherent ensemble of two to five familiar objects" in normalized
    assert "small inhabitants of a real everyday environment" in normalized
    assert "travel between objects" in normalized
    assert "use one object to alter another" in normalized
    assert "Do not scatter unrelated giant props" in normalized
    assert "use at least eight clearly different ordinary-use families" in normalized
    assert "span at least five normal size bands" in normalized
    assert "choose at least three objects" in normalized
    assert "larger than an adult hand" in normalized
    assert "choose no more than three objects" in normalized
    assert "inside a closed adult hand" in normalized
    assert "THE ONE-SENTENCE IDEA" in normalized
    assert "OBJECT TRUTH" in normalized
    assert "HUMAN STAKE" in normalized
    assert "CONCEPT ENGINE" in normalized
    assert "If removing the cast leaves a materials demonstration" in normalized
    assert "CREATIVE-ENGINE SPREAD" in normalized
    assert "at least six substantially different primary engines" in normalized
    assert "No more than two Themes may center on" in normalized
    assert "No more than two may share one relationship grammar" in normalized
    assert "CANDIDATE TOURNAMENT" in normalized
    assert "six genuinely different image opportunities" in normalized
    assert "six images simply tour six components" in normalized
    assert "competition, market, permission system, or intimacy economy" in normalized
    assert "ORDINARY-USE COLLISION" in normalized
    assert "In at least two of the six regions" in normalized
    assert "uses the object in a way instantly recognizable" in normalized
    assert "use the object as designed" in normalized
    assert "EXTERIOR-ONLY SCALE CONTRACT" in normalized
    assert "Never place any body inside the object" in normalized
    assert "Ordinary use never authorizes entry" in normalized
    assert "SIX PROOFS, NOT SIX PARTS" in normalized
    assert "one object-specific ordinary-use collision" in normalized
    assert "At least four stunts must change the cast's goal" in normalized
    assert "At least two must remain compelling" in normalized
    assert "THEME-STAGE CONTRACT" in normalized
    assert "exactly five semicolons" in normalized
    assert "FRAME-STAGE GRID CONTRACT" in normalized
    assert (
        "Every Narrative Frame is one complete portrait 2-column by 3-row grid"
        in normalized
    )
    assert "regardless of frames_per_theme" in normalized
    assert "Never distribute a board across Frames" in normalized
    assert "use one Frame per region" in normalized
    assert (
        "A portrait 2-column by 3-row grid forms one image with six cleanly "
        "separated regions." in normalized
    )
    assert (
        "Every person remains outside all colossal everyday objects throughout "
        "the board." in normalized
    )
    assert '"Region 1:" through "Region 6:"' in normalized
    assert "When frames_per_theme is 1" not in normalized
    assert "work as a standalone campaign key visual" in normalized
    assert "Do not sanitize erotic or hardcore into neutral imagery" in normalized
    assert "MINIATURE-WORLD CAMERA LANGUAGE" in normalized
    assert "controlled tilt-shift or macro-style selective focus" in normalized
    assert "THUMBNAIL SCALE HIERARCHY" in normalized
    assert "read first at thumbnail size" in normalized
    assert "at least four wide or medium views" in normalized
    assert "showing complete adult bodies" in normalized
    assert "no more than two regions for close detail" in normalized
    assert "one whole-object or ensemble hero view" in normalized
    assert "avoid using a broad featureless flank as a wall" in normalized
    assert "conceal the cast-to-object ratio" in normalized
    assert "graphic surface systems may reinforce scale" in normalized
    assert "miniature eye level along the object's surface" in normalized
    assert "high oblique views revealing tiny bodies" in normalized
    assert "This is crisp editorial advertising photography" in normalized
    assert "not a movie still" in normalized
    assert "Do not use cinematic color grading" in normalized
    assert "BRIGHT CLEAN COLOR STANDARD" in normalized
    assert "bright, clean, high-key color" in normalized
    assert "deliberate complementary contrast" in normalized
    assert "one immediately legible dominant color relationship" in normalized
    assert "bold surrounding color field" in normalized
    assert "Avoid boards dominated by stainless steel gray" in normalized
    assert "same tonal band" in normalized
    assert "commercial tabletop campaign" in normalized
    assert "open shadows with visible detail" in normalized
    assert "PHOTOGRAPHIC MATERIAL STANDARD" in normalized
    assert "FINAL CREATIVE PRIORITIES" in normalized
    assert "they are not a hard quality gate" in normalized
    assert "Eliminate a candidate when" not in normalized
    assert "Reject the Theme when" not in normalized
    assert "- T001:" not in brief


def test_edo_warai_e_brief_respects_all_content_levels() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "edo-warai-e.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "ADULT CAST, CONSENT, AND CONTENT LEVEL" in normalized
    assert "Honor the exact requested content level" in normalized
    assert "aesthetic: keep every adult fully dressed" in normalized
    assert "erotic: make unmistakable adult sensuality visible" in normalized
    assert "clearly erotic but non-explicit interaction" in normalized
    assert "hardcore: show an explicit, consensual adult sexual act" in normalized
    assert "already occurring in every Theme and Frame" in normalized
    assert "do not hide the defining content" in normalized
    assert "LEVEL-AWARE CLOTHING AND BODY" in normalized
    assert "At erotic level, robes may fall open" in normalized
    assert "At hardcore level, adults may be partly or fully nude" in normalized
    assert "directly establish the requested content level" in normalized
    assert "Begin every Frame with the selected level's defining state" in normalized
    assert "preserve the Theme's explicit act in every Frame" in normalized
    assert "intimate but fully clothed interaction" not in normalized
    assert "human anatomy natural and fully covered" not in normalized
    assert "Reject any Frame that depends on nudity" not in normalized


def test_edo_warai_e_requires_live_action_ukiyo_e_evidence() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "edo-warai-e.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "PERFORMED UKIYO-E TRANSLATION" in brief
    assert "UKIYO-E COLOR GATE" in brief
    assert "DISTANCE-READ FLATNESS GATE" in brief
    assert "EDO MATERIAL PATINA" in brief
    assert "Flat, borderless nishiki-e theatrical picture plane" in normalized
    assert "enacted by real adult performers" in normalized
    assert "not a literal woodblock print" in normalized
    assert "keyblock-like contour separation" in normalized
    assert "nishiki-e palette" in normalized
    assert "flat separated color blocks" in normalized
    assert "one bokashi-style gradient" in normalized
    assert (
        "At thumbnail size and viewing distance, every Frame must read as a flat "
        "nishiki-e composition" in normalized
    )
    assert "exactly three shallow stacked bands" in normalized
    assert "dominant flat silhouettes" in normalized
    assert "no volumetric light-and-shadow modeling" in normalized
    assert "Bokashi belongs to one background plane" in normalized
    assert "Close inspection may reveal live performers" in normalized
    assert "must never overturn the flat distance read" in normalized
    assert (
        '"Flat, borderless nishiki-e theatrical picture plane in a '
        "[chūban-like or ōban-like] [vertical or horizontal] proportion, enacted "
        "by real adult performers. Exactly three shallow stacked picture bands: "
        "a lower prop strip, a central adult tableau, and an upper architectural "
        "strip, all parallel to the image surface. Adult faces, limbs, garments, "
        "and furniture read as contour-enclosed matte color shapes with crisp "
        "overlaps and two-step values; contour and flat shadow shapes carry all "
        "form. "
        "Edo-period material patina appears only as bounded wear on physical "
        'costumes, props, and set surfaces."' in normalized
    )
    assert "all adults remain in the central picture band" in normalized
    assert "No near-far scale change or projecting foreshortened limbs" in normalized
    assert "Repeat this exact flat-medium lock immediately after" in normalized
    assert (
        "All visible bodies, garments, props, and room planes return immediately "
        "to contour-enclosed matte color shapes on the same flat three-band "
        "nishiki-e surface." in normalized
    )
    assert (
        "combine exactly two close-read performer cues chosen only from" in normalized
    )
    assert "Target 700 to 900 English words" in normalized
    assert "never exceed 1000 English words" in normalized
    assert "one solvable three-dimensional arrangement" not in normalized
    assert "foreground, middle ground, and background" not in normalized
    assert "live-action image of real adult performers" not in normalized
    assert "individual hairs" not in normalized
    assert "subtle skin variation" not in normalized
    assert "three to five specific signs of ordinary age and handling" in normalized
    assert "protected seams remain richer" in normalized
    assert "Distribute wear according to touch, friction, smoke, moisture" in normalized
    assert "must not turn the whole image brown, beige, gray, or desaturated" in (
        normalized
    )
    assert "Keep adult skin as a warm, bounded matte field" in normalized
    assert "global sepia or yellow cast" in normalized
    assert "photographic grain" in normalized
    assert "scanned-print damage" in normalized
    assert "Return only positive prose describing the depicted scene" in normalized
    assert "Enforce every rule silently" in normalized
    assert "Every word must belong to the image-generation description" in normalized
    assert '"The current fully clothed non-erotic interaction is"' in normalized
    assert '"The current erotic but non-explicit interaction is"' in normalized
    assert '"The current explicit consensual adult sexual act is"' in normalized
    assert "name the occurring act directly" in normalized
    assert "Prussian blue is permitted only for settings from the 1820s onward" in (
        normalized
    )
    assert "full-frame or medium-format camera" not in normalized
    assert "mm equivalent" not in normalized
    assert "aperture behavior" not in normalized
    assert "depth of field" not in normalized


def test_ming_gongbi_mixi_tu_owns_historical_painting_contract() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "ming-gongbi-mixi-tu.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "LATE-MING JIANGNAN WORLD" in brief
    assert "GONGBI LINE DISCIPLINE" in brief
    assert "LAYERED GONGBI COLOR" in brief
    assert "CHINESE PAINTING SPACE" in brief
    assert "FLAT GONGBI PICTURE-PLANE GATE" in brief
    assert "ARCHIVAL FACSIMILE MEDIUM LOCK" in brief
    assert "HUMANIZED GONGBI FIGURE DETAIL" in brief
    assert "BORDERLESS FULL-BLEED SILK GATE" in brief
    assert "AGED SILK AND PIGMENT PATINA" in brief
    assert "anonymous late-Ming Jiangnan workshop album leaf" in normalized
    assert "between 1573 and 1644" in normalized
    assert "prepared silk or sized xuan paper" in normalized
    assert "gossamer-line delicacy" in normalized
    assert "iron-wire steadiness" in normalized
    assert "ruled-line jiehua discipline" in normalized
    assert "visual logic of sanfan jiuran" in normalized
    assert "five to seven principal color families" in normalized
    assert "scattered perspective" in normalized
    assert "flat picture plane must dominate the first read" in normalized
    assert "minimal tonal modeling" in normalized
    assert "no volumetric light-and-shadow modeling" in normalized
    assert "Age must be visible at first glance and thumbnail size" in normalized
    assert "roughly two-thirds of the impression" in normalized
    assert "one-third from visible material age" in normalized
    assert "Full-canvas continuous-silk flat archival facsimile" in normalized
    assert "two to four shallow, stacked, overlapping bands" in normalized
    assert "contour-enclosed color fields" in normalized
    assert "darker tea-brown edge oxidation" in normalized
    assert "one shallow age crease" in normalized
    assert "aged prepared-silk painting extends continuously to every canvas edge" in (
        normalized
    )
    assert (
        "no visible mounting margin, mat, frame, border, or rectangular edge band"
        in normalized
    )
    assert "Edge patina must break, vary, and dissolve inward irregularly" in normalized
    assert "Human specificity comes from line drawing and bounded washes" in normalized
    assert "subtle facial asymmetry" in normalized
    assert "exactly three restrained skin tones" in normalized
    assert "convincingly human but unmistakably painted" in normalized
    assert "flat archival facsimile of a hand-painted antique silk album leaf" in (
        normalized
    )
    assert "borderless full-bleed composition" in normalized
    assert (
        "Every person, garment, object, and architectural plane exists only as ink "
        "contour and pigment on silk" in normalized
    )
    assert "Repeat this compact medium lock immediately after" in normalized
    assert "use exactly four descriptive sentences" in normalized
    assert "No sentence after the fixed five-sentence opening may exceed 60" in (
        normalized
    )
    assert 'literal phrase "three shallow stacked bands"' in normalized
    assert "between 350 and 750 English words" in normalized
    assert "Count before returning" in normalized
    assert (
        "The entire image remains a visibly aged, flat, hand-painted gongbi silk "
        "album leaf made from ink contours and mineral pigment" in normalized
    )
    assert "three to five localized, physically plausible age cues" in normalized
    assert "Japanese ukiyo-e" in normalized
    assert "modern guochao illustration" in normalized
    assert "Do not generate readable Chinese" in normalized
    assert '"The current explicit consensual adult sexual act is"' in normalized
    assert "directly naming or describing male reproductive anatomy" in normalized
    assert "Every human mentioned in the Theme or Frame must belong" in normalized
    assert "Do not introduce an absent spouse" in normalized

    frame_contract = brief.split("\nFRAME CONTRACT\n", maxsplit=1)[1]
    for photography_trigger in (
        "observed-from-life",
        "lifelike",
        "living adult sitters",
        "subtle flesh variation",
        "credible weight",
        "painted from observation",
    ):
        assert photography_trigger not in frame_contract


def test_pose_brief_selects_a_varied_text_free_six_pose_group() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "pose.txt").read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert "RANDOM POSE-GROUP SELECTION" in normalized
    assert "CAMERA-ANGLE SELECTION" in normalized
    assert "SEXUAL-INTENT GATE" in normalized
    assert "recognizable consensual adult sexual position" in normalized
    assert "Neutral dance, yoga, fitness, wellness, fashion" in normalized
    assert "The body mechanics themselves must carry the sexual intent" in normalized
    assert "Do not neutralize a pool entry" in normalized
    assert "independent varied selection" in normalized
    assert "selection of exactly six pose blueprints" in normalized
    assert "Do not take six adjacent entries" in normalized
    assert "non-sequentially from at least four different pose-family" in normalized
    assert "assign exactly six distinct camera-angle blueprints" in normalized
    assert "use at least four different azimuth families" in normalized
    assert "at least three camera-height or elevation bands" in normalized
    assert "even as a left-right mirror" in normalized
    assert "50-85 mm on full frame" in normalized
    assert "CURATED CAMERA-ANGLE POOL" in normalized
    assert "pose-and-camera blueprints" in normalized
    assert "front three-quarter from left hip height" in normalized
    assert "one dominant region and five supporting regions" in normalized
    assert "Selecting a concrete wearable look is mandatory" in normalized
    assert "WARDROBE EXPOSURE LADDER" in normalized
    assert "strict three-step progression" in normalized
    assert "Aesthetic uses full-size clothing" in normalized
    assert "erotic uses lingerie-size clothing" in normalized
    assert "hardcore uses minimal or micro-scale" in normalized
    assert "coverage could be mistaken for the neighboring level" in normalized
    assert "OCCASION AND SETTING SELECTION" in normalized
    assert "one concrete adult occasion" in normalized
    assert "All six regions inside that Frame must share" in normalized
    assert "Different Frames and different Themes" in normalized
    assert "Exhaust unused setting families" in normalized
    assert "CURATED OCCASION AND LOCATION FAMILIES" in normalized
    assert "PROFESSIONAL IMAGE-MAKING" in normalized
    assert "PRIVATE RESIDENTIAL" in normalized
    assert "HOSPITALITY AND RETREAT" in normalized
    assert "ART, DESIGN, AND PERFORMANCE" in normalized
    assert "PRIVATE WELLNESS AND LEISURE" in normalized
    assert "ARCHITECTURAL SHOWCASES" in normalized
    assert "SECLUDED OUTDOOR SETTINGS" in normalized
    assert "SEASONAL AND ATMOSPHERIC OCCASIONS" in normalized
    assert "not one permanent room" in normalized
    assert "Shared background means shared within one Frame only" in normalized
    assert "different Frames or Themes to reuse the same occasion" in normalized
    assert "Each Frame names one concrete occasion and location" in normalized
    assert "Name the exact garment and accessory pieces" in normalized
    assert "The Theme premise must name the complete selected look" in normalized
    assert "Every Frame must fully restate that look" in normalized
    assert "Include at least one real garment or wearable accessory" in normalized
    assert "wardrobe is never implicit, generic" in normalized
    assert "Garment scale follows the strict exposure ladder" in normalized
    assert "becomes exactly one physical line" in normalized
    assert "all six regions inside that Frame's single uninterrupted" in normalized
    assert "Never distribute one board across multiple Frames" in normalized
    assert "use one Frame per region" in normalized
    assert "no Frame is one region, a board fragment" in normalized
    assert "The finished board contains no visible title, pose names" in normalized
    assert brief.count("\nCURATED POSE POOL\n") == 1
    assert brief.count("\nCURATED CAMERA-ANGLE POOL\n") == 1
    assert brief.count("\nCURATED OCCASION AND LOCATION FAMILIES\n") == 1

    occasion_pool = brief.split(
        "\nCURATED OCCASION AND LOCATION FAMILIES\n", maxsplit=1
    )[1].split("\nCAMERA-ANGLE SELECTION\n", maxsplit=1)[0]
    occasion_entries = [
        line.removeprefix("- ").strip()
        for line in occasion_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(occasion_entries) >= 40
    assert len(occasion_entries) == len(set(occasion_entries))

    camera_pool = brief.split("\nCURATED CAMERA-ANGLE POOL\n", maxsplit=1)[1].split(
        "\nCURATED POSE POOL\n", maxsplit=1
    )[0]
    camera_entries = [
        line.removeprefix("- ").strip()
        for line in camera_pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(camera_entries) >= 15
    assert len(camera_entries) == len(set(camera_entries))
    assert any("frontal" in entry for entry in camera_entries)
    assert any("side" in entry for entry in camera_entries)
    assert any("rear" in entry for entry in camera_entries)

    pool = brief.split("\nCURATED POSE POOL\n", maxsplit=1)[1]
    pose_entries = [
        line.removeprefix("- ").strip()
        for line in pool.splitlines()
        if line.startswith("- ")
    ]
    assert len(pose_entries) >= 81
    assert len(pose_entries) == len(set(pose_entries))
    assert "invisible wall" not in pool
    assert "seductively" not in pool
    assert "slowly" not in pool
    assert "CURATED SELF-TOUCH POOL" in pool
    assert "NON-EXPLICIT INTIMATE TOUCH" in pool
    assert "DIRECT STATIC ADULT SELF-TOUCH - HARDCORE ONLY" in pool
    for family in (
        "FRONT-PRESENTING STANDING",
        "REAR-PRESENTING STANDING AND HINGED",
        "SEATED AND STRADDLING",
        "KNEELING AND HEEL-SUPPORTED",
        "CROUCHED AND SQUATTING",
        "SUPINE AND PELVIS-LIFTED",
        "SIDE-LYING AND TWISTED",
        "PRONE AND CHEST-SUPPORTED",
        "HANDS-AND-KNEES AND FOREARM-SUPPORTED",
    ):
        assert family in pool


def test_threshold_emergence_brief_locks_cast_geometry_and_batch_variety() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "threshold-emergence.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "EMERGING WOMEN + WITNESS WOMEN = REQUESTED WOMEN" in normalized
    assert "EMERGING MEN + WITNESS MEN = REQUESTED MEN" in normalized
    assert "Never treat the requested cast as witnesses" in normalized
    assert "Every visible or implied human counts toward the cast" in normalized
    assert "The source-side body must remain recognizably human anatomy" in normalized
    assert "The source plane intersects the emerging person once" in normalized
    assert "HALF-IN, HALF-OUT SILHOUETTE" in normalized
    assert "roughly forty to sixty percent of the body is on each side" in normalized
    assert "the pelvis plus at least one complete connected leg inside" in normalized
    assert "REFERENCE CRAWL CHOREOGRAPHY" in normalized
    assert "The adult crawls headfirst perpendicular to the screen" in normalized
    assert "the bezel stays fully visible around the waist" in normalized
    assert "SINGLE-SCENE RENDERING CONTRACT" in normalized
    assert "one camera, one continuous outer location" in normalized
    assert "appears only inside the exact bounded area" in normalized
    assert "End every Frame with one concise geometry-lock sentence" in normalized
    assert "no split screen, second set, reflected duplicate" in normalized
    assert "Do not flatten, paint, pixelate, dissolve" in normalized
    assert "no full-body ripple, translucent overlay" in normalized
    assert "same natural skin, clothing, volume" in normalized
    assert "Do not promise text and then negate it elsewhere" in normalized
    assert "Use each lane exactly once in a five-Theme batch" in normalized
    assert "one home, dinner, party, or other private social setting" in normalized
    assert (
        "one cinema, theater, concert, sports, game, or other communal leisure setting"
        in normalized
    )
    assert "one garden, park, beach, mountain, farm" in normalized
    assert "one train, station, ferry, airport, road stop" in normalized


def test_magazine_cover_brief_builds_a_finished_newsstand_cover() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "magazine-cover.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "MAGAZINE, NOT POSTER" in normalized
    assert "one original recurring masthead at the top" in normalized
    assert "exactly two short secondary cover lines" in normalized
    assert "Do not use movie-poster signals" in normalized
    assert "Do not use social-post signals" in normalized
    assert "Do not show a physical mockup" in normalized
    assert "flat, full-bleed portrait 3:4 front cover" in normalized
    assert "MASTHEAD CONTRACT" in normalized
    assert "COVER-LINE PACKAGE" in normalized
    assert "Keep total visible copy under twenty-four English words" in normalized
    assert "NO MICROTEXT" in normalized
    assert "four percent of the cover height" in normalized
    assert "Do not render a barcode, QR code, ISBN, ISSN" in normalized
    assert "Do not use lowercase letters, digits, punctuation" in normalized
    assert "Every exact string must match `[A-Z]+( [A-Z]+)*`" in normalized
    assert "Never use `&`; write `AND` instead" in normalized
    assert "never a date, month, year, volume, edition" in normalized
    assert "trademark symbol, registered mark, superscript" in normalized
    assert "ENGLISH-ONLY IMAGE TEXT GATE" in normalized
    assert "TEXT-LAYER ISOLATION LOCK" in normalized
    assert "Frame prose must use English throughout" in normalized
    assert (
        "Every character in the complete Frame must be ASCII code point" in normalized
    )
    assert "A single non-ASCII character invalidates the Frame" in normalized
    assert (
        "The cover contains exactly five readable English strings and zero other "
        "letters, words, numbers, symbols, pseudo-letters, or glyph-like marks."
        in normalized
    )
    assert "exactly three controlled typography zones" in normalized
    assert "one aligned information block" in normalized
    assert (
        "The five declared English strings are the complete typographic layer"
        in normalized
    )
    assert (
        "all remaining cover areas are pure photography, uninterrupted color, "
        "or blank negative space" in normalized
    )
    assert "Quarantine all exact visible copy until that final passage" in normalized
    assert (
        "any all-uppercase sequence of two or more letters anywhere earlier"
        in normalized
    )
    assert "Each of the five exact strings appears once and only once" in normalized
    assert "The Frame's final character is the semicolon" in normalized
    assert "dedicated image-text passage" in normalized
    assert "It contains exactly five entries in this order" in normalized
    assert "add a colon, then write the exact uppercase text" in normalized
    assert "Never surround visible text with quotation marks" in normalized
    assert (
        "one dominant hero image occupying roughly sixty to eighty percent"
        in normalized
    )
    assert "At hardcore level" in normalized
    assert "the result is one flat portrait 3:4 magazine front cover" in normalized


def test_extreme_absurdity_requires_visible_human_prop_contact_chain() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "extreme-absurdity.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert "HUMAN-TO-PROP CONTACT CHAIN" in normalized
    assert (
        "name the exact participant, exact body part, exact prop surface, "
        "contact direction, and sustained force"
        in normalized
    )
    assert "A nearby, implied, automatic, or untouched prop is invalid" in normalized
    assert (
        "trace one unbroken visible force path from the human contact point "
        "to the prop's present state"
        in normalized.lower()
    )
    assert (
        "Within the first two sentences, state the human-to-prop contact point"
        in normalized
    )
    assert "HUMAN-PROP SCALE AND FIT" in normalized
    assert "Give every adult a visible height and build" in normalized
    assert "the area carrying body weight, the free space around joints" in normalized
    assert "Keep one scale throughout the Frame" in normalized
    assert "EYEWITNESS STATIC DESCRIPTION" in normalized
    assert (
        "Write as if a photographer is looking at one finished still" in normalized
    )
    assert (
        "state face direction, gaze target, visible expression through brows, "
        "eyelids, mouth, jaw, and cheek tension"
        in normalized
    )
    assert "Describe the final effect as present visible geometry" in normalized
    assert "Do not substitute abstract causal verbs" in normalized
    assert "BRIGHT EXAGGERATED STYLING" in normalized
    assert "Give every participant a distinct, stable, photographable styling package" in normalized
    assert "no participant appears as an unstyled generic nude" in normalized
    assert "an exaggerated but physically plausible hairstyle" in normalized
    assert "Specify visible makeup for every participant" in normalized
    assert "assign complementary colors and different silhouettes" in normalized


def test_near_future_intimacy_uses_compact_conditional_contract() -> None:
    brief = (
        REPOSITORY_ROOT / "story-inputs" / "near-future-intimacy-realism.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    headings = (
        "PRIORITY AND OUTPUT CONTRACT",
        "NON-NEGOTIABLE CORE LOCKS",
        "CAST, CONSENT, AND ANATOMY",
        "CONTENT AND ACTION",
        "FUTURE VISUAL SYSTEM",
        "PHOTOGRAPHIC SYSTEM",
        "CONDITIONAL TECHNOLOGY MODULES",
        "POSITION ARCHITECTURES",
        "TECHNOLOGY FAMILIES",
        "SCENE SEED LIBRARY",
        "SILENT REJECTION CHECK",
        "FINAL FRAME",
    )

    assert brief.startswith("BRIEF\n\n")
    assert brief.isascii()
    assert len(brief) < 54_000
    for heading in headings:
        assert f"\n{heading}\n" in brief

    assert "cold lived-in realism" in normalized
    assert "following behavior is permanent" in normalized
    assert "must never be removed, weakened" in normalized
    assert "exact visible body count" in normalized
    assert "distinct complete styling package for every adult" in normalized
    assert "complete surrounding environment with at least eight compact reality anchors" in normalized
    assert "at least six discrete props distributed across all depth planes" in normalized
    assert "simultaneous room-scale, body-scale" in normalized
    assert "complete force path, center of mass, cast shadow" in normalized
    assert "approved holographic adult identity" in normalized
    assert "approved cooling suspension identity" in normalized
    assert "approved orbital gantry identity" in normalized
    assert "exact batch routing with distinct scene worlds and sexual actions" in normalized
    assert "Write only positive visible instructions" in normalized
    assert "Never copy a rule, rejection, warning" in normalized
    assert "Silently use those checks before returning" in normalized
    assert "at least 600 English words per Frame" in normalized
    assert "no fixed maximum when concrete visual detail remains useful" in normalized
    assert "600-word minimum is hard" in normalized
    assert "put cast, action, anatomy, and technology in the first half" in normalized
    assert "image contains no captions, subtitles, logos" in normalized

    assert "complete requested cast" in normalized
    assert "Exactly N adults and N complete bodies occupy the entire image" in normalized
    assert "Exactly two adults and two complete bodies" in normalized
    assert "single couple remains the only human silhouette group" in normalized
    assert "a 38-year-old Chinese woman named Mei" in normalized
    assert "Always write the words woman or man beside each name" in normalized
    assert "GENDER COMPOSITION LOCK" in brief
    assert "female_count and male_count as immutable gender slots" in normalized
    assert "still uses the word woman or man matching that requested slot" in normalized
    assert "two women and one man: one NN-year-old woman named A" in normalized
    assert "one woman and two men: one NN-year-old woman named A" in normalized
    assert "Repeat the complete requested gender structure independently in every Frame" in normalized
    assert "Show one visible body and face per requested person" in normalized
    assert "woman has one vulva and the man has one penis" in normalized
    assert "pubic regions touch directly" in normalized
    assert "only the attached base remains externally visible" in normalized
    assert "complete contact geometry within the first 120 words" in normalized
    assert "both pubic regions are bare and directly pressed together" in normalized
    assert "Every lower garment is fully removed from both legs" in normalized
    assert "the man's single penis is rooted continuously in his fully unclothed pelvis" in normalized
    assert "only its attached base remains visible at their touching pubic skin" in normalized
    assert "torso-only proxy" in normalized
    assert "show abstract light or empty room architecture" in normalized
    assert "visibly unoccupied from edge to edge" in normalized
    assert "All activity is voluntary" in normalized
    assert "Keep professional service separate from sex" in normalized
    assert "INDIVIDUAL APPEARANCE AND STYLING" in brief
    assert "Describe each person separately" in normalized
    assert "body build, height impression, skin tone" in normalized
    assert "face shape and visible facial features" in normalized
    assert "hairstyle with color, length, texture, cut, parting" in normalized
    assert "visible grooming or makeup treatment" in normalized
    assert "current expression through gaze direction, eyelids, brows" in normalized
    assert "every garment and footwear item" in normalized
    assert "one to three personal accessories" in normalized
    assert "Nudity does not remove the styling requirement" in normalized
    assert "exact placement of their removed outfit" in normalized

    assert "Aesthetic:" in brief
    assert "Erotic:" in brief
    assert "Hardcore:" in brief
    assert "one explicit sexual action visibly underway" in normalized
    assert "SEXUAL ACTION DIVERSITY" in brief
    assert "solo masturbation, partner-guided masturbation, mutual masturbation" in normalized
    assert "consensual BDSM" in normalized
    assert "SINGLE-ADULT OVERRIDE" in brief
    assert "this rule overrides every scene seed, technology family, module" in normalized
    assert "exactly one adult, one complete body, one face, and one silhouette" in normalized
    assert "sole adult performs solo masturbation" in normalized
    assert "Across each ten single-adult Themes" in normalized
    assert "one free release hand" in normalized
    assert "For ten Themes with two or more requested adults" in normalized
    assert "Use each applicable action slot exactly once in a ten-Theme batch" in normalized
    assert "include at least two masturbation scenes and four BDSM scenes" in normalized
    assert "penetration in no more than three Themes" in normalized
    assert "compact non-phallic vibrator" in normalized
    assert "held visibly in one partner's hand" in normalized
    assert "MASTURBATION AND BDSM GEOMETRY" in brief
    assert "trace the active hand continuously from shoulder through elbow" in normalized
    assert "give each adult a separate hand-to-body action" in normalized
    assert "identify the voluntary roles and show reciprocal consent" in normalized
    assert "Every restraint has a visible quick release" in normalized
    assert "Impact lands only on fleshy buttocks or outer thighs" in normalized
    assert "one bare, unobstructed contact center within the first 120 words" in normalized
    assert "fully remove trousers, underwear, skirts, and other lower garments" in normalized
    assert "keep support hardware completely outside both pubic regions" in normalized
    assert "technology is powered, worn, connected" in normalized
    assert "Frames under one Theme are alternative photographs" in normalized

    assert "exactly one primary speculative development" in normalized
    assert "room scale:" in normalized
    assert "body scale:" in normalized
    assert "contact scale:" in normalized
    assert "at least six coherent future signals" in normalized
    assert "Retrofitted megacity domestic" in normalized
    assert "Brutalist habitat utility" in normalized
    assert "Climate-adapted interior" in normalized
    assert "Spectral telepresence room" in normalized
    assert "BATCH DIVERSITY ROUTER" in brief
    assert "ten visibly distinct scene-world buckets" in normalized
    assert "For exactly ten requested Themes, bind identifiers to buckets" in normalized
    assert "T001=A, T002=B, T003=C, T004=D, T005=E" in normalized
    assert "T006=F, T007=G, T008=H, T009=I, and T010=J" in normalized
    assert "never substitute another D or F scene for I or J" in normalized
    assert "inside their assigned A-H buckets" in normalized
    assert "For three to nine Themes, use that many different buckets" in normalized
    assert "complete all ten buckets before reusing any bucket" in normalized
    assert "use at most two conventional bedrooms, mattresses, bunks, or hotel rooms" in normalized
    assert "never repeat a seed, location type, primary technology family" in normalized
    assert "Make the scene silhouette visibly different before varying styling" in normalized
    assert "safe service wear through micro-scratches" in normalized
    assert "remain structurally clean and intact" in normalized

    assert "rectilinear 35-50 mm" in normalized
    assert "f/5.6-f/11" in normalized
    assert "foreground, middle ground, and background" in normalized
    assert "5200K-6500K" in normalized
    assert "palette is cool dominant" in normalized
    assert "four active storytelling systems" in normalized
    assert "at least eight compact reality anchors" in normalized
    assert "complete occupied space rather than a generic backdrop" in normalized
    assert "room type, floor, walls, ceiling, entrance" in normalized
    assert "at least six discrete, visually readable props" in normalized
    assert "specific object identity, material, color, size impression" in normalized
    assert "Distribute them across foreground, middle ground, and background" in normalized
    assert "semicolon-separated environmental sentence" in normalized

    assert "MODULE: SYNTHETIC OR PROXY ADULT" in brief
    assert "MODULE: HAPTIC VOLUMETRIC ADULT" in brief
    assert "55-70 percent optical density" in normalized
    assert "smooth light density" in normalized
    assert "semi-transparent monochromatic volumetric-light adult" in normalized
    assert "external anatomy as continuous light formed from that same" in normalized
    assert "MODULE: HAPTIC OR NEURAL SYSTEM" in brief
    assert "MODULE: ACTIVE SUSPENSION" in brief
    assert "broad graphite ribcage pads and outer-thigh wings" in normalized
    assert "all cables and webbing outside the groin" in normalized
    assert "wide, flat, dark, and visibly connected" in normalized
    assert "complete empty bed surface stays visible" in normalized
    assert "MODULE: ADAPTIVE BED OR TRANSPORT BERTH" in brief
    assert "domestic furniture rather than a medical chair" in normalized
    assert "both partners alert, mutually engaged, and physically contributing" in normalized
    assert "side-lying rear-entry berth" in normalized
    assert "bare hips flush to the receiving pelvis" in normalized
    assert "completely clear of both legs" in normalized
    assert "show rain, transit light, or empty architecture as abstract reflections" in normalized
    assert "MODULE: COOLING SUSPENSION" in brief
    assert "four physically separated flexible support wings" in normalized
    assert "30-40 centimeter oval contact opening" in normalized
    assert "50-80 centimeters above" in normalized
    assert "Pale-cyan coolant" in brief
    assert "front partner on one side with their spine facing" in normalized
    assert "rear partner parallel on the same side" in normalized
    assert "rear three-quarter side camera at pelvic height" in normalized
    assert "MODULE: ORBITAL GANTRY" in brief
    assert "two independent counterweighted body axes" in normalized
    assert "30-40-degree backward incline" in normalized
    assert "35-50-degree forward incline" in normalized
    assert "two visible ceiling carriages" in normalized
    assert "safety webbing a muted violet or graphite color" in normalized
    assert "MODULE: ORBITAL MICROGRAVITY" in brief
    assert "MODULE: SAPIENT POSTHUMAN PARTNER" in brief
    assert "MODULE: POSITIVE CONTACT VOCABULARY" in brief
    assert "directly joined pelvises and touching pubic skin" in normalized
    assert "blank solid-color rental cases" in normalized
    assert "Individual styling: for each adult separately" in normalized
    assert "Future room and props: complete room boundaries" in normalized
    assert "cyan, ice-blue, or muted-violet arcs" in normalized
    assert "incorrect total of faces, heads, torsos, pelvises, bodies" in normalized
    assert "penetrating anatomy appears through clothing, detached from its pelvis" in normalized
    assert "masturbation contains an ownerless hand" in normalized
    assert "BDSM loads the neck or airway" in normalized
    assert "a phallic toy is mounted to a man's pelvis" in normalized
    assert "resembles a second penis" in normalized
    assert "a single-adult request contains a second body" in normalized
    assert "changes female_count or male_count" in normalized
    assert "turns a requested gender slot into an unspecified" in normalized
    assert "Selected-action geometry within the first 120 words" in normalized
    assert "bunched around a thigh, knee, or ankle" in normalized
    assert "transport window contains a human reflection" in normalized
    assert "panels are cracked, broken, or unsafe" in normalized
    assert "flesh-colored support hardware" in normalized
    assert "rust, corrosion, peeling plaster" in normalized

    family_section = brief.split("TECHNOLOGY FAMILIES\n\n", 1)[1].split(
        "\n\nSCENE SEED LIBRARY", 1
    )[0]
    seed_section = brief.split("SCENE SEED LIBRARY\n\n", 1)[1].split(
        "\n\nSILENT REJECTION CHECK", 1
    )[0]
    for number in range(1, 24):
        assert f"\n{number}. " in f"\n{family_section}"
    for number in range(1, 31):
        assert f"\n{number}. " in f"\n{seed_section}"

    assert "Rain-Lag Hologram Motel" in normalized
    assert "Heat-Ration Cooling Suspension" in normalized
    assert "Recycled-Air Hotel Suspension" in normalized
    assert "Use these checks silently" in normalized
    assert "Their vocabulary never appears in the returned Frame" in normalized
    assert "Return only the single positive English ASCII paragraph" in normalized
    assert "confirm at least 600 English words" in normalized
    assert "five to seven sentences" not in normalized
    assert "at most 320 words" not in normalized
    assert "2000 ASCII characters" not in normalized
    assert "straight ASCII equivalent" in normalized


def test_precise_intimate_activity_geometry_has_explicit_spatial_contract() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "precise-intimate-activity-geometry.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert brief.isascii()
    assert "EXACT CAST AND BODY OWNERSHIP" in brief
    assert "THEME SEED GATE" in brief
    assert "CENTRAL PERSON LOCK" in brief
    assert "OTHER PERSON BLOCKS" in brief
    assert "2D PROJECTION AND SURFACE VISIBILITY" in brief
    assert "ACTION-CONTACT CHAIN" in brief
    assert "LIFTING AND SUPPORT GEOMETRY" in brief
    assert "SEXUAL ACTION LIBRARY" in brief
    assert "SILENT REJECTION CHECK" in brief
    assert "Exactly N adults belong to N coherent bodies in this image" in normalized
    assert "Every Theme title and premise defines only cast, room, primary activity" in normalized
    assert "A Theme never defines camera side, lens, framing, crop" in normalized
    assert "The Frame is the sole owner of camera and visibility" in normalized
    assert "ignore that language and build one fresh camera graph in the Frame" in normalized
    assert "Create immutable gender slots before writing each Theme" in normalized
    assert "exactly female_count adult woman slots" in normalized
    assert "exactly male_count adult man slots" in normalized
    assert "every Theme premise and every Frame must name exactly one adult woman" in normalized
    assert "Never replace a requested man with a woman" in normalized
    assert "Every visible face, head, torso, pelvis, arm, hand, leg, foot" in normalized
    assert "Body completeness is topological, not a full-body framing requirement" in normalized
    assert "Describe only visible limbs that perform an action, bear weight, or define the pose" in normalized
    assert "Trace each such limb continuously from its visible body attachment" in normalized
    assert "Hidden limbs and regions outside the frame require no inventory" in normalized
    assert "Choose exactly one central person" in normalized
    assert "in one actor block" in normalized
    assert "screen location: image center, center-left, center-right" in normalized
    assert "every visible body chain and every named occluding volume" in normalized
    assert "facial expression and gaze only when the face is visible" in normalized
    assert "Write each visible limb position, support role, and active contact exactly once" in normalized
    assert "Do not first assign a passive position" in normalized
    assert "Describe every other adult in a separate sentence" in normalized
    assert "describe only the visible limb chains, visible support points" in normalized
    assert "State head angle, gaze, and expression only if the face is visible" in normalized
    assert "A flat foot has heel, ball, and toes on the surface" in normalized
    assert "A raised heel leaves only the ball and toes on the surface" in normalized
    assert "an extended elbow cannot also be planted as a support" in normalized
    assert "one opaque two-dimensional projection" in normalized
    assert "Describe only anatomy and contacts reached by an unobstructed line of sight" in normalized
    assert "Lock the camera in the second sentence" in normalized
    assert "framing scale, and near-side visible surfaces" in normalized
    assert "name any volume that hides the primary contact" in normalized
    assert "Never defer the camera until the paragraph's end" in normalized
    assert "single visibility scene graph used by the entire paragraph" in normalized
    assert "Include only anatomy, contact boundaries, support points, and props visible inside its bounds" in normalized
    assert "Regions outside the frame are absent from the graph" in normalized
    assert "Pose, action, styling, lighting, and focus consume this graph" in normalized
    assert "Assign visibility to surface patches rather than whole body parts" in normalized
    assert "assigns the primary contact boundary one state: visible or occluded" in normalized
    assert "An inserted boundary may remain occluded" in normalized
    assert "action then stays readable from body alignment" in normalized
    assert "Visibility state is immutable" in normalized
    assert "cannot later be described, focused on, contacted in view, or called visible" in normalized
    assert "compare every use of visible, occluded, and hidden" in normalized
    assert "In a front view, the chest and front torso may be visible" in normalized
    assert "the full buttocks and rear cleft are not" in normalized
    assert "In a rear view, the back and buttocks may be visible" in normalized
    assert "both breasts, nipples, abdomen, and front genitals are not fully visible" in normalized
    assert "In a strict side view, show only profile contours" in normalized
    assert "Never combine a full frontal chest with a full rear view of both buttocks" in normalized
    assert "A head turn changes face visibility but does not rotate the torso" in normalized
    assert "Use explicit near-side and far-side occlusion order" in normalized
    assert "move the camera or change the pose" in normalized
    assert "transparent anatomy, impossible twisting, a second viewpoint" in normalized
    assert "one physically consistent reflection" in normalized
    assert "When a contact boundary is visible" in normalized
    assert "do not merely claim that its sightline is clear" in normalized
    assert "Prove it by naming the viewing window" in normalized
    assert "For penile oral insertion, use a side-rear or rear three-quarter camera" in normalized
    assert "head or near thigh occludes the mouth-to-genital boundary" in normalized
    assert "Name fellatio once to establish the action" in normalized
    assert "omit local penis, shaft, glans, lip, tongue, and oral-cavity geometry" in normalized
    assert "For external genital licking" in normalized
    assert "CONTACT STATE INVARIANT" in brief
    assert "Assign every contact one and only one topological state" in normalized
    assert "separated: two structures have a visible gap" in normalized
    assert "external contact: two exterior surfaces meet at one visible boundary" in normalized
    assert "inserted: the receiving boundary encircles the active structure" in normalized
    assert "One contact cannot occupy two states in the same Frame" in normalized
    assert "omit every distal structure beyond that boundary" in normalized
    assert "Do not name, locate, light, focus, or assign motion to anatomy inside" in normalized
    assert "two sides of every contact boundary share one screen location and one depth plane" in normalized
    assert "must be reachable from its connected joints" in normalized
    assert "change the pose or support before writing prose" in normalized
    assert "For penile oral activity, choose exactly one of two alternatives" in normalized
    assert "Oral insertion names fellatio once" in normalized
    assert "assigns their contact boundary to the occluded state" in normalized
    assert "omits its local anatomy" in normalized
    assert "These alternatives never coexist" in normalized
    assert "Any hand contact is a separate action chain" in normalized
    assert "For mouth-to-breast contact" in normalized
    assert "The mouth occludes the central patch beneath the lips" in normalized
    assert "For penetration, use a lateral or three-quarter-lateral view" in normalized
    assert "End the visible chain at that junction and omit the internal segment" in normalized
    assert "For lifted penetration, choose either a front-biased view" in normalized
    assert "the far buttock and far supporting contact remain occluded" in normalized
    assert "Never claim that both buttocks, both under-buttock contacts" in normalized
    assert "For manual or toy contact" in normalized
    assert "a front camera cannot see the rear adult's pelvis" in normalized
    assert "contact trapped between the two torsos or pelvises" in normalized
    assert "Offset the adults and use a lateral three-quarter camera" in normalized
    assert "actor -> owned body part or held object -> target adult" in normalized
    assert "Choose one action-chain form from the contact boundary's camera-graph state" in normalized
    assert "Write that chain once inside the active adult's actor block" in normalized
    assert "does not repeat the contact anatomy or reassign the active limb" in normalized
    assert "For a visible boundary" in normalized
    assert "For an occluded boundary" in normalized
    assert "activity name -> actor and target body alignment" in normalized
    assert "omits the hidden contact anatomy, contact motion, and interior state" in normalized
    assert "Never combine the visible and occluded forms for one action" in normalized
    assert "Mina's tongue extends visibly from Mina's mouth" in normalized
    assert "Occluded oral insertion: An kneels between Bo's parted thighs" in normalized
    assert "side-rear camera overlaps An's head silhouette with Bo's pubic region" in normalized
    assert "Bo's near thigh occludes their contact boundary" in normalized
    assert "Jun's right shoulder leads to his bent right elbow" in normalized
    assert "the penetrating anatomy remains visibly continuous with its owner's pelvis" in normalized
    assert "the receiving adult's pubic region meets it in the same contact plane" in normalized
    assert "the external insertion junction" in normalized
    assert "End the visible description at the receiving boundary" in normalized
    assert "omit the internal portion" in normalized
    assert "Never terminate penetrating anatomy at an abdomen" in normalized
    assert "One limb performs one physical role" in normalized
    assert "across the entire paragraph" in normalized
    assert "When another adult lifts the central person" in normalized
    assert "which region bears weight: upper back, ribcage, waist" in normalized
    assert "both feet clear of the floor" in normalized
    assert "For lifted penetration, use a mechanically compatible axis" in normalized
    assert "Do not describe the lifted adult as horizontal or across the lifter" in normalized
    assert "trace load from the named body region" in normalized
    assert "Every visible adult participates through an action" in normalized
    assert "one concise styling clause using only visible elements from the camera graph" in normalized
    assert "describe footwear only when a foot is visible" in normalized
    assert "Styling never reintroduces an occluded or off-frame region" in normalized
    assert "Do not restate or change the camera established in sentence two" in normalized
    assert "Choose framing for action readability" in normalized
    assert "Keep every active contact and support chain inside the frame" in normalized
    assert "omit all anatomy outside the selected framing" in normalized
    assert "a non-ASCII character remains" in normalized
    assert "without changing the locked camera" in normalized
    assert "Return one concise positive English ASCII paragraph" in normalized

    assert "HIGHEST PRIORITY CAST AND CAMERA LOCK" not in brief
    assert "VISIBLE FUTURE-TECHNOLOGY SIGNATURE" not in brief
    assert "FUTURE VISUAL WORLD LOCK" not in brief
    assert "HIGH FUTURE VISUAL INTENSITY LOCK" not in brief
    assert "ANTI-SCI-FI VISUAL GATE" not in brief


def test_surreal_conceptual_portrait_has_safe_minimal_installation_contract() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "surreal-conceptual-portrait.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert brief.isascii()
    assert "ABSOLUTE OUTPUT PRIORITY" in brief
    assert "at least 600 whitespace-delimited words" in normalized
    assert "Target 650-900 words" in normalized
    assert 'call the image a "live-action dark-fantasy feature-film frame"' in (
        normalized
    )
    assert "do not substitute cinematic, photorealistic" in normalized
    assert "ASCII is an absolute publication requirement" in normalized
    assert "final character-by-character ASCII sweep" in normalized
    assert "This minimum overrides every later request for brevity" in normalized
    assert "museum-caliber surreal conceptual portraits" in normalized
    assert "one impossible but visually coherent metaphor" in normalized
    assert "Do not copy any reference composition" in normalized
    assert "one dominant metaphor" in normalized
    assert (
        "Use exactly the requested number of adult women and adult men"
        in normalized
    )
    assert "this exact visible cast is alone in the scene" in normalized
    assert "every person is Chinese" in normalized
    assert (
        "Give every requested person an indispensable compositional role"
        in normalized
    )
    assert "SUSPENDED ASSEMBLIES" in brief
    assert (
        "credible support lines rising to an off-frame ceiling grid"
        in normalized
    )
    assert "Every heavy object has its own plausible load path" in normalized
    assert (
        "Nothing hangs by a person's hair, skin, neck, genitals, or clothing"
        in normalized
    )
    assert "visible hanger or flat non-human support" in normalized
    assert "Wardrobe archives contain only adult-sized garments" in normalized
    assert "no baby clothes, child-sized clothing, school uniforms" in normalized
    assert "ultralight hollow theatrical replica" in normalized
    assert "other rigid or heavy objects remain beside the cast" in normalized
    assert "OBJECT-HEAD AND FACE CONCEALMENT" in brief
    assert (
        "wearable sculptural headpiece around one existing person's real head"
        in normalized
    )
    assert (
        "never a decapitation, floating replacement, second head"
        in normalized
    )
    assert "Keep the nose and mouth physically uncompressed" in normalized
    assert "Never use tight plastic, adhesive wrap, strangling cord" in normalized
    assert "a balaclava, an enclosed hood, a sack" in normalized
    assert "a generous lower-face breathing gap" in normalized
    assert "an independent load path that bypasses the neck" in normalized
    assert "lightweight shatterproof acrylic" in normalized
    assert "Never place real glass, ceramic, brittle material" in normalized
    assert "never reflect, repeat, fragment, or multiply a person's" in normalized
    assert "Reserve approximately forty to seventy percent" in normalized
    assert "no more than two dominant hues plus one accent" in normalized
    assert "typically 40-105 mm equivalent" in normalized
    assert (
        "Each visible limb connects continuously to one person's torso"
        in normalized
    )
    assert (
        "Do not create extra, detached, repeated, fused, or source-less anatomy"
        in normalized
    )
    assert "At Hardcore level, the installation may frame, echo, count" in normalized
    assert "it may not penetrate, restrain, suspend, strike" in normalized
    assert "shoulders, chest, pelvis, buttocks, and genitals fully covered" in normalized
    assert "Frames within one Theme are parallel finished portraits" in normalized
    assert "three suspended systems, two grounded object arrangements" in normalized
    assert "NO-TEXT IMAGE CONTRACT" in brief
    assert "Every final Frame explicitly restates" in normalized
    assert "Never describe them as handwritten, printed, addressed" in normalized
    assert "at least 600 words long" in normalized
    assert "650-900 word working range" in normalized
    assert "approximately twelve to sixteen sentences" in normalized
    assert "Expand these six areas across the full sentence budget" in normalized
    assert '"Only the specified cast is present"' in normalized
    assert "Use ASCII characters only in an English Frame" in normalized
    assert "scan every character in an English Frame" in normalized
    assert "contains any non-ASCII character in an English Frame" in normalized
    assert (
        "Count whitespace-delimited words before returning each English Frame"
        in normalized
    )
    assert "if the count is below 600" in normalized
    assert "Do not append a material inventory, symbolic interpretation" in normalized


def test_demon_lord_brief_has_gendered_sovereign_dark_fantasy_contract() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "demon-lord.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert brief.isascii()
    assert "exactly one central demon sovereign" in normalized
    assert "adult female demon lord or one adult male demon lord" in normalized
    assert "Never place both a female and a male demon sovereign" in normalized
    assert "at least 600 whitespace-delimited words" in normalized
    assert "Target 650-900 words" in normalized
    assert "live-action dark-fantasy feature-film image" in normalized
    assert "LIVE-ACTION CINEMATIC THESIS" in brief
    assert "real adult performer with natural skin texture" in normalized
    assert "physically wearable horns, wings, armor" in normalized
    assert "finished frame from a large-budget live-action" in normalized
    assert "not an oil painting, illustration, concept art" in normalized
    assert "restrained invisible visual-effects extension" in normalized
    assert "intentionally low-saturation, dark-key, high-tonal-contrast" in (
        normalized
    )
    assert "desaturated blue-grey and tarnished muted amber" in normalized
    assert "Do not copy the reference's demon design" in normalized
    assert "Use exactly the requested number of adult women and adult men" in normalized
    assert "The demon sovereign counts as one requested woman or one requested man" in (
        normalized
    )
    assert "silently build a cast ledger" in normalized
    assert "Never convert a requested woman into a man" in normalized
    assert "Within the first sixty English words" in normalized
    assert "exactly one adult woman and exactly one adult man" in normalized
    assert "For every mixed cast, the first sentence states all requested gender counts" in (
        normalized
    )
    assert "Reserve those two exact \"only\" constructions exclusively" in normalized
    assert "SOLO CAST LOCK" in brief
    assert "strict solo portrait containing only that one demon sovereign" in normalized
    assert 'first sentence must say "one adult Chinese man only"' in normalized
    assert 'first sentence must say "one adult Chinese woman only"' in normalized
    assert "Never use plural people, paired objects implying another owner" in normalized
    assert "with women and no men" in normalized
    assert "with men and no women" in normalized
    assert "with a mixed cast, choose exactly one requested adult" in normalized
    assert "balance female and male sovereigns" in normalized
    assert "visible human-equivalent age from twenty-five through seventy-nine" in (
        normalized
    )
    assert "may never replace it" in normalized
    assert "Use one exact integer age for every person" in normalized
    assert "Never write mid-thirties, early forties, late fifties" in normalized
    assert "retain a clearly Chinese adult identity" in normalized
    assert "EQUAL AGENCY AND CONSENT" in brief
    assert "awake, unimpaired, willing, responsive" in normalized
    assert "describes the interaction as consensual and willing" in normalized
    assert "Within the first one hundred English words" in normalized
    assert 'include the exact phrase "consensual and willing"' in normalized
    assert "Within the first one hundred English words of every Hardcore Frame" in (
        normalized
    )
    assert "whose erect penis is inside whose vagina or anus" in normalized
    assert "Place that direct Hardcore contact in the first or second sentence" in (
        normalized
    )
    assert "Do not spend the opening on face, horns, wardrobe" in normalized
    assert "All word-position checks are silent" in normalized
    assert "Never mention first words, first one hundred words" in normalized
    assert "Never use a prisoner, slave, sacrifice, tribute" in normalized
    assert "ROLE AND CHARACTER VARIETY" in brief
    assert "infernal judge weighing an impossible dispute" in normalized
    assert "court astronomers, alchemists, archivists" in normalized
    assert "Only when the requested cast contains additional adults" in normalized
    assert "Do not let every female sovereign become a seductive queen" in normalized
    assert "one head, one neck, one torso, two arms" in normalized
    assert "Horns are optional but usually desirable" in normalized
    assert "exactly one matched pair attached across the upper back" in normalized
    assert "optional tail emerges continuously from the sacrum" in normalized
    assert "Do not add oversized fantasy genitals" in normalized
    assert "All sexual anatomy remains adult humanoid anatomy" in normalized
    assert "THRONE, COURT, AND WORLD" in brief
    assert "Rotate among distinct scene families" in normalized
    assert "vertical sacred spaces" in normalized
    assert "intimate royal interiors" in normalized
    assert "working seats of power" in normalized
    assert "exterior domains" in normalized
    assert "original transitional spaces" in normalized
    assert "Do not default every scene to smoke, embers" in normalized
    assert "ENVIRONMENTAL SET-PIECE AND EVENT ENGINE" in brief
    assert "exactly one dominant set-piece event already happening" in normalized
    assert "colossal floodgate opening" in normalized
    assert "suspended forge crucible rotating" in normalized
    assert "storm observatory's physical rings turning" in normalized
    assert "mechanical eclipse aperture closing" in normalized
    assert "Choose a peak readable instant" in normalized
    assert "one dominant event and at most one subordinate environmental reaction" in (
        normalized
    )
    assert "complete occupied body zone is dry, room-temperature, stable" in normalized
    assert "Water may form a shallow reflective layer no higher than the ankles" in (
        normalized
    )
    assert "Never stage intimacy underwater" in normalized
    assert "Keep ash, dust, silt, sparks, rain, smoke, steam" in normalized
    assert "remain several body lengths away behind a visible" in normalized
    assert "Do not repeat the reference's close frontal lap arrangement" in normalized
    assert "DEPTH, SILHOUETTE, AND VISUAL IMPACT" in brief
    assert "three readable spatial layers" in normalized
    assert "one dominant graphic structure" in normalized
    assert "Add one scale contrast and one material contrast" in normalized
    assert "Choose one movement vector" in normalized
    assert "POSE AND INTERACTION VARIETY" in brief
    assert "open-ended pose engines" in normalized
    assert "At Aesthetic level, vary" in normalized
    assert "At Erotic level, vary non-explicit adult arrangements" in normalized
    assert "At Hardcore level, rotate physically credible explicit arrangements" in (
        normalized
    )
    assert "face-to-face seated vaginal or anal intercourse" in normalized
    assert "supported standing intercourse" in normalized
    assert "side-lying intercourse" in normalized
    assert "rear-entry vaginal or anal intercourse" in normalized
    assert "mutual masturbation, reciprocal oral contact" in normalized
    assert "one dominant body arrangement" in normalized
    assert "24-135mm equivalent" in normalized
    assert "Reserve 24-28mm for environmental wides" in normalized
    assert "Rotate camera families among frontal eye-level symmetry" in normalized
    assert "floor-level view along a reflective surface" in normalized
    assert "Select one decisive cinematic instant" in normalized
    assert "Every final Frame states one exact focal length in millimeters" in normalized
    assert "vague phrase such as cinematic view, dramatic angle" in normalized
    assert "LIGHT, COLOR, AND LIVE-ACTION FINISH" in brief
    assert "Render as live-action cinematic photography" in normalized
    assert "Practical prosthetics meet skin through credible bases" in normalized
    assert "fine cinematic grain" in normalized
    assert "Avoid oil painting, visible brushwork, illustration" in normalized
    assert "frame from the finished fictional film itself" in normalized
    assert "LOW-SATURATION HIGH-CONTRAST COLOR LOCK" in brief
    assert "Suppress color contrast while preserving strong luminance contrast" in (
        normalized
    )
    assert "At least eighty-five percent of the visible frame" in normalized
    assert "sixty to seventy-five percent of the frame remain in deep readable shadow" in (
        normalized
    )
    assert "a small area of bone-white or metallic highlight" in normalized
    assert "Preserve detail inside blacks" in normalized
    assert "Any colored accent occupies at most five percent" in normalized
    assert "two subdued hue families plus neutral materials" in normalized
    assert "Do not use saturated turquoise, electric cyan" in normalized
    assert "cinematic teal-and-orange grade" in normalized
    assert "Avoid flat grey fog, muddy midtone-only rendering" in normalized
    assert "Every visible limb connects continuously" in normalized
    assert "At Aesthetic level, every person remains fully covered" in normalized
    assert "show no penetration, explicit oral-genital contact" in normalized
    assert "one clearly visible consensual adult sexual act already in progress" in (
        normalized
    )
    assert "for a one-person cast, use visible adult masturbation" in normalized
    assert "for multiple adults, keep the exact cast visible" in normalized
    assert "ordinary adult humanoid sexual anatomy" in normalized
    assert "Never use a horn, claw, tail, tentacle, weapon" in normalized
    assert "use blunt horns swept away from all faces and bodies" in normalized
    assert "No participant grips, pulls, rides, or braces against a horn" in normalized
    assert "Do not use needle points, bladed tail tips" in normalized
    assert "Frames within one Theme are parallel finished images" in normalized
    assert "Within every rolling group of twelve Themes" in normalized
    assert "Across a one-hundred-Theme run" in normalized
    assert "eight distinct dominant set-piece events" in normalized
    assert "six different three-layer depth designs" in normalized
    assert "do not repeat the same environment family, dominant event" in normalized
    assert "may occupy more than one tenth of the Themes" in normalized
    assert "NO-TEXT IMAGE CONTRACT" in brief
    assert "Use ASCII characters only in an English Frame" in normalized
    assert "absolute publication requirement" in normalized
    assert "silently rescan every character" in normalized
    assert "End by restating the exact number of adult women and adult men" in normalized
    assert "Word counting is a silent authoring check" in normalized
    assert 'Do not write phrases such as "six hundred words"' in normalized
    assert 'State zero as "zero adult women" or "zero adult men"' in normalized
    assert "adds any second person, name, owner, gaze partner" in normalized
    assert "falls below 600 English words" in normalized
    assert "uses vivid, neon, jewel-tone, high-saturation" in normalized
    assert "leaves the environment static without one visible current event" in normalized
    assert "combines more than one dominant disaster" in normalized
    assert "omits an exact 24-135mm focal length" in normalized
    assert "postpones exact Hardcore anatomy or direct contact" in normalized
    assert "stages Erotic or Hardcore intimacy underwater" in normalized
    assert "places ash, dust, silt, sparks, rain, smoke" in normalized
    assert 'omits "live-action dark-fantasy feature-film frame"' in normalized


def test_angel_brief_has_dark_cinematic_exact_cast_contract() -> None:
    brief = (REPOSITORY_ROOT / "story-inputs" / "angel.txt").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert brief.isascii()
    assert "live-action dark-fantasy feature-film image" in normalized
    assert "premium feature film with real adult performers" in normalized
    assert "exactly one central angel" in normalized
    assert "adult female angel or one adult male angel" in normalized
    assert "Never place both a female and a male central angel" in normalized
    assert "Exactly one requested adult is an angel" in normalized
    assert "Every other requested adult is an ordinary wingless human" in normalized
    assert "one winged angel and one wingless human" in normalized
    assert "at least 600 whitespace-delimited words" in normalized
    assert "Target 650-900 words" in normalized
    assert "ASCII is an absolute publication requirement" in normalized
    assert "final character-by-character ASCII sweep" in normalized
    assert (
        'first sixty English words of every final Frame, explicitly call the image '
        'a "live-action dark-fantasy feature-film frame"'
    ) in normalized
    assert "LIVE-ACTION CINEMATIC THESIS" in brief
    assert "real adult performer with natural skin texture" in normalized
    assert "physically constructed wings" in normalized
    assert "monumental locations, controlled production design" in normalized
    assert "real feature-film optics" in normalized
    assert "photographic dark-fantasy cinematic realism" in normalized
    assert "Do not use oil-painting language" in normalized
    assert "synthetic CGI gloss" in normalized
    assert "Use restrained invisible visual-effects extension" in normalized
    assert "Create completely original adult characters and scenes" in normalized
    assert "Do not copy a reference face, body, pose" in normalized
    assert "Use exactly the requested number of adult women and adult men" in normalized
    assert "silently build a cast ledger" in normalized
    assert "Within the first sixty English words" in normalized
    assert "identify every non-central requested adult as a wingless human" in (
        normalized
    )
    assert "SOLO CAST LOCK" in brief
    assert "strict solo portrait containing only that central angel" in normalized
    assert 'first sentence must say "one adult Chinese man only"' in normalized
    assert 'first sentence must say "one adult Chinese woman only"' in normalized
    assert "exact visible age from twenty-five through seventy-nine" in normalized
    assert "State an exact integer age" in normalized
    assert "retains a clearly Chinese adult identity" in normalized
    assert "EQUAL AGENCY AND CONSENT" in brief
    assert "awake, unimpaired, willing, responsive" in normalized
    assert 'exact phrase "consensual and willing"' in normalized
    assert "show no alcohol, liquor, wine, beer, cocktail" in normalized
    assert "REALISTIC CHARACTER AND ROLE VARIETY" in brief
    assert "celestial marshal inspecting a storm-battered mountain gate" in normalized
    assert "eclipse navigator adjusting physical rings" in normalized
    assert "night gardener tending pale plants in an ash-dark conservatory" in normalized
    assert "ANGEL ANATOMY AND WINGS" in brief
    assert "plus exactly one matched pair of wings" in normalized
    assert "Attach both wings across the upper back and shoulder-blade region" in (
        normalized
    )
    assert "exactly one matched pair consisting of one left wing and one right wing" in (
        normalized
    )
    assert "long weathered ivory eagle-like flight feathers" in normalized
    assert "oxidized silver falcon-like wings" in normalized
    assert "Do not create six wings, eye-covered wings, detached wings" in normalized
    assert "WARDROBE, ARMOR, AND REGALIA" in brief
    assert "blackened articulated plate with worn old-gold inlay" in normalized
    assert "tarnished pale-gold lamellar" in normalized
    assert "Golden armor is welcome" in normalized
    assert "narrow controlled highlights, darker joint recesses" in normalized
    assert "MONUMENTAL CINEMATIC LOCATIONS" in brief
    assert "cyclopean basalt cathedral beneath a broken oculus" in normalized
    assert "drowned bell crypt lit through deep mineral water" in normalized
    assert "storm observatory with physical rings surrounding an open roof" in normalized
    assert "ENVIRONMENTAL SET-PIECE AND EVENT ENGINE" in brief
    assert "exactly one dominant set-piece event" in normalized
    assert "mechanical eclipse aperture closing across a pale skylight" in normalized
    assert "exactly one dominant event and at most one subordinate" in normalized
    assert "complete occupied body zone is dry, room-temperature, stable" in normalized
    assert "filled with breathable air" in normalized
    assert "no face, chest, pelvis, sexual contact, or breathing passage is submerged" in (
        normalized
    )
    assert "Keep ash, dust, silt, sparks, rain, smoke, steam" in normalized
    assert "several body lengths away and physically isolated" in normalized
    assert "DEPTH, SILHOUETTE, AND VISUAL IMPACT" in brief
    assert "Build every image in three readable layers" in normalized
    assert "foreground threshold" in normalized
    assert "midground containing the complete cast" in normalized
    assert "background carrying monumental architecture" in normalized
    assert "one strong graphic structure per image" in normalized
    assert "one readable movement vector" in normalized
    assert "POSE AND ACTION VARIETY" in brief
    assert "walking through a descending oculus shaft" in normalized
    assert "At Erotic level, use non-explicit adult intimacy" in normalized
    assert "one clearly visible consensual adult sexual act already in progress" in (
        normalized
    )
    assert "Within the first one hundred English words" in normalized
    assert "within the first two sentences" in normalized
    assert "which adult's penis is inside which adult's vagina or anus" in normalized
    assert "generic \"point of contact\" does not satisfy Hardcore" in normalized
    assert "one-hundred-word and first-two-sentence placement checks are silent" in (
        normalized
    )
    assert "Never mention a word position, word threshold" in normalized
    assert "LOW-SATURATION HIGH-CONTRAST CINEMATIC LIGHT AND COLOR LOCK" in brief
    assert "dark-key, low-saturation, high-contrast, and narrow-gamut" in normalized
    assert "At least eighty-five percent of the visible image" in normalized
    assert "roughly sixty to seventy-five percent of the image" in normalized
    assert "colored accent occupies at most five percent" in normalized
    assert "Do not use saturated turquoise, electric cyan" in normalized
    assert "CAMERA AND LIVE-ACTION FINISH" in brief
    assert "24mm or 28mm environmental wide" in normalized
    assert "35mm environmental portrait at eye level" in normalized
    assert "50mm medium full-body shot" in normalized
    assert "100mm or 135mm compressed architectural composition" in normalized
    assert "one exact focal length from 24mm through 135mm" in normalized
    assert "subtle cinematic grain and natural microcontrast" in normalized
    assert "Across every ten Themes" in normalized
    assert "at least eight distinct dominant set-piece events" in normalized
    assert "at least six different three-layer depth designs" in normalized
    assert "Within every rolling group of twelve Themes" in normalized
    assert "Across a one-hundred-Theme run" in normalized
    assert "No single frontal white-wing pose" in normalized
    assert "NO-TEXT IMAGE CONTRACT" in brief
    assert "Word counting is a silent authoring check" in normalized
    assert "Use ASCII characters only in an English Frame" in normalized
    assert "falls below 600 English words" in normalized
    assert "calls any non-central person an angel" in normalized
    assert "more than one winged person or more than one matched pair" in normalized
    assert "uses alcohol, liquor, wine, beer, cocktails" in normalized
    assert "leaves the environment static without one visible current event" in normalized
    assert "lacks readable foreground, midground, and background depth" in normalized
    assert "places intimacy in deep water, on wet or slippery support" in normalized
    assert "finished visible live-action cinematic image" in normalized


def _legacy_motion_blur_photography_contract() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "motion-blur-photography.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "HIGHEST PRIORITY OUTPUT CONTRACT" in brief
    assert "one self-contained English paragraph of at least 700 words" in normalized
    assert "Target 850-1200 words" in normalized
    assert "Apply a final lexical render gate to the Frame" in normalized
    assert "must contain zero instances of camera body, camera mounted, tripod" in normalized
    assert "production crew, photographer, lighting assistant, production personnel" in normalized
    assert "capture cable, shutter trigger, capture monitor" in normalized
    assert "Rewrite them as locked viewpoint, panned viewpoint, off-frame pulse" in normalized
    assert "Do not output a negative inventory of absent gear" in normalized
    assert "Crew cut and crew-neck remain valid appearance and garment-construction terms" in normalized
    assert "A monitor, cable, or equipment rack remains valid when the visible location's ordinary current function genuinely requires it" in normalized
    assert "silently rewrite it if it falls below 700" in normalized
    assert "Do not pad the paragraph with repetition" in normalized
    assert "Write with maximum information density" in normalized
    assert "make every sentence add new, concrete, visible, renderable information" in normalized
    assert "prefer exact nouns and measurements over decorative adjectives" in normalized
    assert "Concision means removing redundancy, never removing required information" in normalized
    assert "Do not shorten by omitting, generalizing, or merely implying" in normalized
    assert "background population, setting, camera, light, exposure" in normalized
    assert "CAVEMAN OUTPUT MODE" in brief
    assert "compact, telegraphic image-prompt prose instead of literary narration" in normalized
    assert "short subject-verb-object clauses joined by semicolons" in normalized
    assert "Order visible facts first" in normalized
    assert "Put the photographic explanation in the final portion" in normalized
    assert "invisible viewpoint geometry, lens and focus, off-frame illumination" in normalized
    assert "State each fact once" in normalized
    assert "remove conversational transitions, scene-setting filler" in normalized
    assert "Order information once in this sequence" in normalized
    assert "Do not circle back to restate an earlier section" in normalized
    assert "one continuous paragraph without headings" in normalized
    assert "compressed syntax and zero ornament, not missing facts" in normalized
    assert "requested female and male counts apply exactly to the primary adult subjects" in normalized
    assert "Contextual background adults are governed only by" in normalized
    assert "lock one complete visual dossier for each requested person" in normalized
    assert "exact adult age, exact height, body proportions" in normalized
    assert "chest and breast proportions as applicable" in normalized
    assert "Repeat that complete dossier independently in every Frame" in normalized
    assert "COMPLETE PERSON DESCRIPTION IN EVERY FRAME" in brief
    assert "exact height in centimeters" in normalized
    assert "natural breast size, shape, projection" in normalized
    assert "face shape and mature facial anatomy" in normalized
    assert "precise skin color and undertone" in normalized
    assert "every visible garment from inner visible layer to outer layer" in normalized
    assert "complete footwear, including shoe type" in normalized
    assert "every piece of jewelry and every accessory" in normalized
    assert "one specific facial expression" in normalized
    assert "one complete current action or held pose" in normalized
    assert "EXPRESSION LEDGER" in brief
    assert "one distinct, stable expression" in normalized
    assert "exact gaze target; eye openness and focus" in normalized
    assert "upper and lower eyelid tension" in normalized
    assert "brow height, angle, and asymmetry" in normalized
    assert "jaw tension; cheek tension" in normalized
    assert "visible evidence of alertness, agency, response, and consent" in normalized
    assert "complementary but non-identical expressions" in normalized
    assert "Lock one expression for the entire exposure" in normalized
    assert "WARDROBE, UNDRESSING, AND ACCESSORY LEDGER" in brief
    assert "one fixed wardrobe inventory for every primary adult" in normalized
    assert "eyeglasses or sunglasses, scarf or neckwear, jewelry" in normalized
    assert "every primary adult exactly one complete pair of footwear" in normalized
    assert "If the person is barefoot, describe both removed shoes" in normalized
    assert "never write only that the person wears no shoes" in normalized
    assert "every primary adult at least two distinctive accessories" in normalized
    assert "at least one jewelry item" in normalized
    assert "one signature non-jewelry item chosen from eyeglasses, sunglasses" in normalized
    assert "cannot replace the required eyeglasses, sunglasses, or silk scarf" in normalized
    assert "Do not satisfy this rule with two jewelry items" in normalized
    assert "Every Frame must account for every inventoried item" in normalized
    assert "partly removed, naming which limb or body region remains inside it" in normalized
    assert "fully removed and visibly placed at one exact location" in normalized
    assert "Never make clothing, shoes, glasses, a scarf, jewelry" in normalized
    assert "where every removed garment, underwear piece, shoe" in normalized
    assert "Place and describe every item separately" in normalized
    assert "never use the words pile, cluster, heap, bundle" in normalized
    assert "A fully nude adult may deliberately retain jewelry, glasses, a scarf" in normalized
    assert "Lay a removed garment flat" in normalized
    assert "never roll it into a bundle" in normalized
    assert "one person's garment on top of another person's garment" in normalized
    assert "at least twenty centimeters apart with no overlap" in normalized
    assert "No garment may be simultaneously worn and lying elsewhere" in normalized
    assert "Audit garment construction before accepting the Frame" in normalized
    assert "A pullover T-shirt has no front opening, buttons, placket, or shirt cuffs" in normalized
    assert "A button-front dress shirt may open along its placket" in normalized
    assert "A slip dress uses straps rather than sleeves" in normalized
    assert "EROTIC LEVEL" in brief
    assert "at least three of those five signals" in normalized
    assert "Bare breasts and nipples, cleavage, back, abdomen" in normalized
    assert "use a self-possessed held pose with deliberate adult self-touch" in normalized
    assert "every requested adult must participate in reciprocal contact" in normalized
    assert "Erotic Frames do not show genital close-ups" in normalized
    assert "HARDCORE LEVEL" in brief
    assert "State the act near the beginning of the Frame" in normalized
    assert "HARDCORE WARDROBE DISTRIBUTION" in brief
    assert "Partial clothing is the default Hardcore styling" in normalized
    assert "Do not choose full nudity merely because" in normalized
    assert "Plan the wardrobe distribution from the requested Hardcore Theme count" in normalized
    assert "At least seventy-five percent of the requested Themes" in normalized
    assert "round this minimum upward to a whole Theme" in normalized
    assert "At most twenty-five percent may show all primary adults fully nude" in normalized
    assert "round this maximum downward to a whole Theme" in normalized
    assert "When the rounded all-nude maximum is zero" in normalized
    assert "Every requested Frame inherits its Theme's" in normalized
    assert "each primary adult retains at least two worn clothing categories" in normalized
    assert "roughly thirty-five to seventy percent" in normalized
    assert "Open, lift, lower, loosen, or displace only the specific garment area" in normalized
    assert "Do not remove an upper garment when only lower anatomy needs access" in normalized
    assert "For a one-person cast, show explicit solo masturbation already in progress" in normalized
    assert "every requested adult must have one active, unmistakable role" in normalized
    assert "An inserted structure enters once at one receiving boundary" in normalized
    assert "For standing penetration, separate and bend the receiving adult's legs" in normalized
    assert "align both pelvises at the same height and depth plane" in normalized
    assert "Do not combine closed or touching legs with visible vaginal" in normalized
    assert "trace only the externally visible portion" in normalized
    assert "end the description at that boundary" in normalized
    assert "fully inserted while also calling its entire length fully visible" in normalized
    assert "Never describe the glans or any internal segment as visible" in normalized
    assert "the external shaft leads continuously from its owner's pelvis" in normalized
    assert "everything beyond the boundary is internal and omitted" in normalized
    assert '"fully inserted," "visibly inserted," "fully visible penis,"' in normalized
    assert "Do not describe the glans in an inserted act" in normalized
    assert "sexual fluid remains a small, localized, sharp surface detail" in normalized
    assert "MOTION MODE CONTRACT" in brief
    assert "SUBJECT MOTION BLUR" in brief
    assert "FLASH-FROZEN ACTION PEAK" in brief
    assert "STILL ANCHOR, MOVING WORLD" in brief
    assert "The modes are mutually exclusive" in normalized
    assert "do not add independently moving crowds, weather, liquid, or thrown props" in normalized
    assert "Never write \"secondary motion,\" \"additional motion evidence,\"" in normalized
    assert "MOTION NECESSITY AND SCENE CAUSALITY" in brief
    assert "Build the believable scene and current activity first" in normalized
    assert "Never add a moving object, weather condition, crowd behavior" in normalized
    assert "Because this visible current activity is happening" in normalized
    assert "Do not add a scarf, jacket, shirt, or stocking solely so it can fly" in normalized
    assert "never introduce a bucket, glass, hose, splash, or spray only for motion" in normalized
    assert "do not give extras flashlights, lanterns, fabric, or choreographed gestures" in normalized
    assert "If deleting the moving element leaves the scene's activity unchanged" in normalized
    assert "SCENE, MECHANICS, AND PHOTOGRAPHIC RESULT" in brief
    assert "Close three causal loops before writing" in normalized
    assert "Scene loop: location, operating state, weather, population" in normalized
    assert "Mechanics loop: every force must have a visible source" in normalized
    assert "Imaging loop: camera movement, shutter time, flash duration" in normalized
    assert "a camera setting that cannot create the claimed result" in normalized
    assert "Never make one hand throw ten liters of water" in normalized
    assert "Every released object follows a ballistic arc" in normalized
    assert "Rain outside glass stays outside" in normalized
    assert "casual conversation, cleanup, equipment handling, or walking extras as sharp" in normalized
    assert "This is the only mode in which every primary adult remains completely motionless" in normalized
    assert "synchronized panning or flash" in normalized
    assert "Never blur the entire person into an unreadable silhouette" in normalized
    assert "Synchronized panning can keep only one tracked plane and velocity" in normalized
    assert "At Hardcore level, do not use synchronized panning" in normalized
    assert "a just-thrown garment flies open above or beside its owner" in normalized
    assert "a longer ambient exposure leaves one coherent trailing path" in normalized
    assert "one of the image's two largest visual masses" in normalized
    assert "roughly thirty to seventy percent of the visible frame" in normalized
    assert "The viewer must recognize motion before reading facial or wardrobe detail" in normalized
    assert "MOTION RECOGNIZABLE AT FIRST GLANCE" in brief
    assert "Choose one dominant motion-evidence carrier per Frame" in normalized
    assert "A subject action and its directly caused garment" in normalized
    assert "background adult group that translates, rotates, falls" in normalized
    assert "When background adults carry the blur" in normalized
    assert "A dense crowd field requires multiple parallel walking lanes" in normalized
    assert "a single-file line cannot fill a broad region" in normalized
    assert "never a top-to-bottom vertical curtain" in normalized
    assert "Choose one dominant motion system, never unrelated competing systems" in normalized
    assert "render background adults as sharp secondary figures" in normalized
    assert "They do not walk, walk in place, gesture, turn" in normalized
    assert "Changing pixels, refreshing data, scrolling screen content" in normalized
    assert "does not count as physical motion" in normalized
    assert "must be visibly active during the current exposure" in normalized
    assert "a boat that already passed, residual wake, aftermath" in normalized
    assert "Describe motion direction in the image plane" in normalized
    assert "a river seen from its bank blurs along its downstream course" in normalized
    assert "Rain in calm air produces vertical trails" in normalized
    assert "Wind-driven rain produces diagonal trails" in normalized
    assert "Choose exactly one of those states per Frame" in normalized
    assert "Gravity-driven water travels downward" in normalized
    assert "Pump-driven water may travel upward" in normalized
    assert "Never describe upward water as gravity-driven" in normalized
    assert "Choose camera movement according to the motion mode" in normalized
    assert "permit one smooth horizontal, vertical, or diagonal pan" in normalized
    assert "the environment streaks in the opposite screen direction" in normalized
    assert "Never combine panning with zooming, rotation, random shake" in normalized
    assert "roughly 1/15 to 1/4 second for panned subject motion" in normalized
    assert "roughly 1/15 to 1/2 second for a frozen action peak" in normalized
    assert "roughly 1/4 to 1 second for a still anchor" in normalized
    assert "Separate shutter time from flash duration" in normalized
    assert "Use a plausible t.1 flash duration around 1/2000 to 1/10000 second" in normalized
    assert "Never call 1/200 or 1/250 second the flash pulse" in normalized
    assert "Flash freezes only surfaces receiving enough flash illumination" in normalized
    assert "at least three stops below the flash exposure" in normalized
    assert "First-curtain flash places the crisp image at the beginning" in normalized
    assert "rear-curtain flash places the crisp image at the end" in normalized
    assert "Estimate the photographed displacement during the open shutter" in normalized
    assert "Do not pair a two-second exposure with a tiny three-centimeter trail" in normalized
    assert "Do not use camera flash to freeze distant rain or a crowd" in normalized
    assert "Claim sharpness only within depth of field" in normalized
    assert "airborne immediately after its owner releases or throws it" in normalized
    assert "An airborne garment is not worn, held, or placed elsewhere" in normalized
    assert "show that hand open immediately after release" in normalized
    assert "Repeat the same owner and same releasing hand" in normalized
    assert "The garment owner must be the person who releases it" in normalized
    assert "may not simultaneously grip a partner, brace on a surface" in normalized
    assert "A panning camera is not locked off" in normalized
    assert "a lean, facial reaction, braced stationary act" in normalized
    assert "Every stationary background object and stationary background adult streaks opposite" in normalized
    assert "Do not claim that fixed architecture blurs while stationary extras" in normalized
    assert "Hardcore motion must be visually consequential" in normalized
    assert "a free hand may release a shirt, blouse, scarf, stocking, jacket" in normalized
    assert "dense informed adult extra crowd follows ordinary routes" in normalized
    assert "Do not reduce Hardcore motion to a distant train" in normalized
    assert "only when removing that item is a natural current part of undressing" in normalized
    assert "Do not add rain, a bucket, thrown liquid, a fan, loose paper" in normalized
    assert "must be visibly moved clear of that exact junction" in normalized
    assert "Never show penetration through intact, normally worn" in normalized
    assert "If a skirt is fastened and worn at normal height" in normalized
    assert '"fully visible externally," "entire visible length,"' in normalized
    assert "A fully nude adult still has a complete removed-clothing inventory" in normalized
    assert "kneeling footwear may contact through toes, uppers, or side edges" in normalized
    assert "glasses cannot be both on the face or head and described as removed" in normalized
    assert "Count physical emitting fixtures, not lighting roles" in normalized
    assert "A bank of four uplights counts as four sources" in normalized
    assert "BACKGROUND POPULATION LEDGER" in brief
    assert "Every Theme and Frame must explicitly state the background population" in normalized
    assert "private, residential, secured, closed, or after-hours location" in normalized
    assert "quiet public location: two to five background adults" in normalized
    assert "ordinarily active public location: six to fifteen background adults" in normalized
    assert "sixteen to thirty background adults" in normalized
    assert "A normally operating public place must look inhabited" in normalized
    assert "A Beijing subway platform, high-speed rail concourse" in normalized
    assert "must never be empty" in normalized
    assert "Do not write a deserted Beijing public location" in normalized
    assert "informed, consenting adult extra" in normalized
    assert "closed to the public and operating as a controlled adult film set" in normalized
    assert "within the first one hundred English words" in normalized
    assert "closure to ordinary public access" in normalized
    assert "informed consenting adult extras is invalid" in normalized
    assert "Render no legible sign, label, advertisement" in normalized
    assert "LIGHTING LEDGER" in brief
    assert "exact number of active light sources" in normalized
    assert "exact position and height relative to the primary subjects" in normalized
    assert "approximate color temperature or precise hue" in normalized
    assert "apparent size, hardness or diffusion, relative intensity" in normalized
    assert "which source is the key, fill, rim, background practical" in normalized
    assert "resulting catchlight shape and position" in normalized
    assert "shadow direction, edge hardness, density" in normalized
    assert "Use a short-duration flash to freeze a moving primary subject" in normalized
    assert "A continuous key may resolve the primary cast without blur only when" in normalized
    assert "Ambient light accumulated during the slow shutter records the selected motion carrier" in normalized
    assert "Keep one Theme's exact location, architectural identity" in normalized
    assert "completely self-contained prompt for isolated rendering" in normalized
    assert "Silently reject and rewrite any Frame that fails" in normalized


def test_motion_blur_photography_locks_cast_and_physical_motion() -> None:
    brief = (
        REPOSITORY_ROOT
        / "story-inputs"
        / "motion-blur-photography.txt"
    ).read_text(encoding="utf-8")
    normalized = " ".join(brief.split())

    assert brief.startswith("BRIEF\n\n")
    assert "HIGHEST PRIORITY" in brief
    assert "every moving element must be a necessary result" in normalized
    assert "Never add a carrier, prop, person, light, or gesture" in normalized
    assert "If the stated camera settings could not produce the described final image" in normalized
    assert "one self-contained English paragraph of at least 700 words" in normalized
    assert "Target 850-1200 words" in normalized
    assert "short subject-verb-object clauses joined by semicolons" in normalized
    assert "Theme count, Frame count, female count, male count" in normalized
    assert "requested primary count" in normalized
    assert "unmistakably mature adults aged 25 or older" in normalized
    assert "MULTI-ADULT ROLE AND DEPTH TOPOLOGY" in brief
    assert "When more than two primary adults are requested, build a private role ledger" in normalized
    assert "record one current explicit role, exact partner or partners" in normalized
    assert "every requested primary adult must directly perform or receive a named explicit act" in normalized
    assert "does not by itself satisfy that role" in normalized
    assert "For three adults, use one connected explicit-contact topology" in normalized
    assert "For four or more adults, use either one connected topology or clearly separated explicit pairs" in normalized
    assert "no primary adult is an assistant, spectator, or support-only participant" in normalized
    assert "One anatomical part contacts only one receiving boundary" in normalized
    assert "name left-to-right and near-to-far order" in normalized
    assert "Place all required faces and decisive boundaries within the declared subject-depth slab" in normalized
    assert "Do not place one pair meters behind another" in normalized
    assert "For three or more adults, normally use a 35-50mm lens" in normalized
    assert "Flash freezes motion; it never expands depth of field" in normalized

    assert "PRIMARY ADULT DOSSIER" in brief
    assert "exact age and height in centimeters" in normalized
    assert "natural breast size, shape, projection" in normalized
    assert "face shape; brow, eyes and color, nose, cheeks" in normalized
    assert "exact skin color and undertone" in normalized
    assert "one precise expression using gaze target" in normalized
    assert "WARDROBE AND ITEM STATE" in brief
    assert "one complete footwear pair" in normalized
    assert "at least one non-jewelry signature item" in normalized
    assert "Give every inventory item its own exact visible color" in normalized
    assert "name base color, secondary color, trim, and pattern placement" in normalized
    assert "name upper, sole, heel, hardware, and lace or strap colors" in normalized
    assert "For jewelry, name metal color, gemstone color, and finish" in normalized
    assert "For glasses or sunglasses, name frame, temple, hardware, and lens colors" in normalized
    assert "For a scarf, name ground color, motif colors, border color, and weave sheen" in normalized
    assert "Carry these colors unchanged through worn, displaced, removed, held, and airborne states" in normalized
    assert "Never use matching, coordinated, dark, light, neutral, colorful, metallic" in normalized
    assert "Every item has exactly one visible current state" in normalized
    assert "A nude adult still has a complete removed-clothing" in normalized
    assert "Removed clothing must look recently and naturally discarded" in normalized
    assert "not folded or art-directed for display" in normalized
    assert "Give each item an exact footprint, orientation, gravity-supported shape, wrinkles" in normalized
    assert "Limited partial overlap is allowed only when every participating item" in normalized
    assert "Never default to neatly folded, laid flat, stacked, aligned" in normalized
    assert "Shoes need not form a tidy pair" in normalized
    assert "Organized packing is allowed only when it is the visible current activity" in normalized
    assert "One hand performs one task" in normalized

    assert "ONE NECESSARY MOTION SYSTEM" in brief
    assert "Natural fit outranks variety" in normalized
    assert "If deleting the carrier leaves the activity unchanged" in normalized
    assert "Do not combine carrier classes" in normalized
    assert "Never pair an action-caused carrier with an independent environmental carrier" in normalized
    assert "SUBJECT MOTION BLUR" in brief
    assert "Use only for aesthetic or erotic content, not Hardcore" in normalized
    assert "FLASH-FROZEN ACTION PEAK" in brief
    assert "its owner has just finished removing that same garment" in normalized
    assert "Do not add a scarf, shirt, jacket, underwear, or stocking solely so it can fly" in normalized
    assert "Do not use required signature glasses, sunglasses, or a silk scarf as the airborne item" in normalized
    assert "exposing only the neck, collarbone, or an accessory position is insufficient" in normalized
    assert "Show that person's release as a visible current action in the same image" in normalized
    assert "The carrier trail starts at that hand" in normalized
    assert "If no primary adult visibly releases the garment, nothing is airborne" in normalized
    assert "Never imply an unseen throw, an off-camera releaser" in normalized
    assert "one unbroken visible causal chain from hand to trail to frozen garment" in normalized
    assert "without an unexplained clear-air gap" in normalized
    assert "A short trail cannot explain an object much farther from the hand" in normalized
    assert "must use real side ties, side snaps" in normalized
    assert "Never pull ordinary closed-loop underwear over occupied legs" in normalized
    assert "must have cleared the exact anatomy, contact, or support boundary" in normalized
    assert "Removing an upper garment merely to expose the torso during lower-body contact does not qualify" in normalized
    assert "Never throw a filled bucket, ten liters of water" in normalized
    assert "prefer installed showerheads, faucets, or tub spouts" in normalized
    assert "Do not add a portable pitcher, bucket, or floating ceramic vessel" in normalized
    assert "STILL ANCHOR, MOVING WORLD" in brief
    assert "Do not give them handheld objects or choreographed gestures" in normalized
    assert "one single-file line cannot fill a wide area" in normalized
    assert "rather than merging incompatible places" in normalized
    assert "roughly 30-70 percent of the frame" in normalized

    assert "SCENE GENERATION AND DIVERSITY" in brief
    assert "Build the scene before choosing the motion carrier" in normalized
    assert "generative constraints, not a location menu" in normalized
    assert "maximize meaningful setting diversity" in normalized
    assert "Avoid the same family in adjacent Themes" in normalized
    assert "Never assign location categories to fixed Theme IDs" in normalized
    assert "Natural fit still outranks diversity" in normalized
    assert "Plan the complete Theme batch before writing individual Themes" in normalized
    assert "For every pair of Themes, make at least three of these materially different" in normalized
    assert "Multiple rooms inside ordinary private residences remain one residential family" in normalized
    assert "Do not repeat that family while another physically credible setting family remains unused" in normalized
    assert "location was selected merely to host a convenient blur effect" in normalized
    assert "SCENE AND MECHANICS" in brief
    assert "Scene loop: location, operating state, time, weather" in normalized
    assert "Mechanics loop: force has a visible source" in normalized
    assert "Wet support requires visible non-slip texture" in normalized
    assert "Keep every decisive contact boundary above opaque or agitated water" in normalized
    assert "CAMERA, EXPOSURE, AND RECORDED RESULT" in brief
    assert "Capture technique is non-rendered metadata, never visible scene content" in normalized
    assert "Describe the complete visible scene first" in normalized
    assert "use one compact method sentence explaining only how the image was made" in normalized
    assert "Captured from a [height], [distance], [azimuth], [pitch] viewpoint" in normalized
    assert "no capture apparatus is visible" in normalized
    assert "Never give the capturing apparatus a visible location, material, support" in normalized
    assert "do not write camera body, camera mounted, tripod, gimbal, flash head" in normalized
    assert "Explain the viewpoint and incoming light, not where hardware stands" in normalized
    assert "A closed production does not justify production gear in the image" in normalized
    assert "State one exact virtual viewpoint for every Frame" in normalized
    assert "sensor height above the supporting floor" in normalized
    assert "distance to the nearest primary, horizontal azimuth around the cast" in normalized
    assert "landscape or portrait orientation, lens-axis target" in normalized
    assert "This describes image geometry, not a visible object" in normalized
    assert "motion origin, complete visible carrier path, and landing or destination zone" in normalized
    assert "Avoid foreshortening that collapses the hand-to-carrier distance" in normalized
    assert "invisible viewpoint must correspond to a real, safe, accessible volume" in normalized
    assert "stable support surface outside the frame" in normalized
    assert "A locked camera is locked relative to one declared reference frame" in normalized
    assert "unseen capture system safely to that same structure so subject distance and framing stay constant" in normalized
    assert "an external stationary viewpoint records the cast translating" in normalized
    assert "focal length, orientation, and crop must geometrically fit" in normalized
    assert "Match viewpoint to motion mode" in normalized
    assert "state pan pivot, start azimuth, end azimuth" in normalized
    assert "view the release path from a clear side or oblique angle" in normalized
    assert "compose the stable cast in one dominant depth layer" in normalized
    assert "do not default every image to a front-facing camera at standing eye level" in normalized
    assert "Shutter time and flash duration are different" in normalized
    assert "plausible t.1 flash duration around 1/2000 to 1/10000 second" in normalized
    assert "at least three stops below flash exposure" in normalized
    assert "A tripod prevents camera shake; it does not freeze people" in normalized
    assert "At shutter times slower than 1/4 second" in normalized
    assert "a still-anchor shutter slower than 1/4 second must use a short flash" in normalized
    assert "Without that flash, cap the shutter at 1/4 second" in normalized
    assert "First-curtain flash puts the crisp image at the beginning" in normalized
    assert "Rear-curtain flash puts the crisp image at the end" in normalized
    assert "A stationary lamp reflected on a stationary floor does not streak" in normalized
    assert "In STILL ANCHOR, every primary adult holds the single stated pose" in normalized
    assert "Do not use rocking, grinding, thrusting, pumping, bouncing" in normalized
    assert "only the selected environmental carrier moves" in normalized
    assert "Claim sharpness only inside plausible depth of field" in normalized
    assert "Use a large aperture and visibly shallow depth of field as the default visual language" in normalized
    assert "prefer roughly f/1.4-f/2.8" in normalized
    assert "use f/3.2-f/4 only when the necessary subject planes cannot otherwise remain readable" in normalized
    assert "Do not default to f/5.6, f/8, or deeper focus" in normalized
    assert "state the required neutral-density filtration" in normalized
    assert "Every Frame must state one shallow depth-of-field design" in normalized
    assert "name the exact focal plane, the nearest and farthest acceptably sharp subject features" in normalized
    assert "Make the nearest primary eye or shared face plane critically sharp" in normalized
    assert "it may enter a gentle focus transition rather than being falsely called tack-sharp" in normalized
    assert "At least one substantial foreground or background plane is strongly optically soft" in normalized
    assert "Describe optical defocus separately from carrier motion" in normalized
    assert "Depth of field must actively stage the motion result" in normalized
    assert "put the tracked nearest-eye or face plane at focus" in normalized
    assert "keep the release hand, trajectory origin, and frozen carrier position on or very near the focal plane" in normalized
    assert "The environmental carrier may sit well outside the depth of field" in normalized
    assert "Never call an out-of-focus environmental carrier crisp" in normalized
    assert "State the camera-to-carrier distance and compare it with the declared near and far depth-of-field limits" in normalized
    assert "An action carrier advertised as flash-frozen must intersect the acceptable focus range" in normalized
    assert "described as optically soft directional motion, never as sharply resolved structure" in normalized
    assert "sensor whose entire width is about 36 millimeters" in normalized

    assert "LIGHTING" in brief
    assert "For visible practical scene lights, state the exact number of real emitting fixtures" in normalized
    assert "A bank of four lamps counts as four sources" in normalized
    assert "Describe non-rendered capture illumination only as incoming light" in normalized
    assert "broad or narrow illumination pattern" in normalized
    assert "Do not name or locate hardware, a modifier, or an equivalent device" in normalized
    assert "Visible practical emitters belong to the environment; capture illumination does not" in normalized
    assert "BACKGROUND POPULATION" in brief
    assert "A normally operating public place in Beijing or any other stated city" in normalized
    assert "closed, access-controlled production" in normalized
    assert "CONTENT LEVEL" in brief
    assert "Separate Erotic from Hardcore by the visible action boundary" in normalized
    assert "Full nudity can be Erotic; partial clothing can be Hardcore" in normalized
    assert "make the adult sexual charge unmistakable and high intensity" in normalized
    assert "Erotic may use coherent provocative clothing, partial nudity, or full nudity" in normalized
    assert "The boundary is the depicted action, not clothing coverage" in normalized
    assert "Hardcore uses only FLASH-FROZEN ACTION PEAK or STILL ANCHOR" in normalized
    assert "An explicit act already in progress is mandatory" in normalized
    assert "does not qualify as Hardcore" in normalized
    assert "Undressing before a future act, preparing access, approaching anatomy" in normalized
    assert "must depict the explicit contact now, not merely promise it" in normalized
    assert "Do not enforce a clothing quota or clothing default at Hardcore level" in normalized
    assert "Choose full nudity, partial dress, or active undressing solely from the scene" in normalized
    assert "Do not add garments to soften Hardcore content or distinguish it from Erotic" in normalized
    assert "at least 75 percent of Themes" not in normalized
    assert "at most 25 percent may make all primary adults nude" not in normalized
    assert "THEMES AND FINAL AUDIT" in brief
    assert "Reject a Theme before generating any Frame" in normalized
    assert "title, premise, and style all name the same single mode and carrier" in normalized
    assert "reject the Theme unless its premise states the explicit act as current contact" in normalized
    assert "reject the Theme unless every adult has a named direct explicit role" in normalized
    assert "Reject any Theme whose wardrobe inventory uses a pile, heap, bundle, scattered items" in normalized
    assert "neatly folded garments, display-like alignment, unexplained overlap" in normalized
    assert "Reject a Theme style when a still-anchor shutter slower than 1/4 second omits the required short flash" in normalized
    assert "defaults to f/5.6 or a smaller aperture without a concrete focus-geometry reason" in normalized
    assert "flash-frozen carrier falls wholly outside its declared depth-of-field limits" in normalized
    assert "out-of-focus environmental carrier is called crisp" in normalized
    assert "The title names one motion idea, not \"X and Y,\"" in normalized
    assert "For a FLASH-FROZEN Theme" in normalized
    assert "For a STILL ANCHOR Theme" in normalized
    assert "Every secondary route, weather effect, fluid system, powered system" in normalized
    assert "Do not mix a private interior with an ordinarily operating public exterior" in normalized
    assert "Do not call a constructed replica functioning public infrastructure" in normalized
    assert "scene loop and mechanics loop pass ordinary-life logic" in normalized
    assert "Finally search the draft for pile, heap, bundle, scattered" in normalized
    assert "For removed-item placement, also search for neatly folded, folded into a rectangle" in normalized
    assert "Do not reject a waistband folded over itself" in normalized
    assert "those are physical post-removal shapes, not organized storage" in normalized
    assert "Silently reject and rewrite any Frame that fails one check" in normalized
