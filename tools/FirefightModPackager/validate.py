#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firefight MOD 数据校验器（基于原版 12.2.0 规范）

用法:
    python validate.py <MOD根目录> [--ref <原版Firefight目录>] [--strict]

检查项:
  1. 标签闭合 / 根元素 / 块顺序
  2. description 必填字段、type/nationality/quality/job/flavour 等枚举合法性
  3. availability 时间升序与取值域
  4. 武器引用是否存在、弹种是否在该武器中声明
  5. 图片引用是否存在于正确的 Units 子目录、尺寸是否合规
  6. uniform 目录是否存在
  7. 装甲值语法、炮塔必填字段
  8. equipment_*.txt 登记情况
  9. 武器文件自身字段与音效引用

退出码: 0 = 无 ERROR；1 = 有 ERROR
"""
import os, re, sys, struct, collections

# 原版数据文件一律为 Windows-1252（已用 1740 个原版文件 100% 验证：
# 全部能按 cp1252 解码，其中 67 个按 UTF-8 解码会失败）
ENC = "cp1252"

# ------------------------------ 枚举表 ------------------------------
_BASE_TYPES = {
    "TYPE_TANK": "Vehicles", "TYPE_INFANTRY_SECTION": "Infantry", "TYPE_ATGUN": "AT Guns",
    "TYPE_ARMOURED_CAR": "Vehicles", "TYPE_ASSAULT_GUN": "Vehicles", "TYPE_HALFTRACK": "Vehicles",
    "TYPE_MORTAR": "Infantry", "TYPE_HMG": "Infantry", "TYPE_HOWITZER": "AT Guns",
    "TYPE_BAZOOKA": "Infantry", "TYPE_AT_RIFLE": "Infantry", "TYPE_FLAMETHROWER": "Infantry",
    "TYPE_INFANTRY_FIGHTING_VEHICLE": "Vehicles", "TYPE_RECOILLESS_RIFLE": "Infantry",
}

TYPES = dict(_BASE_TYPES)          # {值: 所在目录}；运行时被 _extend/_load 扩充
_BASE_VEHICLE_TYPES = {
"TYPE_TANK", "TYPE_ARMOURED_CAR", "TYPE_ASSAULT_GUN", "TYPE_HALFTRACK",
"TYPE_INFANTRY_FIGHTING_VEHICLE"}
_BASE_NATIONALITIES = {
"NATIONALITY_" + n for n in
                 ["GERMAN", "RUSSIAN", "AMERICAN", "BRITISH", "ITALIAN", "JAPANESE", "CHINESE",
                  "FRENCH", "POLISH", "FINNISH", "HUNGARIAN", "ROMANIAN"]}
NAT_FILE_PREFIX = {"NATIONALITY_GERMAN": "German", "NATIONALITY_RUSSIAN": "Russian",
                   "NATIONALITY_AMERICAN": "American", "NATIONALITY_BRITISH": "British",
                   "NATIONALITY_ITALIAN": "Italian", "NATIONALITY_JAPANESE": "Japanese",
                   "NATIONALITY_CHINESE": "Chinese", "NATIONALITY_FRENCH": "French",
                   "NATIONALITY_POLISH": "Polish", "NATIONALITY_FINNISH": "Finnish",
                   "NATIONALITY_HUNGARIAN": "Hungarian", "NATIONALITY_ROMANIAN": "Romanian"}
_BASE_QUALITIES = {
"QUALITY_REGULAR", "QUALITY_SUPERIOR", "QUALITY_ELITE", "QUALITY_UNTRAINED", "QUALITY_POOR"}
_BASE_JOBS = {
"JOB_DRIVER", "JOB_COMMANDER", "JOB_GUNNER", "JOB_LOADER", "JOB_SQUAD_LEADER", "JOB_RADIO",
        "JOB_SQUAD_ASSISTANT_LEADER", "JOB_SQUAD_MG_ASSISTANT", "JOB_MACHINE_GUNNER"}
_BASE_REL = {
"RELIABILITY_AVERAGE", "RELIABILITY_VERY_GOOD", "RELIABILITY_POOR", "RELIABILITY_GOOD",
       "RELIABILITY_VERY_POOR", "RELIABILITY_TERRIBLE"}
_BASE_STEER = {
"STEERING_CLUTCH_AND_BRAKE", "STEERING_CONTROLLED_DIFFERENTIAL", "STEERING_FRONT_WHEELS",
         "STEERING_TWIN_TRANSMISSION", "STEERING_HALFTRACK", "STEERING_TRIPLE_DIFFERENTIAL",
         "STEERING_DOUBLE_DIFFERENTIAL", "STEERING_DOUBLE_DIFFERENTIAL_MAYBACH"}
_BASE_MOUNTS = {
"MOUNT_FRONT", "MOUNT_MIDDLE"}
_BASE_RELOADS = {
"RELOAD_AUTOMATIC", "RELOAD_SEMI_AUTOMATIC"}
_BASE_WEAPON_CLASSES = {
"WEAPON_CANNON", "WEAPON_RIFLE", "WEAPON_LMG", "WEAPON_RPG", "WEAPON_SMG", "WEAPON_HMG",
                  "WEAPON_GRENADE", "WEAPON_MORTAR", "WEAPON_PISTOL", "WEAPON_GRENADE_LAUNCHER",
                  "WEAPON_AT_RIFLE", "WEAPON_SHOTGUN", "WEAPON_CARBINE", "WEAPON_RECOILLESS_RIFLE",
                  "WEAPON_FLAMETHROWER_PORTABLE", "WEAPON_FLAMETHROWER_TANK", "WEAPON_MLRS"}
_BASE_FLAVOURS = {
"FLAVOUR_HE", "FLAVOUR_SMOKE", "FLAVOUR_APCBC", "FLAVOUR_AP", "FLAVOUR_BALL", "FLAVOUR_HEAT",
            "FLAVOUR_MORTAR_HE", "FLAVOUR_APCR", "FLAVOUR_MORTAR_SMOKE", "FLAVOUR_APC", "FLAVOUR_CANISTER",
            "FLAVOUR_GRENADE_HE", "FLAVOUR_APDS", "FLAVOUR_GRENADE_SMOKE", "FLAVOUR_RPG", "FLAVOUR_APFSDS",
            "FLAVOUR_AT_RIFLE_AP", "FLAVOUR_HESH", "FLAVOUR_PELLETS", "FLAVOUR_APCNR", "FLAVOUR_RPG_SMOKE",
            "FLAVOUR_RPG_HEAT", "FLAVOUR_AT_RIFLE_HE", "FLAVOUR_GRENADE_HEAT", "FLAVOUR_FLAME",
            "FLAVOUR_ATGM", "FLAVOUR_HEATFS", "FLAVOUR_GRENADE_FLAME", "FLAVOUR_ROCKET_HE"}
_BASE_ERAS = {
"HEAT_ERA_COLD_WAR", "HEAT_ERA_LATE", "HEAT_ERA_COLD_WAR_EARLY", "HEAT_ERA_MODERN"}
_BASE_GUIDED = {
"GUIDED_MANUAL", "GUIDED_TOP_ATTACK", "GUIDED_FAF"}
_BASE_PERIODS = {
"WW1", "MODERN"}
_BASE_LANGS = {
"AR", "CN", "DE", "FR", "HU", "IL", "IT", "JP", "PL", "RO", "RU", "UA", "UK", "US"}
_BASE_SOUND_SHOOT = {
"shoot_cannon", "shoot_rifle", "shoot_LMG", "shoot_bazooka", "shoot_SMG", "shoot_mortar",
               "shoot_HMG", "shoot_pistol", "shoot_grenade_launcher", "shoot_at_rifle",
               "shoot_recoilless_rifle", "shoot_flamethrower", "shoot_cannon37", "shoot_rocket", "shoot_PIAT"}
_BASE_COUNTRIES = {
"GERMANY", "RUSSIA", "CHINA", "USA", "HUNGARY", "ROMANIA", "POLAND", "UNITED_KINGDOM",
             "JAPAN", "FRANCE", "UKRAINE", "GEORGIA", "ITALY", "FINLAND", "CANADA", "AUSTRIA",
             "AUSTRALIA", "SOUTH_KOREA", "NORTH_KOREA", "IRAQ", "IRAN", "NORTH_VIETNAM", "SOUTH_VIETNAM",
             "INDIA", "PAKISTAN", "EGYPT", "JORDAN", "SYRIA", "KUWAIT", "ISRAEL", "ARMENIA",
             "AZERBAIJAN", "TURKEY", "BELGIUM", "NETHERLANDS"}
# equipment_<国家>_<时代>.txt 的合法时代 token

EQUIP_ERAS = ("WW1", "WW2", "modern")

# ---- 动态枚举: 常量表以 WW2 12.2.0 为基线, 运行时从 --ref 基准学习新增值 ----
_BASE_SETS = {n: set(globals()["_BASE_" + n]) for n in
              ["NATIONALITIES", "QUALITIES", "JOBS", "REL", "STEER", "MOUNTS", "RELOADS",
               "WEAPON_CLASSES", "FLAVOURS", "ERAS", "GUIDED", "PERIODS", "SOUND_SHOOT",
               "COUNTRIES", "VEHICLE_TYPES", "LANGS"]}
for _n, _v in _BASE_SETS.items():
    globals()[_n] = set(_v)
_BASE_TYPES_EXTRA = {}


_ref_enum_cache = {}                                 # ref 目录 → 学到的枚举增量（同进程只读一遍基准）


def _extend_enums_from_ref(ref):
    """把 --ref 基准数据里出现的枚举值并入合法集合（新 MOD 的自定义值）"""
    global TYPES
    for n, v in _BASE_SETS.items():
        globals()[n] = set(v)
    TYPES = dict(_BASE_TYPES)
    if not ref:
        return
    cached = _ref_enum_cache.get(ref)
    if cached:                                       # 命中缓存: 直接回放增量，免重读基准
        TYPES.update(cached.get("TYPES", {}))
        for n, vals in cached.items():
            if n != "TYPES":
                globals()[n].update(vals)
        return
    import os as _os, re as _re
    new = {"TYPES": {}}
    wdir = _os.path.join(ref, "Data", "Weapons")
    pat_type = _re.compile(r"<type>\s*(WEAPON_[A-Z0-9_]+)\s*</type>")
    pat_val = _re.compile(r"<(flavour|era|guided|period|sound_shoot)>\s*([^<]+?)\s*</\1>")
    for f in sorted(_os.listdir(wdir)) if _os.path.isdir(wdir) else []:
        if not f.endswith(".txt"):
            continue
        t = open(_os.path.join(wdir, f), encoding=ENC, errors="replace").read()
        for m in pat_type.finditer(t):
            WEAPON_CLASSES.add(m.group(1))
            new.setdefault("WEAPON_CLASSES", set()).add(m.group(1))
        for fld, val in pat_val.findall(t):
            tgt, name = {"flavour": (FLAVOURS, "FLAVOURS"), "era": (ERAS, "ERAS"),
                         "guided": (GUIDED, "GUIDED"), "period": (PERIODS, "PERIODS"),
                         "sound_shoot": (SOUND_SHOOT, "SOUND_SHOOT")}[fld]
            tgt.add(val)
            new.setdefault(name, set()).add(val)
        for m in _re.finditer(r"<countries>([^<]+)</countries>", t):
            for c in m.group(1).split("|"):
                if c.strip():
                    COUNTRIES.add(c.strip())
                    new.setdefault("COUNTRIES", set()).add(c.strip())
    # 单位侧: type / nationality
    for sub in ("Infantry", "AT Guns", "Vehicles"):
        d = _os.path.join(ref, "Data", sub)
        if not _os.path.isdir(d):
            continue
        for f in sorted(_os.listdir(d)):
            if not f.endswith(".txt"):
                continue
            t = open(_os.path.join(d, f), encoding=ENC, errors="replace").read()
            m = _re.search(r"<description>.*?<type>\s*([A-Z0-9_]+)\s*</type>", t, _re.S)
            if m:
                TYPES.setdefault(m.group(1), sub)
                new["TYPES"][m.group(1)] = sub
            m = _re.search(r"<nationality>\s*([A-Z0-9_]+)\s*</nationality>", t)
            if m:
                NATIONALITIES.add(m.group(1))
                new.setdefault("NATIONALITIES", set()).add(m.group(1))
    _ref_enum_cache[ref] = new
ARMOUR_FACES = {"upper_front", "lower_front", "front", "upper_side", "lower_side", "side", "upper_rear",
                "lower_rear", "rear", "top", "bottom", "mantlet", "side_spaced", "rear_spaced"}

# 图片目录映射
UNIT_IMG_DIRS = {
    "AT Guns": "Images/Units/AT Guns", "HMGs": "Images/Units/HMGs", "Mortars": "Images/Units/Mortars",
    "Recoilless Rifles": "Images/Units/Recoilless Rifles", "Vehicles": "Images/Units/Vehicles",
}
PROFILE_SIZE = {(256, 128)}          # 车辆/火炮侧视剪影（固定尺寸）
PROFILE_SIZE_SMALL = {(132, 110)}    # 机枪/迫击炮/无后坐力炮侧视剪影（固定尺寸）
# 车体俯视图档位（世界坐标 1m = 16px，故档位均为 16 的倍数）
HULL_STEPS = ({32, 48, 64, 96}, {64, 96, 128, 192})   # (宽=2/3/4/6 m, 高=4/6/8/12 m)
# 美式拼写 -> 英式（原版为英式英语）
US_TO_UK = {"armored": "armoured", "armor": "armour", "caliber": "calibre",
            "defense": "defence", "color": "colour", "center": "centre",
            "meter": "metre", "tire": "tyre", "maneuver": "manoeuvre",
            "neighbor": "neighbour", "liter": "litre", "honor": "honour",
            "organization": "organisation", "recognize": "recognise"}

# ------------------------------ 工具 ------------------------------
class Report:
    """标准化/归一化输出: 路径统一 posix 分隔符、消息折叠空白、格式统一「级别 位置: 消息」"""
    def __init__(self):
        self.errors = []
        self.warns = []

    @staticmethod
    def _norm(x):
        x = str(x).replace(os.sep, "/").strip()
        return re.sub(r"\s+", " ", x)

    def err(self, f, msg):
        self.errors.append((self._norm(f), self._norm(msg)))

    def warn(self, f, msg):
        self.warns.append((self._norm(f), self._norm(msg)))

TAG_RE = re.compile(r"<\s*(/?)([A-Za-z_][A-Za-z0-9_]*)\s*>")

def strip_comments(text):
    out = []
    for ln in text.split("\n"):
        i = ln.find("//")
        if i >= 0:
            ln = ln[:i]
        out.append(ln)
    return "\n".join(out)

def parse_tags(text):
    """返回 [(tagpath, value, lineno)] 与 配对错误列表"""
    text = strip_comments(text)
    stack, items, errs = [], [], []
    line_no = 1
    pos = 0
    for m in TAG_RE.finditer(text):
        line_no += text.count("\n", pos, m.start())
        pos = m.start()
        closing, name = m.group(1), m.group(2)
        if not closing:
            stack.append(name)
            rest = text[m.end():]
            nm = re.match(r"\s*([^<]*)", rest)
            items.append(("/".join(stack), (nm.group(1).strip() if nm else ""), line_no))
        else:
            if stack and stack[-1] == name:
                stack.pop()
            else:
                errs.append((line_no, name, list(stack)))
                if name in stack:
                    while stack and stack.pop() != name:
                        pass
    for leftover in stack:
        errs.append((line_no, leftover, ["未闭合"]))
    return items, errs

def leaf(items, path):
    return [v for p, v, _ in items if p == path]

def norm(p):
    """统一为正斜杠，避免 Windows/Unix 分隔符混用导致判断失败"""
    return p.replace("\\", "/")

def png_size(path):
    try:
        with open(path, "rb") as f:
            h = f.read(32)
        if h[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        w, hh = struct.unpack(">II", h[16:24])
        return (w, hh)
    except Exception:
        return None

def is_num(v):
    try:
        float(v)
        return True
    except Exception:
        return False

def sniff_encoding(rep, rel, path):
    """自动嗅探: UTF-8 优先，回退 cp1252（原版）。返回编码或 None"""
    b = open(path, "rb").read()
    if b.startswith(b"\xef\xbb\xbf"):
        rep.err(rel, "文件带 UTF-8 BOM，请另存为无 BOM 的 UTF-8 或 Windows-1252")
        return None
    for enc in ("utf-8", "cp1252"):
        try:
            b.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    rep.err(rel, "既不是 UTF-8 也不是 Windows-1252（含非法字节）")
    return None


def check_british(rep, rel, texts):
    """原版为英式英语：正文里的美式拼写要提示"""
    import re as _re
    for t in texts:
        for us, uk in US_TO_UK.items():
            for m in _re.finditer(r"\b" + us + r"\w*", t, _re.I):
                w = m.group(0)
                if w.lower() == us or w.lower().startswith(us):
                    rep.warn(rel, f"美式拼写「{w}」，原版用英式 → {uk + w[len(us):]}")
                    break

# ------------------------------ 主校验 ------------------------------

# ---- 外部枚举表: MOD 根或脚本旁的 enums_ext.txt（用户单独提供）----
# 每行: <类别>:<值>，类别不区分大小写，支持:
#   type / vehicle_type / nationality / quality / job / reliability / steering /
#   mount / reload / weapon_class / flavour / era / guided / period / sound / country / lang
_EXT_CATS = {"type": "TYPES", "vehicle_type": "VEHICLE_TYPES", "nationality": "NATIONALITIES",
             "quality": "QUALITIES", "job": "JOBS", "reliability": "REL", "steering": "STEER",
             "mount": "MOUNTS", "reload": "RELOADS", "weapon_class": "WEAPON_CLASSES",
             "flavour": "FLAVOURS", "era": "ERAS", "guided": "GUIDED", "period": "PERIODS",
             "sound": "SOUND_SHOOT", "country": "COUNTRIES", "lang": "LANGS"}


def load_ext_enums_text(text):
    """从多行字符串加载枚举（格式同 enums_ext.txt: 类别:值），供 setting.txt Enums 段用"""
    n = 0
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ":" not in ln:
            continue
        cat, _, val = ln.partition(":")
        val = val.split("#")[0].strip()
        tgt = _EXT_CATS.get(cat.strip().lower())
        if not tgt or not val:
            continue
        if tgt == "TYPES":
            TYPES.setdefault(val, None)
        else:
            globals()[tgt].add(val)
        n += 1
    if n:
        print(f"[enums_ext] 已从 setting.txt 加载 {n} 条")
    return n


def _load_ext_enums(mod_root=None):
    """加载 enums_ext.txt（用户单独提供的列举值），并到合法集合"""
    cands = []
    if mod_root:
        cands.append(os.path.join(mod_root, "enums_ext.txt"))
        cands.append(os.path.join(mod_root, "Data", "enums_ext.txt"))
    cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "enums_ext.txt"))
    for path in cands:
        if not os.path.isfile(path):
            continue
        n = 0
        for ln in open(path, encoding="utf-8-sig", errors="replace"):
            ln = ln.strip()
            if not ln or ln.startswith("#") or ":" not in ln:
                continue
            cat, _, val = ln.partition(":")
            val = val.split("#")[0].strip()          # 剥离行内注释
            tgt = _EXT_CATS.get(cat.strip().lower())
            if not tgt or not val:
                continue
            if tgt == "TYPES":                     # TYPES 是 {值: 目录} 字典
                TYPES.setdefault(val, None)        # None = 不检查所在目录
            else:
                globals()[tgt].add(val)
            n += 1
        print(f"[enums_ext] 已加载 {path}（{n} 条）")


def run_check(root, ref=None, strict=False, ext_text=None, progress=None):
    """校验一个 Firefight MOD 根目录。返回退出码：0=无 ERROR，1=有 ERROR。
    progress: 可选回调 fn(str)，用于向 GUI 日志推送阶段进度（不写入报告）。"""
    def _p(msg):
        if progress:
            try:
                progress(msg)
            except Exception:
                pass
    rep = Report()
    data = os.path.join(root, "Data")
    if not os.path.isdir(data):
        print(f"[FATAL] 找不到 Data 目录: {data}")
        return 2
    _extend_enums_from_ref(ref)
    _load_ext_enums(root)
    if ext_text:
        load_ext_enums_text(ext_text)

    rep = Report()

    # 建索引（--ref 目录只建索引，不做逐项校验）
    _p("索引武器定义…")
    weapons = {}
    ref_wdir = os.path.join(ref, "Data", "Weapons") if ref else None
    if ref_wdir and os.path.isdir(ref_wdir):
        for f in sorted(os.listdir(ref_wdir)):
            if f.endswith(".txt"):
                try:
                    txt = open(os.path.join(ref_wdir, f), encoding=ENC, errors="replace").read()
                except Exception:
                    continue
                it, _ = parse_tags(txt)
                wc = leaf(it, "weapon/type")
                weapons[f[:-4]] = {"flavours": set(leaf(it, "weapon/ammo/type/flavour")),
                                   "class": wc[0] if wc else None, "file": f, "from_ref": True}

    wdir = os.path.join(data, "Weapons")
    if os.path.isdir(wdir):
        for f in sorted(os.listdir(wdir)):
            if f.endswith(".txt"):
                wid = f[:-4]
                wenc = sniff_encoding(rep, f"Weapons/{f}", os.path.join(wdir, f))
                if wenc is None:
                    continue
                txt = open(os.path.join(wdir, f), encoding=wenc, errors="replace").read()
                items, errs = parse_tags(txt)
                flavours = set(leaf(items, "weapon/ammo/type/flavour"))
                wclass = leaf(items, "weapon/type")
                weapons[wid] = {"flavours": flavours,
                                "class": wclass[0] if wclass else None,
                                "file": f, "from_ref": False}
                for ln, name, st in errs:
                    rep.err(f"Weapons/{f}", f"标签配对错误 <{name}> (行{ln}, 栈={st[-3:]})")
                if not wclass:
                    rep.err(f"Weapons/{f}", "缺少 <type>")
                # 枚举声明即标准: 学习新值, 不做白名单拦截（MOD 时代会引入新枚举）
                if wclass:
                    WEAPON_CLASSES.add(wclass[0])
                for c in leaf(items, "weapon/usage/countries"):
                    for x in c.split("|"):
                        if x.strip():
                            COUNTRIES.add(x.strip())
                PERIODS.update(leaf(items, "weapon/usage/period"))
                for s in leaf(items, "weapon/shoot/sound_shoot"):
                    SOUND_SHOOT.add(s)
                    if not (os.path.exists(os.path.join(root, "Sounds", s + ".ogg"))
                            or (ref and os.path.exists(os.path.join(ref, "Sounds", s + ".ogg")))):
                        rep.warn(f"Weapons/{f}", f"缺少音频 Sounds/{s}.ogg")
                for fl in leaf(items, "weapon/ammo/type/flavour"):
                    FLAVOURS.add(fl)
                for e in leaf(items, "weapon/ammo/type/era"):
                    ERAS.add(e)
                for g in leaf(items, "weapon/ammo/type/guided"):
                    GUIDED.add(g)
                for v in leaf(items, "weapon/dimensions/calibre"):
                    if not is_num(v):
                        rep.err(f"Weapons/{f}", f"calibre 非数值: {v}")
                # 文件名与 type 前缀一致性
                if wclass and not wid.startswith(wclass[0]):
                    rep.warn(f"Weapons/{f}", f"文件名前缀与 <type>={wclass[0]} 不一致")
                # 文件名只允许字母/数字/下划线（引擎按 ID 查找，空格等可能导致引用失败）
                if not re.fullmatch(r"[A-Za-z0-9_]+", wid):
                    rep.warn(f"Weapons/{f}",
                             f"文件名含非法字符（只允许字母/数字/下划线）: {wid!r}")
                if not leaf(items, "weapon/name"):
                    rep.err(f"Weapons/{f}", "缺少 <name>")
                if not leaf(items, "weapon/usage/countries"):
                    rep.warn(f"Weapons/{f}", "缺少 <usage><countries>（可由 mod.txt 阵营决定，忽略）")

    # 图片索引
    img_index = {}
    for base in ["Images/Units", "Images/Uniforms"]:
        p = os.path.join(root, base)
        if not os.path.isdir(p):
            continue
        for dp, _, fs in os.walk(p):
            for f in fs:
                img_index.setdefault(f, os.path.join(dp, f))
    if ref:
        for dp, _, fs in os.walk(os.path.join(ref, "Images/Units")):
            for f in fs:
                img_index.setdefault(f, os.path.join(dp, f))

    uniform_dirs = set()
    up = os.path.join(root, "Images/Uniforms")
    if os.path.isdir(up):
        for d in os.listdir(up):
            if os.path.isdir(os.path.join(up, d)) and d.startswith("uniform_"):
                uniform_dirs.add(d[8:])
    if ref:
        rup = os.path.join(ref, "Images/Uniforms")
        if os.path.isdir(rup):
            for d in os.listdir(rup):
                if os.path.isdir(os.path.join(rup, d)) and d.startswith("uniform_"):
                    uniform_dirs.add(d[8:])

    # 单位文件
    _p("索引单位文件…")
    squad_files = []
    for sub in ["Infantry", "AT Guns", "Vehicles"]:
        d = os.path.join(data, sub)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".txt"):
                    squad_files.append((sub, f))

    # 自我学习: MOD 自身声明的 type/nationality/quality 也是合法值（新阵营等）
    for sub, f in squad_files:
        try:
            t = open(os.path.join(data, sub, f), encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        m = re.search(r"<description>.*?<type>\s*([A-Z0-9_]+)\s*</type>", t, re.S)
        if m:
            TYPES.setdefault(m.group(1), sub)
        for m in re.finditer(r"<(nationality|quality)>\s*([A-Z0-9_]+)\s*</\1>", t):
            {"nationality": NATIONALITIES, "quality": QUALITIES}[m.group(1)].add(m.group(2))

    for si, (sub, fname) in enumerate(squad_files):
        if si % 50 == 0:
            _p(f"校验单位 {si + 1}/{len(squad_files)}: {sub}/{fname}")
        path = os.path.join(data, sub, fname)
        rel = f"{sub}/{fname}"
        enc = sniff_encoding(rep, rel, path)
        if enc is None:
            continue
        txt = open(path, encoding=enc, errors="replace").read()
        items, errs = parse_tags(txt)
        for ln, name, st in errs:
            rep.err(rel, f"标签配对错误 <{name}> (行{ln}, 栈={st[-3:]})")

        paths = [p for p, _, _ in items]
        if not paths or paths[0] != "squad":
            rep.err(rel, "根元素必须是 <squad>")
            continue

        def L(p):
            return leaf(items, p)

        # ---- description ----
        t = L("squad/description/type")
        if not t:
            rep.err(rel, "缺少 <description><type>")
            continue
        utype = t[0]
        if utype not in TYPES:
            rep.err(rel, f"非法 type: {utype}")
            continue
        expect_dir = TYPES[utype]
        if expect_dir and expect_dir != sub:
            rep.warn(rel, f"type={utype} 通常放在 Data/{expect_dir}/，当前在 {sub}/")

        nat = L("squad/description/nationality")
        if not nat:
            rep.err(rel, "缺少 <nationality>")
        elif nat[0] not in NATIONALITIES:
            rep.err(rel, f"非法 nationality: {nat[0]}")
        else:
            pref = NAT_FILE_PREFIX.get(nat[0], "")
            if pref and not fname.startswith(pref + "-"):
                rep.warn(rel, f"文件名前缀应为 '{pref}-'")

        qual = L("squad/description/quality")
        if utype in VEHICLE_TYPES:
            if qual:
                rep.err(rel, "车辆文件不允许写 <quality>（原版 597/597 都没有）")
        else:
            if not qual:
                rep.err(rel, "缺少 <quality>")
            elif qual[0] not in QUALITIES:
                rep.err(rel, f"非法 quality: {qual[0]}")

        for lg in L("squad/description/language"):
            if lg not in LANGS:
                rep.err(rel, f"非法 language: {lg}")

        for need in ["long_name", "short_name", "comment"]:
            if not L("squad/description/" + need):
                rep.err(rel, f"缺少 <description><{need}>")
        if not L("squad/description/uniform"):
            rep.warn(rel, "缺少 <uniform>（可由 mod.txt <default_images> 按国籍提供，可忽略）")

        for u in L("squad/description/uniform"):
            if uniform_dirs and u not in uniform_dirs:
                rep.err(rel, f"找不到制服目录 Images/Uniforms/uniform_{u}/")
        for ur in L("squad/description/uniform_ranks"):
            if not os.path.exists(os.path.join(root, "Images/Uniforms", ur)):
                rep.warn(rel, f"找不到军衔图 {ur}")

        # ---- availability ----
        months = L("squad/availability/data/month")
        years = L("squad/availability/data/year")
        nums = L("squad/availability/data/number")
        if not months:
            rep.warn(rel, "缺少 <availability><data>（占位/特殊单位可忽略）")
        else:
            if not (len(months) == len(years) == len(nums)):
                rep.err(rel, "availability 的 month/year/number 数量不一致")
            for i, m in enumerate(months):
                if not m.isdigit() or not (1 <= int(m) <= 12):
                    rep.err(rel, f"month 越界: {m}")
            for y in years:
                if not y.isdigit():
                    rep.err(rel, f"year 非数字: {y}")
            for n in nums:
                if not n.lstrip("-").isdigit():
                    rep.err(rel, f"number 非整数: {n}")
            if len(years) == len(months) and len(months) > 1:
                key = [(int(y), int(m)) for y, m in zip(years, months)]
                if key != sorted(key):
                    rep.err(rel, "availability 未按时间升序")

        # ---- 图片引用 ----
        def check_img(tag, subdir_key, rule=None, size_label=""):
            """rule = ('exact', {尺寸集合}) 必须精确；('mult16', 档位dict) 必须是 16 的倍数"""
            for v in L("squad/" + tag):
                full = img_index.get(v)
                if not full:
                    rep.err(rel, f"<{tag}> 找不到图片 {v}")
                    continue
                if subdir_key:
                    want = UNIT_IMG_DIRS[subdir_key]
                    if want not in norm(full):
                        rep.warn(rel, f"<{tag}> 图片 {v} 不在 {want} 下")
                if not rule:
                    continue
                s = png_size(full)
                if not s:
                    continue
                if rule[0] == "exact":
                    if s not in rule[1]:
                        want_s = "/".join(f"{a}x{b}" for a, b in sorted(rule[1]))
                        rep.warn(rel, f"<{tag}> {v} 尺寸 {s[0]}x{s[1]}，{size_label}建议固定为 {want_s}")
                elif rule[0] == "mult16":
                    if s[0] % 16 or s[1] % 16:
                        rep.warn(rel, f"<{tag}> {v} 尺寸 {s[0]}x{s[1]} 不是 16 的倍数"
                                      f"（世界坐标 1m = 16px，绘制档位应为 16 的整数倍）")
                    steps = rule[1]
                    if steps and (s[0] not in steps[0] or s[1] not in steps[1]):
                        rep.warn(rel, f"<{tag}> {v} 尺寸 {s[0]}x{s[1]} 不在常用档位"
                                      f" 宽{sorted(steps[0])} / 高{sorted(steps[1])} 内")

        if sub == "Vehicles":
            check_img("vehicle/attributes/image_profile", "Vehicles",
                      ("exact", PROFILE_SIZE), "车辆侧视剪影")
            check_img("vehicle/hull/image_view", "Vehicles")
            check_img("vehicle/turret/image_view", "Vehicles")
            check_img("vehicle/fixed_weapon/image_view", "Vehicles")
        else:
            if utype == "TYPE_MORTAR":
                check_img("squad/mortar/image_view_base", "Mortars")
                check_img("squad/mortar/image_profile", "Mortars",
                          ("exact", PROFILE_SIZE_SMALL), "迫击炮侧视剪影")
            elif utype == "TYPE_HMG":
                check_img("squad/hmg/image_view_base", "HMGs")
                check_img("squad/hmg/image_view_gun", "HMGs")
                check_img("squad/hmg/image_profile", "HMGs",
                          ("exact", PROFILE_SIZE_SMALL), "机枪侧视剪影")
            elif utype == "TYPE_RECOILLESS_RIFLE":
                check_img("squad/recoilless_rifle/image_view_base", "Recoilless Rifles")
                check_img("squad/recoilless_rifle/image_view_gun", "Recoilless Rifles")
                check_img("squad/recoilless_rifle/image_profile", "Recoilless Rifles",
                          ("exact", PROFILE_SIZE_SMALL), "无后坐力炮侧视剪影")
            elif sub == "AT Guns":
                check_img("squad/atgun/image_view_base", "AT Guns")
                check_img("squad/atgun/image_view_gun", "AT Guns")
                check_img("squad/atgun/image_profile", "AT Guns",
                          ("exact", PROFILE_SIZE), "火炮侧视剪影")

        # 迫击炮不得有 gun 图
        if L("squad/mortar/image_view_gun"):
            rep.err(rel, "<mortar> 不应有 image_view_gun（迫击炮无 gun 图）")

        # ---- 武器引用 ----
        refs = []
        for p, v, _ in items:
            if p.endswith("/weapon/type") and v.startswith("WEAPON_"):
                refs.append((p, v))
            if p.endswith("/ammo/for"):
                refs.append((p, v))
        for p, v in refs:
            if v not in weapons:
                rep.err(rel, f"{p} 引用了未定义的武器 {v}")
        # 单位给武器装弹，但武器文件里没有任何弹药定义 → 游戏无法装填
        for p, v in refs:
            if p.endswith("/ammo/for") and v in weapons and not weapons[v]["flavours"]:
                rep.err(rel, f"武器 {v} 的武器文件未定义弹药（无 <ammo> 弹种），无法装填")
        # 弹种校验
        for i, (p, v, _) in enumerate(items):
            if p.endswith("/ammo/flavour"):
                if v not in FLAVOURS:
                    rep.err(rel, f"非法弹种 {v}")
                # 找同组的 for
                j = i - 1
                while j >= 0:
                    if items[j][0].endswith("/ammo/for"):
                        w = items[j][1]
                        if w in weapons and weapons[w]["flavours"] and v not in weapons[w]["flavours"]:
                            rep.warn(rel, f"{w} 未声明弹种 {v}")
                        break
                    if not items[j][0].startswith("/".join(p.split("/")[:-1])):
                        break
                    j -= 1

        # ---- job ----
        for j in L("squad/man/job") + L("squad/vehicle/hull/man/job") + \
                 L("squad/vehicle/turret/man/job") + L("squad/vehicle/fixed_weapon/man/job"):
            if j not in JOBS:
                rep.err(rel, f"非法 job: {j}")

        # ---- 数值字段 ----
        NUMERIC = {"rounds", "weight", "width", "length", "height", "diameter", "horsepower",
                   "rpm_idle", "rpm_limit", "forwards", "reverse", "offsetX", "offsetY", "offsetZ",
                   "offset_angle", "angle", "vertical_angle", "rotate_time", "rotate_left",
                   "rotate_right", "elevation", "speed", "ammo", "reload", "mass", "trail_length",
                   "capacity", "rof", "range", "calibre", "barrel_length", "explode_in"}
        for p, v, ln in items:
            seg = p.split("/")[-1]
            if seg in NUMERIC and v and not is_num(v):
                rep.err(rel, f"<{seg}> 非数值（行{ln}）: {v}")

        # ---- 车辆专项 ----
        if sub == "Vehicles":
            for r in L("squad/vehicle/drive/engine/reliability"):
                if r not in REL:
                    rep.err(rel, f"非法 reliability: {r}")
            for s in L("squad/vehicle/drive/steering"):
                if s not in STEER:
                    rep.err(rel, f"非法 steering: {s}")
            for m in L("squad/vehicle/drive/engine/mount"):
                if m not in MOUNTS:
                    rep.err(rel, f"非法 engine mount: {m}")
            # 装甲语法
            for p, v, _ in items:
                seg = p.split("/")[-1]
                if "/armour/" in p and seg in ARMOUR_FACES:
                    if "@" in v:
                        th, _, ang = v.partition("@")
                        if not is_num(th) or not is_num(ang):
                            rep.err(rel, f"装甲值语法错误: <{seg}>{v}")
                        elif not (-90 <= float(ang) <= 90):
                            rep.warn(rel, f"倾角越界: <{seg}>{v}（应为 -90..90）")
                    elif not is_num(v):
                        rep.err(rel, f"装甲厚度非数值: <{seg}>{v}")
                elif "/armour/" in p:
                    rep.warn(rel, f"未知装甲面 <{seg}>")
            # 炮塔必填
            if any(p == "squad/vehicle/turret" for p, _, _ in items):
                if not L("squad/vehicle/turret/armour/mantlet"):
                    rep.err(rel, "炮塔缺少 <armour><mantlet>")
                if not L("squad/vehicle/turret/rotate_time"):
                    rep.err(rel, "炮塔缺少 <rotate_time>")
                if not L("squad/vehicle/turret/height"):
                    rep.err(rel, "炮塔缺少 <height>")
                if not L("squad/vehicle/turret/diameter"):
                    rep.err(rel, "炮塔缺少 <diameter>")
            # superstructure 不应有 image_view
            if L("squad/vehicle/superstructure/image_view"):
                rep.err(rel, "<superstructure> 不支持 image_view")
            # 数值必填
            for need in ["vehicle/attributes/weight", "vehicle/hull/width", "vehicle/hull/length",
                         "vehicle/hull/height", "vehicle/drive/engine/horsepower",
                         "vehicle/drive/gears/forwards", "vehicle/drive/gears/reverse"]:
                if not L("squad/" + need):
                    rep.err(rel, f"缺少 <{need.split('/')[-1]}>（路径 {need}）")
            # fixed_weapon 需要 offsetZ
            n_fw = sum(1 for p, _, _ in items if p == "squad/vehicle/fixed_weapon")
            if n_fw and len(L("squad/vehicle/fixed_weapon/offsetZ")) != n_fw:
                rep.err(rel, "有 <fixed_weapon> 缺少 offsetZ")

        # ---- 火炮专项 ----
        if sub == "AT Guns":
            for need in ["atgun/mass", "atgun/trail_length", "atgun/weapon/type"]:
                if not L("squad/" + need):
                    rep.err(rel, f"缺少 <{need.split('/')[-1]}>")
            for m in L("squad/atgun/mass"):
                if not is_num(m):
                    rep.err(rel, f"mass 非数值: {m}")
            for mv in L("squad/atgun/moveable"):
                if mv not in ("yes", "no"):
                    rep.err(rel, f"moveable 取值应为 yes/no: {mv}")

    # ---- 装备表（由 mod.txt <equipment> 引用的 Data/ 下 txt，可任意命名）----
    _p("校验装备表…")
    listed = set()
    EQUIP_RE = re.compile(r"^equipment_([a-z][a-z0-9_]*)(_(" + "|".join(EQUIP_ERAS) + r"))?\.txt$")
    equip_refs = []
    mod_txt = os.path.join(root, "mod.txt")
    if os.path.isfile(mod_txt):
        mt = open(mod_txt, encoding="utf-8", errors="replace").read()
        for blk in re.finditer(r"<nationality>(.*?)</nationality>", mt, re.S):
            equip_refs += re.findall(r"<equipment>([^<]+)</equipment>", blk.group(1))
    equip_refs = sorted({e.strip().replace("\\", "/") for e in equip_refs if e.strip()})
    for e in equip_refs:                                 # mod.txt 引用的清单 = 权威装备表
        ep = os.path.join(data, e.replace("/", os.sep))
        if not os.path.isfile(ep):
            rep.err("mod.txt", f"引用的装备表不存在: Data/{e}")
            continue
        fname = os.path.basename(e)
        if fname.startswith("equipment_") and fname.endswith(".txt") and not EQUIP_RE.match(fname):
            rep.warn(f"Data/{e}",
                     "装备表命名不标准（建议 equipment_<国家>[_<时代>].txt，时代=" + "/".join(EQUIP_ERAS) + "）")
        for ln in open(ep, encoding="utf-8", errors="replace").read().split("\n"):
            ln = ln.split("//")[0].strip()
            if ln:
                listed.add(ln)
                if ln not in {x[:-4] for _, x in squad_files} and not ref:
                    rep.warn(f"Data/{e}", f"清单条目无对应单位文件: {ln}")
    _referenced_lists = {f"Data/{e}" for e in equip_refs}
    for f in sorted(os.listdir(data)):                   # 无人引用的 equipment_*.txt 提示
        if f.endswith(".txt") and f.startswith("equipment_") and f"Data/{f}" not in _referenced_lists:
            rep.warn(f"Data/{f}", "装备表未被 mod.txt 引用，不会生效")
    if listed:
        for sub, fname in squad_files:
            sid = fname[:-4]
            if sid not in listed:
                rep.warn(f"{sub}/{fname}", "未被任何装备表收录，不会出现在选单")

    # ---- 资源格式 ----
    _p("校验资源格式（PNG/OGG 文件头）…")
    check_all_formats(root, rep)

    # ---- 输出 ----
    print("=" * 78)
    print(f"Firefight MOD 校验: {root}")
    print(f"单位 {len(squad_files)} 个 / 武器 {len(weapons)} 个")
    print("=" * 78)
    if rep.errors:
        print(f"\n[ERROR] {len(rep.errors)}")
        for f, m in rep.errors:
            print(f"  ✗ {f}: {m}")
    else:
        print("\n[ERROR] 0  ✓")
    if rep.warns:
        print(f"\n[WARN] {len(rep.warns)}")
        for f, m in rep.warns:                           # 全量输出，不省略
            print(f"  ! {f}: {m}")
    if strict and rep.warns:
        print("\n(strict 模式：WARN 视为失败)")
        return 1
    return 1 if rep.errors else 0




def check_all_formats(root, rep):
    """校验 MOD 内全部资源文件格式: PNG(\x89PNG) / OGG(OggS)，文件头不符即 ERROR"""
    png_magic = b"\x89PNG\r\n\x1a\n"
    for sub, ext, magic, label in (("Images", ".png", png_magic, "PNG"),
                                   ("Sounds", ".ogg", b"OggS", "OGG")):
        d = os.path.join(root, "Data", sub)
        if not os.path.isdir(d):
            continue
        bad = 0
        for dp, _, fs in os.walk(d):
            for f in fs:
                if not f.lower().endswith(ext):
                    continue
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, root)
                try:
                    head = open(p, "rb").read(8)
                except Exception:
                    continue
                if not head.startswith(magic):
                    rep.err(rel, f"文件不是有效 {label}（文件头不符）")
                    bad += 1
        if bad:
            print(f"[格式] {sub} 内 {bad} 个文件头异常")


def main():
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    ref = None
    if "--ref" in argv:
        i = argv.index("--ref")
        if i + 1 < len(argv):
            ref = argv[i + 1]
    if not args:
        print(__doc__)
        return 2
    return run_check(args[0], ref=ref, strict=strict)


if __name__ == "__main__":
    sys.exit(main())
