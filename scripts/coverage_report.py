# -*- coding: utf-8 -*-
"""coverage_report.py — 生成某个拟音体系的覆盖率报告。

用法:
    python scripts/coverage_report.py                 # 默认王力中古
    python scripts/coverage_report.py --system wangli_mc
    python scripts/coverage_report.py --against legacy   # 与项目 703 字旧表对照

报告只做统计与核对，不合成、不改写数据；差额（被跳过的记录）如实列出。
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from language.history import lookup_reading  # noqa: E402
from language.history.sinica_scholar_data import (  # noqa: E402
    SCHOLAR_SYSTEMS, lookup_scholar_reading, scholar_coverage,
)


def _legacy_chars():
    """项目旧字表（703 字），用于说明「哪些字已经有历史读音」。"""
    try:
        from phonology_db import EASTERN_HAN_DB
        return sorted(EASTERN_HAN_DB)
    except Exception:  # noqa: BLE001
        return []


def print_summary_table():
    """六个体系横向对比。"""
    print("# 中古学者方案横向对比")
    print()
    print("| 体系 | 字数 | 记录 | 错位行 | 非单字 | 東 | 融 |")
    print("|---|---|---|---|---|---|---|")
    for sid in SCHOLAR_SYSTEMS:
        cov = scholar_coverage(sid)
        east = lookup_reading("東", sid).ipa or "—"
        rong = lookup_reading("融", sid).ipa or "—"
        print("| `%s` | %d | %d | %d | %d | `%s` | `%s` |"
              % (sid, cov["characters"], cov["records"],
                 cov["skipped_suspect_initial"], cov["skipped_not_single_char"],
                 east, rong))
    print()
    print("同一个「融」在六家方案下的差异，就是各体系不可混用的直接证据。")
    print()


def main():
    ap = argparse.ArgumentParser(description="拟音体系覆盖率报告")
    ap.add_argument("--system", default="wangli_mc",
                    choices=sorted(SCHOLAR_SYSTEMS), help="要报告的系统 id")
    ap.add_argument("--all", action="store_true", help="输出六个体系的横向对比")
    ap.add_argument("--against", default="legacy",
                    choices=("legacy", "none"), help="对照字表")
    args = ap.parse_args()

    if args.all:
        print_summary_table()

    cov = scholar_coverage(args.system)

    print("# 覆盖率报告：%s（%s）" % (cov["system_name"], cov["system_id"]))
    print()
    print("## 记录与字数")
    print("| 项 | 值 |")
    print("|---|---|")
    print("| 上游匹配记录 | %d |" % cov["matched_records"])
    print("| 实际加载记录 | %d |" % cov["records"])
    print("| 跳过：非单字 | %d |" % cov["skipped_not_single_char"])
    print("| 跳过：韻母为空 | %d |" % cov["skipped_empty_final"])
    print("| 去重字数 | %d |" % cov["characters"])
    print("| 多音字（同字多行） | %d |" % cov["multi_reading_characters"])
    print()

    print("## 符号库存")
    print("| 项 | 值 |")
    print("|---|---|")
    print("| 声母种数 | %d |" % cov["distinct_initials"])
    print("| 韵母种数 | %d |" % cov["distinct_finals"])
    print("| 零声母（0） | %d |" % cov["zero_initial"])
    print("| 声母留空 | %d |" % cov["blank_initial"])
    print("| 声调可用 | %s |" % ("是" if cov["tone_available"] else "**否（上游无此字段）**"))
    print()

    print("## 声母清单（%d 种）" % cov["distinct_initials"])
    print("```")
    print(" ".join(cov["initials"]))
    print("```")
    print()

    print("## 韵母样本（前 20 / 共 %d）" % cov["distinct_finals"])
    print("```")
    print(" ".join(cov["finals_sample"]))
    print("```")
    print()

    if args.against == "legacy":
        legacy = _legacy_chars()
        if legacy:
            hit = [c for c in legacy if lookup_scholar_reading(c, args.system)]
            miss = [c for c in legacy if not lookup_scholar_reading(c, args.system)]
            pct = 100.0 * len(hit) / len(legacy)
            print("## 与项目旧字表对照")
            print("| 项 | 值 |")
            print("|---|---|")
            print("| 旧表字数 | %d |" % len(legacy))
            print("| 在本体系中有记录 | %d（%.1f%%） |" % (len(hit), pct))
            print("| 无记录 | %d |" % len(miss))
            print()
            if miss:
                print("缺失字示例：%s%s" % ("".join(miss[:40]),
                                          " …" if len(miss) > 40 else ""))
                print()

    print("## 边界说明")
    print("- 上游**没有声调字段**，本报告与查询接口均不补全，`tone` 恒为空。")
    print("- 聲母 `0` 是上游表示零声母的符号，拼接 IPA 时按无辅音处理。")
    print("- `ȶ` `ȡ` `ɽ` 等属王力方案惯用符号，能否送入合成器需第三阶段"
          "「音素能力矩阵」确认，本报告不作能力承诺。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
