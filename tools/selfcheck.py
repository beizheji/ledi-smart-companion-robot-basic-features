# -*- coding: utf-8 -*-
"""仓库自检：文件齐备 / README 链接有效 / 端点在各产物中一致 / 公开前脱敏无残留。

用法：
    python tools/selfcheck.py [--inv <path/to/route_inventory.json>]

`--inv` 用于「与改造工程的端点清单对差」。该清单**不在本仓库内**；未提供时自动跳过对差项
（其余检查照常执行）。也可以把路径写进本仓库的 `.local/paths.json`（不随仓库分发），
见 `tools/localpaths.py`。

判据（每项都会打印 PASS/FAIL，末尾给通过数）：
  1  文件树
  2  README 内部链接无失效
  3  endpoints.json 条数；有基准时与工程清单对差（缺 [] / 多 []）
  4  http-api.md 与 json 自洽（或与基准一致）
  5  endpoints.csv 数据行数 == json 条数
  6  ★ 脱敏：全仓库 0 处残留（本机路径 / 内部引用 / 指向仓库外的文档）
  7  ★ 手写文档里引用的端点路径都真实存在
  8  ★ docs/ 之间的相对链接无失效
"""
import os, re, json, csv, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sanitize
import localpaths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根

OK = []
FAIL = []


def check(name, passed, detail=""):
    (OK if passed else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name, ("  " + detail) if detail else ""))


def opt(name, default=""):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


# 文档里允许出现、但**不是**本仓库端点表的路径（系统路径 / 语法占位），逐条给理由
DOC_PATH_ALLOW = {
    "/sdcard": "设备上的文件路径，不是 HTTP 端点",
    "/dev/ttyMT0": "串口设备节点",
    "/data": "设备上的目录",
    "/system": "设备上的目录",
    "/proc": "设备上的目录",
    "/console/": "前缀路由（GET /console/ 本身在表里，这里放行子路径说明）",
}


def main():
    inv_path = opt("--inv", localpaths.route_inventory())

    print("=== 文件树 ===")
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in ("__pycache__", ".git", ".local")]
        for f in sorted(fn):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            print("  %-40s %8d B" % (rel, os.path.getsize(p)))

    print("\n=== 判据 ===")

    rd = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    links = re.findall(r"\]\(([^)]+)\)", rd)
    # 带锚点的链接（docs/http-api.md#通用约定）只判文件在不在，锚点不参与
    bad = [l for l in links
           if not l.startswith("http") and not os.path.exists(os.path.join(ROOT, l.split("#")[0]))]
    check("README 内部链接", not bad, "%d 条，失效 %s" % (len(links), bad))

    eps = json.load(open(os.path.join(ROOT, "api", "endpoints.json"), encoding="utf-8"))
    eset = {e["endpoint"] for e in eps}
    paths = {e["endpoint"].split(" ", 1)[1] for e in eps}
    print("  endpoints.json %d 条" % len(eset))

    inv = None
    if inv_path and os.path.isfile(inv_path):
        inv = set(json.load(open(inv_path, encoding="utf-8"))["endpoints"])
        check("与工程清单对差（%d 条）" % len(inv), set(e["endpoint"] for e in eps) == inv,
              "缺 %s / 多 %s" % (sorted(inv - eset), sorted(eset - inv)))
    else:
        print("  （未提供 --inv 且 .local/paths.json 里没有清单，跳过与工程清单对差）")

    md = open(os.path.join(ROOT, "docs", "http-api.md"), encoding="utf-8").read()
    if inv is None:
        got = set(re.findall(r"^\| `(?:GET|POST|PUT|DELETE)` \| `(/[^`]*)`", md, re.M))
        miss = sorted(paths - got)
        check("http-api.md 自洽（无基准时的降级判据）", not miss,
              "表内路径 %d 条，json 里未出现的 %s" % (len(got), miss[:5]))
    else:
        miss = [e for e in inv if ("`" + e.split(" ")[1] + "`") not in md]
        check("http-api.md 覆盖工程清单", not miss, "缺失 %d %s" % (len(miss), miss[:5]))
    print("  http-api.md 域小计行：%d" % len(re.findall(r"^## .*（`\w+`，\d+）", md, re.M)))

    rows = list(csv.DictReader(open(os.path.join(ROOT, "api", "endpoints.csv"), encoding="utf-8")))
    check("endpoints.csv 行数 == json 条数", len(rows) == len(eps),
          "csv %d / json %d" % (len(rows), len(eps)))

    from collections import Counter
    c = Counter(e["domain"] for e in eps)
    print("  按域：%s 合计 %d" % (dict(c), sum(c.values())))

    # ★ 判据 6：脱敏残留
    badf = sanitize.scan_files(ROOT)
    n = sum(len(v) for v in badf.values())
    check("脱敏残留扫描（本机路径 / 内部引用 / 仓库外文档）", not badf,
          "0 处" if not badf else "%d 处，见 tools/sanitize.py 的规则表" % n)
    for rel, h in sorted(badf.items()):
        for why, frag, _ctx in h[:5]:
            print("        - %s: %s: %r" % (rel, why, frag[:50]))

    # ★ 判据 7：手写文档引用的端点必须真实存在（生成物 http-api.md 不查，它是从 json 来的）
    unknown = {}
    for f in sorted(os.listdir(os.path.join(ROOT, "docs"))):
        if not f.endswith(".md") or f == "http-api.md":
            continue
        t = open(os.path.join(ROOT, "docs", f), encoding="utf-8").read()
        for m in re.finditer(r"`(/(?:[A-Za-z0-9_.\-]+)*)`", t):
            p = m.group(1)
            if p in paths or p in DOC_PATH_ALLOW or p == "/" or p.endswith("/") and p[:-1] in paths:
                continue
            unknown.setdefault(f, set()).add(p)
    check("手写文档引用的端点都存在", not unknown,
          "全部命中" if not unknown else "%s" % {k: sorted(v)[:6] for k, v in unknown.items()})

    # ★ 判据 8：docs/ 之间的相对链接无失效（锚点不参与判定）
    docdir = os.path.join(ROOT, "docs")
    dead = {}
    for f in sorted(os.listdir(docdir)):
        if not f.endswith(".md"):
            continue
        t = open(os.path.join(docdir, f), encoding="utf-8").read()
        for l in re.findall(r"\]\(([^)]+)\)", t):
            if l.startswith("http") or l.startswith("#"):
                continue
            if not os.path.exists(os.path.join(docdir, l.split("#")[0])):
                dead.setdefault(f, []).append(l)
    check("docs 内部相对链接无失效", not dead, "全部命中" if not dead else str(dead))

    print("\n=== 合计：%d 项通过 / %d 项失败 ===" % (len(OK), len(FAIL)))
    if FAIL:
        print("失败项：" + "、".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
