# -*- coding: utf-8 -*-
"""correspondence_report.py — 生成东汉 → 中古音类对应报告。

用法:
    python scripts/correspondence_report.py                # 完整报告
    python scripts/correspondence_report.py --char 东      # 单字锚点查询
    python scripts/correspondence_report.py --json         # JSON 概要

对应表是锚定交集上的观测共现（非音变规律）；无锚点的字如实列出，不回填。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from language.history.eastern_mc_correspondence import (  # noqa: E402
    anchor_for,
    anchor_coverage,
    build_report,
    initial_correspondence,
    final_correspondence,
    provenance,
    unanchored_characters,
)


def _char_report(char):
    row = anchor_for(char)
    if row is None:
        print("字表中无此字：%s" % char)
        return 1
    print("# 单字锚点：%s（%s）" % (row.char, row.traditional))
    print()
    print("| 端 | 值 |")
    print("|---|---|")
    print("| 东汉声母 | %s |" % row.han_init)
    print("| 东汉韵部 | %s（%s） |" % (row.han_final, row.han_tone))
    print("| 东汉 IPA | %s |" % row.han_ipa)
    print("| 锚点状态 | %s |" % ("有" if row.anchored else "无（上游表无此首字）"))
    print()
    if row.anchored:
        print("中古音韵地位（逐条）：")
        print("| 声母 | 开合 | 等 | 重纽 | 韵 | 调 |")
        print("|---|---|---|---|---|---|")
        for p in row.positions:
            print("| %s | %s | %s | %s | %s | %s |" % (
                p.shengmu, p.kaihhe or "—", p.deng or "—",
                p.chongniu or "—", p.yun, p.sheng))
    return 0


def _json_report():
    cov = anchor_coverage()
    data = {
        "coverage": cov,
        "initial_correspondence": {
            k: {mk: {"n": p.n, "chars": list(p.chars)}
                for mk, p in pairs.items()}
            for k, pairs in initial_correspondence().items()
        },
        "final_correspondence": {
            k: {mk: {"n": p.n, "chars": list(p.chars)}
                for mk, p in pairs.items()}
            for k, pairs in final_correspondence().items()
        },
        "unanchored": list(unanchored_characters()),
        "provenance": provenance(),
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="东汉→中古音类对应报告")
    ap.add_argument("--char", default=None, help="单字锚点查询")
    ap.add_argument("--json", action="store_true", help="JSON 概要输出")
    ap.add_argument("--top-finals", type=int, default=30,
                    help="韵母对应表显示前 N 个东汉韵部（默认 30）")
    args = ap.parse_args()

    if args.char:
        return _char_report(args.char)
    if args.json:
        return _json_report()
    print(build_report(top_finals=args.top_finals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
