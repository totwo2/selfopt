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
| Layer 2 验证门 | `selfopt.adopt` | 按域证人集查等价性，过不了就拒绝入库 |
| Layer 3 代价评估 | `selfopt.benchmark` | 实测耗时，达标才入 `library.jsonl` |

智能体是生成器，本模块是验证器和计分器。生成可以出错，验证不能缺席——这是整套设计的第一原则。

## 标准流程

1. **识别**：发现一段会被反复调用的函数（热点）。
2. **重写**：LLM 生成一个更快的等价版本。
3. **把关**：调用 `selfopt.adopt(name, fn_old, fn_new, domain_id)`。它会自动查域 → 取证人 → 验等价 → 测速度。
   - 通过 → 记入 `data/library.jsonl`
   - 未知域 → 记入 `data/candidates.jsonl`（生长素材）
   - 等价不过 → 拒绝，不污染库
4. **成长（关键，不可省略，详见下方"⚠️ 成长触发钩子"）**：用 selfopt 时一旦遇到"已知 6 域覆盖不到"的情况，这就是成长机制的触发点——**绝不能只报"无优化"或"域不全"就结束**，必须改用描述性新 domain_id 调 `selfopt.adopt(...)` 让它进候选池，同域攒够 3 次且每次重写都真能过闸门后，调 `selfopt.add_domain(...)` 把这个模式立成正式域。

## 种子域（domains.json）

预置 6 个常见场景，按"证人集完备性"分两类：

- **零一完备**（complete=true）：`sort-small-net` —— 用 `binary_seq` 证人，2^n 覆盖等价于任意输入，正确性有数学保障。门槛可设低（1.02x）。
- **经验采样**（complete=false）：`str-join`、`regex-precompile`、`list-to-set-membership`、`dict-dispatch`、`lru-cache-pure` —— 用随机/补充样本验证，够用但不声称完备。

完整零一原理目前只有排序域有。**为每个新域找到自己的"零一式约简"是这套库能长多大的上限**——这是留给未来研究的地方，种子不强行解决。

## 成长机制（引子）

- `domains.json` 是普通 JSON，LLM 可直接编辑追加新域条目。
- 新域需要三件东西：`scenario`（怎么识别）、`witness`（怎么验证）、`rewrite_hint`（怎么改）。
- `witness` 可以指定 `binary_seq`（数学完备）、`rand_int` / `rand_int_list` / `rand_str` / `rand_rows`（经验采样），或由调用方在 `adopt` 时传 `samples=` 补充正例（证人集本身也能进化）。
- 候选池里同域出现 3 次以上、且每次重写都不等价，说明这个域值得专门做一个证人集——这是蒸馏新域的信号。

## ⚠️ 成长触发钩子（最易被忽略、却是最核心的一步）

种子域只有 6 个，**一定覆盖不到你遇到的所有可优化模式**。覆盖不到不是"没活干"，而是"该长新域了"。但是——**这一跳大模型不会自动做**：用 selfopt 扫一遍、发现域不全，很容易就"哦没优化、结束"。必须在 skill 里写死触发条件，强制去走成长机制。

**⚠️ 先澄清覆盖盲区（避免被"0 信号"误导，这是实测踩过的坑）**：`analyzer` 只能静态检测 **4 类**（`str-join` / `regex-precompile` / `list-to-set-membership` / `dict-dispatch`），而 `domains.json` 实际有 **6 个域**——`sort-small-net` 与 `lru-cache-pure` 是 analyzer **扫不到**的（源码注释明写"静态难可靠检测，留给人工或 LLM 判断"）。所以 **`auto_scan` 返回 0 信号 ≠ 无优化**：可能属于那 2 个 analyzer 盲区的已知域，也可能属于全新域。**0 信号时 LLM 必须主动研判**，绝不能判"没活干"就结束。（历史教训：N_M_memory 的纯文件 I/O 解析缓存，曾因 analyzer 0 信号 + 误套已知域 `lru-cache-pure` 被拒而漏掉——正确做法是识别为全新域走成长机制。）

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
- **域的默认证人往往不够用**：`regex-precompile` 等域的 `rand_str` 证人匹配不到目标模式，必须传 `samples=真实数据`（如真实文件路径、真实记录）才有意义。传入自定义样本时，库记录的 `witness` 标记为 `custom`。
- **测试隔离**：设环境变量 `SELFOPT_DATA_DIR=/tmp/xxx` 后再 import，可把库/候选写到临时目录，避免测试数据污染真实库。

## 设计约束

- 仅依赖标准库，单文件，任何 Python 系 Agent 都能直接 `import`。
- 不做运行时 monkey-patch：入库的是**记录与证明**，是否应用到源码由 Agent 决定（建议附备份与回滚）。
- 不信任任何未验证的优化，包括 LLM 自己写的——adopt 是唯一闸门。
