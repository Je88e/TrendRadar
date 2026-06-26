# coding=utf-8
"""
管理后台模块 - 调度器进程内嵌的在线配置后台。

提供配置编辑器静态资源 + /api/config/* 读写接口，支持在线编辑
config.yaml / frequency_words.txt / timeline.yaml 并保存即生效。

详见 docs/online-config-design.md 与 docs/adr/0004-online-config-admin.md。
"""
