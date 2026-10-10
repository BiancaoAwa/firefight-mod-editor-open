#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firefight MOD 打包核心（供 ffpack_gui.py 调用）

流程: MOD 工程 zip → 解压 → 数据校验(可回退原版/基准APK) → 引用检查 → 未引用剔除
      → 按打包要求(包数/包名/应用名/版本) → 输出 MOD zip + 修改元数据后的 APK

APK 机制: 游戏 MOD 根为 assets/Mod/，mod.txt 定义阵营/装备清单；
打包时把工程内容整体替换进 assets/Mod/。元数据修改用 ManifestEditor（MIT, CodyGit）。
数据文件一律 Windows-1252。
"""
import json
import time
import os, re, sys, io, glob, zipfile, struct, shutil, tempfile, contextlib

ENC = "cp1252"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import validate as V
except ImportError:
    V = None
try:
    import ManifestEditor
except ImportError:
    ManifestEditor = None

RES_STRING_POOL_TYPE = 0x0001
UTF8_FLAG = 0x100


# ================================================================ 通用
def find_ref():
    v = os.environ.get("FIREFIGHT_REF")
    if v and os.path.isdir(os.path.join(v, "Data")):
        return v
    cands = [r"D:\WorkBuddy\2026-09-25-15-03-25\ref\原始游戏文件参考（12.2.0版本）"]
    cands += glob.glob(os.path.join(os.getcwd(), "ref", "*"))
    cands += glob.glob(os.path.join(HERE, "ref", "*"))
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "Data", "Infantry")):
            return os.path.normpath(c)
    return None


def read_txt(path):
    return open(path, encoding=ENC, errors="replace").read()


def strip_comments(text):
    return "\n".join(ln.split("//")[0] for ln in text.split("\n"))


# ================================================================ 解压
def find_mod_root(src_dir):
    """在目录中定位 mod.txt（支持任意深度嵌套），返回工程根目录"""
    direct = os.path.join(src_dir, "mod.txt")
    if os.path.isfile(direct):
        return src_dir
    hits = []
    for dp, _, fs in os.walk(src_dir):
        if "mod.txt" in fs:
            hits.append(dp)
    if not hits:
        raise RuntimeError(f"{src_dir} 及其子目录里都找不到 mod.txt")
    hits.sort(key=lambda d: d.count(os.sep))          # 取最浅的
    return hits[0]


def import_mod(src, work_dir, log=print):
    """导入 MOD 工程（zip 或文件夹均可），保证 mod.txt 位于 work_dir 根。返回工程根。"""
    if os.path.isdir(src):
        root = find_mod_root(src)
        if os.path.normpath(root) == os.path.normpath(work_dir):
            return work_dir
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        shutil.copytree(root, work_dir)
        n = sum(len(fs) for _, _, fs in os.walk(work_dir))
        log(f"MOD 工程已从文件夹导入 {n} 个文件 → {work_dir}")
        return work_dir
    # zip
    zf = zipfile.ZipFile(src)
    names = [n for n in zf.namelist() if not n.endswith("/")]
    if not names:
        raise RuntimeError("MOD 工程包为空")
    mod_txts = [n for n in names if n.split("/")[-1] == "mod.txt"]
    if not mod_txts:
        raise RuntimeError("工程包里找不到 mod.txt（已检查所有嵌套层级）")
    mod_txts.sort(key=lambda n: n.count("/"))          # 取最浅的
    strip = mod_txts[0][:-len("mod.txt")]
    os.makedirs(work_dir, exist_ok=True)
    n = 0
    for n_ in names:
        if not n_.startswith(strip):
            continue                                    # 只取工程目录内的文件
        rel = n_[len(strip):]
        if not rel:
            continue
        dst = os.path.join(work_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with zf.open(n_) as f, open(dst, "wb") as g:
            shutil.copyfileobj(f, g)
        n += 1
    log(f"MOD 工程解压 {n} 个文件 → {work_dir}"
        + (f"（工程根: {strip[:-1]}）" if strip else ""))
    return work_dir


# 兼容旧名
def unpack_mod(zip_path, work_dir, log=print):
    return import_mod(zip_path, work_dir, log)


# ---- setting.txt 读写（GUI 与工具共用；多行值用 \n 转义）----
def _esc_setting(v):
    v = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\r", "")
    return v.replace("\n", "\\n")


def _unesc_setting(v):
    out, i = [], 0
    while i < len(v):
        c = v[i]
        if c == "\\" and i + 1 < len(v):
            nxt = v[i + 1]
            out.append({"n": "\n", "\\": "\\", '"': '"'}.get(nxt, "\\" + nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


HERE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTING_PATH = os.path.join(HERE_DIR, "setting.txt")


def load_settings(path=None):
    d = {}
    path = path or SETTING_PATH
    if os.path.isfile(path):
        for ln in open(path, encoding="utf-8-sig", errors="replace"):
            ln = ln.strip()
            if not ln or "=" not in ln:
                continue
            k, _, v = ln.partition("=")
            v = v.strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            d[k.strip()] = _unesc_setting(v)
    return d


def save_settings(d, path=None):
    path = path or SETTING_PATH
    with open(path, "w", encoding="utf-8") as f:
        for k, v in d.items():
            f.write(f'{k}="{_esc_setting(v)}"\n')


# ---- data/*.txt 数据表加载（穷举值全部外置，py 内不写死）----
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_data_cache = {}


def load_data_table(name, sep="=", comment="#"):
    """读 data/<name> → {key: value}（带缓存）"""
    if name in _data_cache:
        return _data_cache[name]
    d = {}
    path = os.path.join(_DATA_DIR, name)
    if os.path.isfile(path):
        for ln in open(path, encoding="utf-8-sig", errors="replace"):
            ln = ln.strip()
            if not ln or ln.startswith(comment) or sep not in ln:
                continue
            k, _, v = ln.partition(sep)
            if k.strip() and v.strip():
                d[k.strip()] = v.strip()
    _data_cache[name] = d
    return d


def load_data_list(name, comment="#"):
    """读 data/<name> → [行值]（带缓存）"""
    if name in _data_cache:
        return _data_cache[name]
    out = []
    path = os.path.join(_DATA_DIR, name)
    if os.path.isfile(path):
        for ln in open(path, encoding="utf-8-sig", errors="replace"):
            ln = ln.strip()
            if ln and not ln.startswith(comment):
                out.append(ln)
    _data_cache[name] = out
    return out


def load_appname_preset():
    return load_data_table("appname_preset.txt")


def load_voice_map():
    return load_data_table("voice_map.txt")


def load_image_dirs():
    return load_data_list("image_dirs.txt")


def load_key_creds():
    return {k: tuple(v.split(":")) for k, v in load_data_table("key_creds.txt", sep=":").items()
            if len(v.split(":")) == 3}

NAT2LANG = load_voice_map()              # data/voice_map.txt（国籍→语音两字母代码）
KEY_CRED_DEFAULTS = load_key_creds()     # data/key_creds.txt


def _write_base_cache(marker, src):
    """写基准缓存标记：源路径 + 大小 + mtime"""
    try:
        meta = {"src": os.path.abspath(src)}
        if os.path.isfile(src):
            st = os.stat(src)
            meta["size"] = st.st_size
            meta["mtime"] = int(st.st_mtime)
        json.dump(meta, open(marker, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def extract_base_data(base_pkg, out_dir, log=print, use_cache=True):
    """从基准 APK/ZIP/文件夹 提取 Data/Images/Sounds（基准 = 原版数据，可任意来源）。
    use_cache=True 时在 out_dir 写 .base_cache.json 标记，源未变则直接复用已提取数据。"""
    marker = os.path.join(out_dir, ".base_cache.json")
    if use_cache and os.path.isfile(marker) and os.path.isdir(os.path.join(out_dir, "Data")):
        try:
            meta = json.load(open(marker, encoding="utf-8"))
            if os.path.isfile(base_pkg):
                st = os.stat(base_pkg)
                ok = (meta.get("src") == os.path.abspath(base_pkg)
                      and meta.get("size") == st.st_size
                      and meta.get("mtime") == int(st.st_mtime))
            else:
                ok = meta.get("src") == os.path.abspath(base_pkg)
            if ok:
                log(f"基准数据缓存命中（源未变），直接复用 → {out_dir}")
                return out_dir
            log("基准已变化，重新提取…")
        except Exception:
            pass
    if os.path.isdir(base_pkg):                        # 文件夹形式（已解包的游戏数据）
        os.makedirs(out_dir, exist_ok=True)
        n_ok = 0
        for sub in ("Data", "Images", "Sounds"):
            src = os.path.join(base_pkg, sub)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(out_dir, sub)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            n_ok += sum(len(fs) for _, _, fs in os.walk(dst))
        log(f"基准数据(文件夹): 复制 {n_ok} 个文件 → {out_dir}")
        _write_base_cache(marker, base_pkg)
        return out_dir
    zf = zipfile.ZipFile(base_pkg)
    names = zf.namelist()
    for prefix in ("", "assets/"):
        if any(n.startswith(prefix + "Data/equipment_") or n.startswith(prefix + "Data/Infantry/")
               for n in names):
            break
    else:
        raise RuntimeError(f"{base_pkg} 里找不到 Data 目录（试过根目录与 assets/）")
    os.makedirs(out_dir, exist_ok=True)
    n_ok = 0
    for n in names:
        if n.startswith(prefix) and n.endswith("/"):
            continue
        rel = n[len(prefix):]
        if not (rel.startswith("Data/") or rel.startswith("Images/") or rel.startswith("Sounds/")):
            continue
        dst = os.path.join(out_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with zf.open(n) as f, open(dst, "wb") as g:
            shutil.copyfileobj(f, g)
        n_ok += 1
    log(f"基准数据: 前缀 '{prefix}'，提取 {n_ok} 个文件 → {out_dir}")
    _write_base_cache(marker, base_pkg)
    return out_dir


# ================================================================ 校验 / 引用
def run_validate(mod_dir, ref_dir=None, ext_enums_text=None, progress=None):
    if V is None:
        return 2, "缺少 validate.py（需与 ffpack.py 同目录）"
    if not os.path.isdir(os.path.join(mod_dir, "Data")):
        return 2, "MOD 工程没有 Data 目录"
    if ext_enums_text is None:
        st = load_settings()
        ext_enums_text = st.get("Enums") or None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = V.run_check(mod_dir, ref=ref_dir, ext_text=ext_enums_text, progress=progress)
    return rc, buf.getvalue()


def parse_mod_txt(mod_dir):
    """解析 mod.txt: 阵营装备清单、surnames、flags、default_images、voices"""
    p = os.path.join(mod_dir, "mod.txt")
    t = open(p, encoding="utf-8", errors="replace").read()
    info = {"equipments": set(), "surnames": set(), "images": set(), "voices": set()}
    for blk in re.finditer(r"<nationality>(.*?)</nationality>", t, re.S):
        b = blk.group(1)
        info["equipments"].update(re.findall(r"<equipment>([^<]+)</equipment>", b))
        info["surnames"].update(re.findall(r"<surnames>([^<]+)</surnames>", b))
        info["images"].update(re.findall(r"<(?:static|animated|infantry|tank_crew|infantry_profile|tank_crew_profile|ranks)>([^<]+)</", b))
        info["voices"].update(re.findall(r"<voice>([^<]+)</voice>", b))
    return info


def referenced_files(mod_dir, log=print):
    """引用闭包: mod.txt → 装备表 → 单位 → 依赖（武器/弹药/图片/制服/音效）。
    只收集闭包内文件（相对 Mod 根的 posix 路径）；不在闭包内的 Data 文件视为未引用。"""
    info = parse_mod_txt(mod_dir)
    ref = set()
    data = os.path.join(mod_dir, "Data")

    # ---- 所有 Data txt 的 id → 相对路径 索引 ----
    id_map = {}
    all_txt = glob.glob(os.path.join(data, "**", "*.txt"), recursive=True)
    for p in all_txt:
        rel = os.path.relpath(p, mod_dir).replace(os.sep, "/")
        id_map[os.path.splitext(os.path.basename(rel))[0]] = rel

    def add(name):
        ref.add(name.replace("\\", "/"))
        return name

    # ---- 闭包遍历 ----
    IMG_RE = re.compile(r"[A-Za-z0-9 ()_\-.]+\.png", re.I)
    SND_RE = re.compile(r"\b(shoot_[A-Za-z0-9_]+|reload_magazine|eject_clip)\b")
    UNI_RE = re.compile(r"<uniform>\s*([^<]+?)\s*</uniform>")
    IMG_BASES = tuple(load_image_dirs())     # data/image_dirs.txt
    ids = sorted(id_map, key=len, reverse=True)
    ID_RE = re.compile("(?<![A-Za-z0-9_])(?:" + "|".join(re.escape(i) for i in ids) + ")(?![A-Za-z0-9_])") \
        if ids else None

    # 根: mod.txt + 装备表 + 姓氏表
    queue = []
    langs = set(info["voices"])                          # 语音语言（主循环顺带收集）
    if os.path.isfile(os.path.join(mod_dir, "mod.txt")):
        queue.append("mod.txt")
    for e in info["equipments"]:
        rel = "Data/" + e.replace("\\", "/")
        if os.path.isfile(os.path.join(mod_dir, rel.replace("/", os.sep))):
            queue.append(rel)
    for sn in info["surnames"]:
        rel = "Data/Surnames/" + sn.replace("\\", "/")
        if os.path.isfile(os.path.join(mod_dir, rel.replace("/", os.sep))):
            queue.append(rel)

    seen = set()
    while queue:
        rel = queue.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        ref.add(rel)
        p = os.path.join(mod_dir, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            continue
        t = read_txt(p)
        # 制服（整包目录）
        for u in set(UNI_RE.findall(t)):
            add(f"Images/Uniforms/uniform_game_{u}.png")
            add(f"Images/Uniforms/uniform_profile_{u}.png")
            add(f"Images/Uniforms/uniform_{u}/")
        # 图片
        for m in IMG_RE.finditer(t):
            nm = m.group(0).strip()
            for base in IMG_BASES:
                if os.path.exists(os.path.join(mod_dir, f"{base}/{nm}")):
                    add(f"{base}/{nm}")
        # 音效
        for m in SND_RE.finditer(t):
            add(f"Sounds/{m.group(1)}.ogg")
        # 语音语言: 单位国籍 → 两字母代码（随主循环收集，避免二次全量读盘）
        for nat in set(re.findall(r"NATIONALITY_(\w+)", t)):
            if nat in NAT2LANG:
                langs.add(NAT2LANG[nat])
        # txt 依赖: 装备表→单位、单位→武器、武器→弹药/子武器等
        if ID_RE:
            for m in ID_RE.finditer(t):
                rel2 = id_map[m.group(0)]
                if rel2 != rel and rel2 not in seen:
                    queue.append(rel2)

    # default_images 里的制服名 -> 对应制服整包目录
    for u in set(re.findall(r"uniform_(?:game|profile)_([a-z0-9_]+?)\.png", " ".join(info["images"]))):
        add(f"Images/Uniforms/uniform_game_{u}.png")
        add(f"Images/Uniforms/uniform_profile_{u}.png")
        add(f"Images/Uniforms/uniform_{u}/")
    for i in info["images"]:
        for cand in (f"Images/{i}", f"Images/Uniforms/{i}"):
            if os.path.exists(os.path.join(mod_dir, cand)):
                add(cand)
    # 发动机音: 不逐文件枚举（13.x 目录已改名 Engines 且 rpm 档位有变），
    # 整目录由基准 APK 提供，find_unreferenced 的基准豁免 + check_mod_audio 引擎音盘点覆盖
    # 语音目录: mod.txt voices + 闭包内单位国籍映射（主循环已收集 langs）
    for lg in langs:
        add(f"Sounds/Voices/{lg}/")
        # 语音 = 两字母代码目录；缺失只警告不阻断
        if not os.path.isdir(os.path.join(mod_dir, "Sounds", "Voices", lg)):
            log(f"⚠️ 语音目录缺失（将沿用基准/原版）: Sounds/Voices/{lg}/")
    return ref


def find_unreferenced(mod_dir, base_dir=None, log=print, refs=None):
    """MOD 根下未被引用链覆盖的文件。base_dir: 基准数据目录，
    路径相同的文件视为"覆盖原版内容"，不列入剔除清单。refs: 预计算的引用闭包"""
    ref = refs if refs is not None else referenced_files(mod_dir, log=log)
    base_files = set()
    if base_dir and os.path.isdir(base_dir):
        for dp, _, fs in os.walk(base_dir):
            for f in fs:
                base_files.add(os.path.relpath(os.path.join(dp, f), base_dir).replace(os.sep, "/"))

    def hit(rel):
        name = os.path.basename(rel)
        if rel in ref:
            return True
        for r in ref:
            if r.endswith("/") and rel.startswith(r):
                return True
        return name in {os.path.basename(r) for r in ref if not r.endswith("/")} and False

    out = []
    for root, _, files in os.walk(mod_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), mod_dir).replace(os.sep, "/")
            if rel == "mod.txt" or "/" not in rel:
                continue                                # mod.txt 与根目录散文件不参与引用分析
            ok = (rel in ref
                  or any(r.endswith("/") and rel.startswith(r) for r in ref)
                  or rel in base_files)          # 原版也有 = 覆盖原版内容，保留
            if not ok:
                out.append(rel)
    return sorted(out)


def prune(mod_dir, files, log=print):
    for rel in files:
        p = os.path.join(mod_dir, rel.replace("/", os.sep))
        if os.path.exists(p):
            os.remove(p)
    for root, dirs, fs in os.walk(mod_dir, topdown=False):
        if root != mod_dir and not dirs and not fs:
            os.rmdir(root)
    log(f"已剔除 {len(files)} 个未引用文件")


# ================================================================ AXML/ARSC（含 ManifestEditor 桥）
def _parse_string_pool(data, off):
    ctype, chs, csize = struct.unpack_from("<HHI", data, off)
    cnt, style_cnt, flags, strings_start, styles_start = struct.unpack_from("<5I", data, off + 8)
    utf8 = bool(flags & UTF8_FLAG)
    base = off + strings_start
    out = []
    for i in range(cnt):
        p = base + struct.unpack_from("<I", data, off + 28 + 4 * i)[0]
        if utf8:
            n1 = data[p]; p += 2 if n1 & 0x80 else 1
            if n1 & 0x80: n1 = ((n1 & 0x7F) << 8) | data[p - 1]
            n2 = data[p]; p += 2 if n2 & 0x80 else 1
            if n2 & 0x80: n2 = ((n2 & 0x7F) << 8) | data[p - 1]
            out.append(data[p:p + n2].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", data, p)[0]; p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", data, p)[0]; p += 2
            out.append(data[p:p + 2 * n].decode("utf-16-le", "replace"))
    return out, utf8


def _build_string_pool(strings, utf8):
    offsets, body = [], bytearray()
    for s in strings:
        offsets.append(len(body))
        if utf8:
            b = s.encode("utf-8")
            for n in (len(s), len(b)):
                body += bytes([0x80 | (n >> 8), n & 0xFF]) if n > 0x7F else bytes([n])
            body += b + b"\0"                              # UTF-8 池要求 NUL 结尾
        else:
            u = s.encode("utf-16-le")
            if len(s) > 0x7FFE:
                body += struct.pack("<HH", 0x8000 | (len(s) >> 16), len(s) & 0xFFFF)
            else:
                body += struct.pack("<H", len(s))
            body += u + b"\0\0"                           # UTF-16 池要求 NUL 结尾
        body += b"\0" * ((4 - len(body) % 4) % 4)
    strings_start = 28 + 4 * len(strings)
    while len(body) % 4:
        body += b"\0"
    head = struct.pack("<HHIIIIII", RES_STRING_POOL_TYPE, 28, strings_start + len(body),
                       len(strings), 0, UTF8_FLAG if utf8 else 0, strings_start, 0)
    return head + b"".join(struct.pack("<I", o) for o in offsets) + bytes(body)


def arsc_replace_strings(data, replacements):
    """resources.arsc: ResTable header 后的 global string pool（及各 package 内池）替换"""
    out = bytearray()
    off = 0
    if len(data) >= 12 and struct.unpack_from("<H", data, 0)[0] == 0x0002:
        hs = struct.unpack_from("<H", data, 2)[0]
        out += data[:hs]                    # 保留 ResTable header
        off = hs
    while off + 8 <= len(data):
        ctype, _, csize = struct.unpack_from("<HHI", data, off)
        if csize < 8 or off + csize > len(data):
            out += data[off:]
            break
        if ctype == RES_STRING_POOL_TYPE:
            pool, utf8 = _parse_string_pool(data, off)
            out += _build_string_pool([replacements.get(s, s) for s in pool], utf8)
        else:
            out += data[off:off + csize]
        off += csize
    return bytes(out)


def read_apk_manifest(apk_path):
    if ManifestEditor is None:
        raise RuntimeError("缺少 ManifestEditor 包（需与 ffpack.py 同目录）")
    with zipfile.ZipFile(apk_path) as z:
        xml = z.read("AndroidManifest.xml")
    t = tempfile.mktemp(".xml")
    open(t, "wb").write(xml)
    try:
        am = ManifestEditor.AndroidManifest(t)
        tc = am.xml_chunk.find_tag_chunk("manifest")
        return {k: tc.get_attr_value(k) for k in ("package", "versionCode", "versionName")}
    finally:
        os.remove(t)


def parse_arsc_names(arsc_bytes):
    """拆解 resources.arsc：返回 {键名: [该键在各语言配置下的字符串值]}（仅键名含 name 的 string 资源）"""
    d = arsc_bytes

    def parse_pool(off):
        cnt = struct.unpack_from("<I", d, off + 8)[0]
        flags = struct.unpack_from("<I", d, off + 16)[0]
        sstart = struct.unpack_from("<I", d, off + 20)[0]
        utf8 = bool(flags & 0x100)
        base = off + sstart
        out = []
        for i in range(cnt):
            p = base + struct.unpack_from("<I", d, off + 28 + 4 * i)[0]
            if utf8:
                n1 = d[p]; p += 2 if n1 & 0x80 else 1
                if n1 & 0x80: n1 = ((n1 & 0x7F) << 8) | d[p - 1]
                n2 = d[p]; p += 2 if n2 & 0x80 else 1
                if n2 & 0x80: n2 = ((n2 & 0x7F) << 8) | d[p - 1]
                out.append(d[p:p + n2].decode("utf-8", "replace"))
            else:
                n = struct.unpack_from("<H", d, p)[0]; p += 2
                if n & 0x8000:
                    n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", d, p)[0]; p += 2
                out.append(d[p:p + 2 * n].decode("utf-16-le", "replace"))
        return out

    result = {}
    hs = struct.unpack_from("<H", d, 2)[0]
    off = hs
    gpool = None
    # global string pool（第一个池）
    if struct.unpack_from("<H", d, off)[0] == RES_STRING_POOL_TYPE:
        gpool = parse_pool(off)
        off += struct.unpack_from("<I", d, off + 4)[0]
    while off + 8 <= len(d):
        ctype, _, csize = struct.unpack_from("<HHI", d, off)
        if csize < 8 or off + csize > len(d):
            break
        if ctype == 0x0200:                                  # ResTable_package
            phs = struct.unpack_from("<H", d, off + 2)[0]
            ts_off = struct.unpack_from("<I", d, off + 268)[0]
            ks_off = struct.unpack_from("<I", d, off + 276)[0]
            types = parse_pool(off + ts_off)
            keys = parse_pool(off + ks_off)
            string_tids = [i + 1 for i, t in enumerate(types) if t == "string"]
            name_keys = {i for i, k in enumerate(keys) if "name" in k.lower()}
            o2 = off + phs
            while o2 < off + csize:
                ct2, _, cs2 = struct.unpack_from("<HHI", d, o2)
                if cs2 < 8 or o2 + cs2 > off + csize:
                    break
                if ct2 == 0x0201 and d[o2 + 8] in string_tids:   # ResTable_type
                    ec, estart = struct.unpack_from("<II", d, o2 + 12)
                    ths = struct.unpack_from("<H", d, o2 + 2)[0]   # offsets 数组在 type header 之后
                    for ei in range(ec):
                        eo = struct.unpack_from("<I", d, o2 + ths + 4 * ei)[0]
                        if eo == 0xFFFFFFFF:
                            continue
                        ep = o2 + estart + eo
                        if ep + 16 > off + csize:
                            continue
                        eflags, ekey = struct.unpack_from("<HH", d, ep + 2)
                        if eflags & 1 or ekey not in name_keys:
                            continue
                        esz = struct.unpack_from("<H", d, ep)[0]      # entry 头大小
                        vp = ep + esz                                 # Res_value 起点
                        if vp + 8 > off + csize:
                            continue
                        if d[vp + 3] == 3:                            # Res_value.dataType == STRING
                            dval = struct.unpack_from("<I", d, vp + 4)[0]
                            if dval < len(gpool):
                                result.setdefault(keys[ekey], [])
                                if gpool[dval] not in result[keys[ekey]]:
                                    result[keys[ekey]].append(gpool[dval])
                o2 += cs2
        off += csize
    return result


def _rebuild_type_chunk(d, o2, entries, array_len=None):
    """重建 ResTable_type（dense）chunk。
    entries: {entryIdx: entry_bytes}；缺的槽位补 0xFFFFFFFF。
    array_len: 偏移数组长度（默认 = max idx+1）。"""
    hsize = struct.unpack_from("<H", d, o2 + 2)[0]
    flags = struct.unpack_from("<H", d, o2 + 10)[0] & ~1        # 清 sparse 位, 统一 dense
    if array_len is None:
        array_len = max(entries) + 1 if entries else 0
    estart = hsize + 4 * array_len
    body = bytearray()
    offsets = []
    for i in range(array_len):
        if i not in entries:
            offsets.append(0xFFFFFFFF)
            continue
        if len(body) % 4:
            body += b"\0" * (4 - len(body) % 4)
        offsets.append(len(body))
        body += entries[i]
    while (estart + len(body)) % 4:
        body += b"\0"
    total = estart + len(body)
    head = bytearray(d[o2:o2 + hsize])
    struct.pack_into("<I", head, 4, total)
    struct.pack_into("<H", head, 10, flags)
    struct.pack_into("<I", head, 12, array_len)
    struct.pack_into("<I", head, 16, estart)
    return bytes(head) + b"".join(struct.pack("<I", o) for o in offsets) + bytes(body)


def _parse_type_entries(d, o2):
    """解析 ResTable_type chunk → {entryIdx: (keyIdx, entry_bytes, dtype, dval)}"""
    hsize = struct.unpack_from("<H", d, o2 + 2)[0]
    ec, estart = struct.unpack_from("<II", d, o2 + 12)
    out = {}
    for ei in range(ec):
        eo = struct.unpack_from("<I", d, o2 + hsize + 4 * ei)[0]
        if eo == 0xFFFFFFFF:
            continue
        ep = o2 + estart + eo
        esz, eflags, ekey = struct.unpack_from("<HHI", d, ep)
        if eflags & 1:                                           # complex/map 条目
            out[ei] = (ekey, d[ep:ep + esz + 8], -1, -1)
            continue
        vp = ep + esz
        dtype = d[vp + 3]
        dval = struct.unpack_from("<I", d, vp + 4)[0]
        out[ei] = (ekey, d[ep:ep + esz + 8], dtype, dval)
    return out




def _config_locale(d, o2):
    """读 ResTable_type 的 config 语言 → 'zh-rCN' / 'en' / 'default'"""
    lang = d[o2 + 28:o2 + 30].decode("ascii", "replace").replace("\x00", "")
    ctry = d[o2 + 30:o2 + 32].decode("ascii", "replace").replace("\x00", "")
    if not lang:
        return "default"
    return f"{lang}-r{ctry}" if ctry else lang


def set_app_name_all_locales(arsc_bytes, names, log=print):
    """确保 string 资源的每个语言 config 都有 app_name 条目。
    names: str（全部同名）或 {locale: name}（如 {'default': 'Firefight: ...',
    'zh-rCN': '交战：...', 'en': '...'}；查表顺序 精确locale → 语言 → default）。
    AAPT2 的 Entry ID 与 key 号不同：偏移数组位置 = 跨 config 一致的 Entry ID，
    key 号存在 entry 内。缺失的 config 把 app_name 插到同一 Entry ID 槽位，
    空槽补 0xFFFFFFFF；typeSpec entryCount 同步扩大。"""
    d = arsc_bytes
    hs = struct.unpack_from("<H", d, 2)[0]

    gpool, gutf8 = _parse_string_pool(d, hs)
    if isinstance(names, str):
        names = {"default": names}

    def name_for(loc):
        lang = loc.split("-")[0]
        return (names.get(loc) or names.get(lang) or names.get("default")
                or names.get("(default)") or next(iter(names.values())))

    # 所有将用到的名字先并入 pool，得到 {locale: gidx}
    loc_names, gidx_map = {}, {}
    tmp_off = hs + struct.unpack_from("<I", d, hs + 4)[0]
    phs0 = struct.unpack_from("<H", d, tmp_off + 2)[0]
    csize0 = struct.unpack_from("<I", d, tmp_off + 4)[0]
    tmp_types = _parse_string_pool(d, tmp_off + struct.unpack_from("<I", d, tmp_off + 268)[0])[0]
    stids0 = {i + 1 for i, t in enumerate(tmp_types) if t == "string"}
    o = tmp_off + phs0
    while o + 8 <= tmp_off + csize0:
        ct2, hs2, cs2 = struct.unpack_from("<HHI", d, o)
        if cs2 < 8 or o + cs2 > tmp_off + csize0:
            break
        if ct2 == 0x0201 and d[o + 8] in stids0:
            loc = _config_locale(d, o)
            if loc not in loc_names:
                loc_names[loc] = name_for(loc)
        o += cs2
    for loc, nm in loc_names.items():
        if nm in gpool:
            gidx_map[loc] = gpool.index(nm)
        else:
            gpool = gpool + [nm]
            gidx_map[loc] = len(gpool) - 1
    new_gpool_chunk = _build_string_pool(gpool, gutf8)

    def parse_pool(off):
        return _parse_string_pool(d, off)[0]

    def app_entry(appkey, loc):
        return struct.pack("<HHI", 8, 0, appkey) + struct.pack("<HBBI", 8, 0, 3, gidx_map[loc])

    out_pkg_chunks = []
    off = hs + struct.unpack_from("<I", d, hs + 4)[0]
    while off + 8 <= len(d):
        ctype, _, csize = struct.unpack_from("<HHI", d, off)
        if csize < 8 or off + csize > len(d):
            out_pkg_chunks.append(d[off:])
            break
        if ctype != 0x0200:
            out_pkg_chunks.append(d[off:off + csize])
            off += csize
            continue
        phs = struct.unpack_from("<H", d, off + 2)[0]
        types = parse_pool(off + struct.unpack_from("<I", d, off + 268)[0])
        keys = parse_pool(off + struct.unpack_from("<I", d, off + 276)[0])
        string_tids = set(i + 1 for i, t in enumerate(types) if t == "string")
        appkey = keys.index("app_name") if "app_name" in keys else None

        # ---- 第一遍: 扫描, 确定各 string 类型的 app Entry ID 与 spec entryCount ----
        str_chunks = []                                          # [(o2, tid, entries)]
        spec_ec = {}                                             # tid -> typeSpec entryCount
        app_ei = {}                                              # tid -> Entry ID
        o2 = off + phs
        while o2 < off + csize:
            ct2, hs2, cs2 = struct.unpack_from("<HHI", d, o2)
            if cs2 < 8 or o2 + cs2 > off + csize:
                break
            tid = d[o2 + 8] if ct2 in (0x0201, 0x0202) else None
            if ct2 == 0x0202 and tid in string_tids:
                spec_ec[tid] = max(spec_ec.get(tid, 0), struct.unpack_from("<I", d, o2 + 12)[0])
            elif ct2 == 0x0201 and tid in string_tids and appkey is not None:
                entries = _parse_type_entries(d, o2)
                str_chunks.append((o2, tid, entries))
                for ei, (k, _, _, _) in entries.items():
                    if k == appkey:
                        cur = app_ei.setdefault(tid, ei)
                        if cur != ei:
                            log(f"⚠️ string 类型 {tid}: app_name 出现在多个 Entry ID ({cur}/{ei})")
            o2 += cs2
        for tid in set(t for _, t, _ in str_chunks):
            if tid not in app_ei:                                # 整类型都没有 → 分配新 Entry ID
                app_ei[tid] = spec_ec.get(tid, 0)
        need_spec = {}                                           # tid -> 重建后需要的 entryCount
        for _, tid, entries in str_chunks:
            ae = app_ei[tid]
            need_spec[tid] = max(need_spec.get(tid, 0),
                                 max(max(entries) + 1, ae + 1))

        # ---- 第二遍: 重建 type 条目 + 就地扩容 typeSpec ----
        added = replaced = 0
        inner = bytearray()
        o2 = off + phs
        while o2 < off + csize:
            ct2, hs2, cs2 = struct.unpack_from("<HHI", d, o2)
            if cs2 < 8 or o2 + cs2 > off + csize:
                inner += d[o2:off + csize]
                break
            tid = d[o2 + 8] if ct2 in (0x0201, 0x0202) else None
            if ct2 == 0x0201 and tid in app_ei:
                parsed = _parse_type_entries(d, o2)
                entries = {ei: e[1] for ei, e in parsed.items()}
                app_here = [ei for ei, e in parsed.items() if e[0] == appkey]
                loc = _config_locale(d, o2)
                if app_here:
                    replaced += 1
                    for ei in app_here:
                        entries[ei] = app_entry(appkey, loc)
                else:
                    added += 1
                    entries[app_ei[tid]] = app_entry(appkey, loc)
                array_len = max(max(entries) + 1, app_ei[tid] + 1)
                inner += _rebuild_type_chunk(d, o2, entries, array_len)
            elif ct2 == 0x0202 and tid in need_spec:
                want = max(need_spec[tid], struct.unpack_from("<I", d, o2 + 12)[0])
                cur = struct.unpack_from("<I", d, o2 + 12)[0]
                if want > cur:
                    head = bytearray(d[o2:o2 + hs2])
                    struct.pack_into("<I", head, 4, hs2 + 4 * want)
                    struct.pack_into("<I", head, 12, want)
                    inner += head + d[o2 + hs2:o2 + hs2 + 4 * cur] + b"\0" * (4 * (want - cur))
                else:
                    inner += d[o2:o2 + cs2]
            else:
                inner += d[o2:o2 + cs2]
            o2 += cs2
        if added or replaced:
            log(f"[arsc] app_name: 替换 {replaced} 处, 新增 {added} 个语言配置 (Entry ID={app_ei})")
        new_pkg = bytearray(d[off:off + phs])
        struct.pack_into("<I", new_pkg, 4, phs + len(inner))
        out_pkg_chunks.append(bytes(new_pkg) + bytes(inner))
        off += csize

    head = bytearray(d[:hs])
    struct.pack_into("<I", head, 4, hs + len(new_gpool_chunk) + sum(len(c) for c in out_pkg_chunks))
    return bytes(head) + new_gpool_chunk + b"".join(out_pkg_chunks)


def _png_size(b):
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", b[16:24])


def load_icon_pool(src):
    """图标来源: png 文件 / zip / 文件夹 → [(相对路径, w, h, bytes)]
    zip 内按原相对路径（如 res/bS.png）保留，便于同名直配"""
    pool = []
    if os.path.isdir(src):
        for dp, _, fs in os.walk(src):
            for f in fs:
                if f.lower().endswith(".png"):
                    b = open(os.path.join(dp, f), "rb").read()
                    sz = _png_size(b)
                    if sz:
                        rel = os.path.relpath(os.path.join(dp, f), src).replace(os.sep, "/")
                        pool.append((rel, sz[0], sz[1], b))
    elif zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            for n in z.namelist():
                if n.lower().endswith(".png") and not n.endswith("/"):
                    b = z.read(n)
                    sz = _png_size(b)
                    if sz:
                        pool.append((n, sz[0], sz[1], b))
    elif os.path.isfile(src):
        b = open(src, "rb").read()
        sz = _png_size(b)
        if sz:
            pool.append((os.path.basename(src), sz[0], sz[1], b))
    return pool


def _pick_icon(pool, name, orig_bytes):
    """图标选择: ① 同名（res/ 路径一致）→ ② 同尺寸 → ③ 池里唯一一张"""
    by_name = {p: (w, h, b) for p, w, h, b in pool}
    if name in by_name:
        return by_name[name][2]
    osz = _png_size(orig_bytes) if orig_bytes[:8] == b"\x89PNG\r\n\x1a\n" else None
    if osz:
        for p, w, h, b in pool:
            if (w, h) == osz:
                return b
    if len(pool) == 1:
        return pool[0][3]
    return None


def check_mod_audio(mod_dir, base_dir=None, log=print, refs=None):
    """音频对照: 列出原版语音清单（两字母代码目录），Mod 引用逐项对照；
    语音/其他音频缺失（Mod 与基准都没有）只警告不阻断。refs: 预计算的引用闭包"""
    ref = refs if refs is not None else referenced_files(mod_dir, log=log)
    voice_refs = {r.split("/")[2] for r in ref if r.startswith("Sounds/Voices/") and r.endswith("/")}
    sound_refs = {r for r in ref if r.startswith("Sounds/") and r.endswith(".ogg")
                  and "TankEngine" not in r}

    def inventory(root):
        files, dirs = set(), set()
        d = os.path.join(root, "Sounds")
        if os.path.isdir(d):
            for dp, dn, fs in os.walk(d):
                rel = os.path.relpath(dp, root).replace(os.sep, "/")
                for x in dn:
                    dirs.add(f"{rel}/{x}")
                for f in fs:
                    files.add(f"{rel}/{f}")
        return files, dirs

    mod_files, mod_dirs = inventory(mod_dir)
    base_files, base_dirs = inventory(base_dir) if base_dir and os.path.isdir(base_dir) else (set(), set())
    base_voices = {x.split("/")[-1] for x in base_dirs
                   if x.startswith("Sounds/Voices/") and x != "Sounds/Voices"}
    mod_voices = {x.split("/")[-1] for x in mod_dirs
                  if x.startswith("Sounds/Voices/") and x != "Sounds/Voices"}

    # 引擎音: 原版整目录提供（Sounds/Engines|Tank Engine/TankEngine*.ogg），Mod 没有就读原版
    base_eng = {f for f in base_files
                if "/TankEngine" in f or f.endswith("/TankEngine.ogg")}
    mod_eng = {f for f in mod_files if "/TankEngine" in f or f.endswith("/TankEngine.ogg")}
    log(f"[引擎音] 原版 {len(base_eng)} 个（Sounds/Engines/），Mod {len(mod_eng)} 个 —— "
        + ("沿用原版" if base_eng and not mod_eng else "Mod 自带" if mod_eng else "⚠️ 双方均无引擎音"))

    log(f"[语音清单] 原版共 {len(base_voices)} 种: {' '.join(sorted(base_voices)) or '（基准无语音）'}")
    for lg in sorted(voice_refs):
        if lg in mod_voices:
            log(f"    语音 {lg}: Mod 自带{'（覆盖原版）' if lg in base_voices else '（原版无此语言）'}")
        elif lg in base_voices:
            pass                                            # 沿用原版，静默
        else:
            log(f"    ⚠️ 语音 {lg}: Mod 与原版清单均无此语言目录")
    ALIAS = {"Sounds/Tank Engine/": "Sounds/Engines/",          # 13.x 目录改名
             "Sounds/Engines/": "Sounds/Tank Engine/"}
    miss = 0
    for f in sorted(sound_refs):
        alt = None
        for old_p, new_p in ALIAS.items():
            if f.startswith(old_p):
                alt = new_p + f.split("/", 1)[1]
        if (f in mod_files or f in base_files
                or (alt and (alt in mod_files or alt in base_files))):
            continue
        miss += 1
        if miss <= 20:
            log(f"    ⚠️ 音频缺失: {f}")
    if miss > 20:
        log(f"    ⚠️ …另有 {miss - 20} 个音频缺失")
    log(f"[音频] 引用 {len(sound_refs)} 个 ogg，缺失 {miss} 个")


def patch_manifest_permissions(manifest_bytes, old_pkg, new_pkg, log=print):
    """改包名后，同步 manifest 中引用旧包名的包级标识符:
    - uses-permission/permission 的 name（如 <old>.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION）
    - provider 的 authorities（如 <old>.androidx-startup，不改会与原版同装冲突）
    注意: 组件类名（activity name 等）指向 dex 里的旧包类，绝不能改。"""
    tmp = tempfile.mktemp(".xml")
    open(tmp, "wb").write(manifest_bytes)
    out = tempfile.mktemp(".xml")
    try:
        am = ManifestEditor.AndroidManifest(tmp)
        changed = 0
        for tag, attr_key in (("uses-permission", "name"), ("permission", "name"),
                              ("provider", "authorities")):
            for chunk in (am.xml_chunk._tag_chunk_arr.get(tag) or []):
                q = chunk.query_attribute(attr_key, None)
                val = q.get("data") if q else None
                if val and val.startswith(old_pkg + "."):
                    new_name = new_pkg + val[len(old_pkg):]
                    is_str, idx = chunk.modify(attr_key, new_name)
                    if is_str:
                        am.string_chunk.modify(idx, new_name)
                    changed += 1
                    log(f"    权限/authority 同步: {val} → {new_name}")
        if not changed:
            return manifest_bytes
        am.output_bytes(out)
        return open(out, "rb").read()
    finally:
        for t in (tmp, out):
            if os.path.exists(t):
                os.remove(t)


def find_icon_paths(arsc_bytes, icon_id, log=print):
    """解析 resources.arsc，反查图标资源 ID（如 0x7f070013）对应的 res/ 文件路径（含混淆名）"""
    d = arsc_bytes
    hs = struct.unpack_from("<H", d, 2)[0]
    off = hs + struct.unpack_from("<I", d, hs + 4)[0]
    ct, phs, csize = struct.unpack_from("<HHI", d, off)
    gpool = _parse_string_pool(d, hs)[0]
    types = _parse_string_pool(d, off + struct.unpack_from("<I", d, off + 268)[0])[0]
    tid = (icon_id >> 16) & 0xFF
    eidx = icon_id & 0xFFFF
    tname = types[tid - 1] if 0 < tid <= len(types) else f"type{tid}"
    paths = []
    o2 = off + phs
    while o2 + 8 <= off + csize:
        ct2, hs2, cs2 = struct.unpack_from("<HHI", d, o2)
        if cs2 < 8 or o2 + cs2 > off + csize:
            break
        if ct2 == 0x0201 and d[o2 + 8] == tid:
            for ei, (k, raw, dtype, dval) in _parse_type_entries(d, o2).items():
                if ei == eidx and dtype == 3 and 0 <= dval < len(gpool):
                    paths.append(gpool[dval])
        o2 += cs2
    log(f"图标资源 @{icon_id:#010x}（{tname}）→ {len(paths)} 个文件: {paths[:4]}")
    return paths


def check_mod_images(mod_dir, base_dir=None, log=print):
    """打包前图片检查: 扫描 Mod 引用的图片，报告
    ① Mod 与基准都缺失的（APK 里会缺图） ② 从基准自动兜底的 ③ 覆盖基准的（图片更改）"""
    if V is None:
        return
    data = os.path.join(mod_dir, "Data")
    refs = set()
    pat = re.compile(r">([^<>]*\.png)<")          # 只取标签值，避免抓到注释/正文文本
    for dp, _, fs in os.walk(data):
        for f in fs:
            if f.endswith(".txt"):
                t = open(os.path.join(dp, f), encoding="utf-8", errors="replace").read()
                refs.update(m.group(1) for m in pat.finditer(t))
    # 图片文件名 → Mod 内实际路径
    mod_imgs = {}
    for dp, _, fs in os.walk(os.path.join(mod_dir, "Images")):
        for f in fs:
            if f.lower().endswith(".png"):
                mod_imgs.setdefault(f, []).append(os.path.relpath(os.path.join(dp, f), mod_dir).replace(os.sep, "/"))
    base_imgs = set()
    if base_dir and os.path.isdir(os.path.join(base_dir, "Images")):
        for dp, _, fs in os.walk(os.path.join(base_dir, "Images")):
            for f in fs:
                if f.lower().endswith(".png"):
                    base_imgs.add(f)
    missing, fallback, overridden = [], 0, 0
    for name in sorted(refs):
        if name in mod_imgs:
            if name in base_imgs:
                overridden += 1
        elif name in base_imgs:
            fallback += 1
        else:
            missing.append(name)
    log(f"[图片] 引用 {len(refs)} 张: 覆盖基准(图片更改) {overridden} 张, "
        f"基准兜底 {fallback} 张, 双缺 {len(missing)} 张")
    for m_ in missing[:20]:
        log(f"    ⚠️ 缺图: {m_}")
    if len(missing) > 20:
        log(f"    ⚠️ …另有 {len(missing)-20} 张缺失")


def list_arsc_locales(apk_path):
    """列出基准 APK 的 string 资源全部语言 config（可本地化的文本就这些语言）"""
    with zipfile.ZipFile(apk_path) as z:
        d = z.read("resources.arsc")
    hs = struct.unpack_from("<H", d, 2)[0]
    off = hs + struct.unpack_from("<I", d, hs + 4)[0]
    phs = struct.unpack_from("<H", d, off + 2)[0]
    csize = struct.unpack_from("<I", d, off + 4)[0]
    types = _parse_string_pool(d, off + struct.unpack_from("<I", d, off + 268)[0])[0]
    stids = {i + 1 for i, t in enumerate(types) if t == "string"}
    locs = set()
    o = off + phs
    while o + 8 <= off + csize:
        ct2, hs2, cs2 = struct.unpack_from("<HHI", d, o)
        if cs2 < 8 or o + cs2 > off + csize:
            break
        if ct2 == 0x0201 and d[o + 8] in stids:
            locs.add(_config_locale(d, o))
        o += cs2
    return sorted(locs)


def repack_apk(src_apk, dst_apk, mod_dir=None, manifest_attrs=None, app_name=None,
               old_app_name=None, replace_mod=True, arsc_all=None, app_names=None,
               icon_path=None, log=print):
    """重打包 APK。icon_path: 自定义图标 png —— 替换 APK 内全部 ic_launcher 图标；
    为 None 时自动找 Mod 工程根的 icon.png / ic_launcher.png；找不到则不动图标。"""
    """
    以基准 APK 为模板重打包:
      - assets/Mod/ 整体替换为 mod_dir 内容（replace_mod=True）
      - AndroidManifest.xml 改 package/versionCode/versionName（manifest_attrs）
      - resources.arsc 把 old_app_name 字符串替换为 app_name
    保持各 entry 原压缩方式。注意: 输出为未签名 APK。
    """
    if ManifestEditor is None:
        raise RuntimeError("缺少 ManifestEditor 包")
    zin = zipfile.ZipFile(src_apk)
    has_apk_meta = "AndroidManifest.xml" in zin.namelist()
    if manifest_attrs and not has_apk_meta:
        log("基准为电脑版 zip（无 AndroidManifest.xml），跳过元数据修改，仅合并 Mod 数据")
        manifest_attrs = None
        arsc_patch = None
        app_name = None
    os.makedirs(os.path.dirname(dst_apk) or ".", exist_ok=True)
    mod_files = []
    if mod_dir and replace_mod:
        for root, _, fs in os.walk(mod_dir):
            for f in fs:
                p = os.path.join(root, f)
                mod_files.append((p, "assets/Mod/" + os.path.relpath(p, mod_dir).replace(os.sep, "/")))
    icon_n = 0
    icon_pool = []
    # 图标来源: 显式路径(png/zip/文件夹) → Mod 工程根的 icon.png
    if icon_path and (os.path.isfile(icon_path) or os.path.isdir(icon_path)):
        icon_pool = load_icon_pool(icon_path)
        _sizes = sorted({(w, h) for _, w, h, _ in icon_pool})
        log(f"图标来源: {icon_path}（{len(icon_pool)} 张，尺寸 {', '.join(f'{w}x{h}' for w, h in _sizes)}）")
    elif mod_dir:
        for cand in ("icon.png", "ic_launcher.png", os.path.join("Images", "icon.png")):
            p2 = os.path.join(mod_dir, cand)
            if os.path.isfile(p2):
                icon_pool = load_icon_pool(p2)
                log(f"使用 Mod 工程图标: {cand}")
                break
    icon_paths = set()
    if icon_pool:
        try:
            _mid = _extract_manifest(src_apk, tempfile.mktemp(".xml"))
            _am = ManifestEditor.AndroidManifest(_mid)
            _app = _am.xml_chunk.find_tag_chunk("application")
            _iv = _app.get_attr_value("icon") or ""
            os.remove(_mid)
            _iid = int(str(_iv).replace("@", "").replace("#", ""), 16) if _iv.startswith(("@", "#")) else None
            if _iid:
                _arsc = zipfile.ZipFile(src_apk).read("resources.arsc")
                icon_paths = set(find_icon_paths(_arsc, _iid, log=log))
            if not icon_paths:
                # 兜底: 常规命名
                icon_paths = {n for n in zipfile.ZipFile(src_apk).namelist()
                              if re.fullmatch(r"res/(mipmap|drawable)[^/]*/ic_launcher[^/]*\.png", n)}
        except Exception as e:
            log(f"⚠️ 图标路径解析失败（不替换图标）: {e}")
            icon_paths = set()

    # 生成新 manifest bytes
    new_manifest = None
    if manifest_attrs:
        cur = read_apk_manifest(src_apk)           # 只改实际存在的属性, 防 ManifestEditor None 崩溃
        patch = {}
        for k, v in manifest_attrs.items():
            if k not in cur or cur[k] is None:
                log(f"⚠️ manifest 无 <{k}> 属性，跳过")
                continue
            if k == "versionCode":
                v = int(v)
            patch[k] = v
        if patch:
            tmp = tempfile.mktemp(".xml")
            try:
                ManifestEditor.modify_xml_attr(_extract_manifest(src_apk, tmp), {"tag": "manifest"},
                                               [{"key": k, "value": v} for k, v in patch.items()])
                new_manifest = open(tmp, "rb").read()
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
    # 权限名随包名同步（DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION 等）
    if new_manifest and manifest_attrs and manifest_attrs.get("package"):
        old_pkg = (read_apk_manifest(src_apk) or {}).get("package")
        new_pkg = manifest_attrs["package"]
        if old_pkg and old_pkg != new_pkg:
            new_manifest = patch_manifest_permissions(new_manifest, old_pkg, new_pkg, log=log)

    if arsc_all and not app_names:
        arsc_repl = dict(arsc_all)                     # 多语言应用名: {旧名: 新名, ...}
    elif app_name and old_app_name and not app_names:
        arsc_repl = {old_app_name: app_name}
    else:
        arsc_repl = None

    with zipfile.ZipFile(dst_apk, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
        _total = len(zin.infolist())
        for _i, info in enumerate(zin.infolist()):
            if _i % 2000 == 0 and _i:
                log(f"    APK 写入 {_i}/{_total}（{_i * 100 // _total}%）")
            name = info.filename
            if replace_mod and name.startswith("assets/Mod/"):
                continue                              # 旧 Mod 全部移除
            data = zin.read(name)
            if name == "AndroidManifest.xml" and new_manifest:
                data = new_manifest
            elif icon_pool and name in icon_paths:
                cand = _pick_icon(icon_pool, name, data)
                if cand:
                    data = cand
                    icon_n += 1
                else:
                    log(f"    ⚠️ 图标 {name} 无匹配尺寸，保留原版")
            elif name == "resources.arsc" and (app_names or arsc_repl):
                if app_names:
                    data = set_app_name_all_locales(data, app_names, log=log)
                else:
                    data = arsc_replace_strings(data, arsc_repl)
                    data = set_app_name_all_locales(data, list(arsc_repl.values())[0], log=log)
            zi = zipfile.ZipInfo(name, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)
        for p, arcname in mod_files:
            zi = zipfile.ZipInfo(arcname, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            with open(p, "rb") as f:
                zout.writestr(zi, f.read())
    if icon_pool and icon_n:
        log(f"图标替换 {icon_n} 处")
    log(f"APK 重打包完成（Mod 文件 {len(mod_files)}）→ {dst_apk}")
    if manifest_attrs:
        log("⚠️ 输出为未签名 APK，安装前需 apksigner/jarsigner 签名")


def _extract_manifest(src_apk, tmp):
    with zipfile.ZipFile(src_apk) as z:
        open(tmp, "wb").write(z.read("AndroidManifest.xml"))
    return tmp


def _find_build_tool(name):
    """在 Android SDK build-tools 与 PATH 中查找 apksigner/zipalign"""
    from shutil import which
    p = which(name)
    if p:
        return p
    sdk = os.environ.get("LOCALAPPDATA", "")
    cands = sorted(glob.glob(os.path.join(sdk, "Android", "Sdk", "build-tools", "*", name + "*")), reverse=True)
    return cands[0] if cands else None


# ---- 签名密钥（通用逻辑）----
# 无密钥签名使用 AOSP 官方通用测试密钥 keys/testkey.jks
# （别名 testkey / 密码 testkey，公开可验，与常见打包工具的默认密钥一致）
TESTKEY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys", "testkey.jks")
TESTKEY_PASS = "testkey"
TESTKEY_ALIAS = "testkey"
# 已知密钥文件的默认凭据（按文件名匹配，用户未填时使用）


def _gen_debug_keystore(ks, log=print):
    """keytool 自动生成 debug keystore"""
    from shutil import which
    keytool = which("keytool")
    if not keytool:
        jh = os.environ.get("JAVA_HOME", "")
        for cand in (os.path.join(jh, "bin", "keytool.exe"), os.path.join(jh, "bin", "keytool")):
            if cand and os.path.exists(cand):
                keytool = cand
                break
    if not keytool:
        for jdk in sorted(glob.glob(r"C:/Program Files/Java/*/bin/keytool.exe"), reverse=True):
            keytool = jdk
            break
    if not keytool:
        log("⚠️ 找不到 keytool（需要 JDK/JRE），无法生成 keystore")
        return False
    os.makedirs(os.path.dirname(ks), exist_ok=True)
    log(f"自动生成 keystore → {ks}")
    r = os.system(f'"{keytool}" -genkeypair -keystore "{ks}" -storepass android '
                  f'-alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 '
                  f'-validity 10950 -dname "CN=Android Debug,O=Android,C=US"')
    return r == 0


def resolve_signing(keystore=None, ks_pass=None, alias=None, key_pass=None, log=print):
    """解析签名参数 → (路径, storepass, alias, keypass)。
    未指定 keystore 时使用 AOSP 官方 testkey；指定时文件必须存在，
    凭据未填则按文件名查默认表，仍缺失则报错。"""
    if not keystore:
        if os.path.isfile(TESTKEY_PATH):
            log(f"签名密钥: 官方默认 testkey（{TESTKEY_PATH}）")
            return TESTKEY_PATH, TESTKEY_PASS, TESTKEY_ALIAS, TESTKEY_PASS
        ks = os.path.join(os.path.expanduser("~"), ".android", "debug.keystore")
        if not os.path.isfile(ks) and not _gen_debug_keystore(ks, log=log):
            raise RuntimeError("无法准备默认签名密钥（testkey 缺失且 debug keystore 生成失败）")
        log(f"签名密钥: debug keystore（{ks}）")
        return ks, "android", "androiddebugkey", "android"
    keystore = os.path.normpath(keystore)
    if not os.path.isfile(keystore):
        raise RuntimeError(f"签名密钥文件不存在: {keystore}")
    base = os.path.basename(keystore).lower()
    d = KEY_CRED_DEFAULTS.get(base, ("", "", ""))
    ks_pass = ks_pass or d[0]
    alias = alias or d[1]
    key_pass = key_pass or d[2] or ks_pass
    if not ks_pass or not alias:
        raise RuntimeError(f"请填写 {base} 的 keystore 密码与别名")
    log(f"签名密钥: {keystore}（alias={alias}）")
    return keystore, ks_pass, alias, key_pass


def sign_apk(apk_path, keystore=None, ks_pass=None, alias=None, key_pass=None,
             schemes="v1+v2+v3", log=print):
    """zipalign + apksigner 签名（默认 debug keystore）。返回 True=成功"""
    import subprocess
    apksigner = _find_build_tool("apksigner")
    zipalign = _find_build_tool("zipalign")
    if not apksigner:
        log("⚠️ 未找到 apksigner（Android SDK build-tools），APK 保持未签名")
        return False
    try:
        keystore, ks_pass, alias, key_pass = resolve_signing(
            keystore, ks_pass, alias, key_pass, log=log)
    except RuntimeError as e:
        log(f"⚠️ 签名中止: {e}")
        return False
    aligned = apk_path + ".aligned"
    if zipalign:
        r = subprocess.run([zipalign, "-f", "-p", "4", apk_path, aligned],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(aligned):
            for _i in range(4):                        # 杀软可能瞬时锁文件, 重试替换
                try:
                    os.replace(aligned, apk_path)
                    break
                except PermissionError:
                    time.sleep(0.6)
            else:
                log("⚠️ zipalign 结果替换被占用，保留未对齐文件继续签名")
            if os.path.exists(aligned):
                try:
                    os.remove(aligned)
                except Exception:
                    pass
        else:
            log(f"zipalign 失败（继续直接签名）: {r.stderr[:200]}")
    sch = (schemes or "v1+v2+v3").lower()
    flags = []
    for v in ("v1", "v2", "v3"):
        flags += [f"--{v}-signing-enabled", "true" if v in sch else "false"]
    cmd = [apksigner, "sign", *flags,
           "--ks", keystore, "--ks-pass", f"pass:{ks_pass}",
           "--key-pass", f"pass:{key_pass}", "--ks-key-alias", alias, apk_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"⚠️ apksigner 失败: {(r.stderr or r.stdout)[:300]}")
        return False
    log(f"已签名（{os.path.basename(keystore)}）→ {apk_path}")
    # 成功 ≠ 有效: 强制 apksigner verify 实证，报告验证方案与证书指纹
    vr = subprocess.run([apksigner, "verify", "--print-certs", "-v", apk_path],
                        capture_output=True, text=True)
    vout = (vr.stdout or "") + (vr.stderr or "")
    if vr.returncode != 0 or "DOES NOT VERIFY" in vout:
        log("⚠️ 签名验证失败（此 APK 大概率无法安装）:")
        for ln in vout.splitlines()[:12]:
            log("    " + ln)
        return False
    schemes = [s.split(" scheme")[0] for s in re.findall(r"Verified using ([^:]+): true", vout)]
    m1 = re.search(r"certificate SHA-1 digest:\s*([0-9a-fA-F]+)", vout)
    log(f"✅ 签名验证通过（{'/'.join(schemes) or '无方案'}），证书 SHA-1: {m1.group(1).lower() if m1 else '?'}")
    if m1 and m1.group(1).lower() != "61ed377e85d386a8dfee6b864bd85b0bfaa5af81":
        log("    （非 AOSP testkey：与旧 testkey 包覆盖安装会签名冲突，需先卸载）")
    return True


def pack_mod_zip(mod_dir, dst_zip, log=print):
    os.makedirs(os.path.dirname(dst_zip) or ".", exist_ok=True)
    all_files = []
    for root, _, fs in os.walk(mod_dir):
        for f in fs:
            p = os.path.join(root, f)
            all_files.append((p, os.path.relpath(p, mod_dir).replace(os.sep, "/")))
    n = 0
    with zipfile.ZipFile(dst_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p, arc in all_files:
            z.write(p, arc)
            n += 1
            if n % 2000 == 0:
                log(f"    zip 写入 {n}/{len(all_files)}")
    log(f"MOD zip: {n} 个文件 → {dst_zip}")
    return dst_zip
