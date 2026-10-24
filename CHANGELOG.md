# 更新日志

## 0.6.1（2026-10-24）

- 修复：管理员鉴权补齐主程序级操作员通道——`is_local_operator` 只标记 WebUI 控制台消息，QQ 侧操作员现按 bot_config `[plugin].permission`（`platform:id`）比对放行；命令解析依赖的 `text` / `is_local_operator` kwargs 已对照 Host 1.3.4 源码核实为实际下发（官方文档滞后）
- 修复：README 移除已废弃的配置继承说明（0.2.0 起 `[ob]` 全部手填）
- 插件类型改为 `management`（管理/权限类插件）
- manifest 新增 `config.get` 能力声明（读取主程序操作员配置）

## 0.6.0（2026-10-24）

- 新增：删好友后转告管理员（`block.notify_admin_on_remove`，默认开启）
- 仓库整理：`config.example.toml` 配置示例、`.gitignore`、`LICENSE`、本更新日志

## 0.5.0（2026-10-24）

- 新增：屏蔽提示文案可自定义模板（`block.blocked_tip_template`，占位符 `{user}` / `{duration}`），留空回退默认
- 修复：屏蔽到期时间截断到秒导致短时长屏蔽立即过期的精度问题（统一微秒精度）

## 0.4.0（2026-10-24）

- 新增：群聊屏蔽时长上限（`block.max_duration_hours`，默认一天，到期自动解除；`block_user` 可指定更短时长，被钳制在上限内；0 = 不限制）
- `/block list` 显示每条屏蔽的到期时间；后台每 5 分钟清扫到期记录；旧库自动迁移 `expires_at` 列

## 0.3.0（2026-10-24）

- 工具作用域收紧：`block_user` / `unblock_user` 仅群聊（屏蔽本群），`remove_friend` 仅私聊
- 新增：屏蔽成功后向当前会话发送提示（`block.notify_blocked_user` + `blocked_tip_template` 前身）

## 0.2.0（2026-10-24）

- 移除 snowluma-adapter 配置自动继承，OneBot 连接改为用户手动填写（`[ob]` server/port/token）

## 0.1.0（2026-10-24）

- 首个版本：好友申请审批（LLM 自动 / 管理员人工 / 混合三种模式）、用户屏蔽（发言拦截、私聊删好友）、管理命令 `/fr` 与 `/block`
- 自建 OneBot v11 正向 WebSocket 直连 NapCat / SnowLuma 对端，不修改任何适配器
