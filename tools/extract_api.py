# -*- coding: utf-8 -*-
"""
从 CommandRouter.java 机械提取每个端点的：方法 / 路径 / 前置注释 / 参数键 / 归属域。
不手抄 —— 真源只有一个，文档跟着代码走。
用法：
    python tools/extract_api.py --src <path/to/CommandRouter.java> [--json api/endpoints.json]

`--src` 未给时按 `LEDI_ROUTER_JAVA` 环境变量 → 本仓库 `.local/paths.json` 依次找。
★ `CommandRouter.java` 属于机器人改造工程源码，**不在本仓库内**；本仓库只收「提取结果 +
生成器」，所以想让文档跟着代码重跑，需要你自己指向那份源码。

★ 注释在落盘前会过一遍 `tools/sanitize.py`（公开前脱敏）—— 产物里的措辞不受源码注释
  的「内部说法」影响；要改产物里的话，改那张规则表，不要手改生成物。
"""
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sanitize
import localpaths

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根

# CommandRouter.java 的路径来源优先级：--src > 环境变量 LEDI_ROUTER_JAVA > .local/paths.json。
# ★★ 为什么要留「本地配置」这一层：只认 --src 时，忘了传就会**静默不更新** endpoints.json，
#    而 gen_docs.py 拿旧 json 照样生成一份"看着正常"的文档 —— 这正是本项目最怕的假绿灯
#    （产物存在 ≠ 内容更新）。真机上已抓到过一次这个静默失败。
#    但本机绝对路径**不能写进这个仓库**（公开仓库里不该出现任何人的机器目录），
#    所以路径放在 .local/paths.json（已 gitignore）里，见 tools/localpaths.py。
DEFAULT_SRC = localpaths.router_java()


def opt(name, default=""):
    """取 `--name value` 形式的命令行参数（缺省返回 default）。"""
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default

EP_RE = re.compile(r'"((?:GET|POST|PUT|DELETE) /[\w/.\-]*)"\.equals\(act\)')
FIELD_RE = re.compile(r'field\(\s*body\s*,\s*query\s*,\s*"([^"]+)"')
LOCALFIELD_RE = re.compile(r'(?:field|listCsv)\([^,]+,[^,]+,\s*"([^"]+)"')
DOMAIN_RE = re.compile(r'private String (\w+)Routes\(')
TABLE_RE = re.compile(r'TABLE\.put\("((?:GET|POST|PUT|DELETE) /[\w/.\-]*)"\s*,\s*"(\w+)"\)')


def clean_comment(lines):
    out = []
    for l in lines:
        s = l.strip()
        if s.startswith("//"):
            out.append(s[2:].strip())
        elif s.startswith("*") and not s.startswith("*/"):
            out.append(s[1:].strip())
        elif s.startswith("/*"):
            out.append(s[2:].strip())
    return "\n".join(out).strip()


CALL_RE = re.compile(r'([A-Z][A-Za-z0-9_]*)\.([a-z][A-Za-z0-9_]*)\(|"ok"\s*:\s*(true|false)')


def behavior_hint(body_lines):
    """端点体里最有信息量的一行 —— 优先取 return 语句，其次取首个 Class.method( 调用。"""
    text = "\n".join(body_lines)
    # 1) 优先：return 语句里带调用的
    for m in re.finditer(r'return\s+([^;\n]{4,120});', text):
        seg = m.group(1).strip()
        if re.search(r'[A-Za-z_]\w*\.\w+\(|"[a-z_]', seg):
            return "return " + seg[:100]
    # 2) 其次：首个 Xxx.yyy( 调用
    cm = re.search(r'([A-Z][A-Za-z0-9_]*)\.([a-z][A-Za-z0-9_]*)\(', text)
    if cm:
        return "%s.%s()" % (cm.group(1), cm.group(2))
    # 3) 再次：任一 return 片段
    for m in re.finditer(r'return\s+([^;\n]{4,120});', text):
        return "return " + m.group(1).strip()[:100]
    return ""


