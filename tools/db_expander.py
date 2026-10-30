""" db_expander.py 东汉洛阳官音 - 数据库扩充工具 方案二：通过音典 API 批量导入真实东汉音 方案四：基于谐声偏旁推导未收录字读音 """
import os
import re
import json
import urllib.request
import urllib.parse
import time
import csv
import sys

# 脚本挪进了 tools/：把「本目录」和「仓库根」都放进 sys.path，
# 这样 import phonology_db / from db_expander import ... 仍然可用。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.dirname(os.path.abspath(__file__)), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import phonology_db

def fetch_ipa_from_yindian(char):
    """调用音典 API 查询单个字的东汉/上古韵"""
    url = f"https://yindian-api.nk2028.shn.hk/api/char/{urllib.parse.quote(char)}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                for item in data[1]:
                    if isinstance(item, list) and len(item) >= 2:
                        lang_id = item[0]
                        pron = item[1]
                        if lang_id in [1, 2, 3, 5]:
                            return pron
    except Exception as e:
        print(f"  查询 {char} 失败: {e}")
    return None

def parse_init_from_ipa(ipa):
    """从 IPA 字符串中提取声母部分"""
    vowels = "iye\u025b\u00e6a\u0268\u0259\u0250uo\u0254\u028c\u0251\u0252\u0289\u026f\u0264"
    init_ipa = ""
    for ch in ipa:
        if ch in vowels:
            break
        init_ipa += ch
    return init_ipa

def batch_import_from_api(db, chars_list):
    """批量从 API 导入数据到字典"""
    print("=" * 60)
    print("\U0001f50a 方案二：启动 API 批量导入...")
    print("=" * 60)
    added = 0
    for i, char in enumerate(chars_list):
        if char in db:
            continue
        if not char.strip() or len(char) != 1:
            continue
        ipa = fetch_ipa_from_yindian(char)
        if ipa:
            init_ipa = parse_init_from_ipa(ipa)
            db[char] = {
                "ipa": ipa,
                "init": "API\u5bfc\u5165",
                "final": "API\u5bfc\u5165",
                "tone": "\u672a\u77e5",
                "init_ipa": init_ipa
            }
            print(f"  \u2705 [{i+1}/{len(chars_list)}] \u5bfc\u5165 {char}: {ipa}")
            added += 1
        else:
            print(f"  \u2b1c [{i+1}/{len(chars_list)}] \u672a\u627e\u5230 {char} \u7684\u97f3\u97f5\u6570\u636e")
        time.sleep(0.5)
    print(f"\u2705 \u65b9\u6848\u4e8c\u5b8c\u6210\uff1a\u6210\u529f\u8865\u5145 {added} \u4e2a\u5b57\n")
    return db

