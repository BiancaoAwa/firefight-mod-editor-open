# 变更记录

本文件按时间倒序记录值得说明的变更，格式参照
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/)；版本号采语义化版本，
只写在 `core/__init__.py` 一处。

## [0.1.0] — 尚未发布

### 新增

* 编辑器命令行：22 条命令，作用于两个作用域——`Firefight` 为游戏自带数据，任意命名目录为模组工程。
  `init`、`list`、`show`、`get`、`find`、`stats`、`refs`、`deps`、`check`、`set`、`add`、`remove`、
  `index`、`convert`、`settings`、`export`、`pack`、`log`、`undo`、`redo`、`version`、`web`。
  每条都接受 `--json`。
* Web 界面：只绑定回环地址，提供中英两种语言与语言切换，命令与命令行的命令、闸门一致
  （docs/web.zh-CN.md）。写入这一侧由三个页面承担：`/edit` 列出一个文档的全部字段并给每行一个输入框，
  `/ops` 把十一条写入命令各做成表单，并在给出写入链接前先以 `--write --dry-run` 跑一遍，
  `/log` 显示事件日志并带撤销与重做表单。
* MCP 服务：支持两个协议族，暴露 19 个工具，其中 8 个只读；会写入的工具只在 `--write` 下注册
  （docs/mcp.zh-CN.md）。
* `pack`：生成可安装的模组归档 `<名称>-<版本>.zip`，内含 `Mod/` 前缀，工程文档回写成原版 XML，
  工程的 `ModSetting.toml` 渲染成 `Mod/mod.txt`，`EditorCache/` 不入包。成员时间戳固定，
  因此同一工程两次打包字节相同。渲染失败的文档会被报告并略过，`strict=1` 则直接拒绝。
* `init`：从零创建工程——`ModInformation.toml` 与空的 `Data/`。
* `convert`：把某作用域的原版 `.txt` 文档转成目标工程下的工作用 `.toml`；`assets=1` 另把该作用域的
  `Images/` 与 `Sounds/` 两棵树逐字节复制过去。
* `settings`：在工程的 `mod.txt` 与 `ModSetting.toml` 之间双向转换（`op=render`、`op=emit`）。
* `index`：把文档清单与引用表缓存到 `EditorCache/` 下；`refs` 与 `deps` 在指纹仍然新鲜时读缓存，
  不新鲜时重新遍历文档。
* 撤销日志：每次写入追加一条记录，保存写入前后的字节。`log` 列出记录，可按文档、字段、执行者、
  结果或时间过滤；`undo` 与 `redo` 依据记录恢复。`log`、`undo`、`redo` 都接受 `--dry-run`。
* `set` 支持数组与表条目的增删（`op=append`、`op=delete`），`add` 与 `remove` 以整份文档为单位增删。

### 变更

* 用户可见文本统一为英文。Web 界面对 268 条模板提供中文译文，并提供 `lang=zh|en` 切换。
* `export` 默认替换已存在的文件，`overwrite=0` 才跳过；`convert` 与 `settings` 默认跳过已存在的目标，
  `overwrite=1` 才替换。
* 工程的纯文本表格以设置为准：设置里 `<equipment>`、`<surnames>` 点名的文件无论内容如何都算表格。
  没有设置文件的作用域仍退回 `equipment_*`／`surnames_*` 命名约定与无根元素的 `.txt`（docs/cli.zh-CN.md §4.3）。

### 已知限制

* `pack` 原样收录工程目录下的全部内容，外加工程根的 `README.md` 与 `LICENSE`；`Images/` 与
  `Sounds/` 只有在工程目录里已经存在时才进包（docs/cli.zh-CN.md §4.8）。
* 悬空引用由 `check` 报告、由 `pack` 计数，但没有任何命令去解决它们。

[0.1.0]: https://github.com/BiancaoAwa/firefight-mod-editor-open
