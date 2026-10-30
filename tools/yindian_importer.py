"""
yindian_importer.py
从 nk2028/yindian-manus 项目提取东汉音数据，扩充项目音韵数据库

使用方式：
    python tools/yindian_importer.py

依赖：无额外依赖，只需要 yindian-manus 项目已克隆到本地
"""

import os
import json
import re
import sys

# ============================================================
# 配置 - 根据你的实际路径修改
# ============================================================
YINDIAN_DIR = os.path.expanduser("~/yindian-manus")  # 如果克隆在其他位置，修改这里
GUYIN_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 方案A：从 JSON 文件提取（yindian-manus 的数据文件）
# ============================================================
def find_data_files():
    """在 yindian-manus 项目中查找所有数据文件"""
    data_files = []
    for root, dirs, files in os.walk(YINDIAN_DIR):
        for f in files:
            if f.endswith(('.json', '.csv', '.tsv', '.db')):
                path = os.path.join(root, f)
                data_files.append(path)
    return data_files


def scan_yindian_project_structure():
    """扫描 yindian-manus 项目结构，了解数据组织方式"""
    print(f"📂 扫描 yindian-manus 项目结构 ({YINDIAN_DIR})...")
    if not os.path.exists(YINDIAN_DIR):
        print(f"❌ 找不到 {YINDIAN_DIR}")
        print("请修改脚本顶部的 YINDIAN_DIR 变量为你的实际路径")
        return {}

    structure = {}
    for root, dirs, files in os.walk(YINDIAN_DIR):
        rel_path = os.path.relpath(root, YINDIAN_DIR)
        if rel_path == ".":
            continue
        # 跳过 node_modules 等
        if "node_modules" in rel_path or ".git" in rel_path:
            continue
        py_files = [f for f in files if f.endswith(('.ts', '.js', '.json', '.csv', '.db', '.sqlite'))]
        if py_files:
            structure[rel_path] = py_files[:10]  # 最多显示10个

    for path, files in sorted(structure.items()):
        print(f"  📁 {path}/")
        for f in files:
            full_path = os.path.join(YINDIAN_DIR, path, f)
            size = os.path.getsize(full_path) if os.path.isfile(full_path) else 0
            print(f"      📄 {f} ({size:,} bytes)")

    return structure


