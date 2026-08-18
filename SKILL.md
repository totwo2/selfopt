---
name: selfopt
slug: zhi-neng-py-jiao-ben-you-hua
displayName: 智能py脚本优化
summary: "AI 智能体自优化种子包：LLM 生成重写 + 程序把关入库，库随用户负载生长"
agent_created: true
read_when:
  - 写或优化会被反复调用的 Python 函数/脚本时
  - 想让重复劳动自动变快、变可验证
  - 维护一批域级优化模板并希望它能自我生长
  - 用 selfopt 跑完发现已知 6 域覆盖不到某类代码模式时（成长机制触发点：必须去长域，而非只报"无优化"就结束）
---

# selfopt — 自优化种子包

一个**当前就能装进 AI 智能体用、能产生实测加速、且会随用户负载自我生长**的小型优化框架。不追求大而全，只做引子。

## 三层分工

| 层 | 由谁做 | 做什么 |
|----|--------|--------|
| Layer 1 候选生成 | **LLM 智能体本身** | 读代码、识别可优化点、生成重写版本 |
| Layer 2 验证门 | `selfopt.adopt` | 按域证人集（随机+边界，含异常语义）查等价性，过不了就拒绝入库 |
| Layer 3 代价评估 | `selfopt.adopt` | 配对交替测量 + 中位数加速比 + sign-test 显著性，达标才入 `library.jsonl` |

智能体是生成器，本模块是验证器和计分器。生成可以出错，验证不能缺席——这是整套设计的第一原则。

## 数学闸门 v2（2026-08-18 升级：从"算术"到"统计"）

v2 把把关从"点估计 + 硬门槛"升级为"统计检验 + 双条件"，两个数学升级：

**等价性（堵洞1：随机证人无边界覆盖）**
- 证人 = 随机采样 + **边界样本**（空/单元素/极值/负值/重复/中文/非法输入），边界值分析：多数 bug 在边界触发
- **异常语义等价**：两者都抛同类型异常 = 等价（如对非法输入都抛 ValueError），不会误杀合法重写
- 唯一数学完备域 `sort-small-net`（2^n binary_seq 穷举）不受影响
- 实证：demo 场景1 的 join 重写在 `[]` 上旧返回 `''`、新返回 `','`，旧纯随机闸门会放行，v2 边界证人正确拒绝

**性能（堵洞2：mean 点估计把噪声当加速）**
- **配对交替测量**（同轮内 old/new 交替，控制环境漂移）+ **中位数加速比**（抗 GC/调度异常值）
- **sign test（配对符号检验，纯 stdlib 二项分布）**：H0=新旧无差异，p = P(Bin(K,0.5) ≥ wins)
- **双条件入库**：中位加速比 ≥ 门槛 **且**（经验域）p < SIGN_ALPHA(0.05)
  - 零一完备域（complete=true）正确性已有数学保障 → **豁免显著性**，只要求中位加速过门槛（性能门槛意义仅为"别倒退太多"）
- 实证：两个相同函数旧闸门 5 次 trial 里 1 次算出 1.095x 过线入库（噪声假阳性）；v2 sign-test 9 轮 p=0.25 正确拒绝；真实加速 9/9 胜 p=0.002 正确放行

**统计背书**：入库记录带 `speedup_med` / `p_value` / `n_pairs` / `wins`（`speedup` 字段语义 = 中位数加速比）。存量旧记录无这些字段，`report` 会标 `[无统计背书·旧闸门记录，待复核]`——尤其 1.03x-1.10x 的低倍速记录（如 qclaw.auth_main 1.03x、qclaw.extract_docx_text 1.052x）疑似旧闸门噪声假阳性，复核时用真实负载重跑 `adopt` 确认。

**反例返回（验证失败不再只回 False）**：`verify_equivalence` 返回 `(ok, counterexample)`——失败时返回首个反例样本（如 `[]`、`-1`），LLM 据此直接定位"错在哪个输入上"，一次改对，不用盲猜重写。`adopt` 的 verify 拒绝 note 带 `首个反例: ...` 且返回 `counterexample` 字段。

