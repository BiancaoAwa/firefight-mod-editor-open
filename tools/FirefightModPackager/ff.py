#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firefight MOD 工具集 ff.py —— 数据文件的一条龙生成/查询/校验

子命令:
  check    校验 MOD 目录                python ff.py check <MOD目录> [--ref <原版>] [--strict]
  clone    克隆原版单位为 MOD 新单位     python ff.py clone <源ID> <新ID> [选项]
  weapon   生成武器文件骨架              python ff.py weapon <WEAPON_ID> --name "..." [选项]
  assets   生成单位的美工任务单          python ff.py assets <单位ID>
  info     查看单位/武器摘要             python ff.py info <ID>
  list     检索原版单位/武器             python ff.py list [--type tank] [--nation german] [--query pak] [--modern]

clone 选项:
  --out <MOD目录>     写入目标 MOD（默认 ./）
  --nation american   新国籍（同时改文件前缀、NATIONALITY_*、制式）
  --uniform <名字>    制服（如 american_vehicle_crew）
  --era WW2           登记进 equipment_<国家>_<era>.txt（默认 WW2，可选 WW1/WW2/modern）
  --avail "1991-01:200,1995-06:400"   重写 <availability>（YYYY-MM:数量）
  --comment "..."     重写 <comment>
  --long "..." / --short "..."        重写显示名
  --no-register       不自动登记 equipment

