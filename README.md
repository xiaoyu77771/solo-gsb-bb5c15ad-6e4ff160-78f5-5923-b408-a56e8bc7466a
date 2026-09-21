# 机织纹样浮长审计 API（Weave Float Audit API）

基于 **Python + FastAPI + SQLite** 的机织纹样浮长审计服务。提交经纱穿综映射、
踏板—综框绑综矩阵、逐纬踏综序列与最大浮长后，服务自动生成经纬交织矩阵，
找出所有超过上限的**经向 / 纬向连续浮长**；纹样声明循环时，自动合并矩阵
首尾跨边界的连续段。合法设计与审计结果入库，可按 ID 查询；维度不一致或
索引越界的设计将被整份拒绝（HTTP 400，不入库）。对超限设计，还可请求
**单步绑综修复建议**：逐一翻转一个绑综单元重跑审计，给出违规减少的候选；
以及**多步修复方案搜索**：在 1～3 次绑综翻转内搜索最终违规严格减少的方案
（中间状态允许违规数不下降）。还可对已存设计做**最小循环单元分析**：基于
交织矩阵求经纬两个方向的最小正周期（必须整除对应整幅尺寸）与可无缝平铺的
循环单元。

## 快速启动

单条命令（构建镜像、安装依赖、启动服务、自动建表，一步到位）：

```bash
docker compose up --build
```

启动后访问：

| 地址 | 说明 |
| --- | --- |
| `http://localhost:8000` | API 根地址 |
| `http://localhost:8000/docs` | Swagger 交互式文档 |
| `http://localhost:8000/health` | 健康检查 |

不使用 Compose 时，也可直接构建运行：

```bash
docker build -t weave-audit . && docker run -p 8000:8000 weave-audit
```

本地开发（无 Docker）：

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | 服务监听端口（Compose 中映射为主机 `8000:8000`） |
| `DATABASE_PATH` | 容器内 `/data/weave.db`，本地 `data/weave.db` | SQLite 数据库文件路径；Compose 已挂载卷 `weave-data` 持久化 |

数据库表（`designs`、`audits`）在服务启动时自动创建，无需手工迁移。

## 数据模型与约定

**请求体**（`POST /designs`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `threading` | `int[]` | 经纱穿综映射：`threading[w]` = 第 `w` 根经纱所穿综框的索引 |
| `tie_up` | `int[][]` | 绑综矩阵：`tie_up[t][s] ∈ {0,1}`，踏板 `t` 是否提升综框 `s`；行数 = 踏板数，列数 = 综框数 |
| `treadling` | `int[]` | 逐纬踏综序列：`treadling[h]` = 第 `h` 纬踩下的踏板索引 |
| `max_float` | `int ≥ 1` | 允许的最大浮长，**超过**即判违规 |
| `cyclic` | `bool`，默认 `false` | 纹样是否循环；为 `true` 时合并矩阵首尾跨边界的连续段 |
| `name` | `string`，可选 | 设计名称 |

**交织矩阵**：`interlacing[h][w] = tie_up[treadling[h]][threading[w]]`，
`1` 表示经纱在上，`0` 表示纬纱在上。

**浮长定义**：

- `warp`（经向浮长）：同一根经纱连续浮于纬纱之上，即矩阵某**列**中连续的 `1`，
  长度按纬纱数计；
- `weft`（纬向浮长）：同一根纬纱连续浮于经纱之上，即矩阵某**行**中连续的 `0`，
  长度按经纱数计。

**循环合并**（`cyclic: true`）：矩阵在经纬两个方向上首尾相接。若某列（行）
末尾的连续段与开头的连续段同向相连，则合并为一段：起点取**尾部段的起点**，
长度为两段之和（跨边界延伸）。整列（行）皆为同一浮向时只计一段，长度即
列高（行宽）。

**违规记录**字段：`direction`（`warp`/`weft`）、`yarn_index`（经纱列号或
纬纱行号）、`start`（连续段起点）、`length`（浮长）。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/designs` | 提交设计：校验 → 生成交织矩阵 → 浮长审计 → 入库，返回完整结果（201） |
| `GET` | `/designs` | 列出全部合法设计（摘要，含是否超限） |
| `GET` | `/designs/{id}` | 按 ID 查询设计及其审计结果 |
| `GET` | `/designs/{id}/audit` | 按设计 ID 单独查询审计结果 |
| `POST` | `/designs/{id}/tie-up-suggestions` | 单步绑综修复建议：逐一翻转一个绑综单元重跑审计，返回违规减少的候选 |
| `POST` | `/designs/{id}/repair-plans` | 多步绑综修复方案：1～3 次翻转内搜索最终违规严格减少的方案，支持 `max_changes`、`limit` |
| `GET` | `/designs/{id}/repeat-period` | 最小循环单元分析：基于交织矩阵求经纬两方向的最小正周期与循环单元 |
| `GET` | `/health` | 健康检查 |

### 示例：提交设计

```bash
curl -s -X POST http://localhost:8000/designs \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "2/2 twill",
    "cyclic": true,
    "max_float": 2,
    "threading": [0, 1, 2, 3, 0, 1, 2, 3],
    "tie_up": [[1,1,0,0],[0,1,1,0],[0,0,1,1],[1,0,0,1]],
    "treadling": [0, 1, 2, 3, 0, 1, 2, 3]
  }'
