# -*- coding: utf-8 -*-
"""
读 api/endpoints.json -> 生成 docs/http-api.md 与 api/endpoints.csv。
先跑 tools/extract_api.py，再跑本脚本。无参数。
落盘前会过 `tools/sanitize.py` 的脱敏规则，并**自检产物里没有内部引用残留**（有就报错退出）。
"""
import os, re, json, csv, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sanitize

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根

DOMAINS = [
    ("sys",   "系统 / 设备",   "状态、网络、ADB、屏幕、重启、进程与冻结"),
    ("motion", "运动 / 姿态",  "动作播放、舵机直控、姿态文件、姿态数学"),
    ("voice", "语音 / 对话",   "云 ASR、唤醒、对话、TTS、意图、AI 大脑"),
    ("sense", "传感 / 交互",   "电量、头顶键、触摸注入、传感器、声源定位"),
    ("media", "媒体 / 显示",   "音量、灯光、屏幕图片与旋转"),
    ("cap",   "AI 能力层",     "能力索引、权限矩阵、情绪、记忆、性格、工作流、思考"),
    ("sdk",   "原厂 SDK 直调", "EngineService 动作 / SystemMethod 灯光电源 / 事件流"),
    ("probe", "自检 / 探针",   "各引擎纯 JVM 自检、崩溃盾验收、启动日志"),
    ("ui",    "屏保 / 界面",   "屏保与深睡控制、控制台页面"),
]


