"""核心织纹逻辑的单元测试（不依赖 FastAPI）。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.weave import (  # noqa: E402
    DesignError,
    analyze_repeat_period,
    audit_floats,
    build_interlacing,
    repeat_period_of_matrix,
    search_repair_plans,
    suggest_tie_up_flips,
    validate_design,
    _divisors,
    _runs,
)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def test_interlacing():
    # 平纹：2 综 2 踏
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    m = build_interlacing(threading, tie_up, treadling)
    check(m == [[1, 0, 1, 0],
                [0, 1, 0, 1],
                [1, 0, 1, 0],
                [0, 1, 0, 1]], "plain weave interlacing")


def test_warp_and_weft_floats():
    # 第 0 根经纱连续 3 纬浮起；第 0 纬纬纱连续浮过 3 根经纱
    threading = [0, 0, 0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 0, 1]
    # 矩阵:
    # 1 1 1
    # 1 1 1
    # 1 1 1
    # 0 0 0
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    warp = [x for x in v if x.direction == "warp"]
    weft = [x for x in v if x.direction == "weft"]
    check(len(warp) == 3 and all(x.length == 3 and x.start == 0 for x in warp),
          "warp floats of length 3 on all 3 ends")
    check(len(weft) == 1 and weft[0].yarn_index == 3 and weft[0].length == 3,
          "weft float of length 3 on pick 3")
    check(all(x.yarn_index in (0, 1, 2) for x in warp), "warp yarn indices")


def test_cyclic_merge():
    # 列: 1 1 0 0 1 1 -> 非循环两段(0,2),(4,2)；循环合并为 (4,4)
    check(_runs([1, 1, 0, 0, 1, 1], 1, False) == [(0, 2), (4, 2)],
          "non-cyclic runs")
    check(_runs([1, 1, 0, 0, 1, 1], 1, True) == [(4, 4)],
          "cyclic merge across boundary")
    # 全 1 列：只有一段，不自我合并
    check(_runs([1, 1, 1], 1, True) == [(0, 3)],
          "all-float line stays a single run")
    # 首尾不相接时不合并
    check(_runs([1, 0, 0, 1, 0], 1, True) == [(0, 1), (3, 1)],
          "no merge when boundary not both target")


def test_cyclic_audit_end_to_end():
    # 2/2 斜纹 4x4 循环，max_float=2：循环合并后每根经纱浮长恰为 2，不超限
    threading = [0, 1, 2, 3]
    tie_up = [[1, 1, 0, 0],
              [0, 1, 1, 0],
              [0, 0, 1, 1] if False else [0, 0, 1, 1],
              [1, 0, 0, 1]]
    treadling = [0, 1, 2, 3]
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(v == [], "2/2 twill cyclic: no float exceeds 2")
    # 非循环时边界处浮长仍 <= 2，也不超限
    _, v2 = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v2 == [], "2/2 twill non-cyclic: no float exceeds 2")
    # max_float=1 时循环与非循环都应报出浮长 2
    _, v3 = audit_floats(threading, tie_up, treadling, max_float=1, cyclic=True)
    check(len(v3) > 0 and all(x.length == 2 for x in v3),
          "2/2 twill with max_float=1 flags length-2 floats")


def test_cyclic_wrap_violation():
    # 构造跨边界合并后才超限的情形：列 1 1 0 1 1，max_float=2
    # 非循环：两段长度 2、2，不超限；循环：合并为长度 4，超限
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    _, v_off = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v_off == [], "wrap-around float not flagged when cyclic=False")
    _, v_on = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(len(v_on) == 1 and v_on[0].direction == "warp"
          and v_on[0].yarn_index == 0 and v_on[0].start == 3 and v_on[0].length == 4,
          "wrap-around float merged to length 4 starting at 3")


def test_tie_up_suggestions_basic():
    # 列 1 1 0 1 1 循环合并为长度 4 的经向浮长（max_float=2），共 1 条违规
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    suggestions = suggest_tie_up_flips(threading, tie_up, treadling, 2, True)
    # 仅 flip tie_up[0][0] -> 0 可消除违规；受影响点 = 踩踏板 0 的 4 纬 × 1 经
    check(len(suggestions) == 1, "exactly one improving flip")
    s = suggestions[0]
    check(s.treadle == 0 and s.shaft == 0 and s.new_value == 0,
          "flip tie_up[0][0] to 0")
    check(s.remaining_violations == 0, "no violations remain after flip")
    check(s.affected_points == 4, "4 interlacing points affected")
    # 原设计不被修改
    check(tie_up == [[1], [0]], "original tie_up unchanged")


def test_tie_up_suggestions_ordering():
    # 3 根经纱各浮 3 纬 + 末纬纬浮 3 经，共 4 条违规；多个单步翻转可改善
    threading = [0, 1, 1]
    tie_up = [[1, 1], [0, 0]]
    treadling = [0, 0, 0, 1]
    suggestions = suggest_tie_up_flips(threading, tie_up, treadling, 2, False)
    got = [(s.treadle, s.shaft, s.remaining_violations, s.affected_points)
           for s in suggestions]
    # 按 (剩余违规数, 受影响点数, 踏板索引, 综框索引) 升序
    check(got == [(0, 1, 2, 6), (1, 0, 3, 1), (1, 1, 3, 2), (0, 0, 3, 3)],
          "suggestions sorted by remaining, affected, treadle, shaft")
    check(all(s.remaining_violations < 4 for s in suggestions),
          "all candidates strictly reduce violations")
    check(tie_up == [[1, 1], [0, 0]], "original tie_up unchanged")


def test_tie_up_suggestions_no_improvement():
    # 平纹无违规：违规数为 0，不存在严格更少的翻转，返回空列表
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    check(suggest_tie_up_flips(threading, tie_up, treadling, 2, False) == [],
          "empty list when no flip improves")


def test_repair_plans_two_flips_needed():
    # 单列 6 纬全 1，cyclic 下整列一段长度 6，max_float=2：1 条经向违规。
    # 每个踏板各踩 1 纬，单次翻转只产生 1 个 0，仍有 1 条违规（长度 5）；
    # 循环上间隔恰为 3 的两次翻转把 1-段切成三段各长 2，违规清零。
    threading = [0]
    tie_up = [[1], [1], [1], [1], [1], [1]]
    treadling = [0, 1, 2, 3, 4, 5]
    _, base_v = audit_floats(threading, tie_up, treadling, 2, True)
    check(len(base_v) == 1, "baseline has exactly one violation")

    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=1)
    check(plans == [], "no improving plan within 1 flip")

    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=2)
    # 循环 6 点上两个 0 间隔恰为 3 时三段各长 2：恰 3 个方案
    check(len(plans) == 3, f"3 two-flip plans, got {len(plans)}")
    seq0 = [(s.treadle, s.shaft) for s in plans[0].steps]
    check(seq0 == [(0, 0), (3, 0)], "lexicographically smallest sequence first")
    check([(s.treadle, s.shaft) for s in plans[1].steps] == [(1, 0), (4, 0)]
          and [(s.treadle, s.shaft) for s in plans[2].steps] == [(2, 0), (5, 0)],
          "remaining plans in lexicographic order")
    for p in plans:
        check(p.changes == 2 and p.final_violations == 0,
              "every plan uses 2 flips and clears violations")
        check(p.changed_points == 2, "2 interlacing points changed")
        check(len(p.steps) == 2 and p.steps[0].step == 1 and p.steps[1].step == 2,
              "steps are numbered 1..2")
        check(p.steps[0].old_value == 1 and p.steps[0].new_value == 0
              and p.steps[1].old_value == 1 and p.steps[1].new_value == 0,
              "flips 1 -> 0 with correct old/new values")
        check(p.steps[0].violations_after == 1,
              "intermediate state may keep violations unchanged")
        check(p.violations == [], "final violation list empty")
        check(sum(x for row in p.interlacing for x in row) == 4,
              "final matrix has exactly two zeros")
    check(tie_up == [[1], [1], [1], [1], [1], [1]],
          "original tie_up unchanged")


def test_repair_plans_state_dedup():
    # 同一绑综终态可由不同翻转序列到达：按状态去重，只保留字典序最小序列。
    # 2 踏 2 综，单列单纬时仅被踩踏板所提升的综框影响矩阵；构造多步搜索，
    # 验证终态去重（无重复终态）且原设计不被修改。
    threading = [0, 1]
    tie_up = [[1, 1], [0, 0]]
    treadling = [0, 0, 0, 1]
    plans = search_repair_plans(threading, tie_up, treadling, 2, False,
                                max_changes=3, limit=50)
    finals = []
    for p in plans:
        check(p.final_violations < 4, "plan strictly improves over baseline")
        # 同一单元在一条序列内不重复出现
        coords = [(s.treadle, s.shaft) for s in p.steps]
        check(len(coords) == len(set(coords)),
              "no cell flipped twice within one sequence")
        finals.append(tuple(tuple(row) for row in p.interlacing))
    check(len(finals) == len(set(finals)),
          "equivalent final states deduplicated")
    # 排序键：最终违规数、改动数、变化点数、序列字典序
    keys = [
        (p.final_violations, p.changes, p.changed_points,
         tuple((s.treadle, s.shaft) for s in p.steps))
        for p in plans
    ]
    check(keys == sorted(keys), "plans sorted by the declared key")
    check(tie_up == [[1, 1], [0, 0]], "original tie_up unchanged")


def test_repair_plans_limit_and_validation():
    threading = [0]
    tie_up = [[1], [1], [1], [1], [1], [1]]
    treadling = [0, 1, 2, 3, 4, 5]
    plans = search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=2, limit=2)
    check(len(plans) == 2, "limit caps the number of plans")
    for bad in (0, 4):
        try:
            search_repair_plans(threading, tie_up, treadling, 2, True,
                                max_changes=bad)
            raise AssertionError(f"max_changes={bad} should be rejected")
        except DesignError:
            pass
    try:
        search_repair_plans(threading, tie_up, treadling, 2, True, limit=0)
        raise AssertionError("limit=0 should be rejected")
    except DesignError:
        pass
    print("  ok: repair plan parameter validation")


def test_repeat_period_plain_weave():
    # 平纹 4x4：单元 [[1,0],[0,1]]，经/纬周期均为 2
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    r = analyze_repeat_period(threading, tie_up, treadling)
    check(r.warp_period == 2, "plain weave warp period 2")
    check(r.weft_period == 2, "plain weave weft period 2")
    check(r.unit == [[1, 0], [0, 1]], "plain weave unit matrix")
    check(r.strict_2d_repeat is True, "plain weave is strict 2D repeat")
    check(r.warp_ends == 4 and r.weft_picks == 4, "full dimensions reported")
    # unit 平铺必须无差别复现整幅矩阵
    matrix = build_interlacing(threading, tie_up, treadling)
    tiled = [
        [r.unit[h % r.weft_period][w % r.warp_period]
         for w in range(r.warp_ends)]
        for h in range(r.weft_picks)
    ]
    check(tiled == matrix, "unit tiles the full matrix exactly")


def test_repeat_period_twill():
    # 2/2 斜纹 8x8：交织单元为 4x4（非 8），两方向周期均为 4
    threading = [0, 1, 2, 3, 0, 1, 2, 3]
    tie_up = [[1, 1, 0, 0],
              [0, 1, 1, 0],
              [0, 0, 1, 1],
              [1, 0, 0, 1]]
    treadling = [0, 1, 2, 3, 0, 1, 2, 3]
    r = analyze_repeat_period(threading, tie_up, treadling)
    expected_unit = [[1, 1, 0, 0],
                     [0, 1, 1, 0],
                     [0, 0, 1, 1],
                     [1, 0, 0, 1]]
    check((r.warp_period, r.weft_period) == (4, 4),
          "2/2 twill 8x8 has 4x4 repeat unit")
    check(r.unit == expected_unit, "twill unit is the 4x4 tie-up pattern")
    check(r.strict_2d_repeat is True, "twill is strict 2D repeat")


def test_repeat_period_asymmetric_directions():
    # 非对称单元 2 列 x 3 行，在 4 列 x 6 行上平铺：
    # 专门防止把经/纬方向弄反——warp_period 必须整除列数(=2)，
    # weft_period 必须整除行数(=3)。
    unit = [[1, 0],
            [0, 1],
            [1, 1]]
    matrix = [
        [unit[h % 3][w % 2] for w in range(4)]
        for h in range(6)
    ]
    r = repeat_period_of_matrix(matrix)
    check(r.warp_period == 2 and r.weft_period == 3,
          "warp period counts columns, weft period counts rows")
    check(r.unit == unit, "unit is 3 rows x 2 cols")
    check(r.strict_2d_repeat is True, "strict 2D repeat")


def test_repeat_period_based_on_matrix_not_threading():
    # 比较必须基于交织矩阵而非分别检查 threading/treadling：
    # 穿综 [0,1,2,0,1,2] 看似周期 3，但三个综框的绑综列完全相同，
    # 交织矩阵全为同一值，真实最小周期是 1x1。
    threading = [0, 1, 2, 0, 1, 2]
    tie_up = [[1, 1, 1]]
    treadling = [0, 0]
    r = analyze_repeat_period(threading, tie_up, treadling)
    check((r.warp_period, r.weft_period) == (1, 1),
          "identical tie-up columns collapse matrix warp period to 1")
    check(r.unit == [[1]], "unit is 1x1")
    check(r.strict_2d_repeat is True, "constant matrix is strict 2D repeat")

    # 非退化版本：穿综/踏综序列周期均为 4，但综框 0/2、1/3 的绑综列分别
    # 等价，交织矩阵的真实周期只有 2（矩阵周期只可能小于序列周期）。
    threading2 = [0, 1, 2, 3, 0, 1, 2, 3]
    tie_up2 = [[1, 0, 1, 0],
               [0, 1, 0, 1]]
    treadling2 = [0, 1, 0, 1, 0, 1, 0, 1]
    r2 = analyze_repeat_period(threading2, tie_up2, treadling2)
    check((r2.warp_period, r2.weft_period) == (2, 2),
          "equivalent shafts/treadles shrink the matrix repeat below sequences")
    check(r2.unit == [[1, 0], [0, 1]], "matrix unit 2x2, not the apparent 4x4")


def test_repeat_period_cyclic_boundary():
    # 循环纹样也要正确处理首尾边界：周期判定等价于跨末/首边界的循环比较。
    # 序列 1 0 0 1 0 0 周期 3（平移 3 列后首行与自身跨边界相接一致）。
    m = [[1, 0, 0, 1, 0, 0],
         [0, 1, 1, 0, 1, 1]]
    r = repeat_period_of_matrix(m)
    check(r.warp_period == 3, f"cyclic-style boundary period 3, got {r.warp_period}")
    check(r.weft_period == 2, "rows alternate with period 2")
    check(r.unit == [[1, 0, 0], [0, 1, 1]], "unit across boundary")

    # 仅首尾相接处不吻合时，即使整除尺寸的候选也不能算周期：
    # 1 0 0 1 0 1 无周期 3（平移 3 后末位与首位冲突），只能取整幅 6。
    m2 = [[1, 0, 0, 1, 0, 1]]
    r2 = repeat_period_of_matrix(m2)
    check(r2.warp_period == 6, "boundary mismatch rejects divisor candidate")
    check(r2.weft_period == 1, "single row has weft period 1")
    check(r2.strict_2d_repeat is False,
          "one-direction-only repeat is not strict 2D")


def test_repeat_period_full_size_fallback():
    # 质数尺寸且无任何更小周期：两方向都返回完整尺寸，unit 即整幅矩阵
    m = [[1, 0, 1],
         [0, 1, 1],
         [1, 1, 0]]
    r = repeat_period_of_matrix(m)
    check((r.warp_period, r.weft_period) == (3, 3),
          "prime-sized non-repeating matrix falls back to full size")
    check(r.unit == m, "unit is the full matrix")
    check(r.strict_2d_repeat is False, "full size is not a strict 2D repeat")

    # 单行矩阵：纬向必为 1（严格小于行数 1 不可能），非严格二维重复
    r_one_row = repeat_period_of_matrix([[1, 0, 1, 0]])
    check((r_one_row.warp_period, r_one_row.weft_period) == (2, 1),
          "single row: warp period 2, weft period 1")
    check(r_one_row.strict_2d_repeat is False,
          "degenerate weft direction makes it non-strict")


def test_repeat_period_only_one_direction():
    # 仅列方向重复：每行各自水平周期 2，但三行互异（行数 3 为质数，
    # 唯一真因数候选 1 不成立），故纬向取完整尺寸 3。
    m = [[1, 0, 1, 0],
         [0, 1, 0, 1],
         [1, 1, 1, 1]]
    r = repeat_period_of_matrix(m)
    check((r.warp_period, r.weft_period) == (2, 3),
          "repeats across columns but not rows")
    check(r.unit == [[1, 0], [0, 1], [1, 1]], "unit spans all rows")
    check(r.strict_2d_repeat is False, "not strict when rows never repeat")


def test_repeat_period_divisors_only():
    # 非整除尺寸的“视觉周期”不算合法周期：
    # 1 0 1 0 1 在 5 列上像周期 2，但 2 不整除 5，无缝平铺做不到，取 5。
    m = [[1, 0, 1, 0, 1]]
    r = repeat_period_of_matrix(m)
    check(r.warp_period == 5, "period must divide the dimension")
    check(_divisors(12) == [1, 2, 3, 4, 6, 12], "divisors ascending")
    check(_divisors(7) == [1, 7], "prime divisors")


def test_validation():
    ok_cases = []
    # 维度不一致：绑综矩阵不是矩形
    try:
        validate_design([0], [[1, 0], [1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 穿综索引越界
    try:
        validate_design([0, 2], [[1, 0], [0, 1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 踏综索引越界
    try:
        validate_design([0], [[1], [0]], [2], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 绑综取值非 0/1
    try:
        validate_design([0], [[2]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 空输入
    try:
        validate_design([], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 负索引
    try:
        validate_design([-1], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    check(all(ok_cases), "invalid designs are rejected")


if __name__ == "__main__":
    test_interlacing()
    test_warp_and_weft_floats()
    test_cyclic_merge()
    test_cyclic_audit_end_to_end()
    test_cyclic_wrap_violation()
    test_tie_up_suggestions_basic()
    test_tie_up_suggestions_ordering()
    test_tie_up_suggestions_no_improvement()
    test_repair_plans_two_flips_needed()
    test_repair_plans_state_dedup()
    test_repair_plans_limit_and_validation()
    test_repeat_period_plain_weave()
    test_repeat_period_twill()
    test_repeat_period_asymmetric_directions()
    test_repeat_period_based_on_matrix_not_threading()
    test_repeat_period_cyclic_boundary()
    test_repeat_period_full_size_fallback()
    test_repeat_period_only_one_direction()
    test_repeat_period_divisors_only()
    test_validation()
    print("all tests passed")
