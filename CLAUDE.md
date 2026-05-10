# 番茄钟计时器

## 项目说明

Windows 桌面番茄钟应用，使用 customtkinter 构建，支持三种模式（专注/短休息/长休息）、壁纸自定义、桌面通知。

## 编码规范

- 类名使用帕斯卡命名法（`PomodoroTimer`, `PomodoroApp`）
- 变量/方法使用蛇形命名法（`_load_wallpaper`, `session_count`）
- 常量全大写加下划线（`CONFIG_DIR`, `THEME_COLORS`）
- 私有方法/属性前缀 `_`（`_tick`, `_timer`）
- 所有 `def` 和 `class` 前必须有功能描述（`"""docstring"""`），说明做什么、参数含义、返回值
- 注释只写 WHY（隐藏约束、变通方案），不写 WHAT
- 导入顺序：标准库 → 第三方库 → 本地模块，每组空行分隔

## 技术栈

- Python 3.12+
- customtkinter — GUI 框架
- PIL/Pillow — 图片加载与缩放
- plyer — 系统桌面通知
- winsound — 提示音

## 架构约定

当前为单文件 `pomodoro.pyw`，逻辑分层：
- 模块顶部：常量与配置（`CONFIG_DIR`, `THEME_COLORS`, `MODE_*`）
- 工具函数：`_read_json`, `_write_json`
- `Settings`：JSON 持久化，dict 接口
- `PomodoroTimer`：倒计时核心，独立于 UI 线程
- `PomodoroApp`：主窗口，Canvas 渲染 + CTk 控件
- `SettingsDialog`：设置弹窗

## 壁纸系统

- 壁纸存储在 `bg_canvas`（tk.Canvas）上，非 CTkLabel
- 叠加层（overlay）使用 stipple 实现半透明暗色遮罩
- 进度圆弧和文字直接画在 bg_canvas 上，无容器遮挡
- 每个模式可独立设置壁纸

## Git 与 GitHub

- 主分支：`main`
- 推送需设置 `HTTPS_PROXY=http://127.0.0.1:7897`
- 仓库：https://github.com/779028472/pomodoro-timer