**规模维度（交叉点 n\*）**：`crossing_analysis(fn_old, fn_new, kind, spec, sizes=..., threshold=..., sample_fn=...)` 跨规模配对测量，返回 `{"curve": [(n, speedup)...], "n_star": ...}`——n\* = 中位加速比首次 ≥ threshold 的最小规模，回答"这个优化从多大输入才开始赢"。`adopt(..., analyze_crossing=True)` 时入库记录带 `n_star` + `curve`，report 显示 `交叉点n*=...`。**注意**：默认证人类型可能与目标函数不匹配（如 str-join 域证人是 int 列表、拼接函数要字符串列表），跨规模分析用 `sample_fn` 传真实形态（与"默认证人不够用、必须传 samples"同理）。实测：join vs `+=` 加速比随规模单调上升（1 元素 ~1.4x → 1024 元素 ~9x）。

**版本感知（加速比是 CPython 版本的函数）**：3.11+ 自适应特化、3.12 优化 `str +=`、3.13/3.14 tier-2 JIT 会系统性吃掉传统优化技巧收益。入库记录带 `py_version`；`report` 对旧版本记录提示 `[版本x.y，当前z.w，加速比可能已失效]`。判定"优化过时"时用当前版本重跑 `adopt` 复核，而非直接信旧记录。

**作废机制（retract）**：复核发现假阳性时用 `selfopt.retract(name, reason, domain, recheck_speedup)` 追加到 `data/retracted.jsonl`——**不删 library.jsonl**（审计保留历史），report 在认证列表标 `[已作废，见下]` 并单列作废清单。已作废：`get_greeting`（复核 0.896x 反向）、`qclaw.get_os_name`（复核 0.509x 反向），均为 dict-dispatch 域旧 mean 点估计噪声假阳性。库内仍标"待复核"的旧记录（无 p_value）应优先用 v2.1 闸门重跑确认后再决定入库或作废。

## 标准流程

1. **识别**：发现一段会被反复调用的函数（热点）。
2. **重写**：LLM 生成一个更快的等价版本。
3. **把关**：调用 `selfopt.adopt(name, fn_old, fn_new, domain_id)`。它会自动查域 → 取证人（随机+边界）→ 验等价（含异常语义）→ 配对实测 + 符号检验 → 入库（v2 双条件）。
   - 通过 → 记入 `data/library.jsonl`（带统计背书：speedup_med/p_value/n_pairs/wins）
   - 未知域 → 记入 `data/candidates.jsonl`（生长素材，outcome=candidate）
   - 等价不过 → 拒绝，不污染库
4. **成长（关键，不可省略，详见下方"⚠️ 成长触发钩子"）**：用 selfopt 时一旦遇到"已知 6 域覆盖不到"的情况，这就是成长机制的触发点——**绝不能只报"无优化"或"域不全"就结束**，必须改用描述性新 domain_id 调 `selfopt.adopt(...)` 让它进候选池，同域攒够 3 次且每次重写都真能过闸门后，调 `selfopt.add_domain(...)` 把这个模式立成正式域。

## 种子域（domains.json）

预置 6 个常见场景，按"证人集完备性"分两类：

- **零一完备**（complete=true）：`sort-small-net` —— 用 `binary_seq` 证人，2^n 覆盖等价于任意输入，正确性有数学保障。门槛可设低（1.02x）；v2 下**豁免显著性检验**（正确性已证明，性能门槛仅为"别倒退太多"）。
- **经验采样**（complete=false）：`str-join`、`regex-precompile`、`list-to-set-membership`、`dict-dispatch`、`lru-cache-pure` —— 用随机/补充样本验证，够用但不声称完备。
- **版本敏感域**：`dict-dispatch` 已标 `version_sensitive: true`——CPython 3.13+ 自适应特化后 elif 链已被优化得很好，dict/三元重写普遍倒退（v2.1 复核：嵌套三元 0.896x、dict.get 0.509x，两条旧记录已作废）。3.13+ 环境下本域默认不值得重写，确要重写必须过 adopt 双条件把关。analyzer 扫到本域时 confidence 仅供参考，重写前先跑 benchmark。

