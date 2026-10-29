# dsh-novel 插件内置网文写作方法论 · 可迁移笔记

> 对象：`G:\txt\.plugin-stage\dsh-novel`（作者 ddedook）。纯静态阅读，未安装、未执行、未修改仓库。
> 全部结论均来自 `seed\skills\`、`seed\templates\` 与 `src\novel\` 中实际读到的文字，引用处标注来源文件名。

---

## 一、这套方法论的骨架：实体、字段、写入顺序

它把一部网文拆成 **1 个概述 + 13 个实体域**（`src\novel\domains.ts` 的 `ENTITY_DOMAINS`）：`role`、`roleRelation`、`roleTimeline`、`creature`、`creatureTimeline`、`item`、`itemTimeline`、`level`、`world`、`worldTimeline`、`timeline`、`outline`、`chapter`。概述不进实体表，落在 `novels.blueprint_json`（`src\novel\schema.ts`）。

三个贯穿全局的字段习惯（`seed\skills\chapter\章节数据维护.md`、`src\novel\normalize-entity.ts`）：

- **模板字段写顶层**：先 `get_template`，把 key 直接写在实体根上，**不要**包进 `profile`。
- **身份＝序号 + 短名**：卷/章只填 `ordinal` + `name`，"第1章"由界面拼；`name` 里的"第1章/第一章"前缀会被剥掉，**禁止**把章号写进 `name`，也**禁止**用 `volumeNo`/`chapterNo` 做主键。
- **引用按姓名解析**：`faction`、`parentName`、`relatedOutlineName`、关系边两端都可用名字；解析失败直接报错，不静默丢层级。

| 实体 / 概述 | 关键字段 | 谁写 | 谁审 |
|---|---|---|---|
| 概述 blueprint | `genre` `tone` `coreConflict` `motivation` `theme` `targetAudience` `styleReference` `narrativePerspective` `chapterCountPlan` `chapterWordTarget` `specialRequirements` | 卖点与定位 / 开书种子 / 标题创作 | 大纲审查·主轴与承诺 |
| `world` | `name` + `kind`（universe/continent/city/faction/sect…）+ `parentId` + 四栏 `geography`/`culture`/`history`/`factions` | 世界规则、势力与地图 | 大纲审查·设定一致性 |
| `role` | 模板 `detailFields` 顶层 key：`roleType` `faction` `longTermGoal` `shortTermGoal` `weaknesses` `arcInitial/arcTurning/arcFinal` `memoryAnchors` `oocBoundaries` `foreshadowingTags` | 角色档案、人物塑造 | 大纲审查·主角弧线；章节审查·连续性 |
| `roleRelation` | 一条有向边：`roleId`/`targetRoleId`（或 from/to 姓名）+ `relationType` + 非空 `content` | 关系与配角 | 章节审查·连续性 |
| `roleTimeline` | `roleId\|roleName` + `timeLabel` + 整数 `timePoint` + `content` | 状态同步 | 章节审查·数据维护 |
| `level` | `system.name` / `category` / `description` / `levels[]`（`name` `promotionCondition` `abilities` `subLevels` `lifespan`） | 能力与代价、成长与爽点 | 大纲审查·设定一致性 |
| `timeline` | `title` + `content` + `timeLabel` + 整数 `timePoint` + `eventType`(plot/conflict/suspense/foreshadow/turning/resolution/other) + `isResolved` + `resolveChapterNo` + `relatedChapterNo` | 事件轴规划、伏笔账本 | 大纲审查·前后呼应 |
| `item` / `itemTimeline` | `name` 唯一 + `owner`（**人物名字符串**）+ `type`/`grade`/`origin`/`effect`/`appearance`；履历 = `itemId\|itemName` + `timeLabel` + `timePoint` + `content` | 物品档案要素、流转与归属 | 章节审查·数据维护 |
| `creature` / `creatureTimeline` | `name` 唯一 + 库表标量 `kind`(animal/beast/plant/spirit/other) + `owner` + `habitat`/`habit`/`ability`/`dangerLevel`；履历同上 | 生物档案要素、异兽与灵植 | 同上 |
| `outline`（卷 / 章） | 卷：`kind=volume` + `ordinal` + `name`；章：`kind=chapter_segment` + `parentId`/`parentName`。两者都写 `theme`/`conflict`/`majorEvents`（顶层或 `extra`，会被升到顶层）+ `content`＝走向 + 章末（卷末）期待 | 结构与卷章模板、剧情骨架流水线 | 大纲审查（`submitOutlineReview`） |
| `chapter` | `ordinal` + `name` + `content`（正文）+ `relatedOutlineId`/`relatedOutlineName` | 章节节奏、对话与情绪、去 AI 味 | 章节审查（`submitChapterReview`） |

**写入顺序与域边界**（`seed\skills\outline\剧情骨架流水线.md`、`seed\skills\outline\结构与卷章模板.md`、`src\novel\host-skills.ts`）：

1. **开书设定**：概述 blueprint → 世界（先父后子） → 人物顶层字段 → `roleRelation` → `level.system` → 全书 `timeline` 关键事件（伏笔/冲突/悬念必须带 `eventType` + `isResolved`）。此步**禁止** mutate `outline` / `chapter`。
2. **大纲步**：只写 `domain=outline` 的卷/章节点；**禁止**顺带 mutate 人物、生物、物品、世界、时间线、章节（缺设定留到对应工作区）。
3. **正文步**：读对应章合同 → 写正文 → 写 `chapter` → 用 `mutate_entities` 同步本章引起的各域设定变更。
4. 依赖方向是单向的：level / world / role 是 outline 的前置输入；`outline` + 各设定域是 `chapter` 的前置输入。审查者只判定、不改稿（`seed\skills\review\outline\大纲审查.md` 的「角色」节）。

---

## 二、黄金三章的验收标准

「留人义务」的定义（`seed\skills\outline\黄金三章与验收.md`）：**承诺 → 加压 → 早期兑现 → 打开长线**。验收看这套义务是否兑现，而不是看设定文档有多厚——"不因文档不够厚继续扩设定；能写黄金三章即可开工"。

逐章必须交付：

| 章 | 必须交付 | 读者应感到 |
|---|---|---|
| 第 1 章 | 立住主角、问题、即时张力、钩子；写入 theme / conflict / majorEvents / content | 开篇承诺清晰，想继续看 |
| 第 2 章 | 升级矛盾，或揭示能力/约束边界 | 压力上来，或规则边界可见 |
| 第 3 章 | 早期兑现（小翻盘 / 揭秘 / 关系进展）+ 打开下一长线问题 | 有收获，且知道后头更大 |

**保存前验收清单（9 条）**：类型与读者预期一致；一句话主轴可售；剧情骨架无自相矛盾；卖点与阶段目标对齐；主角/关键配角动机可读；世界观仅含约束行动的部分；第 1–3 章节点字段齐且可写（能支撑净变化与章末期待）；第 3 章后长线问题已打开；阻塞写作的待确认问题已列出。

**写入硬要求**：三章均有具体 `conflict` 与有序 `majorEvents`、`content` 含章末期待；待确认问题**仅列阻塞项**。

**禁忌**：第 1 章纯日常无压力；第 3 章仍无任何兑现；字段齐全但读感劝退（无承诺、无兑现、无长线开口）；未合并种子/卖点/人设输入就宣称大纲完成；写作侧自行宣布"通过/放行"。题材级加码：仙侠"每卷至少一个渡劫或近死破境"、历史"每卷一次公开评价逆转"、末世"每卷一个可说清的生存目标"。

---

## 三、爽点与升级的工程化写法

**爽点循环**（`seed\skills\level\成长与爽点.md`）：`压力 → 能力触发 → 选择 → 兑现 → 更大压力`；短循环＝章内或数章内小兑现，中循环＝小卷/阶段大兑现。**避免同质打脸的三换法**：换对手类型、换代价、换舞台。都市题材的落地版同型："压力 → 触发 → 选择 → 兑现 → 新问题扩大"。

**阶段递升判据**：资源价值、敌人层级、认知反转、影响范围**至少升一项**。每阶段写清：可检验的目标、主要对手量级、关键资源/门槛（对应 `promotionCondition`）、兑现形式（突破/打脸/夺宝/身份跃迁/经营成果）、阶段末钩子（新地图/新敌/规则反噬）；长篇还须标出**中盘局势改写点**与**无法退回日常的节点**。

**越级的条件**：策略、代价、信息差或环境，**而非无脑数值碾压**；战斗要有策略、代价、误判、底牌。

**与等级体系的绑定**：阶段目标必须能映射到 `system.levels` 的升阶，**每升一级要有新玩法或新限制**（写在 `abilities` / `promotionCondition`），而非只加数值；多体系并存时用体系 `name` 区分人物境界 vs 物品品阶，并写清动的是哪条阶梯。写库风险：**传入完整 `levels` 会替换该体系旧阶梯**，勿只改一级却丢其余级。

**能力设计七问**（同上）：核心能力（能/不能解决什么）、获取、限制（触发/消耗/冷却/暴露风险）、代价（身体/资源/关系/道德/时间/污染）、反制（同类克制/信息差/环境/规则漏洞）、成长路径、每级的门槛与能力增量。判据：金手指不能替主角跳过关键成长与选择；敌人须有可见反制或误判空间。

**禁忌**：反复碾压同级杂兵无递升；升级后无新问题；只靠旁白宣布"变强了"；无限制无冷却无暴露风险的全能金手指；只写"突破了"而无原因代价与后续。

---

## 四、题材规则库：8 题材横向对比

每题材都有 `overview\题材规则.md`（读者期待 / 大纲重点 / 章纲正文重点 / 雷点 / 联动区块）与 `review\outline\大纲审查.md`（题材审查重点 + 雷点 + 判定提示）。

- **仙侠**：与玄幻共享升级骨架，但强调"修"的代价与**境界质变**（不只改称号）；机缘必须有代价（因果、心魔、天妒、宗门争夺），宗门/散修/魔道三角张力，每卷至少一个渡劫或近死破境，长线指向更高天域但不透支终局。雷点：纯数值仙、打怪升级无人情。
- **历史**：爽点由**信息差与制度压力**驱动，考据服务冲突；主角优势落到信息差/技术/组织/商业/军事，反派须有时代制度优势而非现代傻子，每卷一次公开评价逆转（考中/立功/破案/翻案）。雷点：考据展览、古人无脑捧杀、时代感只靠服饰名词。
- **悬疑**：核心是**三层规则**（表层 → 隐藏例外 → 真相规则）与可回溯的惩罚，线索链"误导 → 验证 → 反证 → 汇聚 → 揭示"必须对读者公平；能力只助观察试错，不能无视规则通关；卷末回收核心规则并打开更高层问题。雷点：无逻辑惊吓、结局靠新规则硬翻盘。
- **末世**：感染规则 + 物资约束下的生存、建基与人性博弈，先定爆发起因、感染规则、异能晶核边界、基地准入逻辑；每卷一个生存阶段（立足/守潮/迁徙/远征），资源变化写明弹药、食物、晶核、伤势、理智、信任。雷点：设定讲座无选择、无限开挂、各卷互不关联。
- **玄幻**：主轴唯一（复仇/登顶/救人/破局/改命择一），**四层压力**递进（同辈 → 家族宗门 → 地图势力 → 天道规则），金手指有限制，换地图带走旧伏笔/旧敌/旧情感至少一项，战斗要策略、代价、误判、底牌。雷点：同质打脸循环、设定百科先于故事。
- **科幻**：先定灾变成因、科技或异常边界、任务发布逻辑；每卷一个阶段且目标一句话可说清，资源约束、死亡条件、隐藏奖励、错误通关线齐全，团队按功能配置含背叛风险。审查特别看**技术自洽**与**尺度推进**（权限、敌我、真相层级）。雷点：设定讲座、副本互不关联。
- **言情**：先定女主现实困境（婚姻/职场/家庭/经济/身份不平等），**感情线与成长线双轴**并行，不靠脑残误会无限拖；情绪产品明确（被认可、珍视、尊重、看见），阻力来自现实逻辑（利益、面子、阶层、家庭、舆论），虐点后须反转或成长。雷点：女主长期无力、男主工具人标签。
- **都市**：现实压力（钱、考试、职场、家庭、面子）具体可见，金手指解决压力并引来更大压力；首卷主能力宜少（约 1 主 + 1 辅），微创新≤3，建现代评价体系（学校/公司/官方/榜单），地图按社区学校 → 组织城市 → 全国或超凡隐秘层递进。雷点：说明书灌水、反派现代傻子、全程装逼无评价变化。

**横向差异**被落实成字段语义（`seed\templates\`）：`type`/`grade`/`effect` 在玄幻是"血脉秘宝/品级/功效"，仙侠是"法宝飞剑/法器灵宝仙器/神通反噬"，历史是"兵器印信文书/品级规格/政治意义"，悬疑是"证物凶器文件/关键程度/证明或暗示"，言情是"信物礼物文书/情感分量/叙事作用"，末世是"物资载具晶核/稀缺度/消耗风险"；`level` 在历史是官阶品级、言情是"关系跃迁条件 + 社会资源"、悬疑是"职级代号 + 情报权限 + 暴露风险"、都市是"职级/考核门槛/权限资源"。八个模板骨架完全一致（overview/role/world/timeline/outline/item/level/creature），差异只在选项与 label 语义——**题材规则最终只落成字段语义，规则与题材审查文件并不随书加载**（见第八节）。

---

## 五、审查体系

两套审查都是"资深连载读者立场、只判定不改稿"，必须先过 **读者验收五问**，任一项明确失败即不得判 `accepted`。

**读者验收五问**（章节审查与大纲审查措辞略有差异，槽位一致）：① 开篇会不会想划走？能否一句话说清这本书/这卷在追什么？② 读完能否一句话说清"得到了什么"？前三章是否有承诺、有加压、有早期兑现？③ 有没有哪段像说明书/复读/注水？往后阶段是更刺激还是同质循环会腻？④ 对白是否像不同的人在说话且全是 `""`？随便抽一章说明能否想象成有冲突、有净变化、有章末期待的正文？⑤ 章末是否想立刻看下一章（真期待非假钩）？有没有承诺打架、伏笔悬空、设定互斥等硬伤？

**大纲审查十维**：读者验收；主轴与承诺（开篇承诺与终局一致）；设定一致性（概述/人设/世界观/level 无冲突）；阶段递升与压力（同质打脸或误会循环当主结构 → 不通过）；因果与可写性（`majorEvents` 具体、有序、可执行、章间可因果推导）；主角弧线；前后呼应（伏笔→兑现可读、卷间无断点）；高潮起伏（每卷至少一个爆发点，爽点有代价反噬）；结构与黄金三章（卷+单章说明完整、章号唯一、四字段齐）；章纲支撑正文。

**章节审查十维**：读者验收；章节职责（合同要求的事件与信息是否兑现）；读者回报（关系/信息/局势至少一项实质推进，并写清该句净变化）；主角主动性；连续性（人物硬设定、伏笔、物件归属、时间序、生物出场是否自洽，"出戏即卡"）；节奏与翻页欲；表达（去 AI 味 + **对白硬规则**：人物说出的话一律用 `""`，禁止英文直引号/「」/`()`/`[]`/`《》`/`『』` 充当对白外壳，禁止括号夹注对白或内心，违者至少 `local_patch`）；长线（结构性冲突 → `stop_for_replan`）；数据维护（漏报新人物/生物/物品/关系则不得判 `accepted`）；单章字数。

**判定表（五档，必选一）**：`accepted`（通过）/ `continue_with_warning`（记质量债，通过）/ `local_patch`（局部可修，不通过）/ `rewrite_needed`（重写关键段落，不通过）/ `stop_for_replan`（结构性冲突，不通过）。大纲审查另给严重度映射：`structural` → `stop_for_replan`，`patch` → `local_patch`/`rewrite_needed`，`debt` → `continue_with_warning`。

**字数判据**：对照概述 `chapterWordTarget`，**允许 ±15%，去空白计**；越界不得判 `accepted`/`continue_with_warning`，应判 `local_patch`（略短补写/略长删注水）或 `rewrite_needed`；未设目标则 notes 注明即可。**字数达标仍可因注水、零回报、假钩不通过**。

**伏笔账本怎么记账**（`seed\skills\world\伏笔账本.md`）：生命周期＝埋设 → 推进 → 提示 → 回收 → 后果；每个伏笔必须有状态而非只是灵感，**回收必须影响关系、规则或主线**。落库映射：伏笔 = `eventType=foreshadow`；埋设/推进 = `title` + `content`；未/已回收 = `isResolved=false/true`；回收章 = `resolveChapterNo`，关联章 = `relatedChapterNo`；冲突/悬念同用 `conflict`/`suspense` + `isResolved`（`src\novel\timeline-labels.ts` 只对这三类显示"已解决/未解决"）。写章时必须标注**新增/推进/回收/延后**并同步 timeline，无新增要明确写"本章无新增伏笔"；过期伏笔须补回收/延后/转长线/放弃并更新 `isResolved`。禁忌：大量埋而不收、回收只解释设定不改变行动、用新万能设定覆盖旧伏笔、账本只在聊天或平行 Markdown。

---

## 六、结构化建模的可迁移经验

这套库真正值钱的不是设定表，而是**用字段和校验点把"长篇必崩"的四种病变成可检查项**：

**防设定漂移**：① 状态类变更写回**正确宿主域 + 对应 `*Timeline`**，不把一切塞进一张全书时间线（`timeline\状态同步.md` 域分流表）；② 权威节点唯一——人物 `faction` **必须等于**已存在的世界节点名，`parentName` 解析成 `parentId`，"解析失败会报错，勿静默丢层级"（`world\势力与地图.md`、`normalize-entity.ts`）；③ 写入步骤隔离——大纲步只写 outline，开书步禁止碰 outline/chapter，缺设定留到对应步骤（`结构与卷章模板.md`、`host-skills.ts`）；④ 写章后必须补建正文里新出现的人物/生物/物品/关系，否则不通过（`章节数据维护.md`、章节审查维度 9）。

**防伏笔丢失**：`eventType=foreshadow` + `isResolved` + `resolveChapterNo` 三件套，配合"过期伏笔必须处置"与"禁止平行 Markdown 账本当唯一真相"——把伏笔从"作者的记忆"变成"带状态位的事件行"。

**防人物前后不一**：`memoryAnchors`（必须记住的人设事实）、`oocBoundaries`（避免 OOC）、`arcInitial`/`arcTurning`/`arcFinal`（弧线三点）、`distinctiveMarks`、`decisionStyle`、语言风格卡（用词习惯/句长/口头禅/禁忌话题/对谁说话会变），加上关系必须是**一条有向边**（`roleRelation` 带 `relationType` + 非空 `content`，禁止反向重复行）。审查侧对应"闭眼能辨声口""三人同腔 = 失败"。

**防爽点同质**：把"递升"写成四选一的硬判据（资源/敌人/认知/影响范围至少升一项），把"避免同质"写成三换法（换对手类型、换代价、换舞台），再由审查维度与题材雷点表兜底。

**易错的校验点**：`owner` 只放人物名字符串（不是 UUID/`ownerId`），附属时间线宿主用 `*Name`/`*Id`；**owner 变更 = 实体 owner + 对应 `*Timeline`，缺一不可**；`level` 整表替换的破坏性提示；`timeLabel`（展示）+ 整数 `timePoint`（排序，推荐 YYYYMMDD）双字段；"只有能影响后续决策的变化才入库"。可直接借鉴的一句：**每个易漂移的设定对象都应有"宿主域 + 履历域 + 状态位"三元组，任何变更必须同时落三处，或显式声明无变更。**

---

## 七、可直接搬进写作流程的清单

**开书写前**
- [ ] 一句话主轴（读者追什么 + 终局方向），开篇承诺与终局不打架；核心卖点 ≤3 且与 `tone`/`coreConflict` 一致
- [ ] 十秒可售（题材 + 处境 + 杠杆 + 主回报）；种子六要素齐：主角处境/开局困境/核心杠杆/主动选择/首章爆点/长篇升级暗示
- [ ] 能拆出 ≥5 个不重复剧情方向；≥三档量级不同的目标/对手/地图
- [ ] 主角动机三角（想要/害怕/信念）可追溯；关键配角按主角缺口配置
- [ ] 世界观每条规则都回答"能做什么/不能做什么/违反代价"，并写清信息公开度（读者/主角/配角/反派各知道什么）
- [ ] 等级体系每级有门槛与能力差，不是空名列表

**每章写前**
- [ ] 找出本章大纲合同：`theme` / `conflict` / `majorEvents`（有序可执行）/ `content` 的章末期待；过读者五问，预先写下"一句话净变化"
- [ ] 章首选五类手段之一（行动中开场/反常情境/震撼对话/倒计时/重大发现）；承上禁复述，用回声细节、未完成动作、物件与伤势状态承接
- [ ] 单章场景 1–3 场，每场至少推进情节/人物/信息之一；章末钩子须"改写读者对局势的理解或下一步期待"

**每章写后**
- [ ] 数据维护：人物（伤势/位置/知情范围/关系阶段/能力解锁）→ role·roleRelation·roleTimeline；世界势力 → world·worldTimeline；关键道具归属 → item·itemTimeline；生物有主战损 → creature·creatureTimeline；伏笔冲突悬念 → timeline；时间是否推进
- [ ] 伏笔标注新增/推进/回收/延后，无新增则显式声明
- [ ] 二稿顺序：列不可改事件与信息边界 → 挑 3–8 处表达簇场景化改写 → 重写成连续正文（不留初稿句序） → 按合同与五问复验；修复顺序：保爽点与事实 → 最小片段替换 → 无效再整章 → 记质量债停止死循环
- [ ] 字数落在目标 ±15%（去空白计），越界先补写/删注水；对白外壳全部为 `""`，无括号夹注内心

**每卷收尾**
- [ ] 卷末打开"下一问"；阶段递升四选一已兑现；本卷至少一个爆发/兑现点
- [ ] 换地图带走旧伏笔/旧敌/旧情感至少一项，旧冲突阶段性收束
- [ ] 题材硬指标：仙侠每卷一次渡劫或近死破境；历史每卷一次公开评价逆转；末世卷末回收阶段真相并扩大世界问题；科幻/悬疑卷末回收核心规则并打开更高层问题
- [ ] 长篇核对中盘局势改写点与"不可回头"节点是否仍然成立

---

## 八、这份仓库的方法论局限

1. **题材技能其实是"死代码"**：`seed\skills\genres\` 下 8 题材的 `题材规则.md` 与题材级 `大纲审查.md` 物理存在，但 `src\novel\seed.ts` 的 `DIR_TO_SECTION` 不含 `genres`（注释明写"genre-specific files under seed/skills/genres are not loaded"），`schema.ts` 启动时还会 `DELETE FROM novel_skills WHERE folder = '题材' OR LIKE '题材/%'`，`listSkills` 亦过滤题材目录。8 题材规则只是**人读资料，不进入运行时的写作/审查上下文**；README 与技能文本（如章节 `updateManifest`）也与其实现（`defaults.ts` 仅三条极简技能）不一致，搬运时需自行补齐"规则 → 提示词"的挂载。
2. **题材覆盖不全**：没有武侠、游戏电竞、无限流、快穿、宫斗宅斗、种田美食、校园青春、同人、双男主的独立规则；模板 `genre` 列出大量子类型却无题材级规则兜底，跨题材作品只能回落到通用审查。
3. **只有规则，没有语言资产**：全是判据与禁忌，没有台词样本库、场景句库、题材词表、意象库；文风包只 3 个且都绑定具体已完结作品，迁移题材要靠作者自己改。
4. **情绪与关系写得薄**：`对话与情绪.md` 只有"加压→误判→爆发→余波"与"少用抽象词"，`人物塑造.md` 的"展示而非讲述"只给 3 组对照例子；虐点补偿、感情线阶段门槛、群像调度、CP 张力都没有可操作模板。
5. **节奏缺量化**：爽点密度、钩子强度、章内起伏曲线都没有数值判据，唯一硬数字是 `chapterWordTarget ±15%` 与篇幅档位；"成簇才修"没给簇判定阈值；字数只按去空白计字，对短篇、女频、对话驱动章不做区分，无信息密度类替代指标。
6. **无市场验证与协作流程**：没有追读率、完读率、平台签约标准的任何数据接入；标题与卖点全是纯人工判据（"十秒可售""3–5 个候选"），不含番茄/起点/晋江等平台差异；审查者禁止改稿、写者不能自行放行，但争议仲裁、返工上限、质量债台账归谁都没写——"记质量债并停止死循环"只有倡议而无载体（`outline_draft_md`/`outline_final_md`/`outline_status` 字段存在但技能未规定用法）。

---

## 九、文件清单与字数

实际逐份读过的文件（行数）：

**仓库根**：`README.md` 149、`CHANGELOG.md` 13、`package.json` 79、`cordis.patch.yml` 3

**seed\skills\outline**：`黄金三章与验收.md` 42、`结构与卷章模板.md` 68、`剧情骨架流水线.md` 51
**seed\skills\level**：`成长与爽点.md` 44、`能力与代价.md` 42
**seed\skills\overview**：`卖点与定位.md` 52、`开书种子.md` 60、`标题创作.md` 43
**seed\skills\chapter**：`章首钩子.md` 40、`章节节奏与开头.md` 61、`对话与情绪.md` 52、`去AI味与质检.md` 34、`章节数据维护.md` 61
**seed\skills\review**：`chapter\章节审查.md` 72、`outline\大纲审查.md` 74
**seed\skills\role**：`角色档案.md` 52、`人物塑造.md` 52、`关系与配角.md` 53
**seed\skills\world**：`世界规则.md` 30、`伏笔账本.md` 44、`势力与地图.md` 52
**seed\skills\timeline**：`事件轴规划.md` 33、`状态同步.md` 41
**seed\skills\item**：`物品档案要素.md` 13、`流转与归属.md` 22
**seed\skills\creature**：`生物档案要素.md` 13、`异兽与灵植.md` 11
**seed\skills\genres**（各 `overview\题材规则.md` / `review\outline\大纲审查.md`）：仙侠 32/21、历史 32/21、悬疑 33/21、末世 33/21、玄幻 32/22、科幻 33/21、言情 31/21、都市 32/21（小计 16 份 417 行）
**seed\skills\writing-style**：`da-feng-da-geng-ren\STYLE.md` 132、`meta.json` 6；`hei-dao-da-feng\STYLE.md` 144、`meta.json` 6；`hei-dao-xie-huang\STYLE.md` 139、`meta.json` 6
**seed\templates**：`玄幻.json` 1322、`仙侠.json` 1322、`都市.json` 1318、`科幻.json` 1322、`末世.json` 1127、`言情.json` 1318、`悬疑.json` 1318、`历史.json` 1318
**src\novel**：`schema.ts` 94、`domains.ts` 67、`template-fields.ts` 145、`outline-labels.ts` 100、`tools.ts` 313、`store.ts` 390、`host-skills.ts` 159、`seed.ts` 155、`normalize-entity.ts` 152、`defaults.ts` 40、`timeline-labels.ts` 38、`http.ts` 185
**src**：`index.ts` 26

合计 **86 个文件、39,486 行**（其中 `seed\templates\` 8 份 JSON 共 10,365 行，为字段结构与选项语义逐项核对；JSON 的同一批选项在 8 个模板间大量重复，故正文只抽取差异项陈述）。仓库全部 `.md/.json/.ts/.yml` 的中文字符总量约 46,214 字，本笔记为其中方法论部分的提炼。