```

响应（201）：

```json
{
  "id": 1,
  "name": "2/2 twill",
  "cyclic": true,
  "max_float": 2,
  "shafts": 4,
  "treadles": 4,
  "warp_ends": 8,
  "weft_picks": 8,
  "threading": [0, 1, 2, 3, 0, 1, 2, 3],
  "tie_up": [[1,1,0,0],[0,1,1,0],[0,0,1,1],[1,0,0,1]],
  "treadling": [0, 1, 2, 3, 0, 1, 2, 3],
  "created_at": "2026-09-21T00:00:00Z",
  "audit": {
    "exceeds": false,
    "interlacing": [[1,1,0,0,1,1,0,0], "..."],
    "violations": []
  }
}
```

超示例（跨边界合并后超限）：`threading=[0]`、`tie_up=[[1],[0]]`、
`treadling=[0,0,1,0,0]`、`max_float=2`、`cyclic=true` →

```json
{"direction": "warp", "yarn_index": 0, "start": 3, "length": 4}
```

### 查询

```bash
curl -s http://localhost:8000/designs/1        # 设计 + 审计结果
curl -s http://localhost:8000/designs/1/audit  # 仅审计结果
curl -s http://localhost:8000/designs          # 全部设计摘要
```

### 单步绑综修复建议

`POST http://localhost:8000/designs/{id}/tie-up-suggestions`：读取已入库设计，
逐一翻转 `tie_up` 的一个 0/1 单元，并按原 `cyclic`、`max_float` 重跑完整审计；
仅返回**违规总数严格减少**的候选。接口只读计算，**不修改原设计**；设计不存在
返回 404，无改善时返回空列表 `[]`。

查询参数：`limit`（可选，1～50，默认 50）——返回候选数上限。

每个候选包含：

| 字段 | 说明 |
| --- | --- |
| `treadle` | 踏板索引（`tie_up` 行号） |
| `shaft` | 综框索引（`tie_up` 列号） |
| `new_value` | 该单元翻转后的新值（0 或 1） |
| `remaining_violations` | 翻转后完整审计的剩余违规总数 |
| `affected_points` | 受影响交织点数（翻转前后交织矩阵中取值变化的单元数） |

结果按 `remaining_violations` → `affected_points` → `treadle` → `shaft`
升序稳定排序。

```bash
curl -s -X POST 'http://localhost:8000/designs/1/tie-up-suggestions?limit=5'
```

响应（200）：

```json
[
  {"treadle": 0, "shaft": 1, "new_value": 0, "remaining_violations": 2, "affected_points": 6},
  {"treadle": 1, "shaft": 0, "new_value": 1, "remaining_violations": 3, "affected_points": 1}
]
```

### 多步绑综修复方案

`POST http://localhost:8000/designs/{id}/repair-plans`：读取已入库设计，
在最多 `max_changes`（1～3，默认 **2**）次 `tie_up` 0/1 单元翻转内广度优先
搜索修复方案。**中间状态允许违规数不下降**（容许先变差或持平），但方案终态
的违规总数必须**严格少于原设计**。搜索按绑综状态（整个 `tie_up` 的 0/1 位图）
去重，同一单元不会在一条翻转序列内重复翻转；等价终态（相同绑综状态）只保留
排序最优的翻转序列。接口只读计算，**不修改原设计**；设计不存在返回 404，
没有改善方案时返回空列表 `[]`。

查询参数：

| 参数 | 范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `max_changes` | 1～3 | `2` | 最多翻转绑综单元的次数 |
| `limit` | 1～50 | `50` | 返回方案数上限 |

方案排序键（依次升序，稳定排序）：最终违规数 → 改动数（翻转次数）→
最终交织矩阵相对原矩阵的**变化点数** → 翻转序列字典序（按
`(treadle, shaft)` 依次比较）。

每个方案包含：

| 字段 | 说明 |
| --- | --- |
| `changes` | 翻转次数（1～`max_changes`） |
| `final_violations` | 最终违规总数（严格小于原设计） |
| `changed_points` | 最终交织矩阵相对原矩阵取值变化的点数 |
| `steps[]` | 逐步翻转：`step`（从 1 起）、`treadle`、`shaft`、`old_value`、`new_value`、`violations_after`（该步翻转后的违规总数，允许不下降） |
| `violations[]` | 最终违规列表（字段同审计结果） |
| `interlacing[][]` | 最终交织矩阵（1=经纱在上，0=纬纱在上） |