def collapse(s):
    s = (s or "").strip()
    s = s.replace("\r", " ").replace("\n", " · ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s


BANNER = re.compile(r"^[=\-*·\s]+$")
BANNER_INLINE = re.compile(r"^[=\-]{3,}\s*(.*?)\s*[=\-]{3,}$")


DECOR = "★☆✅⚠⛔✗✔"
STOP_WORDS = ("用户 20", "用户2", "为什么")


def clean_desc(e, limit=180):
    """把源码注释压成「是什么 + 怎么用」：剥掉 ===== 横幅、装饰符号与设计来由。"""
    raw = sanitize.scrub(e.get("comment") or "").strip()   # 兜底再脱敏一次（幂等）
    parts = []
    for ln in raw.split("\n"):
        t = ln.strip()
        if not t or BANNER.match(t):
            continue
        m = BANNER_INLINE.match(t)
        if m:
            t = m.group(1)
            if not t:
                continue
        parts.append(t)
    segs = []
    for seg in collapse(" · ".join(parts)).split(" · "):
        if any(w in seg for w in STOP_WORDS):
            break
        segs.append(seg)
    s = collapse(" · ".join(segs))
    s = "".join(ch for ch in s if ch not in DECOR)   # 去掉装饰符号（保留其后的文字）
    s = collapse(s)
    if not s:
        h = e.get("hint") or ""
        s = ("`" + h + "`") if h and h != "SleepMode.touch()" else "—"
    if len(s) > limit:
        s = s[:limit - 1] + "…"
    return s


def summary(e):
    """表列用的短说明。"""
    return clean_desc(e).replace("|", "\\|")


def main():
    eps = json.load(open(os.path.join(HERE, "api", "endpoints.json"), encoding="utf-8"))
    by_dom = {}
    for e in eps:
        by_dom.setdefault(e["domain"], []).append(e)

    # ---------- CSV（机器可读） ----------
    apidir = os.path.join(HERE, "api")
    os.makedirs(apidir, exist_ok=True)
    with open(os.path.join(apidir, "endpoints.csv"), "w", encoding="utf-8",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["method", "path", "domain", "params", "summary", "hint"])
        for e in eps:
            m, p = e["endpoint"].split(" ", 1)
            w.writerow([m, p, e["domain"], " ".join(e["params"]),
                        clean_desc(e, 240), e["hint"]])

    # ---------- Markdown（人读） ----------
    docs = os.path.join(HERE, "docs")
    os.makedirs(docs, exist_ok=True)
    L = []
    L.append("# HTTP 控制接口参考\n")
    L.append("> 机器人内置 HTTP 服务（默认端口 8899）的全部 %d 条端点。" % len(eps))
    L.append("> 本文件由 `tools/extract_api.py` + `tools/gen_docs.py` 从 `CommandRouter.java` "
             "自动生成，不要手改。\n")
    L.append("## 通用约定\n")
    L.append("- **请求**：`GET /path?k=v` 或 `POST /path` + JSON body。两者字段等价，"
             "路由里统一用 `field(body, query, key)` 取值。")
    L.append("- **响应**：一律 `HTTP 200` + JSON。**成功与否只看 body 顶层**，不要信 HTTP 码 —— "
             "本 ROM 的 HttpBridge 无论对错都回 200。失败形如 `{\"error\":\"...\"}`。")
    L.append("- **屏保闸**：进入屏保/深睡后，白名单外的端点统一被拦（返回 "
             "`{\"error\":\"sleeping\"}`）。白名单见 `SleepGate`（56 条 + `GET /console/` 前缀）。")
    L.append("- **权限**：写类/红线类能力受 `Abilities` 权限矩阵约束，拒绝形如 `{\"error\":\"forbidden ...\"}`。\n")
    L.append("## 端点分布\n")
    L.append("| 域 | 端点数 | 覆盖 |")
    L.append("|---|---|---|")
    for key, name, desc in DOMAINS:
        n = len(by_dom.get(key, []))
        if n:
            L.append("| `%s` | %d | %s |" % (key, n, desc))
    other = set(by_dom) - {d[0] for d in DOMAINS}
    for k in sorted(other):
        L.append("| `%s` | %d | |" % (k, len(by_dom[k])))
    L.append("")

    for key, name, desc in DOMAINS:
        rows = sorted(by_dom.get(key, []), key=lambda e: (e["endpoint"].split(" ")[1],
                                                          e["endpoint"].split(" ")[0]))
        if not rows:
            continue
        L.append("## %s（`%s`，%d）\n" % (name, key, len(rows)))
        L.append("> %s\n" % desc)
        L.append("| 方法 | 路径 | 参数 | 说明 |")
        L.append("|---|---|---|---|")
        for e in rows:
            m, p = e["endpoint"].split(" ", 1)
            d = summary(e)
            params = "`" + "`, `".join(e["params"]) + "`" if e["params"] else "—"
            L.append("| `%s` | `%s` | %s | %s |" % (m, p, params, d))
        L.append("")

    for k in sorted(other):
        rows = sorted(by_dom[k], key=lambda e: e["endpoint"])
        L.append("## `%s`（%d）\n" % (k, len(rows)))
        L.append("| 方法 | 路径 | 参数 | 说明 |")
        L.append("|---|---|---|---|")
        for e in rows:
            m, p = e["endpoint"].split(" ", 1)
            d = summary(e)
            params = "`" + "`, `".join(e["params"]) + "`" if e["params"] else "—"
            L.append("| `%s` | `%s` | %s | %s |" % (m, p, params, d.replace("|", "\\|")))
        L.append("")

    out = os.path.join(docs, "http-api.md")
    open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print("-> %s (%d 端点)" % (out, len(eps)))
    print("-> %s" % os.path.join(apidir, "endpoints.csv"))

    # ★ 脱敏闸：产物里绝不允许出现本机路径 / 内部引用（规则表在 tools/sanitize.py）。
    #   规则没盖到就停下补规则 —— 而不是把脏内容生成出来等着有人发现。
    bad = []
    for f in (out, os.path.join(apidir, "endpoints.csv")):
        for h in sanitize.scan_file(f, HERE):
            bad.append((os.path.relpath(f, HERE), h))
    if bad:
        for rel, (why, frag, _ctx) in bad[:12]:
            print("  x %-22s %s: %r" % (rel, why, frag[:60]))
        sys.exit("★ 生成物里仍有 %d 处未脱敏内容（见上）—— 请在 tools/sanitize.py 补规则后重跑" % len(bad))
    print("-> 脱敏自检：0 处残留")


if __name__ == "__main__":
    main()