完整零一原理目前只有排序域有。**为每个新域找到自己的"零一式约简"是这套库能长多大的上限**——这是留给未来研究的地方，种子不强行解决。

## 成长机制（引子）

- `domains.json` 是普通 JSON，LLM 可直接编辑追加新域条目。
- 新域需要三件东西：`scenario`（怎么识别）、`witness`（怎么验证）、`rewrite_hint`（怎么改）。
- `witness` 可以指定 `binary_seq`（数学完备）、`rand_int` / `rand_int_list` / `rand_str` / `rand_rows`（经验采样），或由调用方在 `adopt` 时传 `samples=` 补充正例（证人集本身也能进化）。
- 候选池里同域出现 3 次以上、且每次重写都不等价，说明这个域值得专门做一个证人集——这是蒸馏新域的信号。

## ⚠️ 成长触发钩子（最易被忽略、却是最核心的一步）

种子域只有 6 个，**一定覆盖不到你遇到的所有可优化模式**。覆盖不到不是"没活干"，而是"该长新域了"。但是——**这一跳大模型不会自动做**：用 selfopt 扫一遍、发现域不全，很容易就"哦没优化、结束"。必须在 skill 里写死触发条件，强制去走成长机制。

**⚠️ 先澄清覆盖盲区（避免被"0 信号"误导，这是实测踩过的坑）**：`analyzer` 只能静态检测 **4 类**（`str-join` / `regex-precompile` / `list-to-set-membership` / `dict-dispatch`），而 `domains.json` 实际有 **7 个域（6 种子域 + 1 长出的 `io-parse-cache`，见下方「成长机制」实战）**——其中 `sort-small-net`、`lru-cache-pure` 是 analyzer **扫不到**的（源码注释明写"静态难可靠检测，留给人工或 LLM 判断"），`io-parse-cache` 是 round 1 实测长出的新域、分析器从未覆盖。所以 **`auto_scan` 返回 0 信号 ≠ 无优化**：可能属于那 3 个 analyzer 盲区（含长出的 `io-parse-cache`）的已知域，也可能属于全新域。**0 信号时 LLM 必须主动研判**，绝不能判"没活干"就结束。（历史教训：N_M_memory 的纯文件 I/O 解析缓存，曾因 analyzer 0 信号 + 误套已知域 `lru-cache-pure` 被拒而漏掉——正确做法是识别为全新域走成长机制。）

**触发条件（满足任一即触发，不要犹豫）**：
- `auto_scan` / `analyze_file` 返回 0 信号，但你（LLM）读代码后识别出可优化模式；
- 你想优化的模式不属于 `str-join` / `regex-precompile` / `list-to-set-membership` / `dict-dispatch` / `sort-small-net` / `lru-cache-pure` 任一；
- `adopt` 返回 `{"stage":"domain","note":"未知域...已记候选"}`。

**触发后的必做动作（不可省略，不可只报"无优化"就结束）**：
1. 给这个模式起一个描述性 `domain_id`（如 `io-parse-cache`、`json-memo`、`io-stat-memo`）；
2. 生成一个**真能过等价+速度闸门**的等价重写（用新 `domain_id` 调 `adopt` 才会进候选池）；
3. `selfopt.adopt(name, fn_old, fn_new, "你的域id")` → 自动写 `data/candidates.jsonl` 攒证据（未知域分支在验等价/测速之前就 return，故无论重写好坏都会记，记的是"这个模式出现过"）；
4. **进入候选池是即时的（第一次就记），立域不等 3 次**：用新 `domain_id` 调一次 `adopt` 就写 `data/candidates.jsonl`（这就是"进入成长机制"）。**只要该重写真能过 adopt 闸门（speedup≥门槛、等价通过），当场就 `selfopt.add_domain(entry)` 立域**（`scenario` / `witness` / `rewrite_hint` 三件套缺一不可）+ `reload_domains()` 热重载——**不要等攒够 3 次**。`DISTILL_THRESHOLD` 已设为 1，即首次候选就标记 `ready`；**下次遇到就加、就进成长机制**，而非攒满 3 次才动作。

