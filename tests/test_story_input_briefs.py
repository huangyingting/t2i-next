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
    assert "normal-human-sized adult woman/man visitor" in normalized
    assert "giant-country native giant woman/man" in normalized
    assert "不得写成天生微型种族、玩偶、模型、克隆人或儿童" in normalized
    assert "巨人不得拥有年轻、健美、无瑕或模特化的完美身材" in normalized
    assert "肥胖并有自然腹部与皮肤褶皱" in normalized
    assert "苍老并有皱纹、松弛皮肤与老年斑" in normalized
    assert "瘦削并有突出的锁骨、肋骨与关节" in normalized
    assert "疤痕、静脉、妊娠纹、色斑和左右轻微不对称" in normalized
    assert "同一 Theme 全部 Frame 固定年龄层、体型和皮肤特征" in normalized
    assert "身体层" in normalized
    assert "物件层" in normalized
    assert "所有属于巨人国原住民、巨人国建筑或当地环境的可见物件都必须远大于正常人类" in normalized
    assert "英文名称前必须明确写“giant-scale”或“colossal giant-country”" in normalized
    assert "禁止只写普通 cup、chair、door、rope、lever、bucket 或 platform" in normalized
    assert "必须明确写“visitor-scale”" in normalized
    assert "不得把巨人国原生物件误写成 visitor-scale" in normalized
    assert "环境层" in normalized
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
    assert "占幅层" in normalized
    assert "同一清晰焦平面同时出现四层证据" in normalized
    assert "至少一件巨人国日用品" in normalized
    assert "至少一个巨人国环境参照" in normalized
    assert "巨人从骨盆到胸腹或大腿的连续身体必须跨越多个巨人国功能区" in normalized
    assert "完整访客仍只占巨大手掌附近的小区域" in normalized
    assert "each complete visitor is visibly smaller than the giant's thumbnail" in normalized
    assert "不得把这条尺度关系延迟到第二句或后文" in normalized
    assert "完整身高小于巨人的一枚拇指甲" in normalized
    assert "整名访客可直立在巨人拇指甲表面且头脚四周仍留出清楚可见的甲面边框" in normalized
    assert "访客头部小于巨人拇指甲根部的半月痕" in normalized
    assert "禁止退回一根手指高、掌心大小、玩偶大小、膝高或腰高" in normalized
    assert "巨人的一只眼睛、鼻孔或嘴唇单独所占画面面积远大于每名访客的完整身体" in normalized
    assert "不得把访客放在前景单独放大" in normalized
    assert "访客面部不得以近景尺寸接近巨人面部" in normalized
    assert "张开的巨大手掌" in normalized
    assert "不能用一方贴近镜头制造假差距" in normalized
    assert "张开的巨大手掌只作为接触点旁的同焦平面尺寸参照" in normalized
    assert "访客继续站、跪、坐或躺在唯一动作支撑面上" in normalized
    assert "不得同时写访客站在手掌、装置平台和接触点" in normalized
    assert "禁止用 three times、twice、several times 等偏弱数字倍率" in normalized
    assert "不能只靠巨人与访客并排证明渺小" in normalized
    assert "每名访客必须从头顶到双脚全身可见" in normalized
    assert "完整位于巨人身体外部" in normalized
    assert "访客的头部、胸廓、腹部和骨盆四周" in normalized
    assert "可见空气、背景空隙或刚性平台边界" in normalized
    assert "除一个明确命名的局部接触面外" in normalized
    assert "禁止整名访客横跨、趴伏或贴伏在巨人的胸部、腹部、阴阜、骨盆或大腿表面" in normalized
    assert "访客只能从与巨人皮肤分离的刚性平台操作装置" in normalized
    assert "只有装置末端或访客的一只手或一只脚可以到达接触点" in normalized
    assert "访客的头、脸、颈、胸部、腹部和骨盆绝不接触巨人身体" in normalized
    assert "a visible air gap separates the visitor's head, torso, abdomen, and pelvis from the giant's skin" in normalized
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
    assert "只写“continuous with the pelvis”不算定位完成" in normalized
    assert "禁止用 lower surface、one side、lower rim" in normalized
    assert "必须以巨人的耻骨、下腹、会阴、臀沟或大腿为参照" in normalized
    assert "全部性行为只发生在一个或多个正常人类访客" in normalized
    assert "与唯一巨人国原住民之间" in normalized
    assert "大量且清晰可见的精液、尿液喷射、阴道液体或灌肠喷射" in normalized
    assert "自愿 BDSM 系统" in normalized
    assert "把胸部与胸廓安全束带改成秋千、摩天轮、索道或弹射台" in normalized
    assert "不得把乳头、阴毛或柔软组织作为唯一锚点" in normalized
    assert "显示自然阴毛及其与皮肤、骨盆的连续边界" in normalized
    assert "所有人物都必须穿衣或半裸露，不得全身裸体" in normalized
    assert "巨人国原住民穿着两至四件符合场景的正常衣物及一件配饰" in normalized
    assert "只局部打开、卷起、移开或解开当前动作所需区域" in normalized
    assert "正常人类访客保持从头到脚的完整服装设计" in normalized
    assert "必须真实可穿、与维护良好的环境一致" in normalized
    assert "衣物不得遮住接触点、身体定位地标、完整访客" in normalized
    assert "所有人物都要有可辨认且完整的人物造型" in normalized
    assert "每人固定发型、妆容、服装轮廓、两种主色、两种真实材质" in normalized
    assert "鞋履及一件配饰" in normalized
    assert "妆容须像真人摄影可见的实际化妆" in normalized
    assert "肤色处理、眼妆、唇色或指甲中的两项" in normalized
    assert "每人拥有与角色一致且彼此不同的表情和神情" in normalized
    assert "明确视线目标、眉眼、嘴唇、面颊潮红或肌肉张力" in normalized
    assert "不得所有人共享同一微笑、呆滞脸、闭眼" in normalized
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
    assert "不可变的 S2–S5 subject block" in normalized
    assert "把该 block 逐字复制到两个 Frame" in normalized
    assert "不得为第二个机位重新生成同义词、左右侧、尺度物件" in normalized
    assert "严格按以下物理句序写，任何顺序变化都重写" in normalized
    assert "S1 CAST + EARLY SCALE + MECHANISM + CAMERA" in normalized
    assert "必须逐字套用以下单句骨架" in normalized
    assert "while the separated visitor operates [colossal giant-country urban Signature Mechanism]" in normalized
    assert "from [visitor-scale rigid support]" in normalized
    assert "在 perspective 之前不得出现句号或分号" in normalized
    assert "年龄、体型、背景空隙和造型全部后移" in normalized
    assert "S2 TARGET MAP" in normalized
    assert "S3 FOUR SCALE PROOFS" in normalized
    assert "Four simultaneous scale proofs share one clear focal plane:" in normalized
    assert "the visitor's complete body is smaller than the giant's thumbnail" in normalized
    assert "the visitor stands entirely inside the thumbnail with a visible nail border on every side" in normalized
    assert "the visitor's head is smaller than the thumbnail crescent" in normalized
    assert "逐字粘贴“the giant's open palm”" in normalized
    assert "不得在 open 与 palm 之间插入 left、right 或其他词" in normalized
    assert "S4 CHARACTER DESIGN" in normalized
    assert "包含所有人物造型的一整个物理句子" in normalized
    assert "在最后一人写完前不得出现句号" in normalized
    assert "S5 POSE AND ACTION" in normalized
    assert "包含所有人物姿势的一整个物理句子" in normalized
    assert "该手只能保持张开作尺度参照" in normalized
    assert "物理第一句必须点名具体 real-world urban setting" in normalized
    assert "第一句不得提前结束" in normalized
    assert "不得插入年龄、体型、背景空隙、人物造型、妆容或详细姿势" in normalized
    assert "紧接句号后的物理第二句必须以" in normalized
    assert "任何人物介绍、服装、妆容、机制解释或环境句都不得出现在它之前" in normalized
    assert "live-action photorealistic location photography captured with a real 20–32 mm wide-angle camera" in normalized
    assert "不得凭记忆改写为 photorealistic fantasy、20-32mm、20–32mm、wide-angle lens" in normalized
    assert "previous frame, same, identical, unchanged, still, again, now, remains" in normalized
    assert "输出前按句号切分并确认 S2 以 The single 开头" in normalized
    assert "S3 以 Four simultaneous scale proofs 开头" in normalized
    assert "NEVER OUTPUT THESE TOKENS IN ANY CONTEXT" in normalized
    assert "最终逐词扫描并替换：same 改为 shared 或直接删除" in normalized
    assert "S4 包含所有人物造型、S5 包含所有人物姿势" in normalized
    assert "只允许英文 ASCII 字母、阿拉伯数字和英文标点" in normalized
    assert "逐字符删除中文、日文、韩文及孤立 CJK 字符" in normalized
    assert "The camera uses an environment-scale wide establishing shot" in normalized
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
    assert "普通公寓墙面、街道路灯、停车楼梁架、地铁立柱、脚手架或港口设施" in normalized
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

    assert "Use exactly one human protagonist and no other human figure." in brief
    assert "either one woman and zero men or zero women and one man" in normalized
    assert "The protagonist remains fully human." in brief
    assert "Include one to three furry beings." in brief
    assert "alert, intelligent, speaking or clearly reasoning adult" in normalized
    assert "photographed adult performer" in normalized
    assert "physically present cinematic creature" in normalized
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
    assert "T001: one public-domain Journey to the West figure" in normalized
    assert "T002: one of the Eight Immortals" in normalized
    assert "T003: one completely original high-fantasy furry adult" in normalized
    assert "T004: one traditional angel, demon" in normalized
    assert "T006: one completely original heroic" in normalized
    assert "visible, consequential decision that has already taken effect" in normalized
    assert 'Never write "must choose," "must decide,"' in normalized
    assert "End every Theme premise with two concise proof clauses" in normalized
    assert '"Decision: [protagonist name]' in normalized
    assert "The premise must end after the Immediate response clause." in brief
    assert "Put the visual style only in the separate Theme style value." in normalized
    assert "Begin every Frame by independently naming the precise location" in normalized
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
