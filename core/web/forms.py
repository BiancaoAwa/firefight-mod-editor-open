"""The forms the interface offers for the writing commands.

A form is declared next to the command it drives, in one place; the command registry
says which commands are writing ones, and the page builds its controls from here.
"""

from core import registry
from core.web.i18n import tr


class Operation:
    """One writing command as the UI offers it: what it does and what it asks for."""

    __slots__ = ("command", "title", "selector", "note", "fields")

    def __init__(self, command: str, title: str, selector: str, note: str, fields: tuple) -> None:
        self.command = command
        self.title = title
        self.selector = selector
        self.note = note
        self.fields = fields


def _declared() -> tuple:
    """Every writing command, with the form the UI shows for it.

    Built per request so each label goes through the language in force. A field is
    ``(option, label, kind, default)``; the kinds are ``text``, ``check`` and
    ``select:<value>|<value>``, where an empty value is the default choice.
    """
    return (
        Operation(
            "set",
            tr("改字段"),
            tr("文档"),
            tr("改一个字段的值；数组或表条目用「数组动作」追加或删除。"),
            (
                ("field", tr("字段路径"), "text", ""),
                ("value", tr("新值"), "text", ""),
                ("op", tr("数组动作"), "select:|append|delete", ""),
                ("from", tr("新值取自文档字段"), "text", ""),
            ),
        ),
        Operation(
            "batch",
            tr("批量修改"),
            tr("补丁文件"),
            tr("按补丁文件一次改多份文档；任一条被拒则整批不写。"),
            (),
        ),
        Operation(
            "add",
            tr("新建文档"),
            tr("新文档路径"),
            tr("按 schema 建一份骨架；填「复制来源」则复制那份文档。"),
            (("from", tr("复制来源"), "text", ""),),
        ),
        Operation(
            "clone",
            tr("复制文档"),
            tr("源文档"),
            tr("以新 token 复制一份文档；源可写成 作用域:路径 借原版数据。"),
            (
                ("as", tr("新 token"), "text", ""),
                ("into", tr("目标作用域或目录"), "text", ""),
            ),
        ),
        Operation("remove", tr("删除文档"), tr("文档"), tr("把一份文档从工程里删掉；撤销会把它放回。"), ()),
        Operation("index", tr("建索引"), "", tr("重建 EditorCache/index.toml 与 refs.toml。"), ()),
        Operation(
            "convert",
            tr("转换原版数据"),
            "",
            tr("把当前作用域的数据转成工程文档；assets=1 时连 Images/ 与 Sounds/ 一起复制。"),
            (
                ("to", tr("目标目录"), "text", ""),
                ("type", tr("存储形态"), "select:|toml|txt", ""),
                ("assets", tr("一并复制素材"), "check", ""),
                ("overwrite", tr("覆盖已有文件"), "check", ""),
            ),
        ),
        Operation(
            "settings",
            tr("工程设置"),
            "",
            tr("render 读 Mod/mod.txt 写 ModSetting.toml；emit 反向写回原版文件。"),
            (
                ("op", tr("方向"), "select:render|emit", "render"),
                ("overwrite", tr("覆盖已有文件"), "check", ""),
            ),
        ),
        Operation(
            "roster",
            tr("清单"),
            tr("单位表"),
            tr("列出工程声明的清单；给「清单动作」则增、改或删条目。"),
            (
                ("op", tr("清单动作"), "select:|add|set|remove", ""),
                ("section", tr("组或注记"), "text", ""),
                ("value", tr("条目"), "text", ""),
                ("line", tr("行号"), "text", ""),
                ("as", tr("新条目"), "text", ""),
            ),
        ),
        Operation(
            "export",
            tr("导出文档"),
            "",
            tr("把工程里的文档按工程相对路径导出到目录；overwrite=0 跳过已存在的文件。"),
            (
                ("to", tr("目标目录"), "text", ""),
                ("overwrite", tr("覆盖已有文件"), "check", ""),
            ),
        ),
        Operation(
            "pack",
            tr("打包"),
            "",
            tr("打成可安装的 zip；strict=1 时加载错误与悬空引用会拒绝写入。"),
            (
                ("to", tr("目标目录"), "text", ""),
                ("strict", tr("严格模式"), "check", ""),
                ("overwrite", tr("覆盖已有归档"), "check", ""),
            ),
        ),
        Operation("init", tr("新建工程"), "", tr("把当前目录建成一个模组工程。"), (("name", tr("工程名"), "text", ""),)),
        Operation(
            "build",
            tr("构建"),
            "",
            tr("依次索引、检查、打包，任一步失败即停。"),
            (("to", tr("打包到目录"), "text", ""),),
        ),
        Operation(
            "adopt",
            tr("收编"),
            tr("来源目录或 zip"),
            tr("由既有模组建成工程并建索引，源目录不改。"),
            (("to", tr("目标目录"), "text", ""), ("overwrite", tr("覆盖已有工程"), "check", "")),
        ),
        Operation(
            "unpack",
            tr("还原原版"),
            "",
            tr("把工程写回原版 XML 与文本，工程带 mod.txt 时先刷新它。"),
            (("to", tr("导出到目录"), "text", ""), ("overwrite", tr("覆盖已有文件"), "check", "")),
        ),
        Operation(
            "run",
            tr("按步运行"),
            tr("步骤文件"),
            tr("按文件列出的顺序逐条运行，任一步失败即停。"),
            (),
        ),
        Operation(
            "import",
            tr("导入工程"),
            tr("来源目录或 zip"),
            tr("由既有模组建成工程；素材与 mod.txt 一并带入，目标已有工程时需覆盖。"),
            (
                ("to", tr("目标目录"), "text", ""),
                ("overwrite", tr("覆盖已有工程"), "check", ""),
            ),
        ),
        Operation("undo", tr("撤销"), tr("条数"), tr("把最近几次写入换回原来的字节；条数是文档参数，不是选项。"), ()),
        Operation("redo", tr("重做"), tr("条数"), tr("重新应用最近撤销掉的写入；条数是文档参数，不是选项。"), ()),
    )


def operation_options(operation: Operation, query: dict) -> dict:
    """The options a query asks for; a blank control means the option is not sent."""
    options = {}
    for name, _label, kind, _default in operation.fields:
        raw = query.get(name, "")
        if kind == "check":
            if raw in ("1", "yes", "true"):
                options[name] = "1"
        elif raw.strip():
            options[name] = raw.strip()
    return options

def operations() -> tuple:
    """The declared forms, ordered as the registry orders the commands.

    A command that writes but declares no form, or a form whose command is not a
    writing one, stops the page: the two tables have to stay in step.
    """
    declared = {operation.command: operation for operation in _declared()}
    writing = [command.name for command in registry.commands() if command.writes]
    missing = [name for name in writing if name not in declared]
    extra = [name for name in declared if name not in writing]
    if missing or extra:
        raise ValueError(
            f"writing forms out of step with the registry: missing={missing} extra={extra}"
        )
    return tuple(declared[name] for name in writing)
