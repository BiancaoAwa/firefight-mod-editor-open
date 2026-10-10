# Firefight MOD 打包工具

> 基于《Firefight》（Sean O'Connor's Windows Games Ltd）原版 12.2.0 数据格式逆向整理的通用 MOD 打包工具，适用于任意时代的 Firefight MOD（WW1/WW2/modern 等）。

## 文件清单

| 文件 | 用途 |
|---|---|
| `ffpack_gui.py` | **打包 GUI（推荐入口）**：`python ffpack_gui.py` |
| `ffpack.py` | 打包核心：工程 zip → 校验 → 引用闭包检查 → 剔除未引用 → 基准 APK 重打包 + 签名 |
| `validate.py` | 校验器（`ff.py check` / `ffpack` 的后端） |
| `ff.py` | 数据工具：克隆单位 / 生成武器骨架 / 美工任务单 / 查询 / 检索 / 校验 |
| `ManifestEditor/` | [ManifestEditor](https://github.com/ohyeah521/ManifestEditor)（MIT）— APK 二进制 manifest 修改（含 1 处本地补丁，见 `ManifestEditor-upstream/LOCAL_FIX.md`） |
| `ManifestEditor-upstream/` | 上游官方仓库源码存档（LICENSE/README/setup/test + 补丁说明） |
| `data/` | 外置数据表（图片目录映射、语音映射、密钥默认凭据等） |
| `keys/testkey.jks` | AOSP 官方通用测试密钥（不填密钥时使用；别名/密码均为 `testkey`） |
| `enums_ext.txt` | 额外枚举值（格式 `类别:值`，可自行扩充） |
| `LICENSE.ManifestEditor` | 第三方许可 |

依赖：Python 3.13+，**无第三方库**（PNG 尺寸用标准库解析）。

## 打包 GUI 三步

① **解压并校验**：选 MOD 工程（zip/文件夹）+ 基准 APK → 解压、对照基准校验（缺资源从基准兜底），输出校验报告.txt
② **扫描未引用文件**：mod.txt 引用闭包之外的文件列出来，勾选剔除
③ **打包任务**：任意多个 zip / APK 任务（各自可设包名、versionCode、versionName）；自动改图标、多语言应用名（resources.arsc 全语言）、同步权限与 provider authority，最后 zipalign + apksigner 签名并验证

所有界面输入都会持久化到工具目录 `setting.txt`（下次启动自动恢复）。

## 命令行用法

```bash
# 校验（对照原版基准，0 ERROR 才交付）
python ff.py check <MOD根目录> [--strict]

# 克隆原版单位 → 新单位（自动登记装备表、打印美工任务单）
python ff.py clone "German-Panther Ausf G" "German-Leopard 2A7" \
    --out <MOD根目录> --nation german \
    --long "Leopard 2A7" --short "Leo 2A7" \
    --avail "1991-01:200,1995-06:400"

# 新武器骨架
python ff.py weapon WEAPON_CANNON_120_RH120_L55 --cls CANNON \
    --name "Rheinmetall 120mm L/55" --modern --country GERMANY --calibre 120

# 检索原版单位 / 查看摘要 / 美工任务单
python ff.py list --query leopard
python ff.py info "German-Panther Ausf G"
python ff.py assets "German-Leopard 2A7"
```

## 原版参考数据（校验兜底用）

工具按以下顺序自动定位原版 12.2.0 数据：

1. 环境变量 `FIREFIGHT_REF`
2. 工作区 `ref/*/`（内含 `Data/Infantry` 的目录）
3. 也可用 `--ref` 显式指定

## 关键规格

- 单位图 1m = 16px；地图 1m = 8px
- 侧视剪影固定尺寸：车辆/火炮 256×128，机枪/迫击炮 132×110
- 数据文件：Tab 缩进、`//` 注释；UTF-8 / cp1252 自动嗅探
- equipment 清单由 `mod.txt` 的 `<equipment>` 引用，建议命名 `equipment_<小写国家>[_<时代>].txt`（时代 = WW1/WW2/modern）
- 签名：不填密钥 = AOSP testkey；apk 与原版包互相覆盖安装需同密钥（密钥不同时先卸载）
