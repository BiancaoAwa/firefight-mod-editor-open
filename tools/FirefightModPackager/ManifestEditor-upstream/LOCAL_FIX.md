# 本地补丁说明

来源: https://github.com/ohyeah521/ManifestEditor （MIT License，master 分支，2026-09-26 拉取）

相对官方 master 仅一处修改（见 LOCAL_FIX_StringChunk.py，已应用到上游包目录 ManifestEditor/StringChunk.py）：
`StringChunk.modify` 修改字符串池条目后同步更新内存中的 `string_value_arr[index]`。

原因: `uses-permission` 与 `permission` 等多个标签可能引用同一条去重后的池字符串，
官方实现第二次 modify 会用过期的旧长度重新拼接，导致字符串池偏移错位、NUL 结尾丢失
（aapt 报 `Bad string block: string #N is not null-terminated`），manifest 损坏无法安装。
同步后第二次调用命中 `old_str == new_str` 直接早退。
