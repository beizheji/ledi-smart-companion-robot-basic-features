# -*- coding: utf-8 -*-
"""注释脱敏：把生成物里「对公开读者无意义、或不该公开」的片段换成中性表述。

为什么需要这一层，而不是直接改源码注释：
  `docs/http-api.md` 与 `api/*` 都是生成物，手改下次生成就被覆盖。
  注释的真源在改造工程源码里，那份源码不在本仓库、也不随本仓库公开；
  所以「公开版该长什么样」这条规则只能落在生成链路上 —— 就是本模块。

规则是**字面量**替换（不是正则魔法），一条一行，便于逐条核对：
  (源码里的原文, 换成什么)     —— 命中即替换；写成 `""` 就是删掉。

加规则时先看 `python tools/sanitize.py` 的自证输出：这条的命中数应当是 **>0**；
命中 0 说明规则写偏了（那是规则自己错了，不等于产物已经干净）。

改完规则必须重跑（生成器自带脱敏闸，漏了会直接报错退出，不会带着脏内容出产物）：
  python tools/extract_api.py --json api/endpoints.json
  python tools/gen_docs.py
  python tools/selfcheck.py
"""
import os, re, sys, json

# ---------------------------------------------------------------- 替换规则
RULES = [
    # 1) 第三方语音服务授权来源。这不是凭据泄露（没有任何 key 值），但公开仓库没必要点明
    #    「改造包里带着设备原厂买的第三方语音授权」—— 容易被厂商盯上，也等于教别人复用额度。
    (
        "本机不需要用户掏 key：原厂 App 的讯飞 appid\n"
        "和 libmsc.so 已经因为 --merge-dex 全在我们的包里了，见 CloudAsr 类注释。",
        "云端凭据沿用设备原有配置，本仓库不含任何凭据。",
    ),
    # 2) 指向仓库外文档 / 工程内部小节 / 内部脚本的引用：公开读者看不到那些文件，留着只是噪声。
    ("（判决见 06_语音唤醒专题/离线ASR_任意语音可行性判决_v97.md）。", ""),
    ("（见 §C7）", ""),
    ("（KWS 见记忆 §I3；离线 ASR", "（KWS 与离线 ASR"),
    ("，判据说明见 _deploy_v122.py 文件头", ""),
]

# ------------------------------------------------- 产物里绝不允许再出现的模式
# (正则, 人话说明)。工具直接引用本表：生成器出产物前自检，selfcheck 扫全仓库。
BANNED = [
    (r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]", "本机盘符绝对路径"),
    (r"§[A-Za-z0-9]+", "工程内部小节引用"),
    (r"见记忆", "工程内部记忆引用"),
    (r"06_语音", "工程内部目录名"),
    (r"(?i)\blibmsc\b", "第三方语音 SDK 库名"),
    (r"(?i)--merge-dex", "打包手法（暗示复用原厂授权）"),
    (r"(?i)\bappid\b", "第三方应用授权标识"),
    (r"\bpose_lib\b", "工程内部模块名"),
    (r"_route_inventory", "工程内部文件名"),
    (r"_deploy_v\d+", "工程内部脚本名"),
    (r"\bvtest\b|\bledi_serial\b", "工程内部脚本名"),
]

# 规则与禁用表本身必然含这些字面量，扫描时跳过（且这是唯一的跳过项）。
SELF = os.path.abspath(__file__)

# 值得扫的文本后缀（只扫这些，避免读二进制）
TEXT_EXT = (".md", ".json", ".csv", ".py", ".txt", ".yml", ".yaml", ".html",
            ".gitignore", ".gitattributes", ".editorconfig")


def scrub(text):
    """按 RULES 逐条字面量替换。幂等：再跑一次结果不变。"""
    if not text:
        return text
    for old, new in RULES:
        text = text.replace(old, new)
    return text


def rule_hits(text):
    """本文件各规则在 text 里的命中次数（自证用：新增规则必须 >0）。"""
    return [(old, new, text.count(old)) for old, new in RULES]