def extract_from_json_files():
    """尝试从 JSON 数据文件中提取汉字读音"""
    print("\n🔍 搜索 JSON 数据文件...")
    results = {}
    for root, dirs, files in os.walk(YINDIAN_DIR):
        for f in files:
            if f.endswith('.json'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    # 尝试不同数据结构
                    if isinstance(data, dict):
                        # 格式1: {"字": "音标"}
                        sample_keys = list(data.keys())[:5]
                        sample_vals = list(data.values())[:5]
                        if all(len(k) == 1 for k in sample_keys if isinstance(k, str)):
                            print(f"  ✅ {f}: 字典格式 ({len(data)} 条目)")
                            print(f"     示例: {dict(zip(sample_keys, sample_vals))}")
                            results[f] = data
                        else:
                            print(f"  📋 {f}: 字典 (非汉字键), 键示例: {sample_keys}")
                    elif isinstance(data, list) and len(data) > 0:
                        print(f"  📋 {f}: 列表 ({len(data)} 条)")
                        if isinstance(data[0], list):
                            print(f"     首条: {data[0][:3]}...")
                        elif isinstance(data[0], dict):
                            print(f"     键: {list(data[0].keys())[:5]}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                except Exception as e:
                    print(f"  ⚠️  {f}: {e}")
    return results


# ============================================================
# 方案B：调用 yindian 的 API（推荐，实时查询）
# ============================================================
def query_yindian_api(char):
    """调用 nk2028 的音典 API 查询单个汉字"""
    import urllib.request
    import json

    urls = [
        f"https://yindian-api.nk2028.shn.hk/api/char/{char}",
        f"https://nk2028.shn.hk/api/char/{char}",
    ]

    for url in urls:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return data
        except Exception:
            continue
    return None


def extract_eastern_han_from_api(char):
    """从 API 结果中提取东汉音"""
    data = query_yindian_api(char)
    if not data:
        return None

    # yindian 的返回格式是 [char, [[lang_id, pronunciation, note], ...]]
    # 东汉/上古韵的 language_id 可能是特定值

    # 常见的东汉音 ID（需实测确认）
    EASTERN_HAN_IDS = [1, 2, 3, 5]  # 从 yindian 源码中看

    if isinstance(data, list) and len(data) >= 2:
        pronunciations = data[1] if isinstance(data[1], list) else []
        for item in pronunciations:
            if isinstance(item, list) and len(item) >= 2:
                lang_id = item[0]
                pron = item[1]
                if lang_id in EASTERN_HAN_IDS:
                    return pron
    return None


# ============================================================
# 方案C：直接用项目自带的现有数据库扩充
# ============================================================
def load_current_db():
    """加载项目现有的音韵数据库"""
    db_path = os.path.join(GUYIN_DIR, "phonology_db.py")
    if not os.path.exists(db_path):
        print(f"❌ 找不到 {db_path}")
        return {}

    with open(db_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析现有数据库
    db = {}
    # 正则匹配字典条目
    pattern = r'\s+"([^"]+)":\s*\{[^}]+\},'
    for match in re.finditer(pattern, content):
        char = match.group(1)
        entry_text = match.group(0)
        # 提取 ipa
        ipa_match = re.search(r'"ipa":\s*"([^"]*)"', entry_text)
        init_match = re.search(r'"init":\s*"([^"]*)"', entry_text)
        final_match = re.search(r'"final":\s*"([^"]*)"', entry_text)
        tone_match = re.search(r'"tone":\s*"([^"]*)"', entry_text)
        init_ipa_match = re.search(r'"init_ipa":\s*"([^"]*)"', entry_text)

        db[char] = {
            "ipa": ipa_match.group(1) if ipa_match else "",
            "init": init_match.group(1) if init_match else "",
            "final": final_match.group(1) if final_match else "",
            "tone": tone_match.group(1) if tone_match else "",
            "init_ipa": init_ipa_match.group(1) if init_ipa_match else "",
        }
    return db


def get_pinyin_fallback(char):
    """拼音回退 - 用现代拼音作为近似音"""
    from pypinyin import pinyin, Style
    try:
        py = pinyin(char, style=Style.TONE3)[0][0]
        # 去掉声调数字
        return re.sub(r'[0-9]', '', py)
    except:
        return None


def estimate_donghan_from_pinyin(py):
    """从现代拼音大致估计东汉音（最粗糙的回退）"""
    # 这只是兜底方案，准确率有限
    mapping = {
        'a': 'a', 'o': 'a', 'e': 'ə', 'i': 'i', 'u': 'o',
        'b': 'p', 'p': 'pʰ', 'm': 'm', 'f': 'p',
        'd': 't', 't': 'tʰ', 'n': 'n', 'l': 'l',
        'g': 'k', 'k': 'kʰ', 'h': 'h',
        'j': 'k', 'q': 'kʰ', 'x': 'h',
        'zh': 'tɕ', 'ch': 'tɕʰ', 'sh': 'ɕ', 'r': 'ȵ',
        'z': 'ts', 'c': 'tsʰ', 's': 's',
        'y': 'j', 'w': 'ʔ',
    }

    if not py:
        return None

    # 提取声母
    initials = ['zh', 'ch', 'sh']
    for init in initials:
        if py.startswith(init):
            init_ipa = mapping.get(init, '')
            rest = py[len(init):]
            break
    else:
        init_ipa = mapping.get(py[0], '')
        rest = py[1:] if py else ''

    if not init_ipa:
        return None

    return f"{init_ipa}{rest}"


# ============================================================
# 批量扩充：读取高频汉字列表，补充数据库
# ============================================================
def batch_import_from_file(word_list_file=None):
    """
    从文件批量导入汉字进行音韵扩充
    如果提供文件，逐行读取汉字；否则使用内置的常用字表
    """
    # 现代汉语最常用 500 字 + 古籍高频字
    common_chars = (
        "的一是不了人在我有他这那中大小上个国到说时会就也可在以"
        "为和要她之来出得里后过儿能下天家年生头地只没去看起做过"
        "还对从事成自同于法如自己开当道想心心样都向变问进法长水"
        "高很月儿正活多全个着学又手新主么些意间无事把部从种相重"
        "被见问两关十名前政体定名实民经外如社会文立白通角车元件"
        "回北南东天西三二第区等产之与面但方量几如度品力员四加第"
        "由口五军决机性据干边至张接称手斯改海象世间质近任该提花"
        "今果确展空结解统论组导期值联育程信管较快完转安广受该容"
        "林集配红升态制各维目题商办价设议报造九派八代质人程管件"
        "交路区队号共战究界七山统省速增志调王厂色万许县满华片创"
        "铁苏板值布示率规党严验半南至胜席非构存即单止式需型状节"
        "土根构保石批简已市青府查消病选适党低县土史型铁划属厂际"
        "星念层片准试写低且价史型铁划属厂际雨呀猫狗猪鸡鸭鱼龙虎"
        "春夏秋冬梅兰竹菊诗酒琴棋书画仁义礼智信天地玄黄宇宙洪荒"
        "日月盈昃辰宿列张寒来暑往秋收冬藏闰馀成岁律吕调阳云腾致"
        "关关雎鸠在河之洲窈窕淑女君子好逑参差荇菜左右流之"
    )

    # 去重
    chars_to_add = []
    seen = set()
    for c in common_chars:
        if c not in seen:
            seen.add(c)
            chars_to_add.append(c)

    return chars_to_add


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("  yindian-manus 数据导入工具")
    print("  用于扩充「古韵·东汉洛阳官音」音韵数据库")
    print("=" * 60)

    # 1. 查看 yindian 项目结构
    structure = scan_yindian_project_structure()

    # 2. 尝试从 JSON 提取
    json_data = extract_from_json_files()

    # 3. 查询 API 测试
    print("\n🔍 测试 API 查询...")
    test_char = "天"
    result = query_yindian_api(test_char)
    if result:
        print(f"  ✅ API 查询 {test_char} 成功!")
        print(f"     返回: {json.dumps(result, ensure_ascii=False)[:200]}")

        # 测试东汉音提取
        dh = extract_eastern_han_from_api(test_char)
        if dh:
            print(f"     东汉音: {dh}")
    else:
        print(f"  ⚠️  API 查询失败（可能需 VPN 或 API 已变更）")
        print(f"  你可以直接去 https://yindian.nk2028.shn.hk 查一下")

    # 4. 查看当前项目数据库状态
    db = load_current_db()
    print(f"\n📊 当前音韵数据库: {len(db)} 字")

    # 5. 生成可补充的字列表
    chars = batch_import_from_file()
    new_chars = [c for c in chars if c not in db]
    print(f"\n📝 可以补充的常用字: {len(new_chars)} 个")
    print(f"   示例: {''.join(new_chars[:30])}")

    print("\n" + "=" * 60)
    print("  📋 使用说明")
    print("=" * 60)
    print("""
1. 打开浏览器访问 https://yindian.nk2028.shn.hk
2. 搜索一个汉字（例如"的"）
3. 在结果中找到"上古韵"或"东汉音"列
4. 复制 IPA 音标
5. 手动添加到 phonology_db.py

或者用自动方式：
6. 修改本脚本中的 YINDIAN_DIR 路径
7. 运行 python tools/yindian_importer.py --auto
""")

    # 输出可补充的字列表，方便逐字查询
    if new_chars:
        print(f"\n🔤 建议优先补充的字（前50个）：")
        for i, c in enumerate(new_chars[:50]):
            print(f"  {c}", end=" ")
            if (i+1) % 10 == 0:
                print()
        print()


def auto_import():
    """自动模式 - 尝试从 API 批量导入"""
    import urllib.request
    import time

    db = load_current_db()
    chars = batch_import_from_file()
    new_chars = [c for c in chars if c not in db]

    print(f"🔄 自动导入模式: 尝试补充 {len(new_chars)} 字...")

    added = 0
    for i, char in enumerate(new_chars):
        try:
            dh = extract_eastern_han_from_api(char)
            if dh:
                print(f"  ✅ {char}: {dh}")
                added += 1
            else:
                print(f"  ⬜ {char}: 无东汉音数据")
        except:
            print(f"  ⚠️  {char}: 查询失败")

        # API 限流
        if i % 10 == 9:
            time.sleep(1)

    print(f"\n✅ 完成: 成功获取 {added} 字的东汉音")


if __name__ == "__main__":
    if "--auto" in sys.argv:
        auto_import()
    elif "--scan" in sys.argv:
        scan_yindian_project_structure()
        extract_from_json_files()
    else:
        main()
