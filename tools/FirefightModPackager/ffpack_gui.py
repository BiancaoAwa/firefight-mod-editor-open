#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firefight MOD 打包工具 GUI

流程: ① 选择 MOD 工程（zip 或文件夹）+ 基准（APK / 电脑版 zip / 数据文件夹）→ 解压并校验（报告写 txt）
      ② 扫描未引用文件（单列勾选剔除；根目录文件不参与分析）
      ③ 打包要求：输出类型(zip/apk)、份数、APK 元数据（可单独读取）、多语言应用名 → 打包
日志实时输出到 cmd 窗口（用 `py ffpack_gui.py` 启动）。
"""
import os, re, sys, time, json, threading, queue, zipfile, shutil, tempfile, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ffpack




# ---------- setting.txt / 日志（settings 读写统一用 ffpack 的实现）----------
SETTINGS_FILE = ffpack.SETTING_PATH
load_settings = ffpack.load_settings
save_settings = ffpack.save_settings
LOG_DIR = os.path.join(HERE, "logs")
BASE_CACHE_DIR = os.path.join(HERE, "base_data")


def load_preset_file():
    """多语言应用名预置：setting.txt 的 AppNamePreset 段（无则用内置表）"""
    d = {}
    for ln in (ffpack.load_settings().get("AppNamePreset") or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        if k.strip() and v.strip():
            d[k.strip()] = v.strip()
    return d or ffpack.load_appname_preset()


# 首次运行: 生成带默认值的 setting.txt（预翻译 + 枚举全部并入这一个文件）
if not os.path.isfile(SETTINGS_FILE):
    _seed = ffpack.load_appname_preset()
    _enums = ""
    _ext = os.path.join(HERE, "enums_ext.txt")
    if os.path.isfile(_ext):
        _enums = open(_ext, encoding="utf-8-sig", errors="replace").read().strip()
    ffpack.save_settings({
        "AppNamePreset": "\n".join(f"{k}={v}" for k, v in _seed.items()),
        "Enums": _enums,
    })


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Firefight MOD 打包工具")
        self.geometry("860x720")
        self.q = queue.Queue()
        self.mod_dir = None
        self.base_dir = None
        self.unref_vars = {}
        self._apply_settings(load_settings())
        # 迁移: 旧 setting 缺 Enums/AppNamePreset 时, 从 enums_ext.txt / 内置表迁入
        _ext = os.path.join(HERE, "enums_ext.txt")
        if not self._settings.get("Enums") and os.path.isfile(_ext):
            self._settings["Enums"] = open(_ext, encoding="utf-8-sig", errors="replace").read().strip()
            self.log_write("已将 enums_ext.txt 内容并入 setting.txt 的 Enums 段")
        if not self._settings.get("AppNamePreset"):
            self._settings["AppNamePreset"] = "\n".join(
                f"{k}={v}" for k, v in ffpack.load_appname_preset().items())
        os.makedirs(LOG_DIR, exist_ok=True)
        self.log_path = os.path.join(LOG_DIR, f"打包日志_{time.strftime('%Y%m%d_%H%M%S')}.txt")
        self.log_fh = open(self.log_path, "a", encoding="utf-8")
        self._step_name, self._step_t0, self._busy_on = "就绪", None, False
        self.report_path = None
        self.var_basecache = tk.BooleanVar(value=self._settings.get("BaseCache", "true").lower() == "true")
        self._build()
        self.after(100, self._poll)
        self.after(1000, self._tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.log_write(f"会话开始，日志文件: {self.log_path}")

    def _build(self):
        """整体布局：统一两列网格（标签列固定宽 + 输入列自适应），窗口加宽可缩放"""
        self.geometry("1000x780")
        self.minsize(880, 680)
        pad = dict(padx=6, pady=3)
        LBW = 22                                    # 标签列统一宽度

        def lb(parent, text, r):
            ttk.Label(parent, text=text, width=LBW, anchor="e").grid(row=r, column=0, sticky="e", **pad)

        # ============ ① 输入 ============
        f1 = ttk.LabelFrame(self, text=" ① 输入 ")
        f1.pack(fill="x", **pad)
        f1.columnconfigure(1, weight=1)
        self.var_zip = tk.StringVar(value=self._settings.get("ModPath", ""))
        self.var_apk = tk.StringVar(value=self._settings.get("BasePath") or self._guess_apk())
        self.tasks = []
        # 默认包名/版本: 优先取 setting.txt（Pkg/VersionCode/VersionName），缺的再从基准 APK 补
        self.var_pkg_default = self._settings.get("Pkg", "")
        self.var_vcode_default = str(self._settings.get("VersionCode", "") or "")
        self.var_vname_default = self._settings.get("VersionName", "")
        _base0 = self.var_apk.get()
        if _base0 and os.path.isfile(_base0):
            try:
                _meta = ffpack.read_apk_manifest(_base0)
                if not self.var_pkg_default:
                    self.var_pkg_default = _meta.get("package") or ""
                if not self.var_vcode_default:
                    self.var_vcode_default = str(_meta.get("versionCode") or "")
                if not self.var_vname_default:
                    self.var_vname_default = str(_meta.get("versionName") or "")
            except Exception:
                pass
        self._load_tasks(self._settings.get("Tasks", ""))
        if not self.tasks:                                   # 首次运行才给默认任务
            self.tasks = [{"type": "zip", "file": "MOD.zip"},
                          {"type": "apk", "file": "MOD.apk",
                           "pkg": self.var_pkg_default,
                           "vcode": self.var_vcode_default,
                           "vname": self.var_vname_default}]

        lb(f1, "MOD 工程 (zip/文件夹):", 0)
        ttk.Entry(f1, textvariable=self.var_zip).grid(row=0, column=1, sticky="we", **pad)
        _b = ttk.Frame(f1); _b.grid(row=0, column=2, **pad)
        ttk.Button(_b, text="选 zip…", width=9,
                   command=lambda: self._pick("var_zip", [("zip", "*.zip")])).pack(side="left", padx=1)
        ttk.Button(_b, text="选文件夹…", width=10,
                   command=lambda: self._pick_dir("var_zip")).pack(side="left", padx=1)

        lb(f1, "基准 (APK/zip/文件夹):", 1)
        ttk.Entry(f1, textvariable=self.var_apk).grid(row=1, column=1, sticky="we", **pad)
        _b2 = ttk.Frame(f1); _b2.grid(row=1, column=2, **pad)
        ttk.Button(_b2, text="选 apk/zip…", width=10,
                   command=lambda: self._pick("var_apk", [("apk/zip", "*.apk *.zip")])).pack(side="left", padx=1)
        ttk.Button(_b2, text="选文件夹…", width=10,
                   command=lambda: self._pick_dir("var_apk")).pack(side="left", padx=1)

        _b3 = ttk.Frame(f1); _b3.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        ttk.Button(_b3, text="① 解压并校验", command=self.step1).pack(side="left", padx=(0, 6))
        ttk.Button(_b3, text="读取 APK 元数据", command=self.step_meta).pack(side="left", padx=6)
        ttk.Button(_b3, text="查看校验报告", command=lambda: self._open_path(self.report_path)).pack(side="left", padx=6)
        ttk.Button(_b3, text="打开日志文件夹", command=lambda: self._open_path(LOG_DIR)).pack(side="left", padx=6)
        self.var_basecache = tk.BooleanVar(value=self._settings.get("BaseCache", "true").lower() == "true")
        ttk.Checkbutton(_b3, text="基准缓存复用 (base_data/)", variable=self.var_basecache).pack(side="left", padx=6)

        # ============ ② 未引用 ============
        f3 = ttk.LabelFrame(self, text=" ② 未引用文件（勾选 = 剔除；根目录文件与基准同名覆盖不参与） ")
        f3.pack(fill="both", expand=True, **pad)
        _bar = ttk.Frame(f3); _bar.pack(fill="x")
        ttk.Button(_bar, text="扫描未引用文件", command=self.step2).pack(side="left", padx=4, pady=2)
        ttk.Button(_bar, text="全选", width=6, command=lambda: self._set_all_unref(True)).pack(side="left", padx=2)
        ttk.Button(_bar, text="全不选", width=6, command=lambda: self._set_all_unref(False)).pack(side="left", padx=2)
        self.unref_box = ttk.Frame(f3)
        self.unref_box.pack(fill="both", expand=True)
        self.unref_canvas = tk.Canvas(self.unref_box, height=120, highlightthickness=0)
        _sb = ttk.Scrollbar(self.unref_box, orient="vertical", command=self.unref_canvas.yview)
        self.unref_inner = ttk.Frame(self.unref_canvas)
        self.unref_canvas.create_window((0, 0), window=self.unref_inner, anchor="nw")
        self.unref_inner.bind("<Configure>",
                              lambda e: self.unref_canvas.configure(scrollregion=self.unref_canvas.bbox("all")))
        self.unref_canvas.configure(yscrollcommand=_sb.set)
        self.unref_canvas.pack(side="left", fill="both", expand=True)
        _sb.pack(side="right", fill="y")

        # ============ ③ 打包任务 ============
        self.var_out = tk.StringVar(value=self._settings.get("OutDir")
                                    or os.path.join(os.path.expanduser("~"), "Desktop"))
        self.var_do_zip = tk.BooleanVar(value=True)
        self.var_do_apk = tk.BooleanVar(value=True)
        f4 = ttk.LabelFrame(self, text=" ③ 打包任务 ")
        f4.pack(fill="x", **pad)
        self.task_tree = ttk.Treeview(f4, columns=("type", "file", "pkg", "ver"), height=3, show="headings")
        for col, w, txt in (("type", 60, "类型"), ("file", 200, "输出文件"),
                            ("pkg", 230, "包名"), ("ver", 110, "版本")):
            self.task_tree.heading(col, text=txt)
            self.task_tree.column(col, width=w)
        self.task_tree.pack(fill="x", padx=4, pady=2)
        _tbar = ttk.Frame(f4); _tbar.pack(fill="x")
        ttk.Button(_tbar, text="添加 zip 打包", command=self.add_zip_task).pack(side="left", padx=3)
        ttk.Button(_tbar, text="添加 APK 打包", command=self.add_apk_task).pack(side="left", padx=3)
        ttk.Button(_tbar, text="编辑选中", command=self.edit_task).pack(side="left", padx=3)
        ttk.Button(_tbar, text="删除选中", command=self.del_task).pack(side="left", padx=3)
        ttk.Label(_tbar, text="输出目录:").pack(side="left", padx=(14, 2))
        ttk.Entry(_tbar, textvariable=self.var_out, width=26).pack(side="left", padx=2)
        ttk.Button(_tbar, text="…", width=3, command=self._pick_out).pack(side="left")

        # ============ ④ 签名与应用名 ============
        f5 = ttk.LabelFrame(self, text=" ④ 签名与应用名 ")
        f5.pack(fill="x", **pad)
        f5.columnconfigure(1, weight=1)
        self.var_sign = tk.BooleanVar(value=self._settings.get("Sign", "true").lower() == "true")
        self.var_keystore = tk.StringVar(value=self._settings.get("KeyStore", ""))
        self.var_ks_pass = tk.StringVar(value=self._settings.get("KeyStorePass", ""))
        self.var_key_alias = tk.StringVar(value=self._settings.get("KeyAlias", ""))
        self.var_key_pass = tk.StringVar(value=self._settings.get("KeyPass", ""))
        self.var_schemes = tk.StringVar(value=self._settings.get("SignSchemes", "v1+v2+v3"))
        self.var_icon = tk.StringVar(value=self._settings.get("IconPath", ""))

        # 密钥: 留空 = 官方 testkey；填路径/下拉选 = 自定义（凭据可自动补）
        lb(f5, "密钥 (空=官方 testkey):", 0)
        _kr = ttk.Frame(f5); _kr.grid(row=0, column=1, columnspan=2, sticky="we", **pad)
        ttk.Entry(_kr, textvariable=self.var_keystore).pack(side="left", fill="x", expand=True)
        ttk.Button(_kr, text="…", width=4, command=lambda: self._pick("var_keystore",
                   [("keystore", "*.keystore *.jks"), ("all", "*.*")])).pack(side="left", padx=(4, 0))

        lb(f5, "工具目录密钥:", 1)
        self.key_list = ttk.Combobox(f5, values=self._scan_keys(), state="readonly")
        self.key_list.grid(row=1, column=1, sticky="we", **pad)
        self.key_list.bind("<<ComboboxSelected>>", self._on_key_selected)

        lb(f5, "签名方案:", 2)
        ttk.Combobox(f5, textvariable=self.var_schemes, state="readonly", width=12,
                     values=["v1+v2+v3", "v2+v3", "v1+v2", "v3", "v1"]).grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(f5, text="多语言应用名(每行 语言=名称):", width=LBW, anchor="ne").grid(
            row=3, column=0, sticky="ne", **pad)
        self.txt_names = tk.Text(f5, height=5, font=("Consolas", 9))
        saved_names = self._settings.get("AppNames")
        if saved_names:
            self.txt_names.insert("1.0", saved_names)
        else:
            self.txt_names.insert("1.0", "\n".join(f"{k}={v}" for k, v in load_preset_file().items()))
        self.txt_names.grid(row=3, column=1, columnspan=2, sticky="we", **pad)

        lb(f5, "APK 图标 (png/zip/文件夹):", 4)
        ttk.Entry(f5, textvariable=self.var_icon).grid(row=4, column=1, sticky="we", **pad)
        ttk.Button(f5, text="…", width=4, command=lambda: self._pick("var_icon",
                   [("png/zip", "*.png *.zip"), ("all", "*.*")])).grid(row=4, column=2, sticky="w", **pad)

        _go = ttk.Frame(f5); _go.grid(row=6, column=0, columnspan=3, sticky="w", **pad)
        ttk.Checkbutton(_go, text="打包后自动签名", variable=self.var_sign).pack(side="left", padx=(0, 10))
        ttk.Button(_go, text="③ 开始打包", command=self.step3).pack(side="left")

        # ============ 状态栏 ============
        self.status = ttk.Label(self, text="✅ 就绪", anchor="w", relief="sunken")
        self.status.pack(fill="x", side="bottom")

    # ---------- setting.txt ----------
    def _apply_settings(self, d):
        self._settings = d

    # ---------- 任务列表 ----------
    @staticmethod
    def _sanitize_name(name):
        """Windows 文件名非法字符清洗，返回 (新名, 是否有改动)"""
        import re as _re
        fixed = name.replace(":", " - ")
        fixed = _re.sub(r'[<>"/\\|?*]', "-", fixed)
        fixed = _re.sub(r"\s{2,}", " ", fixed).strip()
        return fixed, fixed != name

    def _load_tasks(self, spec):
        # Tasks="zip:MOD.zip|apk:out.apk:pkg:vcode:vname"
        # 注意: 输出文件名本身可含冒号，apk 段从右往左切出 vname/vcode/pkg
        self.tasks = []
        try:
            for part in (spec or "").split("|"):
                part = part.strip()
                if not part:
                    continue
                if part.startswith("zip:"):
                    name = part[4:].strip()
                    if name:
                        self.tasks.append({"type": "zip", "file": name})
                    continue
                if part.startswith("apk:"):
                    pieces = part[4:].rsplit(":", 3)
                    if len(pieces) == 4 and all(p.strip() for p in pieces):
                        self.tasks.append({"type": "apk", "file": pieces[0].strip(),
                                           "pkg": pieces[1].strip(),
                                           "vcode": pieces[2].strip(),
                                           "vname": pieces[3].strip()})
                        continue
                self.log_write(f"setting 中 Tasks 段无法解析已跳过: {part!r}", level="WARN")
        except Exception as ex:
            self.tasks = []
            self.log_write(f"打包列表初始化失败，已重置为空: {ex}", level="ERROR")
        for t in self.tasks:                                 # 文件名落盘前清洗
            fixed, changed = self._sanitize_name(t["file"])
            if changed:
                self.log_write(f'输出文件名含 Windows 非法字符，已改为: {fixed}', level="WARN")
                t["file"] = fixed
        if hasattr(self, "task_tree"):
            self._refresh_tasks()

    def _tasks_spec(self):
        parts = []
        for t in self.tasks:
            if t["type"] == "zip":
                parts.append(f"zip:{t['file']}")
            else:
                parts.append(f"apk:{t['file']}:{t['pkg']}:{t['vcode']}:{t['vname']}")
        return "|".join(parts)

    def _collect_settings(self):
        d = dict(self._settings)                        # 保留 AppNamePreset/Enums 等非 UI 键
        d.update({
            "ModPath": self.var_zip.get(),
            "BasePath": self.var_apk.get(),
            "OutDir": self.var_out.get(),
            "Tasks": self._tasks_spec(),
            "AppNames": self.txt_names.get("1.0", "end").rstrip("\n"),
            "Sign": str(self.var_sign.get()),
            "DoZip": str(self.var_do_zip.get()),
            "DoApk": str(self.var_do_apk.get()),
            "BaseCache": str(self.var_basecache.get()),
            "SignMode": self._settings.get("SignMode", "auto"),
            "KeyStore": self.var_keystore.get(),
            "KeyStorePass": self.var_ks_pass.get(),
            "KeyAlias": self.var_key_alias.get(),
            "KeyPass": self.var_key_pass.get(),
            "Pkg": self.var_pkg_default,
            "VersionCode": self.var_vcode_default,
            "VersionName": self.var_vname_default,
            "IconPath": self.var_icon.get(),
            "SignSchemes": self.var_schemes.get(),
        })
        return d

    def _save_settings(self):
        try:
            save_settings(self._collect_settings())
        except Exception as e:
            print("setting.txt 保存失败:", e, flush=True)

    def _on_close(self):
        self._save_settings()
        self.log_write("会话结束")
        try:
            self.log_fh.close()
        except Exception:
            pass
        self.destroy()

    # ---------- 任务列表 ----------
    def add_zip_task(self):
        name = self._ask_str("zip 打包", "输出文件名:", "MOD.zip")
        if name:
            self.tasks.append({"type": "zip", "file": name})
            self._refresh_tasks()

    def add_apk_task(self):
        d = self._apk_dialog("添加 APK 打包", {
            "file": (load_preset_file().get("default") or "MOD") + ".apk",
            "pkg": self.var_pkg_default,
            "vcode": self.var_vcode_default,
            "vname": self.var_vname_default})
        if d:
            self.tasks.append({"type": "apk", **d})
            self._refresh_tasks()

    def edit_task(self):
        sel = self.task_tree.selection()
        if not sel:
            return
        i = self.task_tree.index(sel[0])
        t = self.tasks[i]
        if t["type"] == "apk":
            d = self._apk_dialog("编辑 APK 打包", t)
            if d:
                self.tasks[i] = {"type": "apk", **d}
        else:
            name = self._ask_str("zip 打包", "输出文件名:", t["file"])
            if name:
                self.tasks[i]["file"] = name
        self._refresh_tasks()

    def del_task(self):
        sel = self.task_tree.selection()
        if sel:
            del self.tasks[self.task_tree.index(sel[0])]
            self._refresh_tasks()

    def _refresh_tasks(self):
        try:
            self.task_tree.delete(*self.task_tree.get_children())
        except Exception as ex:
            self.log_write(f"任务列表初始化异常: {ex}", level="ERROR")
            return
        for i, t in enumerate(self.tasks):
            try:
                if t["type"] not in ("zip", "apk") or not t.get("file"):
                    raise ValueError(f"第 {i+1} 项格式非法: {t!r}")
                self.task_tree.insert("", "end", values=(
                    t["type"].upper(), t["file"],
                    t.get("pkg", "—"), f'{t.get("vcode", "")} / {t.get("vname", "")}' if t["type"] == "apk" else "—"))
            except Exception as ex:
                self.log_write(f"任务 {i+1} 无法显示已跳过: {ex}", level="WARN")

    def _ask_str(self, title, label, initial):
        win = tk.Toplevel(self); win.title(title); win.transient(self); win.grab_set()
        ttk.Label(win, text=label).pack(padx=10, pady=6)
        e = ttk.Entry(win, width=40); e.insert(0, initial); e.pack(padx=10, pady=2)
        out = []
        def ok():
            v = e.get().strip()
            if v:
                fixed, changed = self._sanitize_name(v)
                if changed:
                    self.log_write(f'输出文件名含 Windows 非法字符，已改为: {fixed}', level="WARN")
                    v = fixed
            out.append(v); win.destroy()
        ttk.Button(win, text="确定", command=ok).pack(pady=6)
        win.wait_window()
        return out[0] if out and out[0] else None

    def _apk_dialog(self, title, init):
        win = tk.Toplevel(self); win.title(title); win.transient(self); win.grab_set()
        rows = [("输出文件名:", "file"), ("包名:", "pkg"),
                ("版本号 versionCode:", "vcode"), ("版本名 versionName:", "vname")]
        vars = {}
        for i, (label, key) in enumerate(rows):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky="e", padx=8, pady=3)
            v = tk.StringVar(value=str(init.get(key, "")))
            vars[key] = v
            ttk.Entry(win, textvariable=v, width=42).grid(row=i, column=1, padx=8, pady=3)
        out = []
        def ok():
            d = {k: v.get().strip() for k, v in vars.items()}
            if d.get("file"):
                fixed, changed = self._sanitize_name(d["file"])
                if changed:
                    self.log_write(f'输出文件名含 Windows 非法字符，已改为: {fixed}', level="WARN")
                    d["file"] = fixed
            out.append(d)
            win.destroy()
        ttk.Button(win, text="确定", command=ok).grid(row=len(rows), column=1, pady=8)
        win.wait_window()
        return out[0] if out and all(out[0].values()) else None

    def _open_path(self, p):
        if p and os.path.exists(p):
            try:
                os.startfile(p)
            except Exception as ex:
                self.log_write(f"打开失败: {ex}")
        else:
            messagebox.showinfo("提示", "文件尚不存在（先跑一次步骤①）")

    def _scan_keys(self):
        """扫工具根目录 + keys/ 子目录的 keystore/jks"""
        import glob as _g
        hits = []
        for d in (HERE, os.path.join(HERE, "keys")):
            for pat in ("*.keystore", "*.jks"):
                hits += _g.glob(os.path.join(d, pat))
        ks = os.path.join(os.path.expanduser("~"), ".android", "debug.keystore")
        if os.path.isfile(ks):
            hits.append(ks)
        return hits

    def _refresh_keys(self):
        self.key_list["values"] = self._scan_keys()
        self.log_write(f"密钥列表已刷新: {len(self.key_list['values'])} 个")

    def _on_key_selected(self, _e=None):
        v = self.key_list.get()
        if not v:
            return
        self.var_keystore.set(v)
        creds = ffpack.KEY_CRED_DEFAULTS.get(os.path.basename(v).lower())
        if creds:
            self.var_ks_pass.set(creds[0])
            self.var_key_alias.set(creds[1])
            self.var_key_pass.set(creds[2])
            self.log_write(f"已选择密钥: {v}（凭据已自动填充）")
        else:
            self.log_write(f"已选择密钥: {v}（请填写密码与别名）")

    def load_preset_names(self):
        preset = load_preset_file()
        preset_text = "\n".join(f"{k}={v}" for k, v in preset.items())
        self.txt_names.delete("1.0", "end")
        self.txt_names.insert("1.0", preset_text)
        self.log_write(f"已载入预置翻译 {len(preset)} 条（来源: setting.txt 的 AppNamePreset 段）")

    def _guess_apk(self):
        import glob as _g
        for d in (os.getcwd(), HERE):
            hits = sorted(_g.glob(os.path.join(d, "*.apk")))
            if hits:
                return hits[0]
        return ""

    def _pick(self, var, types):
        p = filedialog.askopenfilename(filetypes=types + [("all", "*.*")])
        if p:
            getattr(self, var).set(p)

    def _pick_dir(self, var):
        p = filedialog.askdirectory()
        if p:
            getattr(self, var).set(p)

    def _pick_out(self):
        p = filedialog.askdirectory()
        if p:
            self.var_out.set(p)

    def log_write(self, msg, level="INFO"):
        """分级日志: [HH:MM:SS][级别] 消息（INFO/STEP/WARN/ERROR/HB/KEY）
        控制台只在 stdout 未被重定向时打印 —— 校验期间 stdout 是报告缓冲区，
        此时 print 会把心跳/进度日志漏进校验报告.txt"""
        line = f"[{time.strftime('%H:%M:%S')}][{level}] {msg}"
        if sys.stdout is sys.__stdout__:
            print(line, flush=True)
        try:
            self.log_fh.write(line + "\n")
            self.log_fh.flush()
        except Exception:
            pass

    def log_warn(self, msg):
        self.log_write(msg, level="WARN")

    def _step_begin(self, name):
        self._step_name, self._step_t0, self._busy_on = name, time.time(), True
        self.log_write(f"{name} 开始", level="STEP")
        self._refresh_status()

    def _step_end(self, extra=""):
        if self._step_t0:
            dt = time.time() - self._step_t0
            self.log_write(f"{self._step_name} 结束，耗时 {dt:.1f}s {extra}", level="STEP")
        self._busy_on = False
        self._step_name = "就绪"
        self._refresh_status()

    def _tick(self):
        # 每秒: 任务/密钥状态检查 + 心跳日志 + 界面刷新
        try:
            if hasattr(self, "task_tree"):
                sig = repr([(t.get("type"), t.get("file"), t.get("pkg"),
                             t.get("vcode"), t.get("vname")) for t in self.tasks])
                if sig != getattr(self, "_task_sig", None):
                    self._task_sig = sig
                    self._refresh_tasks()
            if hasattr(self, "key_list"):
                keys = self._scan_keys()
                if keys != list(self.key_list["values"]):
                    self.key_list["values"] = keys
                    self.log_write(f"密钥列表变化，已自动刷新（{len(keys)} 个）")
        except Exception:
            pass
        if self._busy_on and self._step_t0:
            dt = time.time() - self._step_t0
            try:
                n_task = len(self.tasks) if hasattr(self, "tasks") else 0
                self.log_fh.write(f"[{time.strftime('%H:%M:%S')}][HB] {self._step_name}"
                                  f" 已运行 {dt:.0f}s（任务 {n_task} 个，输出目录 {self.var_out.get()}）\n")
                self.log_fh.flush()
            except Exception:
                pass
        self._refresh_status()
        self.after(1000, self._tick)

    def _refresh_status(self):
        try:
            if self._busy_on and self._step_t0:
                self.status.config(text=f"⏳ {self._step_name} … {time.time()-self._step_t0:.0f}s")
            else:
                self.status.config(text="✅ 就绪")
            self.update_idletasks()
        except Exception:
            pass

    def _poll(self):
        try:
            while True:
                fn = self.q.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def run_bg(self, fn):
        if self._busy_on:
            self.log_write("⏳ 上一任务仍在进行，请等待完成")
            return

        def worker():
            try:
                fn()
            except Exception as ex:
                msg = str(ex)
                tb = traceback.format_exc()
                self.q.put(lambda m=msg: messagebox.showerror("出错", m))
                self.log_write(f"异常: {msg}", level="ERROR")
                print(tb, flush=True)
            finally:
                self.q.put(lambda: self._busy(False))
        self._busy(True)
        threading.Thread(target=worker, daemon=True).start()

    def _busy(self, on):
        if not on:
            self._step_end()
        self.config(cursor="watch" if on else "")
        self.update_idletasks()

    # ---------- 步骤 ----------
    def step1(self):
        src, base = self.var_zip.get(), self.var_apk.get()
        if not (os.path.isfile(src) or os.path.isdir(src)):
            messagebox.showwarning("提示", "先选择 MOD 工程（zip 或文件夹）"); return
        if base and not (os.path.isfile(base) or os.path.isdir(base)):
            messagebox.showwarning("提示", "基准路径无效"); return

        def job():
            self._step_begin("① 解压并校验")
            t0 = time.time()
            work = tempfile.mkdtemp(prefix="ffpack_mod_")
            ffpack.import_mod(src, work, log=self.log_write)
            self.mod_dir = work
            self._refs = None                          # 新工程, 引用闭包缓存失效
            self.log_write(f"    工程导入耗时 {time.time()-t0:.1f}s")
            base_ref = None
            if base:
                t1 = time.time()
                if self.var_basecache.get():
                    base_ref = ffpack.extract_base_data(base, BASE_CACHE_DIR, log=self.log_write)
                else:
                    base_ref = ffpack.extract_base_data(base, tempfile.mkdtemp(prefix="ffpack_base_"),
                                                        log=self.log_write)
                self.base_dir = base_ref
                self.log_write(f"    基准数据就绪耗时 {time.time()-t1:.1f}s → {base_ref}")
            t2 = time.time()
            self.log_write("开始校验（对照基准兜底）…")
            rc, report = ffpack.run_validate(work, base_ref, progress=self.log_write)
            # 报告模组个数
            m_unit = re.search(r"单位 (\d+) 个", report)
            m_wpn = re.search(r"武器 (\d+) 个", report)
            n_err = report.count("✗")
            n_warn = report.count("  ! ") + report.count("  ! [")
            if m_unit:
                self.log_write(f"模组个数: 单位 {m_unit.group(1)} 个, 武器 {m_wpn.group(1) if m_wpn else '?'} 个")
            self.log_write(f"校验结果: {n_err} 个 ERROR, {n_warn} 条 WARN（退出码 {rc}）")
            report_path = os.path.join(self.var_out.get() or os.path.expanduser("~"), "校验报告.txt")
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(report)
                self.report_path = report_path
                self.log_write(f"完整报告已写入: {report_path}（界面可点「查看校验报告」）")
            except Exception as ex2:
                self.log_write("报告写入失败: " + str(ex2))
            self._save_settings()
        self.run_bg(job)

    def step_meta(self):
        apk = self.var_apk.get()
        if not apk or not os.path.isfile(apk):
            messagebox.showwarning("提示", "先选择基准 APK"); return

        def job():
            try:
                meta = ffpack.read_apk_manifest(apk)
                self.var_pkg_default = meta.get("package") or self.var_pkg_default
                self.var_vcode_default = meta.get("versionCode") or self.var_vcode_default
                self.var_vname_default = meta.get("versionName") or self.var_vname_default
                sel = self.task_tree.selection()
                if sel:
                    i = self.task_tree.index(sel[0])
                    t = self.tasks[i]
                    if t["type"] == "apk":
                        t["pkg"] = self.var_pkg_default
                        t["vcode"] = self.var_vcode_default
                        t["vname"] = self.var_vname_default
                        self._refresh_tasks()
                self.log_write(f"当前元数据: package={self.var_pkg_default}, "
                               f"versionCode={self.var_vcode_default}, versionName={self.var_vname_default}"
                               + ("（已回填选中任务）" if sel else "（将作为新建 APK 任务的默认值）"))
                self._save_settings()                # 包名/版本持久化进 setting.txt
                try:
                    locs = ffpack.list_arsc_locales(apk)
                    self.log_write(f"可本地化语言 {len(locs)} 个: {' '.join(locs)}")
                except Exception as ex2:
                    self.log_write(f"读语言列表失败: {ex2}")
            except Exception as ex:
                self.log_write(f"读取元数据失败: {ex}")
        self.run_bg(job)

    def step2(self):
        if not self.mod_dir:
            messagebox.showwarning("提示", "先执行步骤①"); return

        def job():
            self._step_begin("② 扫描未引用文件")
            t2 = time.time()
            files = ffpack.find_unreferenced(self.mod_dir, self.base_dir,
                                             log=self.log_write, refs=self._get_refs())
            self.log_write(f"    扫描耗时 {time.time()-t2:.1f}s")
            self.q.put(lambda f=files: self._show_unref(f))
        self.run_bg(job)

    def _get_refs(self):
        """引用闭包缓存: 一次计算, 步骤②③复用"""
        if getattr(self, "_refs", None) is None:
            self._refs = ffpack.referenced_files(self.mod_dir, log=self.log_write)
        return self._refs

    def _show_unref(self, files):
        for w in self.unref_inner.winfo_children():
            w.destroy()
        self.unref_vars.clear()
        if not files:
            ttk.Label(self.unref_inner, text="（无未引用文件 —— 全部资源都被引用或与基准一致）",
                      foreground="gray").grid(row=0, column=0, sticky="w", padx=4)
            return
        for i, f in enumerate(files):
            v = tk.BooleanVar(value=False)
            self.unref_vars[f] = v
            ttk.Checkbutton(self.unref_inner, text=f, variable=v).grid(row=i, column=0, sticky="w", padx=4)
        self.log_write(f"未引用文件 {len(files)} 个（未勾选的不会被剔除）")
        if files:
            import collections
            cat = collections.Counter(f.split("/")[0] for f in files if "/" in f)
            for k, v in cat.most_common():
                self.log_write(f"    {k}: {v} 个")

    def _set_all_unref(self, val):
        for v in self.unref_vars.values():
            v.set(val)

    def step3(self):
        if not self.mod_dir:
            messagebox.showwarning("提示", "先执行步骤①"); return
        out_dir = self.var_out.get()
        if not os.path.isdir(out_dir):
            messagebox.showwarning("提示", "输出目录不存在"); return
        if not self.tasks:
            messagebox.showwarning("提示", "请先添加打包任务"); return
        base = self.var_apk.get()
        is_apk_base = base and os.path.isfile(base) and base.lower().endswith(".apk")

        app_names, repl = {}, {}
        loc_re = re.compile(r"^(default|\(default\)|[a-z]{2,3}(-r[A-Z]{2})?)$")
        for ln in self.txt_names.get("1.0", "end").split("\n"):
            ln = ln.strip()
            if not ln or "=" not in ln:
                continue
            key, _, val = ln.partition("=")
            key, val = key.strip(), val.strip()
            if not key or not val:
                continue
            if loc_re.match(key):
                app_names["default" if key in ("default", "(default)") else key] = val
            else:
                repl[key] = val                      # 兼容旧格式: 旧名=新名 全池替换

        doomed = [f for f, v in self.unref_vars.items() if v.get()]
        if doomed:
            if not messagebox.askyesno("确认剔除", f"将删除 {len(doomed)} 个未引用文件，继续？"):
                return
            ffpack.prune(self.mod_dir, doomed)

        def job():
            self._step_begin("③ 打包（任务列表）")
            self.log_write("检查图片引用…")
            try:
                ffpack.check_mod_images(self.mod_dir, self.base_dir, log=self.log_write)
            except Exception as ex:
                self.log_write(f"⚠️ 图片检查异常（继续打包）: {ex}")
            self.log_write("对照音频（Mod/基准）…")
            try:
                ffpack.check_mod_audio(self.mod_dir, self.base_dir,
                                       log=self.log_write, refs=self._get_refs())
            except Exception as ex:
                self.log_write(f"⚠️ 音频对照异常（继续打包）: {ex}")
            t_all = time.time()
            for i, t in enumerate(self.tasks, 1):
                dst = os.path.join(out_dir, t["file"])
                self.log_write(f"[任务 {i}/{len(self.tasks)}] {t['type'].upper()} → {t['file']}")
                t_task = time.time()
                if t["type"] == "zip":
                    ffpack.pack_mod_zip(self.mod_dir, dst)
                else:
                    if not is_apk_base:
                        self.log_write("  ⚠️ 基准不是 APK，跳过该任务"); continue
                    ffpack.repack_apk(base, dst, mod_dir=self.mod_dir,
                                      manifest_attrs={"package": t["pkg"],
                                                      "versionCode": t["vcode"],
                                                      "versionName": t["vname"]},
                                      arsc_all=(repl or None),
                                      app_names=(app_names or None),
                                      icon_path=(self.var_icon.get().strip() or None),
                                      log=self.log_write)
                    if self.var_sign.get():
                        _ks = self.var_keystore.get().strip()
                        ffpack.sign_apk(
                            dst,
                            keystore=(_ks or None),
                            ks_pass=(self.var_ks_pass.get().strip() or None),
                            alias=(self.var_key_alias.get().strip() or None),
                            key_pass=(self.var_key_pass.get().strip() or None),
                            schemes=self.var_schemes.get(),
                            log=self.log_write)
                self.log_write(f"    输出大小: {os.path.getsize(dst)/1e6:.1f} MB，任务耗时 {time.time()-t_task:.1f}s")
            self.log_write(f"③ 总耗时 {time.time()-t_all:.1f}s")
            self._save_settings()
            self.log_write(f"✅ 全部完成，输出在 {out_dir}")
            self.q.put(lambda: messagebox.showinfo("完成", f"打包完成，输出在 {out_dir}"))
        self.run_bg(job)


if __name__ == "__main__":
    App().mainloop()