**反例（错误用法，务必避免）**：用已知域 `lru-cache-pure` 去跑一个"纯文件 I/O 解析缓存"重写，被 bench 拒（0.3x 回归）就认为"selfopt 没用、结束"。—— 这错在两处：① 用了已知域，没触发 unknown-domain 分支，所以根本没进候选池；② 被一次回归挡住就停，没意识到"纯 I/O 解析缓存不在 6 域里"本身就是要去立的新域。正确做法：改用 `io-parse-cache` 这个新域 id 去 `adopt`，让它进候选池、攒证据、最终立域。**发现域不全 = 去长域，不是扫完就完。**

**⚠️ 验证闸门陷阱：集合字面量常量折叠（假加速会污染库，等于反向改进）**：给 `list-to-set-membership`（以及任何"把 `in` 容器换成 set"的优化）写测试样本时，**禁止使用集合字面量**（如 `{"a","b","c"}`）。原因：CPython 自 3.2 起会把 `x in {全常量}` 这类集合字面量在**编译期折叠成 `frozenset` 常量**（权威佐证：CPython 自带测试 `Lib/test/test_peepholer.py` 的 `test_folding_of_sets_of_constants` 断言 `a in {1,2,3}` 字节码只有 `LOAD_CONST (frozenset(...))`、无 `BUILD_SET`；核心答主 user2357112 也写明"Saving the set to a variable prevents the optimization"）。后果：若 `fn_old` 用元组/列表线性扫、`fn_new` 用集合字面量，微基准会报出**虚假加速**——我们第 2 轮就曾误认证 5 个小元组（2.56x / 1.95x），回滚才发现是这坑。闸门把它当真优化写进 `library.jsonl` = **库被污染，正好是"改进机制"的反面**。正确样本写法：用**运行时变量列表**（如 `lst = list(range(8))`，或真实负载里的可变列表），比 `x in lst`（线性）vs `x in set(lst)`（构建+查找）；真正的优化是把 `set(...)` **提到循环外/模块级只建一次**（对应域场景"列表长度>4 且循环内复用"），而不是在代码里写 `x in {字面量}`（那只是编译器作弊，不能推广到真实可变负载）。

**成长 API**（在 `selfopt` 模块中）：

```python
selfopt.growth_signals()   # 扫描候选池，返回各域计数及 ready 标志
selfopt.add_domain(entry)  # 追加新域到 domains.json + 热重载（幂等）
selfopt.reload_domains()   # 手动重载域库（LLM 外部编辑后调用）
```

## 用法

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import selfopt

# 第 1 步：分析器定位热点（随包发，消费方不用自己写分析器）
for fd in selfopt.analyze_file("your_script.py"):
    print(fd["function"], fd["domain"], fd["line"], fd["hint"])
    # → 例如 compute_discount dict-dispatch L968

