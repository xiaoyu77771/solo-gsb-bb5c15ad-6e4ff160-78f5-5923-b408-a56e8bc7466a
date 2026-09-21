"""HTTP 接口集成测试（FastAPI TestClient + 临时 SQLite 库）。

需要安装 fastapi / httpx（见 requirements.txt 及其传递依赖）；
环境中缺少这些依赖时整体跳过，而核心逻辑测试 tests/test_weave.py
不依赖它们，始终可以用 `python3 tests/test_weave.py` 运行。

直接运行：python3 tests/test_api.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 在导入 app 之前指定独立的临时数据库，避免污染本地 data/weave.db
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="weave-test-"), "test.db")
os.environ["DATABASE_PATH"] = _TMP_DB

try:
    from fastapi.testclient import TestClient  # noqa: E402
    from app.main import app  # noqa: E402
except ImportError:  # pragma: no cover - 本地最小环境下跳过
    print("skipping API tests: fastapi/httpx not installed")
    sys.exit(0)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


client = TestClient(app)

TWILL_BODY = {
    "name": "2/2 twill 8x8",
    "cyclic": True,
    "max_float": 2,
    "threading": [0, 1, 2, 3, 0, 1, 2, 3],
    "tie_up": [[1, 1, 0, 0],
               [0, 1, 1, 0],
               [0, 0, 1, 1],
               [1, 0, 0, 1]],
    "treadling": [0, 1, 2, 3, 0, 1, 2, 3],
}

# 非重复设计：质数尺寸 3x3，且逐点检查无更小周期
NON_REPEAT_BODY = {
    "name": "non-repeat",
    "cyclic": False,
    "max_float": 3,
    "threading": [0, 1, 2],
    "tie_up": [[1, 0, 1],
              [0, 1, 1],
              [1, 1, 0]],
    "treadling": [0, 1, 2],
}

# 穿综看似周期 3，但三个综框绑综列完全相同 → 交织矩阵常量，真实周期 1x1
COLLAPSE_BODY = {
    "name": "collapse",
    "cyclic": False,
    "max_float": 2,
    "threading": [0, 1, 2, 0, 1, 2],
    "tie_up": [[1, 1, 1]],
    "treadling": [0, 0],
}


def submit(body):
    resp = client.post("/designs", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_health():
    resp = client.get("/health")
    check(resp.status_code == 200 and resp.json() == {"status": "ok"},
          "health endpoint")


def test_repeat_period_twill():
    design_id = submit(TWILL_BODY)
    resp = client.get(f"/designs/{design_id}/repeat-period")
    check(resp.status_code == 200, f"GET repeat-period 200 ({resp.status_code})")
    data = resp.json()
    check(set(data.keys()) == {
        "warp_period", "weft_period", "strict_2d_repeat",
        "unit", "warp_ends", "weft_picks",
    }, "response contains the documented fields")
    check(data["warp_period"] == 4 and data["weft_period"] == 4,
          "twill 8x8 -> 4x4 unit")
    check(data["unit"] == [[1, 1, 0, 0],
                           [0, 1, 1, 0],
                           [0, 0, 1, 1],
                           [1, 0, 0, 1]], "twill unit matrix")
    check(data["strict_2d_repeat"] is True, "twill strict_2d_repeat=true")
    check(data["warp_ends"] == 8 and data["weft_picks"] == 8,
          "full dimensions 8x8")

    # unit 平铺必须与已存审计中的整幅交织矩阵完全一致
    detail = client.get(f"/designs/{design_id}").json()
    full = detail["audit"]["interlacing"]
    tiled = [
        [data["unit"][h % 4][w % 4] for w in range(8)]
        for h in range(8)
    ]
    check(tiled == full, "unit tiles stored interlacing matrix exactly")
    # 周期必须整除对应尺寸
    check(8 % data["warp_period"] == 0 and 8 % data["weft_period"] == 0,
          "periods divide full dimensions")


def test_repeat_period_non_repeat_falls_back():
    design_id = submit(NON_REPEAT_BODY)
    resp = client.get(f"/designs/{design_id}/repeat-period")
    data = resp.json()
    check((data["warp_period"], data["weft_period"]) == (3, 3),
          "no smaller period -> full dimensions")
    check(data["unit"] == [[1, 0, 1],
                           [0, 1, 1],
                           [1, 1, 0]], "unit equals full matrix")
    check(data["strict_2d_repeat"] is False,
          "full-size periods are not strict 2D repeat")


def test_repeat_period_collapse_from_matrix():
    design_id = submit(COLLAPSE_BODY)
    data = client.get(f"/designs/{design_id}/repeat-period").json()
    check((data["warp_period"], data["weft_period"]) == (1, 1),
          "analysis based on interlacing matrix: 1x1 despite threading period 3")
    check(data["unit"] == [[1]], "constant interlacing -> 1x1 unit")
    check(data["strict_2d_repeat"] is True, "1x1 unit of 6x2 matrix is strict")


def test_repeat_period_read_only_and_404():
    # 接口只读：重复调用结果一致，设计本体不变
    design_id = submit(TWILL_BODY)
    first = client.get(f"/designs/{design_id}/repeat-period").json()
    second = client.get(f"/designs/{design_id}/repeat-period").json()
    check(first == second, "repeat-period is a stable read-only computation")

    resp = client.get("/designs/999999/repeat-period")
    check(resp.status_code == 404, "unknown design -> 404")
    check(resp.json()["detail"] == "design 999999 not found", "404 detail")


if __name__ == "__main__":
    test_health()
    test_repeat_period_twill()
    test_repeat_period_non_repeat_falls_back()
    test_repeat_period_collapse_from_matrix()
    test_repeat_period_read_only_and_404()
    print("all API tests passed")
