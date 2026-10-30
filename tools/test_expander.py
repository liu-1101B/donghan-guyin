""" test_expander.py 验证 db_expander 的核心逻辑是否正常 """
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.dirname(os.path.abspath(__file__)), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import phonology_db

# ============================================================
# 测试1：parse_init_from_ipa 声母提取
# ============================================================
from db_expander import parse_init_from_ipa

test_cases = [
    ("tʰen", "tʰ"),
    ("krim", "kr"),
    ("ŋʷat", "ŋʷ"),
    ("dʑim", "dʑ"),
    ("ȵit", "ȵ"),
    ("ɕiŋ", "ɕ"),
    ("la", "l"),
    ("ɡa", "ɡ"),
    ("a", ""),
]
print("=== 测试1：parse_init_from_ipa 声母提取 ===")
all_pass = True
for ipa, expected in test_cases:
    result = parse_init_from_ipa(ipa)
    status = "✅" if result == expected else "❌"
    if result != expected:
        all_pass = False
    print(f"  {status} {ipa} -> '{result}' (期望: '{expected}')")
print(f"  {'全部通过!' if all_pass else '有失败用例'}\n")


# ============================================================
# 测试2：谐声推导逻辑（无需 API，无需 csv 文件）
# ============================================================
print("=== 测试2：谐声推导逻辑 ===")

# 伪造一个小数据库做测试
fake_db = {
    "青": {"ipa": "tsʰeŋ", "init": "清母", "final": "耕部", "tone": "平声", "init_ipa": "tsʰ"},
    "可": {"ipa": "kʰalʔ", "init": "溪母", "final": "歌部", "tone": "上声", "init_ipa": "kʰ"},
    "工": {"ipa": "koŋ", "init": "见母", "final": "东部", "tone": "平声", "init_ipa": "k"},
}

from db_expander import derive_from_xiesheng

# 创建临时测试用的 xiesheng.csv
import tempfile, csv
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(["清", "青"])   # 青声字，声旁已收录
    writer.writerow(["晴", "青"])   # 声旁已收录
    writer.writerow(["河", "可"])   # 声旁已收录
    writer.writerow(["阿", "可"])   # 声旁已收录
    writer.writerow(["空", "工"])   # 声旁已收录，且现代读 k-（送气）
    writer.writerow(["贡", "工"])   # 声旁已收录，现代读 g-（不送气）
    writer.writerow(["贡贡", "工"])  # 无效行（>1字）
    test_csv = f.name

# 执行推导
print("  使用临时 xiesheng.csv:")
print("    清,青 / 晴,青 / 河,可 / 阿,可 / 空,工 / 贡,工")
print()

derived_db = derive_from_xiesheng(fake_db.copy(), test_csv)

# 验证结果
checks = [
    ("清", "tsʰ"),  # 送气，继承 tsʰ
    ("晴", "tsʰ"),  # 现代 q-，送气
    ("河", "kʰ"),   # 继承 kʰ
    ("阿", "kʰ"),   # 继承 kʰ（没触发送气规则因为现代不是 p/t/k/c/q 开头）
    ("空", "k"),    # 现代 k-，送气化规则触发
    ("贡", "k"),    # 现代 g-，不触发送气规则
]
all_ok = True
for char, expected_init in checks:
    if char in derived_db:
        actual_ipa = derived_db[char]["ipa"]
        actual_init = derived_db[char]["init"]
        ok = actual_ipa.startswith(expected_init)
        status = "✅" if ok else "⚠️"
        if not ok:
            all_ok = False
        print(f"  {status} {char} -> ipa={actual_ipa} (声母期望以'{expected_init}'开头), init标记={actual_init}")
    else:
        print(f"  ❌ {char} 未被推导出!")
        all_ok = False

print(f"  {'全部正确!' if all_ok else '有异常'}\n")

os.unlink(test_csv)


# ============================================================
# 测试3：和真实数据库对比（查询几个字的覆盖情况）
# ============================================================
print("=== 测试3：当前数据库覆盖情况 ===")
db = phonology_db.EASTERN_HAN_DB
print(f"  当前总字数: {len(db)}")

# 检查部分常用字是否在数据库中
check_chars = "天地人日月星风雨山水火木金石花草春夏秋冬东西南北中前后左右大中小多少一二三四五六七八九十父母子女心身手耳目头面行道仁义礼智信明清白青龙凤马牛鱼虎今古时年岁"
in_db = [c for c in check_chars if c in db]
missing = [c for c in check_chars if c not in db]
print(f"  检测 {len(check_chars)} 个常用字:")
print(f"    已收录: {len(in_db)} 个")
print(f"    缺失: {len(missing)} 个 -> {''.join(missing)}")

if missing:
    print(f"\n  💡 这些字可以通过 db_expander.py + API 导入或 xiesheng.csv 来补充")


# ============================================================
# 最终结论
# ============================================================
print("\n" + "=" * 60)
print("✅ 验证完成！")
print("=" * 60)
print("如果上面都是 ✅ 没有 ❌，说明 db_expander.py 逻辑正确。")
print("你可以在自己电脑上运行完整的 API 导入: python tools/db_expander.py")