# 第 2 步：LLM 在标出的位置生成 faster_fn，过闸门入库
ok = selfopt.adopt("my_hot_fn", old_fn, new_fn, "str-join")
# ok["ok"] == True → 已入库；False → 看 ok["stage"] 和 ok["note"]
```

```bash
python scripts/selfopt.py            # 跑内置 demo
python scripts/selfopt.py report     # 看库里有什么、候选池有什么
python scripts/analyzer.py file.py   # 静态扫描热点
```

分析器（`scripts/analyzer.py`）用 AST 静态扫描，覆盖消费方最常提的 4 类场景：
`str-join`（循环内字符串 +=）、`regex-precompile`（函数内 re.compile）、
`list-to-set-membership`（循环内 `x in list`）、`dict-dispatch`（3+ elif 长链）。
`sort-small-net` 与 `lru-cache-pure` 静态难可靠检测，留给人工或 LLM 判断。
职责边界：分析器只答"热点在哪、疑似哪个域"，改写由 LLM 生成、`adopt` 把关。

**降噪设计（类型推断 + 开放式）**：分析器不做"拍板"，只给信号。每条发现带
`confidence`（high/low）+ `reason`。最基础的过程内类型推断（只看初始化赋值推断
累加器/容器类型）用来打标——例如 `s = ""` 后 `s += x` 判 high，`s = []` 后 `+=`
判 low（疑似误报），`re.compile(常量)` 判 high、模式依赖运行期输入判 low。
`auto_scan` / `selfopt-hook.py` 默认只看 high（自动模式保守，挡住误报）；
人工审查传 `min_confidence="low"` 看全部（含 low 待 LLM 自行研判）。

**规则不写死**：各家场景不同，误报长什么样只有各家大模型自己清楚。因此核心只放
最通用的判定，另留公开的 `CONFIDENCE_RULES` 列表，大模型可就地追加自家规则来抑制
误报或加自家判定，无需改动核心。规则返回值契约（务必分清，否则会误杀）：

```python
import analyzer
def my_rule(finding, fn, infer):
    if finding["domain"] == "str-join" and "FrameworkBuf" in fn.name:
        return analyzer.SUPPRESS   # 明确抑制该发现（自家确认的误报）
    return None                    # 不改动，交给下一条规则（不要用来"杀"）
    # return "high" / "low"        # 覆盖置信度
analyzer.CONFIDENCE_RULES.append(my_rule)
```

随包另发 `scripts/analyzer_rules_example.py`——一份复制即用的规则模板（抑制框架
特化累加器、抑制测试函数、把一次性初始化的分派降为 low），`import` 后调一次
`register()` 即生效。消费方按自家情况删改即可，不单独成技能，和 selfopt 放一起。

## 自动触发：说工作就自动跑

"安装后还要手动喂一个 .py 让我分析"——这不科学。根因是**本包原本是被动工具箱，缺一个触发器层**，跟"预装还是后装"无关。补上这层后，流程就变成：你只说"干活"，Agent 做完代码类任务自动去扫描、标热点、长库。

两步即可接线：

**1) 自动扫描（无需手动路径）**——`selfopt.auto_scan()` 会扫当前工作目录（或 `SELFOPT_SCAN_ROOT`）下的 `.py`，自动跳过 `.venv/node_modules/__pycache__/.git/site-packages/.workbuddy`，返回聚合热点清单：

```python
import selfopt
hits = selfopt.auto_scan()                 # 不传参 = 扫 cwd
for h in hits:
    print(h["file"], h["line"], h["domain"], h["function"], h["hint"])
