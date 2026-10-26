# Claude Desktop 简体中文精简补丁

**面向 Windows 第三方 API / Claude-3p（含 DeepSeek 网关）模式的最小、可逆中文界面补丁。**

> 非官方社区项目，不隶属于 Anthropic。本仓库不包含 Claude 官方软件、你的账号、API Key、聊天数据或网关配置。请先阅读下面的版本范围和风险说明。

## 为何做这个项目

某些 Claude Desktop Windows 第三方 API 模式没有可选的简体中文；传统汉化脚本可能一次修改大量前端 bundle，升级后容易不兼容。这里按 **只改 1 个语言白名单 JS 文件 + 添加中文资源 + 定点修改 locale** 的思路，把可观察的修改范围降到最小。

在一台 Windows 电脑上，针对 **Claude MSIX 包版本 `3.1623.0.0`**（包内 `app/version` 曾显示 `44.9.0`）完成了实际中文 UI / 第三方 DeepSeek 对话验证（2026-10-26）。同一次验证中，原始 JS 恢复文件 SHA-256 为 `87400e6f593dff3c6aef0177b575da988212210f9ba4eea4652e87e5a55cb8d6`。

**支持范围严格限定到这一个实测构建。** 检测到其他版本、不同 JS 哈希或无法定位唯一白名单时，安装器直接停止，不尝试猜测。如果 Claude 自动更新（实测后该电脑已经出现 `3.6556.2.0`），请不要把旧补丁套到新版本上。

## 设计边界

- 只在本机运行，无遥测、无网络上传；脚本不会触碰 DeepSeek API 地址或模型别名。
- 不修改 `Claude.exe`、`app.asar`、系统代理、Cowork/Code 配置或自动更新开关。
- 安装前验证 Claude 安装包版本、JS 原始 SHA-256、白名单锚点和已有语言文件。
- 只修改一个 JS 白名单；英文缺少中文译文的字段，使用本机安装的英文资源兜底。
- 备份原始 JS 和旧 `locale` 值；卸载只恢复这些改动。
- 严格禁止对已被其他程序修改的目标文件“盲目覆盖”；无法安全恢复时停止并保留备份。
- 资源修改属于非官方行为，**不能保证微软商店签名、升级或 Cowork 在所有设备上正常**。应用更新时应优先使用官方原版。

## 运行要求

Windows 10/11、Python 3.10+、已经安装的 Claude Desktop MSIX **`3.1623.0.0`**。支持简体中文 `zh-CN`；暂不支持 macOS/Linux、其他语言、便携版以及其他 Claude 构建。修改安装目录时可能出现 Windows UAC 管理员确认；如果受 MSIX 权限保护而写入失败，应停止，不要强行更改系统目录所有权。

## 使用方法

1. 下载本仓库 ZIP 并解压。不要从未知渠道单独下载 `.bat` 或 `.ps1` 文件。
2. **先完全退出 Claude Desktop，包括系统托盘后台进程**。保存未完成的任务。
3. 双击 `status-windows.cmd` 检查支持情况；若提示版本不支持，不要继续。
4. 双击 `install-windows.cmd`，按 Windows UAC 提示操作。成功后从开始菜单启动 Claude。
5. 在 Claude 第三方 API 模式的语言设置里确认中文界面，再验证你自己的网关和模型是否正常回复。
6. 恢复原版时先退出 Claude，再运行 `uninstall-windows.cmd`。原始文件备份保留在 `%LOCALAPPDATA%\ClaudeZhMinimal\` 下。

也可以在命令行运行：

```powershell
python src/claude_zh.py status
python src/claude_zh.py install
python src/claude_zh.py uninstall
```

`install` 和 `uninstall` 会在非管理员状态下请求 Windows UAC；`status` 是只读检查。自动回滚仅处理本工具的修改，**不会卸载 Claude 原软件**。如果你已经使用其他汉化工具修改了 Claude，请先用原工具恢复，不要覆盖安装。

## 备份 / 升级 / 故障

- 安装前会在 `%LOCALAPPDATA%\ClaudeZhMinimal\` 生成私有 manifest 和原始 JS 备份。**不得将此目录上传到 GitHub**。
- 升级 Claude 前建议先卸载补丁。如果应用已经升级，安装器将拒绝把旧 JS 恢复到新版本。
- 若此前安装过旧汉化工具，必须用旧工具恢复其原始文件后才能安装。这个精简工具不是其他项目补丁的通用卸载器。
- 若出现“此页面出现问题”、空白页或应用不能启动：停止重新安装；保留备份，检查当前 Claude 版本和安装日志，并优先从官方安装包恢复。
- 该补丁没有第三方模型合法性、网络连通性或服务可用性的保证。

## 开发测试

```powershell
python -m unittest discover -s tests -v
```

测试只使用临时目录和模拟 JS，不会对真实 Claude 安装进行写入。代码不依赖第三方 Python 包。

## 开源许可和致谢

安装器代码采用 [MIT License](LICENSE)。中文翻译文件来自 [javaht/claude-desktop-zh-cn](https://github.com/javaht/claude-desktop-zh-cn) 的 MIT 授权翻译资源（本地来源包 `1.4.12`），原作者版权声明保存在 [licenses/javaht-MIT.txt](licenses/javaht-MIT.txt)。详见 [NOTICE.md](NOTICE.md)。

**未上传**任何 Anthropic 原版程序文件、英文词表、修改后的 `.js`、API Token、个人日志或真实用户截图。中文词表在安装时与用户本机的官方英文词表合并。

## 免责声明

此项目仅为社区学习和兼容性尝试，未经 Anthropic 认可。请勿将“支持一个实测版本”理解为对所有 Claude 版本的适配保证。任何新版本必须经静态校验和独立测试后才能添加到白名单。
