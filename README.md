# 乐迪机器人 API 与开发接口

设备是一台 MTK 平台的定制 Android 机器人（乐迪）。改造 App `com.ledi.agent` 常驻设备，
对外提供一个 HTTP 服务（默认端口 8899），把三套控制面统一成一套接口。

本仓库只收录**接口文档 + 机器可读端点清单 + 文档生成器**，不含改造工程源码。

## 1. 控制面

| 面 | 入口 | 实际落到 |
|---|---|---|
| 自研 HTTP API | `http://<IP>:8899/...` | App 内各控制器（AgentService 及各单例） |
| 原厂 SDK | `POST /sdk/*`（HTTP 封装） | `EngineService` / `Function.SystemMethod` / 系统广播 |
| 串口运动协议 | 由 `/motor`、`/pose` 间接使用 | 12 字节帧 → `/dev/ttyMT0` @ 115200 |

## 2. 连接方式

| 通道 | 说明 |
|---|---|
| HTTP | `http://192.168.1.8:8899`（IP 随网络变化，用 `GET /netinfo` 查） |
| 网页控制台 | 设备的 HTTP 服务自带，浏览器打开 `http://<IP>:8899/`；该页面在屏保闸之前被接住，屏保期间也能打开 |
| 无线 ADB | 5555 端口，`GET /adbwifi` 查状态与 scrcpy 命令 |
| 蓝牙 SPP | 没有网络时的兜底通道，路径 / 参数 / 返回与 HTTP 完全一致，见 `docs/python-client.md` |

## 3. 通用约定

下面是摘要；**完整版以生成物 [`docs/http-api.md`](docs/http-api.md#通用约定) 为真源**
（那段文字同样由 `tools/gen_docs.py` 产出，改口径要改生成器，不要在两处各写一份）。

1. **HTTP 状态码不可用作判据。** 本 ROM 的 HttpBridge 一律返回 200，错误响应同样是 200。
   判成功 / 失败只看响应 body 顶层：失败形如 `{"error":"..."}`，部分写操作形如 `{"ok":false,...}`。
2. **屏保闸。** 进入屏保或深睡后，白名单外的端点统一返回 `{"error":"sleeping"}`。
   白名单共 56 条 + `GET /console/` 前缀，见 `docs/security.md`。
3. **参数来源等价。** `GET /x?a=1` 与 `POST /x` + `{"a":1}` 等价，路由统一用 `field(body, query, key)` 取值。
4. **权限。** 写类与红线类能力受 `Abilities` 矩阵约束，拒绝形如 `{"error":"forbidden ..."}`。
   边界用 `GET /abilities` 查。

## 4. 文档

| 文件 | 内容 |
|---|---|
| [`docs/http-api.md`](docs/http-api.md) | 199 个 HTTP 端点全表（自动生成） |
| [`docs/motion.md`](docs/motion.md) | 运动控制：动作、姿态文件、单帧直发、串口帧、角度回读 |
| [`docs/voice.md`](docs/voice.md) | 语音：唤醒、识别、TTS、对话、意图、常听、多轮思考 |
| [`docs/display.md`](docs/display.md) | 显示：表情、情绪、灯光、屏幕、音量 |
| [`docs/system.md`](docs/system.md) | 系统：状态、网络、进程、屏保与深睡、诊断自检 |
| [`docs/factory-sdk.md`](docs/factory-sdk.md) | 原厂 SDK 可调用面（动作引擎 / 系统广播 / 事件 / 常量类） |
| [`docs/security.md`](docs/security.md) | 权限矩阵、屏保白名单、判定口径 |
| [`docs/python-client.md`](docs/python-client.md) | Python 客户端 `AgentLink` |
| [`api/endpoints.json`](api/endpoints.json) · [`api/endpoints.csv`](api/endpoints.csv) | 机器可读端点清单 |

## 5. 快速开始

```bash
BASE=http://192.168.1.8:8899
H='Content-Type: application/json'

curl -s $BASE/health
curl -s $BASE/status

# 说话 / 动作 / 表情 / 灯
curl -s -X POST -H "$H" -d '{"text":"你好"}'                  $BASE/say
curl -s -X POST -H "$H" -d '{"name":"hug"}'                   $BASE/motion
curl -s -X POST -H "$H" -d '{"name":"happy"}'                 $BASE/face
curl -s -X POST -H "$H" -d '{"color":"blue","action":"on"}'   $BASE/led

# 舵机：单帧角度直发 + 回读
curl -s -X POST -H "$H" -d '{"j1":20,"j2":0,"j3":0,"ms":600}' $BASE/motor
curl -s $BASE/motorpos

# 能力与边界
curl -s $BASE/abilities
curl -s "$BASE/caps?q=握手"

# 原厂引擎
curl -s -X POST -H "$H" -d '{"names":["hug","handshake"],"delay":200}' $BASE/sdk/series
curl -s -X POST -H "$H" -d '{"bpm":120}'                               $BASE/sdk/bpm
curl -s $BASE/sdk/stat
```

## 6. 仓库结构

```
.
├── README.md
├── docs/                 接口文档（http-api.md 是生成物）
├── api/                  endpoints.json / endpoints.csv（生成物）
└── tools/
    ├── extract_api.py    从 CommandRouter.java 提取端点 -> api/endpoints.json
    ├── gen_docs.py       endpoints.json -> docs/http-api.md + api/endpoints.csv
    ├── sanitize.py       生成物脱敏规则表 + 残留扫描（公开版措辞的唯一真源）
    ├── localpaths.py     本机路径注入（读不入库的 .local/paths.json）
    └── selfcheck.py      文件树 / README 链接 / 端点计数 / 脱敏 / 文档引用
```

## 7. 维护

重新生成（需要指向改造工程里的 `CommandRouter.java`）：

```bash
python tools/extract_api.py --src <path>/CommandRouter.java --json api/endpoints.json
python tools/gen_docs.py
```

两份源码侧文件（`CommandRouter.java`、端点清单）**不在本仓库内**，也不想每次敲路径的话，
把它们写进 `.local/paths.json`（该目录已 gitignore，不会入库）：

```json
{ "router_java": "<path>/CommandRouter.java", "route_inventory": "<path>/route_inventory.json" }
```

自检：

```bash
python tools/selfcheck.py
# 与改造工程的端点清单对差（清单在工程里，不在本仓库；放进 .local/paths.json 可免参数）：
python tools/selfcheck.py --inv <path>/route_inventory.json
```

`docs/http-api.md` 与 `api/*` 是生成物，不要手改。要改产物里的**措辞**（脱敏），
改 `tools/sanitize.py` 的规则表再重跑；两个生成器都带脱敏闸，规则没盖到的内部引用会直接报错退出。

## 8. 已知不精确处

- HTTP 端点表由脚本从源码机械提取。参数列是源码里 `field(body, query, "k")` 的出现集合，
  少数端点可能带上邻近键；关键用法以源码为准。
- 舵机角度可以回读，但回读值是 12 位编码器计数，角度是按实测拟合换算出来的近似值，
  0..90° 段线性、90° 以上压缩，标定随机器走。**不能作为控制回路**。见 `docs/motion.md`。
- 原厂在线动作库与 OTA 链路指向的服务器已停服，不可用。
- 屏幕背光物理不可调。

## 9. 说明

- 所有逆向结论来自自有设备的原厂 APK 字节码解析与真机验证。
- 请勿对外分发重打包的原厂安装包。
- 关机 / 重启 / 关闭 ADB / 冻结进程等操作会直接影响设备可用性，执行前需确认存在回退通道。
