#!/usr/bin/env python3
"""
selfopt math_gate 原型（自证用，非正式集成）
=============================================
老高 2026-08-18 提问："selfopt 也是数学计算，它的数学模型/方程够不够用？"

审计结论（对应代码行）：
  洞1 等价性（selfopt.py L77-85 + L50-74）：
      纯随机证人无边界覆盖 → 错误重写可混入库
  洞2 性能（selfopt.py L90-98 + L128-134）：
      mean 点估计 + 硬门槛，无统计检验 → 噪声可被当成加速

本原型用两个反例证明洞是真的，并给出升级方程：
  升级A 边界+随机混合证人（边界值分析：多数 bug 在边界触发）
  升级B 配对交替测量 + 中位数 + 符号检验（sign test，纯 stdlib）

仅依赖标准库，与 selfopt 一致。运行：python scripts/math_gate_proto.py
"""
import math
import random
import statistics
import time

MIN_SPEEDUP = 1.05          # selfopt.DEFAULT_MIN_SPEEDUP
MIN_SPEEDUP_SORT = 1.02     # sort 域低门槛
ALPHA = 0.05                # 显著性水平


# ============================================================
# 洞1 复现：随机证人 vs 边界证人
# ============================================================

def old_witness_rand(kind="rand_int_list", n_samples=50, seed=42):
    """旧闸门证人（与 selfopt.make_witnesses 同逻辑）：纯随机，无边界"""
    rng = random.Random(seed)
    n = 8
    return [[rng.randint(0, 99) for _ in range(n)] for _ in range(n_samples)]


def upgraded_witness(kind="rand_int_list", n_samples=50, seed=42):
    """升级A：随机采样 + 边界样本（空/单元素/极值/负值/重复）"""
    rng = random.Random(seed)
    n = 8
    rands = [[rng.randint(0, 99) for _ in range(n)] for _ in range(n_samples)]
    boundaries = [
        [],                        # 空列表 —— 随机绝不会生成
        [0],                       # 单元素
        [0] * 100,                 # 全零
        [99] * 100,                # 全最大
        [-1],                      # 负值 —— 随机绝不会生成
        [100, -1, 0, 99],          # 混合极值
        [0, 0, 0, 0, 0, 0, 0, 0],  # 重复元素
    ]
    return rands + boundaries


# 构造"错误但能混过旧闸门"的重写：sum 的新版本对空列表抛异常
def sum_old(xs):
    s = 0
    for x in xs:
        s += x
    return s


def sum_buggy(xs):
    # 非空时正常；空列表走 xs[0] → IndexError（只在边界触发）
    return sum(xs) if xs else xs[0]


def verify(fn_old, fn_new, samples):
    """等价性判定（与 selfopt.verify_equivalence 同逻辑）"""
    for s in samples:
        try:
            if fn_old(s) != fn_new(s):
                return False
        except Exception:
            return False
    return True


# ============================================================
# 洞2 复现：点估计 vs 配对符号检验
# ============================================================

def benchmark_old(fn, samples, rounds=30):
    """旧闸门：mean(rounds)/n —— 点估计，无方差、无检验"""
    ts = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        for s in samples:
            fn(s)
        ts.append((time.perf_counter() - t0) * 1000)
    return statistics.mean(ts) / max(len(samples), 1)


def paired_benchmark(fn_old, fn_new, samples, K=9):
    """升级B：K 轮配对交替测量（同轮内 old/new 交替，控制环境漂移）"""
    pairs = []
    for _ in range(K):
        t0 = time.perf_counter()
        for s in samples:
            fn_old(s)
        to = (time.perf_counter() - t0) * 1000 / max(len(samples), 1)
        t0 = time.perf_counter()
        for s in samples:
            fn_new(s)
        tn = (time.perf_counter() - t0) * 1000 / max(len(samples), 1)
        pairs.append((to, tn))
    return pairs


def sign_test(pairs):
    """配对符号检验：H0 = 新旧无差异。
    p = P(Bin(K, 0.5) >= wins)。纯 stdlib（二项分布）。"""
    wins = sum(1 for to, tn in pairs if tn < to)
    n = len(pairs)
    p = sum(math.comb(n, k) for k in range(wins, n + 1)) / (2 ** n)
    return {"wins": wins, "n": n, "p": round(p, 4)}


def speedup_stats(pairs):
    """中位数加速比（抗噪，替代 mean 点估计）"""
    med_old = statistics.median(to for to, _ in pairs)
    med_new = statistics.median(tn for _, tn in pairs)
    return round(med_old / max(med_new, 1e-9), 3), round(med_old, 5), round(med_new, 5)


