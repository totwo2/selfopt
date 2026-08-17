# selfopt — AI 智能体自优化种子包 / AI Agent Self-Optimization Seed Pack

> [中文] 一个当前就能装进 AI 智能体用、能产生实测加速、且会随用户负载自我生长的小型优化框架。不做大而全，只留引子。
> [EN] A small optimization framework you can drop into an AI agent today: it produces measured speedups and grows with the user's workload. Not ambitious—just a seed.

## 三层分工 / Three-layer division

| 层 Layer | 由谁做 By whom | 做什么 What |
|----|--------|--------|
| Layer 1 候选生成 Candidate generation | **LLM 智能体本身** The LLM agent itself | 读代码、识别可优化点、生成重写版本 Read code, spot optimizable points, generate rewrite versions |
| Layer 2 验证门 Verification gate | `selfopt.adopt` | 按域证人集查等价性，过不了就拒绝入库 Check equivalence against domain witnesses; reject if it fails |
| Layer 3 代价评估 Cost evaluation | `selfopt.benchmark` | 实测耗时，达标才入 `library.jsonl` Measure real elapsed time; only admit if it clears the bar |

> [中文] 智能体是生成器，本模块是验证器和计分器。生成可以出错，验证不能缺席。
> [EN] The agent is the generator; this module is the verifier and scorer. Generation may err; verification must not be absent.

## 安装 / Install

> [中文] 解压后把 `selfopt/` 目录放到你的 Agent 的**技能目录**下即可：
> [EN] After unzipping, place the `selfopt/` directory under your agent's **skills directory**:

- WorkBuddy：`~/.workbuddy/skills/selfopt/`
- OpenClaw：ClawHub 技能目录或自定义 skills 路径
- 其他 Python 系 Agent：任何会被该 Agent 扫描为技能的目录

```bash
unzip selfopt-skill.zip -d ~/.workbuddy/skills/
```

> [中文] 仅依赖 Python 标准库，无需 pip install。
> [EN] Depends only on the Python standard library—no `pip install` required.

## 用法 / Usage

> [中文] LLM 生成 faster_fn 后，过闸门入库：
> [EN] After the LLM produces a `faster_fn`, pass it through the gate:

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import selfopt
ok = selfopt.adopt("my_hot_fn", slow_fn, faster_fn, "str-join")
# ok["ok"] == True → 已入库；False → 看 ok["stage"] 和 ok["note"]
```

## 完整工作流 / Full workflow

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import selfopt

# 1) 分析器定位热点（随包发，消费方不用自己写分析器）
for fd in selfopt.analyze_file("your_script.py"):
    print(fd["function"], fd["domain"], fd["line"], fd["hint"])

# 2) LLM 在标出的位置生成更快版本，过闸门入库
ok = selfopt.adopt("hot_fn", slow_fn, faster_fn, "str-join")
```

> [中文] 分析器（`scripts/analyzer.py`）用 AST 静态扫描，覆盖最常提的 4 类场景：字符串拼接、循环内正则编译、列表成员检测、if-elif 长链分派。
> [EN] The analyzer (`scripts/analyzer.py`) statically scans via AST, covering the 4 most common cases: string joining, in-loop regex compilation, list membership tests, and if-elif dispatch chains.

**降噪 + 开放式 / Denoising + open rules**：每条发现带 `confidence`（high/low）+ `reason`，最基础的类型推断只用来打标不拍板——`auto_scan` 默认只看 high（自动挡误报），人工审查传 `min_confidence="low"` 看全部。规则不写死在核心：各家误报长什么样只有自家大模型清楚，故留公开 `CONFIDENCE_RULES` 列表，大模型可 `append` 自家规则。

## 自动触发 / Auto-trigger

> [中文] 包本身是被动工具箱，差一个触发器层才会"还要手动喂 py"。补上后，Agent 做完代码任务自动扫描、标热点、长库：
> [EN] The package is a passive toolbox; it needs a trigger layer so the agent auto-scans after code tasks instead of being hand-fed a `.py`:

```python
import selfopt
hits = selfopt.auto_scan()   # 不传参 = 扫当前工作目录，自动跳过 .venv/node_modules 等
```

- WorkBuddy / OpenClaw：挂到 `session end` 或 `after tool write` 钩子。
- LangChain / CrewAI：工具执行后 callback 里调用 `selfopt.auto_scan()`。

## 成长机制 / Growth mechanism

> [中文] 种子域只有 6 个，一定覆盖不到你遇到的所有模式。**遇到已知域覆盖不到的模式时，必须主动走成长机制（而非扫完就结束）**：
> [EN] The seed has only 6 domains and will never cover every pattern you meet. **When a pattern falls outside the known domains, you must proactively engage the growth mechanism (don't just stop after scanning):**

- 未知域的优化尝试 → 记进 `data/candidates.jsonl`
- `selfopt.growth_signals()` 检测候选；`DISTILL_THRESHOLD=1`，**首次即标记 ready**（不等攒 3 次）
- 只要重写能过 `adopt` 闸门，LLM 立即 `selfopt.add_domain()` 把新域追加进 `domains.json` 并热重载
- ⚠️ `analyzer` 只能静态检测 4 类（str-join / regex-precompile / list-to-set / dict-dispatch），`sort-small-net` 与 `lru-cache-pure` 是 analyzer 盲区——`auto_scan` 0 信号 ≠ 无优化，LLM 须主动研判
- 每个用户的库随自己的负载生长

## 实战注意 / Practical notes

- 样本要代表真实规模（加速比有交叉点，小样本可能误杀好优化）
- 域的默认证人常不够用，必要时传 `samples=真实数据`
- 测试隔离：设 `SELFOPT_DATA_DIR=/tmp/xxx` 后再 import，避免污染真实库

详见 `SKILL.md` / See `SKILL.md` for details.