def scan_text(text, root):
    """扫出 text 里的残留，返回 [(说明, 命中片段, 上下文)]。

    含两类：BANNED 模式，以及**指向仓库外**的 `.md` 引用（仓库内存在的 docs/*.md 不算）。
    """
    out = []
    for pat, why in BANNED:
        for m in re.finditer(pat, text):
            out.append((why, m.group(0), text[max(0, m.start() - 50):m.start() + 50].replace("\n", " | ")))
    # .md 引用：先剥掉紧贴的引号/反引号/括号再判（否则 "http-api.md 这种会把引号算进文件名）
    for m in re.finditer(r"""[^\s，。；（）()\[\]`|"'“”‘’]{2,60}\.md""", text):
        ref = m.group(0)
        cands = (os.path.join(root, ref), os.path.join(root, "docs", os.path.basename(ref)))
        if not any(os.path.exists(c) for c in cands):
            out.append(("指向仓库外的文档", ref,
                        text[max(0, m.start() - 50):m.start() + 50].replace("\n", " | ")))
    return out


def scan_file(path, root=None):
    """扫单个文件。`root` 用于判定 `.md` 引用是否指向仓库外（缺省取文件所在目录）。"""
    root = root or os.path.dirname(os.path.abspath(path))
    try:
        t = open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return []
    return scan_text(t, root)


def scan_files(root, skip_dirs=(".git", ".local", "__pycache__", ".venv")):
    """扫一棵树里的文本文件（跳过本模块自身）。返回 {相对路径: [命中]}。"""
    bad = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in skip_dirs]
        for f in sorted(fn):
            p = os.path.join(dp, f)
            if os.path.abspath(p) == SELF or not f.endswith(TEXT_EXT):
                continue
            h = scan_file(p, root)
            if h:
                bad[os.path.relpath(p, root).replace("\\", "/")] = h
    return bad


def measure_text(path):
    """取「用来量规则命中」的文本。

    ★ 不能直接读 .json 的原始字节：文件里换行是转义的 `\\n` 两个字符，而规则里是真实换行，
      直接量会把跨行的规则误判成「命中 0」—— 量法自己错，结论就错。
      所以 .json 一律按注释字段拼成真文本再量。返回 (文本, 量法说明)。
    """
    t = open(path, encoding="utf-8", errors="replace").read()
    if path.lower().endswith(".json"):
        try:
            data = json.loads(t)
            if isinstance(data, list):
                return "\n".join((e.get("comment") or "") for e in data), "逐条注释拼接（真换行）"
        except Exception:
            pass
    return t, "按原始文本"


def main():
    """自证：① 每条规则的命中数 ② 全仓库残留扫描。有残留返回 1。

    默认对着**已脱敏**的 api/endpoints.json 量规则命中（此时全 0 是正常的）。
    想验证「规则还认得出原文」，给一个未脱敏的文件：`python tools/sanitize.py --in <旧json>`。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "api", "endpoints.json")
    if "--in" in sys.argv and sys.argv.index("--in") + 1 < len(sys.argv):
        p = sys.argv[sys.argv.index("--in") + 1]
    if os.path.isfile(p):
        try:
            rel = os.path.relpath(p, root)
        except ValueError:
            rel = p
        text, how = measure_text(p)
        print("=== 规则命中数（量 %s，%s）===" % (rel, how))
        tot = 0
        for old, new, n in rule_hits(text):
            tot += n
            print("  [命中 %2d] %-46s -> %s" % (n, old[:46].replace("\n", "\\n"), (new[:30] or "(删除)")))
        print("  合计 %d 处。" % tot)
        print("  ☆ 新增规则时必须先确认命中 >0（用 --in 指一份未脱敏的旧产物来验），否则是规则写偏了；")
        print("    默认对产物量得 0 才是想要的状态（说明已脱敏）。")
    else:
        print("  （找不到 %s）" % p)
    print()
    print("=== 全仓库残留扫描（跳过 .git / .local / 本模块自身）===")
    bad = scan_files(root)
    if not bad:
        print("  干净：0 处残留")
    for rel, h in sorted(bad.items()):
        print("  [%s] %d 处" % (rel, len(h)))
        for why, frag, ctx in h[:8]:
            print("      - %s: %r" % (why, frag[:60]))
            print("        ...%s..." % ctx)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