```bash
# 默认最多翻转 2 次，最多返回 50 个方案
curl -s -X POST http://localhost:8000/designs/2/repair-plans

# 最多 3 次翻转，只取前 5 个方案
curl -s -X POST 'http://localhost:8000/designs/2/repair-plans?max_changes=3&limit=5'
```

响应（200）：

```json
[
  {
    "changes": 2,
    "final_violations": 0,
    "changed_points": 2,
    "steps": [
      {"step": 1, "treadle": 0, "shaft": 0, "old_value": 1, "new_value": 0, "violations_after": 1},
      {"step": 2, "treadle": 3, "shaft": 0, "old_value": 1, "new_value": 0, "violations_after": 0}
    ],
    "violations": [],
    "interlacing": [[0], [1], [1], [0], [1], [1]]
  }
]
```

### 最小循环单元分析

`GET http://localhost:8000/designs/{id}/repeat-period`：读取已入库设计，
重新生成**交织矩阵**，在经、纬两个方向寻找能**无缝平铺**整个矩阵的最小正
周期，并返回最小循环单元（完全组织）。接口只读计算，**不修改原设计**；
设计不存在返回 404。

分析规则：

- 比较**直接基于交织矩阵的逐点取值**，而不是分别检查 `threading` /
  `treadling` 序列：不同综框（踏板）若在绑综中等价，交织结果会比穿综
  （踏综）序列更早重复，反之序列的表观周期也不能直接当作矩阵周期；
- `warp_period`（经向周期）= 单元包含的**经纱数（列数）**，沿行方向平铺，
  必须整除 `warp_ends`；`weft_period`（纬向周期）= 单元包含的**纬纱数
  （行数）**，沿列方向平铺，必须整除 `weft_picks`。只在整幅尺寸的**因数**
  中寻找周期，保证整数次平铺恰好铺满整幅（视觉上重复但不整除尺寸的候选
  不算合法周期）；
- 周期判定使用下标取模逐点比较（`matrix[h][w] == matrix[h][w % p]` 等）。
  在“周期整除尺寸”的前提下，这与平移后跨过末列/首列（末行/首行）边界的
  循环比较完全等价，因此**循环纹样首尾相接处的边界也被正确检验**；
- 不存在小于整幅的周期时，对应方向返回完整尺寸（`warp_period = warp_ends`
  或 `weft_period = weft_picks`），`unit` 即整幅矩阵；
- `strict_2d_repeat` 仅当**两个方向**的周期都严格小于整幅尺寸时为 `true`
  （矩阵确为一个小于整幅的二维单元的重复；任一方向退化、或矩阵只有一行/
  一列时均为 `false`）。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `warp_period` | 经向最小正周期：单元经纱数（列数），整除 `warp_ends`；无更小周期时等于 `warp_ends` |
| `weft_period` | 纬向最小正周期：单元纬纱数（行数），整除 `weft_picks`；无更小周期时等于 `weft_picks` |
| `unit` | 最小循环单元交织矩阵（`weft_period` 行 × `warp_period` 列，1=经纱在上，0=纬纱在上），两方向平铺即复现整幅 |
| `strict_2d_repeat` | 是否为严格二维重复（两方向周期都严格小于整幅尺寸） |
| `warp_ends` | 整幅经纱数（交织矩阵列数） |
| `weft_picks` | 整幅纬纱数（交织矩阵行数） |

```bash
curl -s http://localhost:8000/designs/1/repeat-period
```

响应（200，2/2 斜纹 8×8 → 4×4 单元）：

```json
{
  "warp_period": 4,
  "weft_period": 4,
  "strict_2d_repeat": true,
  "unit": [
    [1, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 1],
    [1, 0, 0, 1]
  ],
  "warp_ends": 8,
  "weft_picks": 8
}
```

无更小周期时（3×3 非重复设计）：

```json
{
  "warp_period": 3,
  "weft_period": 3,
  "strict_2d_repeat": false,
  "unit": [[1, 0, 1], [0, 1, 1], [1, 1, 0]],
  "warp_ends": 3,
  "weft_picks": 3
}
```

### 拒绝情形（HTTP 400，整份设计不入库）

- 绑综矩阵非矩形（各行长度不一致）或含非 0/1 值；
- 穿综索引越界：`threading[i] ∉ [0, 综框数)`；
- 踏综索引越界：`treadling[i] ∉ [0, 踏板数)`；
- 空穿综 / 空踏综 / 空绑综矩阵、`max_float < 1`。

```json
{"detail": "threading[3]=9 out of range: valid shaft index is [0, 4)"}
```

## 项目结构

```
app/
  main.py    # FastAPI 路由与启动钩子（启动时建表）
  weave.py   # 交织矩阵生成与浮长审计核心逻辑
  db.py      # SQLite 持久层
  models.py  # Pydantic 请求/响应模型
tests/
  test_weave.py  # 核心逻辑单元测试：python3 tests/test_weave.py
  test_api.py    # HTTP 接口集成测试（TestClient）：python3 tests/test_api.py
Dockerfile
docker-compose.yml
requirements.txt
```
