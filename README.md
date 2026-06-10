# 局域网课堂举手互动工具

## 项目介绍

这是一个面向固定教室、机房和培训课堂的 Windows 桌面互动工具。老师端在局域网内作为服务端运行，学生端作为客户端连接课堂；整个流程不需要公网、不需要云服务器，也不要求学生打开浏览器。

项目重点解决课堂里几个高频问题：学生可以低摩擦举手、反馈“讲慢一点 / 我没听懂”、提交不懂点截图；老师端可以看到匿名弹窗提醒、举手队列、反馈统计和问题收件箱，并能直接回复学生。适合需要本地部署、长期固定使用、希望课堂数据留在本机的教学场景。

当前版本支持举手、取消举手、快捷反馈、文字提问、截图图片上传、老师回复、单实例防多开、窗口居中打开和本地课堂记录归档。

## 功能

- 老师端：在线学生、举手队列、反馈统计、问题收件箱、截图预览、回复学生、匿名弹窗提醒、课堂设置保存、新班级一键清空、课堂记录本地保存。
- 学生端：自动发现课堂、手动输入老师 IP、自动记住姓名和连接信息、举手、取消举手、快捷反馈、上传不懂点文字和截图图片、查看老师回复。
- 启动保护：教师端和学生端都禁止多开，重复打开会用中文提示并退出，避免重复连接或端口冲突。
- 网络：TCP 长度前缀 JSON 协议传输课堂事件，UDP 广播用于局域网自动发现。
- 数据：老师端保存到 `data/class_sessions/<session_id>/`。

完整操作流程请看：[完整使用说明](docs/完整使用说明.md)。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m classroom_hand_raise.teacher.app
python -m classroom_hand_raise.student.app
```

如果只验证核心逻辑，不需要安装 PySide6：

```powershell
python -m unittest discover -s tests
python -m compileall classroom_hand_raise
```

安装依赖后，可用以下命令做桌面入口冒烟检查：

```powershell
python -m classroom_hand_raise.teacher.app --smoke-test
python -m classroom_hand_raise.student.app --smoke-test
```

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_teacher.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_student.ps1
```

如果当前系统禁止运行 PowerShell 脚本，也可以直接双击或执行 `scripts\build_teacher.cmd` 和 `scripts\build_student.cmd`。

打包输出：

- `dist\教师端\教师端.exe`
- `dist\学生端\学生端.exe`

打包后可检查入口能否加载：

```powershell
.\dist\教师端\教师端.exe --smoke-test
.\dist\学生端\学生端.exe --smoke-test
```

## 局域网使用提示

- 老师端先启动课堂，学生端再自动发现或手动输入老师端显示的“推荐连接地址”。
- 学生举手、重点反馈和提交不懂点会在老师端显示非阻塞匿名弹窗提醒；老师端管理界面可查看具体学生。
- 教师端和学生端都禁止多开；如果已经运行，再次双击会提示“已经在运行，请不要重复打开”。
- 同一台学生电脑重连会复用同一名学生记录；短暂断线会显示为离线，不会在老师端变成多个人。
- 学生端有互动频率限制：举手提问 10 秒冷却，课堂反馈 5 秒冷却，不懂点提交 30 秒冷却，用来防止误点和刷屏。
- 老师端可保存课堂名称和端口，下次打开会自动沿用上次设置。
- 换新班级时可点击“新班级清空”，系统会先把旧课堂记录自动归档为 zip，再清空当前课堂列表；课堂名称和端口设置会保留。
- 如果学生端无法发现老师端，优先尝试手动输入老师端显示的 IP 和端口。
- Windows 防火墙可能拦截 TCP/UDP 通信；首次运行时请选择允许局域网访问。
- 不支持任意文件上传，只支持文字说明和截图图片。学生可先用 Windows 截图工具、QQ/微信截图等方式截图，再在学生端选择图片或粘贴发送。
- 老师回复会推送到在线学生端；学生临时离线时，使用同一台电脑重连后会补收本课堂未读回复。

## 课堂试用建议

上课前用 3-5 台学生电脑试一次：老师端保存设置、新班级清空并生成归档 zip、自动发现、手动 IP、举手提问、匿名提醒、反馈、文字不懂点、截图图片上传、老师回复、学生查看回复、老师端标记已处理和导出课堂记录。确认这些都正常后再用于正式课堂。