def main():
    src = opt("--src", DEFAULT_SRC)
    if not src:
        sys.exit("缺少源码路径：请用 --src <CommandRouter.java> 或设置环境变量 LEDI_ROUTER_JAVA")
    if not os.path.isfile(src):
        sys.exit("找不到 CommandRouter.java：%s" % src)
    print("提取源：%s" % src)
    txt = open(src, encoding="utf-8", errors="replace").read()
    lines = txt.split("\n")

    # 1) 端点 -> 域（从 TABLE）
    dom_of = {}
    for ep, dom in TABLE_RE.findall(txt):
        dom_of[ep] = dom

    # 2) 方法 -> 域（用于端点无 TABLE 项时的兜底：取最近一个 Routes 方法名）
    method_spans = []
    for m in DOMAIN_RE.finditer(txt):
        method_spans.append((m.start(), m.group(1)))

    def dom_at(pos):
        cur = None
        for p, name in method_spans:
            if p < pos:
                cur = name
            else:
                break
        return cur

    # 3) 逐行找端点条件，回溯紧邻上方的注释块
    # 先标出所有「端点条件行」的索引，用于把每个端点体切到下一个端点之前（防参数串行）
    ep_lines = [idx for idx, l in enumerate(lines) if EP_RE.search(l)]
    eps = []
    seen = set()
    for i, l in enumerate(lines):
        for ep in EP_RE.findall(l):
            if ep in seen:
                continue
            seen.add(ep)
            # 向上找注释块（允许中间夹空行）；支持 // 与 /* */ 两种
            j = i - 1
            buf = []
            blanks = 0
            if j >= 0 and lines[j].strip().endswith("*/"):
                k = j
                while k >= 0 and "/*" not in lines[k]:
                    k -= 1
                buf = lines[k:j + 1]
                j = k - 1
            while j >= 0:
                s = lines[j].strip()
                if s.startswith("//"):
                    buf.insert(0, lines[j])
                    blanks = 0
                    j -= 1
                elif s == "" and blanks < 1:
                    blanks += 1
                    j -= 1
                else:
                    break
            # 端点体：从下一行到**下一个端点条件之前**（最多 40 行），
            # 并在遇到闭合 `}`（本 if 块结束）时立即停 —— 防内联块/长块越界。
            nxt = [x for x in ep_lines if x > i]
            end = (min(nxt) if nxt else i + 40)
            end = min(end, i + 40)
            stop = end
            for k in range(i + 1, end):
                if lines[k].strip() == "}":
                    stop = k
                    break
            body = lines[i:stop]
            tail = "\n".join(body)
            keys = sorted(set(LOCALFIELD_RE.findall(tail)))
            hint = behavior_hint(body[1:])
            dom = dom_of.get(ep) or dom_at(sum(len(x) + 1 for x in lines[:i]))
            eps.append({
                "endpoint": ep,
                "domain": dom,
                "comment": clean_comment(buf),
                "params": keys,
                "hint": hint,
            })
    # 未在源码里出现的（只在白名单/前缀路由）补上
    for ep, dom, note in (
        ("GET /programmer", "probe", "仅在屏保白名单，无独立派发分支"),
        ("POST /kws", "probe", "仅在屏保白名单，无独立派发分支"),
        ("GET /console/", "ui", "前缀路由：返回控制台页面 assets/console.html（不受屏保闸）"),
    ):
        if ep not in seen:
            eps.append({"endpoint": ep, "domain": dom, "comment": note,
                        "params": [], "hint": ""})
    # sleep/deepsleep 由 handle 内联块直接 return（不经 TABLE 派发）
    for e in eps:
        if e["domain"] is None:
            e["domain"] = "ui"
            if not e["comment"]:
                e["comment"] = "屏保 / 深睡控制（内联块，不经查表派发）"

    # ★ 脱敏：所有注释统一过一遍规则表（幂等；放这里是为了把所有入口都盖上）
    for e in eps:
        e["comment"] = sanitize.scrub(e["comment"])

    # ★ 数量闸：提取到 0 条一律报错退出 —— 否则后面 gen_docs 会拿旧 json 生成"看着正常"
    #   的文档，而没人知道源根本没被读到（假绿灯）。
    if not eps:
        sys.exit("★ 提取到 0 条端点 —— 源读到了但没匹配上，禁止继续（别让旧 json 冒充新结果）")

    # ★ 脱敏闸：规则没覆盖到的新内部说法不许流出去。命中 = 规则表漏了一条，停下来补规则，
    #   而不是带着它继续生成（这条闸门比"记得改"可靠）。
    dirty = [(e["endpoint"], h) for e in eps for h in sanitize.scan_text(e.get("comment") or "", HERE)]
    if dirty:
        for ep, (why, frag, _ctx) in dirty[:12]:
            print("  x %-18s %s: %r" % (ep, why, frag[:60]))
        sys.exit("★ 注释里还有未脱敏的内部引用（见上 %d 处）—— 请在 tools/sanitize.py 补规则后重跑" % len(dirty))
    eps.sort(key=lambda e: (e["endpoint"].split(" ")[1], e["endpoint"].split(" ")[0]))
    print("提取端点 %d 条" % len(eps))
    from collections import Counter
    print("按域：", dict(Counter(e["domain"] for e in eps)))
    print("有注释：", sum(1 for e in eps if e["comment"]), "/", len(eps))
    out = opt("--json")
    if out:
        # newline="\n"：Windows 上别把 \n 写成 \r\n（会凭空多出「行数」个字节）；
        # 末尾补一个换行：POSIX 文本文件的规矩，也让 git diff 不再出现
        # "\ No newline at end of file" 这种噪声。
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(eps, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("-> " + out)
    else:
        print("（未写文件；加 --json api/endpoints.json 落盘）")
    for e in eps[:5]:
        print("  ", e["endpoint"], "|", e["domain"], "|", e["params"], "|", e["comment"][:60].replace("\n", " "))


if __name__ == "__main__":
    main()