```

**2) 触发器示例**——`scripts/selfopt-hook.py` 就是现成的触发脚本：跑 `auto_scan()`、把热点打印出来交回 Agent。宿主只需在合适的事件上调用它：

```bash
python scripts/selfopt-hook.py             # 手动触发一次（等价于"让 Agent 自己跑一遍"）
```

接入方式（各宿主通用，脚本不依赖任何私有机制）：

- **WorkBuddy / OpenClaw**：挂到 `session end` 或 `after tool write` 钩子，钩子里 `python <skill>/scripts/selfopt-hook.py`。
- **LangChain / CrewAI**：在工具执行后的 callback 里调用 `selfopt.auto_scan()`，把结果喂回 LLM 决定要不要改写。
- **最轻量（无需改框架）**：把"每次产出 Python 代码后跑一遍 auto_scan，对热点生成更快版本并 adopt 入库"写进 Agent 的常驻记忆/系统提示，它就会自发去做。

接上之后，用户视角就是：**说工作 → Agent 干活 → 顺手把活出的代码过一遍优化闸门，库随每次工作默默生长**。分析报告里会显示新发现的域热点；Agent 决定采纳时再 `adopt()` 把关，绝不未经验证就改写源码。

## 友好扫描流程（新旧 py 通用）

无论是**对话中新生成的 .py**还是**仓库里已有的旧 .py**，都用同一套友好流程，差别只在"什么时候触发"：

**两句话对话框**（已在 `selfopt-hook.py --ask` / `selfopt.interactive_scan()` 实现，CLI 用 `input()`，宿主 Agent 换自家对话框即可）：
1. **扫描前**：先问"有目标还是全量？"——目标可以是模糊路径片段，也可以是函数名。`auto_scan(target=...)` 先按路径/文件名模糊匹配，匹配不到再全扫按函数名过滤。这样用户给个方向，我们就只找那一块，不惊动整个仓库。
2. **找到后**：把热点按 (域, 函数) 聚合、按频率排序，`suggest_targets()` 标出"●高频"组（同形态出现 ≥2 次），再问"要优化哪几个？"——高频且高置信的优先问。用户勾选后，Agent 才在对应位置生成更快版本并 `adopt()` 把关。

```bash
python scripts/selfopt-hook.py --ask     # 友好交互：先问目标/全量，再问高频是否优化
python scripts/selfopt.py scan           # 同上（自带的 scan 子命令）
```

**新 .py（对话中生成）该走"先优化再落地"还是"先跑再优、第二次才好"？**
推荐**混合**，不要二选一卡死：
- **明显的结构性热点 → 写代码当时就 adopt**：`str-join`、`re.compile(常量)` 这类，等价性由证人集/语法结构保证，不依赖真实运行数据，生成时分析器标 high 就能直接过关入库，用户第一次拿到就是优化版。
- **"到底热不热 / 要多大样本才赢" → 先跑起来，第二次再优**：优化收益是输入规模敏感的（交叉点问题），且你只有代码跑过、见过真实负载，才知道它是否真热、该喂多大样本。所以**不阻塞交付**——先写出来跑（第一次未优化只是常数因子，摊到多次调用里可忽略），等真实负载出来，再对那些"确实热"的做优化并入库；从此相关调用走优化版。
- 一句话：**库随对话持续累积，不是每生成一次都要先过我们这关；但明显的赢当场就拿，热度的赢等跑出来再拿。**

**旧 .py（仓库已有）**：就是上面的"友好扫描流程"——手动触发 `--ask` → 问目标/全量 → 扫 → 问高频是否优化 → adopt。绝不在用户没确认时改源码。

无论新旧、何种模式，都只"标热点 + 交回 + 把关"，**绝不未经 `adopt` 验证就改写源码**；真要应用到文件，由 Agent 在用户确认后做并保留备份。

## 实战注意事项

- **样本要代表真实规模**：加速比依赖输入大小（交叉点问题）。例如 `str-join` 在大列表上才赢、小列表上 `+=` 反而快。样本太小会通过不了门槛，把本来划算的优化误杀。喂样本时按真实负载量级构造。
- **v2 性能判定是双条件**：中位加速比 ≥ 门槛 且（经验域）sign-test p < 0.05。真实负载下若加速真实存在但幅度小（1.05x 上下），可加大 `rounds` 或喂更大样本提高检验力；不要为了过闸门刻意挑选噪声样本。
- **自定义 samples 时边界由调用方负责**：`adopt(..., samples=...)` 会跳过域的默认证人（含边界样本），等价性只在你传的样本上验证——传真实负载的边界形态（空/极值/非法）是调用方责任。
- **域的默认证人往往不够用**：`regex-precompile` 等域的 `rand_str` 证人匹配不到目标模式，必须传 `samples=真实数据`（如真实文件路径、真实记录）才有意义。传入自定义样本时，库记录的 `witness` 标记为 `custom`。
- **测试隔离**：设环境变量 `SELFOPT_DATA_DIR=/tmp/xxx` 后再 import，可把库/候选写到临时目录，避免测试数据污染真实库。
- **写 `list-to-set-membership` 样本禁用集合字面量**：CPython 会把 `x in {"a","b","c"}` 折叠成编译期 `frozenset` 常量，微基准会报虚假加速、污染库。正确写法与原理见上方「⚠️ 成长触发钩子」节的"验证闸门陷阱"。

## 设计约束

- 仅依赖标准库，单文件，任何 Python 系 Agent 都能直接 `import`。
- 不做运行时 monkey-patch：入库的是**记录与证明**，是否应用到源码由 Agent 决定（建议附备份与回滚）。
- 不信任任何未验证的优化，包括 LLM 自己写的——adopt 是唯一闸门。
