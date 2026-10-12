# -*- coding: utf-8 -*-
"""本机路径注入：让「作者自己在这台机器上跑」方便，同时保证公开仓库里**不出现任何本机路径**。

查找顺序（只读，不写任何文件）：
  1) 环境变量 `LEDI_ROUTER_JAVA` / `LEDI_ROUTE_INVENTORY`
  2) 本仓库的 `.local/paths.json`（已在 `.gitignore` 里，永远不会被提交）

`.local/paths.json` 形如（写成 `.../` 只是因为这是公开仓库的示例，
真实值就是本机绝对路径）：

    {
      "router_java":     ".../agent/src/com/ledi/agent/core/CommandRouter.java",
      "route_inventory": ".../route_inventory.json"
    }

为什么要有第 2 层，而不是只认命令行参数：
  只认 `--src` 时，忘了传就会拿到**上一次的产物**，而下游照旧生成一份「看着正常」的文档
  —— 产物存在 ≠ 内容更新。这个项目在真机上吃过一次这个静默失败。
  把路径放进一个不随仓库分发的本地文件，既保住了这份便利，又不让它进公开仓库。

外部克隆本仓库的人没有这个文件，此时 `--src` / `--inv` 必须显式给；
`extract_api.py` 会因此**直接报错退出**（而不是悄悄用旧数据），`selfcheck.py` 会跳过对差项。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, ".local", "paths.json")
_cache = None


def _conf():
    global _cache
    if _cache is None:
        try:
            _cache = json.load(open(CONF, encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def router_java():
    """CommandRouter.java 的路径；没有则返回 ""（调用方负责报错，不要静默兜底）。"""
    return os.environ.get("LEDI_ROUTER_JAVA") or _conf().get("router_java", "")


def route_inventory():
    """改造工程导出的端点清单路径；没有则返回 ""（对差项会自动跳过）。"""
    return os.environ.get("LEDI_ROUTE_INVENTORY") or _conf().get("route_inventory", "")


if __name__ == "__main__":
    print("本地配置：%s  %s" % (CONF, "存在" if os.path.isfile(CONF) else "（无）"))
    print("  router_java     = %s" % (router_java() or "（未设置）"))
    print("  route_inventory = %s" % (route_inventory() or "（未设置）"))