原版目录自动定位顺序: 环境变量 FIREFIGHT_REF → 内置候选路径 → 工作区 ref/*/ → MOD 目录自身。
所有文件读写一律 Windows-1252。
"""
import os, re, sys, struct, glob, argparse, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import validate as V
except ImportError:
    sys.stderr.write("[FATAL] 找不到 validate.py —— 它必须与 ff.py 放在同一目录\n"
                     "       请从项目资产「工具」文件夹把 ff.py 和 validate.py 一起下载\n")
    sys.exit(2)

ENC = "cp1252"
NAT_SMALL = {"German": "german", "Russian": "russian", "American": "american", "British": "british",
             "Italian": "italian", "Japanese": "japanese", "Chinese": "chinese", "French": "french",
             "Polish": "polish", "Finnish": "finnish", "Hungarian": "hungarian", "Romanian": "romanian"}
SUB_BY_TYPE = {"TYPE_TANK": "Vehicles", "TYPE_ARMOURED_CAR": "Vehicles", "TYPE_ASSAULT_GUN": "Vehicles",
               "TYPE_HALFTRACK": "Vehicles", "TYPE_INFANTRY_FIGHTING_VEHICLE": "Vehicles",
               "TYPE_INFANTRY_SECTION": "Infantry", "TYPE_MORTAR": "Infantry", "TYPE_HMG": "Infantry",
               "TYPE_BAZOOKA": "Infantry", "TYPE_AT_RIFLE": "Infantry",
               "TYPE_FLAMETHROWER": "Infantry", "TYPE_RECOILLESS_RIFLE": "Infantry",
               "TYPE_ATGUN": "AT Guns", "TYPE_HOWITZER": "AT Guns"}
HULL_STEPS_W = [32, 48, 64, 96]
HULL_STEPS_H = [64, 96, 128, 192]


# ---------------------------------------------------------------- 原版定位
def find_ref():
    """原版数据目录自动定位：环境变量 → 已知工作区路径 → cwd/脚本旁的 ref/*"""
    v = os.environ.get("FIREFIGHT_REF")
    if v and os.path.isdir(os.path.join(v, "Data")):
        return v
    cands = [r"D:\WorkBuddy\2026-09-25-15-03-25\ref\原始游戏文件参考（12.2.0版本）"]
    cands += glob.glob(os.path.join(os.getcwd(), "ref", "*"))
    cands += glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref", "*"))
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "Data", "Infantry")):
            return os.path.normpath(c)
    return None


class Store:
    """原版 + MOD 数据索引"""
    def __init__(self, ref, mod=None):
        self.roots = []
        if ref:
            self.roots.append(ref)
        if mod and os.path.normpath(mod) != os.path.normpath(ref or ""):
            self.roots.append(mod)
        self.squads = {}    # id -> (subdir, fullpath)
        self.weapons = {}   # id -> fullpath
        self.images = {}    # filename -> fullpath
        for r in self.roots:
            for sub in ["Infantry", "AT Guns", "Vehicles"]:
                d = os.path.join(r, "Data", sub)
                if os.path.isdir(d):
                    for f in sorted(os.listdir(d)):
                        if f.endswith(".txt"):
                            self.squads.setdefault(f[:-4], (sub, os.path.join(d, f)))
            wd = os.path.join(r, "Data", "Weapons")
            if os.path.isdir(wd):
                for f in sorted(os.listdir(wd)):
                    if f.endswith(".txt"):
                        self.weapons.setdefault(f[:-4], os.path.join(wd, f))
            up = os.path.join(r, "Images", "Units")
            if os.path.isdir(up):
                for dp, _, fs in os.walk(up):
                    for f in fs:
                        self.images.setdefault(f, os.path.join(dp, f))

    @staticmethod
    def read(path):
        return open(path, encoding=ENC, errors="replace").read()


def png_size(path):
    try:
        with open(path, "rb") as f:
            h = f.read(32)
        if h[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", h[16:24])
    except Exception:
        return None


def up_step(v, steps):
    for s in steps:
        if s >= v - 0.5:
            return s
    return steps[-1]


# ---------------------------------------------------------------- assets
def assets_report(store, uid, out=sys.stdout):
    if uid not in store.squads:
        print(f"找不到单位 {uid}"); return 1
    sub, path = store.squads[uid]
    t = store.read(path)
    items, _ = V.parse_tags(t)
    L = lambda p: V.leaf(items, p)
    utype = L("squad/description/type")[0]
    print(f"单位 {uid}   [{utype}]   文件: {sub}/{uid}.txt")
    print("=" * 70)

    def req(tag, subdir, rule):
        for name in L("squad/" + tag):
            sz = ""
            if rule == "exact_256":
                sz = "256×128（固定）"
            elif rule == "exact_132":
                sz = "132×110（固定）"
            elif rule == "hull":
                w = L("squad/vehicle/hull/width")
                l = L("squad/vehicle/hull/length")
                if w and l:
                    pw = up_step(int(w[0]) / 100 * 16, HULL_STEPS_W)
                    ph = up_step(int(l[0]) / 100 * 16, HULL_STEPS_H)
                    sz = f"{pw}×{ph}（{int(w[0])}×{int(l[0])} cm 按单位 1m=16px 取档）"
                else:
                    sz = "16 的倍数"
            else:
                sz = "16 的倍数（单位 1m=16px）"
            exists = "✓ 已有" if name in store.images else "✗ 需新做"
            print(f"  {tag:28s} {subdir:38s} {name:48s} {sz}   {exists}")

    if sub == "Vehicles":
        req("vehicle/attributes/image_profile", "Images/Units/Vehicles/Profiles/", "exact_256")
        req("vehicle/hull/image_view", "Images/Units/Vehicles/Hulls/", "hull")
        req("vehicle/turret/image_view", "Images/Units/Vehicles/Turrets/", "mult16")
        req("vehicle/fixed_weapon/image_view", "Images/Units/Vehicles/Turrets/", "mult16")
    elif utype == "TYPE_MORTAR":
        req("squad/mortar/image_view_base", "Images/Units/Mortars/", "mult16")
        req("squad/mortar/image_profile", "Images/Units/Mortars/", "exact_132")
    elif utype == "TYPE_HMG":
        req("squad/hmg/image_view_base", "Images/Units/HMGs/", "mult16")
        req("squad/hmg/image_view_gun", "Images/Units/HMGs/", "mult16")
        req("squad/hmg/image_profile", "Images/Units/HMGs/", "exact_132")
    elif utype == "TYPE_RECOILLESS_RIFLE":
        req("squad/recoilless_rifle/image_view_base", "Images/Units/Recoilless Rifles/", "mult16")
        req("squad/recoilless_rifle/image_view_gun", "Images/Units/Recoilless Rifles/", "mult16")
        req("squad/recoilless_rifle/image_profile", "Images/Units/Recoilless Rifles/", "exact_132")
    elif sub == "AT Guns":
        req("squad/atgun/image_view_base", "Images/Units/AT Guns/", "mult16")
        req("squad/atgun/image_view_gun", "Images/Units/AT Guns/", "mult16")
        req("squad/atgun/image_profile", "Images/Units/AT Guns/", "exact_256")

    for u in L("squad/description/uniform"):
        print(f"\n制服 {u}：需 Images/Uniforms/uniform_game_{u}.png 384×768、"
              f"uniform_profile_{u}.png 1024×220，"
              f"及 uniform_{u}/ 下 384×320 的持械变体（WEAPON_NONE/RIFLE/SMG/LMG/RPG/PISTOL…）")
    for ur in L("squad/description/uniform_ranks"):
        print(f"军衔图：Images/Uniforms/{ur}（700×100）")
    return 0


# ---------------------------------------------------------------- clone
def rewrite_field(text, field, value):
    return re.sub(r"<%s>[^<]*</%s>" % (field, field), "<%s>%s</%s>" % (field, value, field),
                  text, count=1)


def cmd_clone(a):
    ref = find_ref()
    store = Store(ref, a.out)
    if a.src not in store.squads:
        print(f"找不到源单位 {a.src}（原版目录: {ref}）"); return 1
    sub, spath = store.squads[a.src]
    text = store.read(spath)
    out_root = a.out or "."
    out_dir = os.path.join(out_root, "Data", sub)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, a.dst + ".txt")

    new_nation = None
    if a.nation:
        cap = a.nation.capitalize()
        nat_tok = "NATIONALITY_" + a.nation.upper()
        if nat_tok not in V.NATIONALITIES:
            print(f"警告: {nat_tok} 不是原版 12 个枚举之一，游戏可能不认识（现代阵营需自测）")
        new_nation = cap
        text = rewrite_field(text, "nationality", nat_tok)
        # 制式默认跟随国籍
        if not a.uniform:
            text = rewrite_field(text, "uniform", a.nation)
    if a.uniform:
        text = rewrite_field(text, "uniform", a.uniform)
    if a.long:
        text = rewrite_field(text, "long_name", a.long)
    if a.short:
        text = rewrite_field(text, "short_name", a.short)
    if a.comment:
        text = rewrite_field(text, "comment", a.comment)
    if a.avail:
        rows = []
        for part in re.split(r"[,;，；]", a.avail):
            m = re.match(r"\s*(\d{3,4})-(\d{1,2})\s*:\s*(\d+)\s*$", part)
            if not m:
                print(f"--avail 段格式错误: {part}（应为 YYYY-MM:数量）"); return 1
            rows.append("\t\t<data><month>%d</month><year>%d</year><number>%d</number></data>"
                        % (int(m.group(2)), int(m.group(1)), int(m.group(3))))
        text = re.sub(r"<availability>.*?</availability>",
                      "<availability>\n" + "\n".join(rows) + "\n\t</availability>",
                      text, count=1, flags=re.S)

    with open(out_path, "wb") as f:
        f.write(text.replace("\r\n", "\n").encode(ENC))
    print(f"已生成 {out_path}")
    print("⚠️ 装甲/武器/弹药/乘员等数值仍是源单位的占位，请按史实修改；"
          "新武器可先 ff.py weapon 生成骨架，再回填到本文件的 <weapon><type> 引用。")

    # 登记 equipment_<国家>_<时代>.txt
    if not a.no_register:
        era = a.era or "WW2"
        nat_small = a.nation or (new_nation and NAT_SMALL.get(new_nation)) or \
                    re.match(r"([A-Za-z]+)-", a.dst).group(1).lower()
        eq_name = f"equipment_{nat_small}_{era}.txt"
        eq_path = os.path.join(out_root, "Data", eq_name)
        os.makedirs(os.path.dirname(eq_path), exist_ok=True)
        lines = []
        if os.path.exists(eq_path):
            lines = open(eq_path, encoding=ENC, errors="replace").read().rstrip("\n").split("\n")
        if a.dst not in [x.split("//")[0].strip() for x in lines]:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(a.dst)
            with open(eq_path, "wb") as f:
                f.write(("\n".join(lines) + "\n").encode(ENC))
            print(f"已登记进 {eq_name}")

    print("\n—— 美工任务单（图片沿用源单位引用名，按需重画/改名）——")
    store2 = Store(ref, out_root)
    assets_report(store2, a.dst)
    return 0


# ---------------------------------------------------------------- weapon
def cmd_weapon(a):
    wid = a.weapon_id
    cls = a.cls
    if not wid.startswith("WEAPON_" + cls):
        print(f"武器 ID 应以 WEAPON_{cls} 开头"); return 1
    ammo = {
        "CANNON": ('\t\t<type><flavour>FLAVOUR_HE</flavour><speed>800</speed><mass>20</mass><HE>3</HE><name>HE</name></type>\n'
                   '\t\t<type><flavour>FLAVOUR_HEAT</flavour><speed>900</speed><mass>18</mass><era>HEAT_ERA_COLD_WAR</era><HE>2</HE><name>HEAT</name></type>\n'
                   '\t\t<type><flavour>FLAVOUR_APFSDS</flavour><speed>1650</speed><mass>7</mass><name>APFSDS</name></type>\n'
                   '\t\t<type><flavour>FLAVOUR_SMOKE</flavour><speed>800</speed><mass>20</mass><name>Smoke</name></type>\n'),
    }.get(cls,
          '\t\t<type><flavour>FLAVOUR_BALL</flavour><speed>900</speed><mass>0.01</mass><name>Ball</name></type>\n')
    mag = ""
    if cls in ("RIFLE", "SMG", "LMG", "HMG", "CARBINE", "PISTOL", "SHOTGUN", "AT_RIFLE"):
        mag = ('\t<magazine>\n\t\t<capacity>30</capacity>\n\t\t<sound_reload>reload_magazine</sound_reload>\n\t</magazine>\n\n')
    snd = {"CANNON": "shoot_cannon", "RIFLE": "shoot_rifle", "LMG": "shoot_LMG", "HMG": "shoot_HMG",
           "SMG": "shoot_SMG", "MORTAR": "shoot_mortar", "PISTOL": "shoot_pistol",
           "RPG": "shoot_bazooka", "AT_RIFLE": "shoot_at_rifle",
           "GRENADE_LAUNCHER": "shoot_grenade_launcher"}.get(cls, "shoot_rifle")
    period = "\t\t<period>MODERN</period>\n" if a.modern else ""
    countries = "|".join(a.country) if a.country else "USA"
    rof = {"CANNON": "8", "RIFLE": "60", "LMG": "750", "HMG": "600", "SMG": "700",
           "PISTOL": "90", "MORTAR": "12", "RPG": "6"}.get(cls, "100")
    cal = a.calibre or "7.62"
    tpl = f"""<weapon>

	<name>{a.name or wid}</name>
	<type>WEAPON_{cls}</type>

	<dimensions>
		<calibre>{cal}</calibre>
		<barrel_length>{a.barrel or '50'}</barrel_length>
	</dimensions>

	<shoot>
		<sound_shoot>{snd}</sound_shoot>
		<rof>{rof}</rof>
	</shoot>

{mag}\t<ammo>
{ammo}\t</ammo>

	<usage>
{period}\t\t<countries>{countries}</countries>
	</usage>

</weapon>
"""
    out_root = a.out or "."
    d = os.path.join(out_root, "Data", "Weapons")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, wid + ".txt")
    with open(p, "wb") as f:
        f.write(tpl.replace("\r\n", "\n").encode(ENC))
    print(f"已生成 {p}（数值为占位，请按史实修改）")
    return 0


# ---------------------------------------------------------------- info / list
def cmd_info(a):
    ref = find_ref()
    store = Store(ref, a.out)
    if a.id in store.squads:
        sub, p = store.squads[a.id]
        t = store.read(p)
        items, _ = V.parse_tags(t)
        L = lambda k: V.leaf(items, k)
        g = lambda k: (L(k) or ["—"])[0]
        print(f"单位 {a.id}  ({sub})")
        for k in ["type", "nationality", "quality", "language", "long_name", "short_name", "uniform"]:
            print(f"  {k:12s} {g('squad/description/' + k)}")
        if sub == "Vehicles":
            print(f"  weight      {g('squad/vehicle/attributes/weight')} kg")
            print(f"  hull        {g('squad/vehicle/hull/width')}×{g('squad/vehicle/hull/length')}×{g('squad/vehicle/hull/height')} cm, "
                  f"armour {g('squad/vehicle/hull/armour/upper_front') or g('squad/vehicle/hull/armour/front')}")
            print(f"  engine      {g('squad/vehicle/drive/engine/name')} {g('squad/vehicle/drive/engine/horsepower')} hp, "
                  f"{g('squad/vehicle/drive/engine/reliability')}")
        elif sub == "AT Guns":
            print(f"  mass/trail  {g('squad/atgun/mass')} kg / {g('squad/atgun/trail_length')} m")
        print("  availability: " + ", ".join(
            f"{y}-{m} x{n}" for m, y, n in zip(L("squad/availability/data/month"),
                                               L("squad/availability/data/year"),
                                               L("squad/availability/data/number"))))
        crew = sum(1 for p, _, _ in items if p.endswith("/man"))
        weapons_all = sorted({v for p, v, _ in items if p.endswith("/weapon/type")})
        print("  crew: " + str(crew) + "   weapons: " + ", ".join(weapons_all[:8]))
        return 0
    if a.id in store.weapons:
        t = store.read(store.weapons[a.id])
        items, _ = V.parse_tags(t)
        L = lambda k: V.leaf(items, k)
        g = lambda k: (L(k) or ["—"])[0]
        print(f"武器 {a.id}")
        print(f"  name    {g('weapon/name')}")
        print(f"  class   {g('weapon/type')}")
        print(f"  calibre {g('weapon/dimensions/calibre')} mm  barrel {g('weapon/dimensions/barrel_length')} cm  rof {g('weapon/shoot/rof')}")
        print(f"  usage   {g('weapon/usage/period') or 'WW2'}  {g('weapon/usage/countries')}")
        for f, sp, m, he in zip(L("weapon/ammo/type/flavour"), L("weapon/ammo/type/speed"),
                                L("weapon/ammo/type/mass"), L("weapon/ammo/type/HE")):
            print(f"  ammo    {f:22s} {sp:>5s} m/s  {m:>7s} kg  HE {he}")
        return 0
    print(f"找不到 {a.id}"); return 1


def cmd_list(a):
    ref = find_ref()
    store = Store(ref, a.out)
    rows = []
    tmap = {"tank": "TYPE_TANK", "armoured_car": "TYPE_ARMOURED_CAR", "assault_gun": "TYPE_ASSAULT_GUN",
            "halftrack": "TYPE_HALFTRACK", "ifv": "TYPE_INFANTRY_FIGHTING_VEHICLE",
            "infantry": "TYPE_INFANTRY_SECTION", "mortar": "TYPE_MORTAR", "hmg": "TYPE_HMG",
            "bazooka": "TYPE_BAZOOKA", "at_rifle": "TYPE_AT_RIFLE", "flamethrower": "TYPE_FLAMETHROWER",
            "atgun": "TYPE_ATGUN", "howitzer": "TYPE_HOWITZER", "recoilless": "TYPE_RECOILLESS_RIFLE"}
    for uid, (sub, p) in sorted(store.squads.items()):
        t = store.read(p)
        items, _ = V.parse_tags(t)
        ut = (V.leaf(items, "squad/description/type") or [""])[0]
        nat = (V.leaf(items, "squad/description/nationality") or [""])[0]
        if a.type and ut != tmap.get(a.type, a.type):
            continue
        if a.nation and nat != "NATIONALITY_" + a.nation.upper():
            continue
        if a.query and a.query.lower() not in uid.lower():
            continue
        ws = set(re.findall(r"WEAPON_[A-Z0-9_]+", t))
        if a.modern:
            ok = False
            for w in ws:
                wp = store.weapons.get(w)
                if wp and re.search(r"<period>MODERN</period>", store.read(wp)):
                    ok = True; break
            if not ok:
                continue
        rows.append(f"{uid}   [{ut}]")
    for r in rows:
        print(r)
    print(f"\n共 {len(rows)} 个", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(prog="ff.py", description="Firefight MOD 工具集")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="校验 MOD 目录")
    p.add_argument("root"); p.add_argument("--ref"); p.add_argument("--strict", action="store_true")

    p = sub.add_parser("clone", help="克隆单位为新单位")
    p.add_argument("src"); p.add_argument("dst")
    p.add_argument("--out"); p.add_argument("--nation"); p.add_argument("--uniform")
    p.add_argument("--era"); p.add_argument("--avail"); p.add_argument("--comment")
    p.add_argument("--long"); p.add_argument("--short"); p.add_argument("--no-register", action="store_true")

    p = sub.add_parser("weapon", help="生成武器骨架")
    p.add_argument("weapon_id"); p.add_argument("--name"); p.add_argument("--out")
    p.add_argument("--cls", default="CANNON")
    p.add_argument("--country", action="append")
    p.add_argument("--modern", action="store_true")
    p.add_argument("--calibre"); p.add_argument("--barrel")

    p = sub.add_parser("assets", help="单位的美工任务单")
    p.add_argument("unit_id"); p.add_argument("--out"); p.add_argument("--ref")

    p = sub.add_parser("info", help="单位/武器摘要")
    p.add_argument("id"); p.add_argument("--out")

    p = sub.add_parser("list", help="检索原版")
    p.add_argument("--type"); p.add_argument("--nation"); p.add_argument("--query")
    p.add_argument("--modern", action="store_true"); p.add_argument("--out")

    a = ap.parse_args()
    if a.cmd == "check":
        ref = a.ref or find_ref()
        return V.run_check(a.root, ref=ref, strict=a.strict)
    if a.cmd == "clone":
        return cmd_clone(a)
    if a.cmd == "weapon":
        return cmd_weapon(a)
    if a.cmd == "assets":
        return assets_report(Store(find_ref(), a.out), a.unit_id)
    if a.cmd == "info":
        return cmd_info(a)
    if a.cmd == "list":
        return cmd_list(a)
    return 2


if __name__ == "__main__":
    sys.exit(main())