# ============================================================
# Demo
# ============================================================

def demo_hole1():
    print("=" * 64)
    print("洞1：等价性 —— 随机证人无边界覆盖，错误重写可混入")
    print("=" * 64)
    w_old = old_witness_rand()
    w_up = upgraded_witness()
    print(f"\n旧闸门证人: 纯随机 {len(w_old)} 个（0-99 的 8 元列表，无空/负/极值）")
    print(f"升级证人  : 随机 {len(w_old)} 个 + 边界 {len(w_up) - len(w_old)} 个")
    print(f"\nsum_buggy（对空列表抛 IndexError 的'优化'）:")
    print(f"  旧闸门 verify → {'通过！错误重写混入库 ✗✗' if verify(sum_old, sum_buggy, w_old)
          else '拒绝'}")
    print(f"  升级闸门 verify → {'通过' if verify(sum_old, sum_buggy, w_up)
          else '拒绝（边界样本 [] 触发 IndexError，抓住）✓'}")


def demo_hole2():
    print("\n" + "=" * 64)
    print("洞2：性能 —— mean 点估计无统计检验，噪声可被当成加速")
    print("=" * 64)

    # 用两个完全相同的函数：真实加速 = 1.0x，一切 >1 都是噪声
    def fn_same_a(xs):
        s = 0
        for x in xs:
            s += x
        return s

    fn_same_b = fn_same_a
    samples = [list(range(200)) for _ in range(20)]

    # 旧闸门：mean 点估计 + 硬门槛。多跑几轮看波动。
    print(f"\n对照：两个完全相同的函数（真实加速必须=1.0x）")
    verdicts = []
    for trial in range(5):
        to = benchmark_old(fn_same_a, samples)
        tn = benchmark_old(fn_same_b, samples)
        sp = to / max(tn, 1e-9)
        verdicts.append(sp)
        tag = "过线入库 ✗" if sp >= MIN_SPEEDUP else "拒绝 ✓"
        print(f"  旧闸门 trial{trial}: mean加速 {sp:.3f}x (门槛 {MIN_SPEEDUP}x) → {tag}")
    print(f"  → 5 次里 {sum(1 for v in verdicts if v >= MIN_SPEEDUP)} 次把纯噪声当成了加速")

    # 新闸门：配对 + 中位数 + sign test
    pairs = paired_benchmark(fn_same_a, fn_same_b, samples, K=9)
    med_sp, _, _ = speedup_stats(pairs)
    st = sign_test(pairs)
    sig = "显著，可入库" if (med_sp >= MIN_SPEEDUP and st["p"] < ALPHA) else "不显著，拒绝 ✓"
    print(f"\n  新闸门: 配对 {st['n']} 轮, 中位加速 {med_sp}x, "
          f"新更快 {st['wins']}/{st['n']} 轮, sign-test p={st['p']}")
    print(f"  → 判定: {sig}（噪声翻不出显著性，假阳性被统计检验挡住）")

    # 对比：真实加速时新闸门仍放行（证明升级不误杀）
    def fn_slower(xs):
        s = 0
        for i in range(len(xs)):
            s += xs[i]
        return s

    pairs2 = paired_benchmark(fn_slower, fn_same_a, samples, K=9)
    med_sp2, _, _ = speedup_stats(pairs2)
    st2 = sign_test(pairs2)
    sig2 = "显著，可入库 ✓" if (med_sp2 >= MIN_SPEEDUP and st2["p"] < ALPHA) else "不显著"
    print(f"\n对照（真实加速：下标循环 → for-in 迭代）:")
    print(f"  新闸门: 中位加速 {med_sp2}x, 新更快 {st2['wins']}/{st2['n']} 轮, "
          f"sign-test p={st2['p']} → {sig2}")


def demo_decision_table():
    print("\n" + "=" * 64)
    print("升级后的完整决策表（洞1 + 洞2 合并）")
    print("=" * 64)
    print("""
  等价性(边界+随机)  性能(中位+sign test)      结论
  ──────────────────────────────────────────────────
  过                显著(med>=门槛, p<α)      → 入库，记录统计背书
  过                不显著                    → 拒绝(可能是噪声/交叉点)
  不过               —                        → 拒绝(正确性优先，绝不污染库)
    """)


if __name__ == "__main__":
    demo_hole1()
    demo_hole2()
    demo_decision_table()