def derive_from_xiesheng(db, xiesheng_file="xiesheng.csv"):
    """根据谐声偏旁和清浊对应关系推导未收录字的读音"""
    print("=" * 60)
    print("\U0001f9ec 方案四：启动谐声推导（进阶规则版）...")
    print("=" * 60)

    if not os.path.exists(xiesheng_file):
        print(f"\u26a0\ufe0f 未找到谐声数据文件 {xiesheng_file}，跳过推导。")
        print("    请创建该文件，格式为 CSV，两列：形声字,声旁字")
        return db

    phonetic_map = {}
    try:
        with open(xiesheng_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2 and len(row[0]) == 1 and len(row[1]) == 1:
                    phonetic_map[row[0]] = row[1]
    except Exception as e:
        print(f"读取谐声文件出错: {e}")
        return db

    init_rules = {
        'p': {'\u6e05\u5316': 'p', '\u9001\u6c14': 'p\u02b0', '\u9f3b\u97f3': 'm'},
        't': {'\u6e05\u5316': 't', '\u9001\u6c14': 't\u02b0', '\u9f3b\u97f3': 'n'},
        'k': {'\u6e05\u5316': 'k', '\u9001\u6c14': 'k\u02b0', '\u9f3b\u97f3': '\u014b'},
        'ts': {'\u6e05\u5316': 'ts', '\u9001\u6c14': 'ts\u02b0', '\u9f3b\u97f3': 'nz'},
    }

    derived = 0
    try:
        from pypinyin import pinyin, Style
        PYPINYIN_AVAILABLE = True
    except:
        PYPINYIN_AVAILABLE = False

    for char, phonetic in phonetic_map.items():
        if char not in db and phonetic in db:
            base_data = db[phonetic].copy()
            base_init_ipa = base_data.get("init_ipa", "")

            if PYPINYIN_AVAILABLE:
                try:
                    py = pinyin(char, style=Style.NORMAL)[0][0]
                    if py and py[0] in ['p', 't', 'k', 'c', 'q']:
                        for base_init, rule in sorted(init_rules.items(), key=lambda x: len(x[0]), reverse=True):
                            if base_init_ipa.startswith(base_init):
                                base_data["init_ipa"] = rule['\u9001\u6c14'] + base_init_ipa[len(base_init_ipa):]
                                base_data["ipa"] = rule['\u9001\u6c14'] + base_data["ipa"][len(base_init_ipa):]
                                break
                except:
                    pass

            base_data["init"] = base_data.get("init", "") + "(\u63a8\u5bfc)"
            db[char] = base_data
            print(f"  \U0001f517 推导 {char} (声旁:{phonetic}) -> {db[char]['ipa']}")
            derived += 1

    print(f"\u2705 方案四完成：成功推导 {derived} 个字\n")
    return db

def save_db_to_py(db, filepath="phonology_db.py"):
    """将扩充后的字典写回 phonology_db.py"""
    print("=" * 60)
    print("\U0001f4be 正在将数据写回 phonology_db.py ...")
    print("=" * 60)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_dict_str = 'EASTERN_HAN_DB = {\n'
    for char, data in db.items():
        ipa = data.get("ipa", "")
        init = data.get("init", "")
        final = data.get("final", "")
        tone = data.get("tone", "")
        init_ipa = data.get("init_ipa", "")
        ipa = ipa.replace('"', '\\"')
        init = init.replace('"', '\\"')
        final = final.replace('"', '\\"')
        tone = tone.replace('"', '\\"')
        init_ipa = init_ipa.replace('"', '\\"')
        new_dict_str += f'    "{char}": {{"ipa": "{ipa}", "init": "{init}", "final": "{final}", "tone": "{tone}", "init_ipa": "{init_ipa}"}},\n'
    new_dict_str += '}\n'

    pattern = r'EASTERN_HAN_DB\s*=\s*\{.*?\n\}\n'
    new_content = re.sub(pattern, new_dict_str, content, flags=re.DOTALL)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"\U0001f389 数据库已更新并保存！当前总字数: {len(db)}")

if __name__ == "__main__":
    db = phonology_db.EASTERN_HAN_DB.copy()
    print(f"当前数据库字数: {len(db)}")

    # 常用字表（最小化以避bug）
    common_chars_str = "的一是不了在和有大这主中人上为们地个用工时要动国产以我到他会作来分生对于学下级就年阶发民部本方体理面起当社前定业义之制反合什么可家进想些表然两加把被样力去象使东明关点向重此信通长本期化由名手给位次们行十内日些政海任知建常北天少交作合总东表现成化水少合必手又军文重治看成关当于第能果定思化级党当民力加通命提农统平意放间问到五路象则思品立先件明理体治全组数期群第其门线已准级声院近门前反金南候展达京业保必手件指物日平由决机图当革权治民图流这文节展业命前总治军立及发心法少命多加一见体向式发方如向起本体部上难民方军方水东民军理十系治文活水起长基少方革放那信日线统前力体被周最机需持非向党流干统北气叫流做被十气高流主进级上向长都制即提转至长生由七些事今制水体地系化周干向流象才儿由立办土便才低且在专必手才之维部率空结解统论组导期值联育程信管较快完转安广受该容林集配红升态制各维目题商办价设议报造九派八代质人程管件交路区队号共战究界七山统省速增志调王厂色万许县满华片创铁苏板值布示率规党严验半南至胜席非构存即单止式需型状节土根构保石批简已市青府查消病选适党低县土史型铁划属厂际星念层片准试写低且价史型铁划属厂际"

    chars_to_fetch = []
    seen = set()
    for c in common_chars_str:
        if c not in seen and len(c.strip()) == 1:
            seen.add(c)
            chars_to_fetch.append(c)

    print(f"\n准备从 API 导入 {len(chars_to_fetch)} 个常用字...")
    db = batch_import_from_api(db, chars_to_fetch)
    db = derive_from_xiesheng(db, "xiesheng.csv")
    save_db_to_py(db, "phonology_db.py")
