"""Package the release EXE into a user-facing folder and ZIP.

The build output is a single one-file EXE. This step adds the checksum,
short usage notes, release notes and the full project document, stages the
folder under dist, then packs the ZIP into release\\.
"""
import hashlib
import sys
import zipfile
from datetime import date
from pathlib import Path

VERSION = "1.4.1.0"
BASE = Path(__file__).resolve().parent.parent
EXE_NAME = f"从零开始的塔科夫生活_V{VERSION}.exe"
ICON_ROOT = BASE / "build" / "icons"
ICON_FILES = ("first_icon.ico", "killer_queen.ico", "itachi_mangekyo.ico")
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "build" / EXE_NAME
DIST = BASE / "dist"
RELEASE = BASE / "release"
STAGE = DIST / f"从零开始的塔科夫生活_V{VERSION}"
ZIP = RELEASE / f"从零开始的塔科夫生活_V{VERSION}.zip"
ZIP_HASH = RELEASE / f"从零开始的塔科夫生活_V{VERSION}.zip.sha256"

USAGE = """从零开始的塔科夫生活 V{version}（正式版）

运行环境
- Windows 10 / 11 64 位。
- 建议游戏使用窗口化或无边框窗口，保持 16:9 或 16:10。
- 支持 Windows 显示缩放；程序以 Per-Monitor DPI 感知运行，识别模板已用 2560×1440 实图回归。若游戏画面仍无法被识别，请提供诊断日志与 `startup.log`。
- 启动时若弹出管理员权限提示，请选择“是”。发送 Alt+F4 与自动按键需要管理员权限；如果在系统 UAC 窗口选择“否”，程序会继续以普通权限运行，不再自动关闭。
- 重复启动时会提示“工具已经运行”，已有副本保持运行；升级/提权交接失败时也不会把原窗口一起关掉。

快速上手
1. 双击 从零开始的塔科夫生活_V{version}.exe。
2. 进入游戏后按 F1 开启或关闭监控；快捷键可在界面中修改。测试模式默认关闭；开启测试模式并开始监控后，状态卡片的分数行会显示当前画面的判定得分与分项，画面顶部还会有独立得分浮窗。
3. 浮窗默认显示在主屏幕右上角，可显示当前界面编号，例如 TKF-7314-0、TKF-7314-A、TKF-7314-B、TKF-7314-Z、TKF-7314-M；测试模式监控中，编号浮窗下方会出现同款独立得分浮窗，尺寸比编号浮窗小一档，只显示 `SC <分值>`，停止监控后自动收起。
4. 撤离流程：
   - 识别到撤离点 TKF-7314-B：播放关闭提示音，立即暂停 Alt+F4，但继续检测。
   - 黑屏加载 TKF-7314-Z：继续保持暂停，不发送 Alt+F4。
   - 撤离结束 TKF-7314-M：保持暂停且不播放音效；3 秒后停止监控，浮窗变为 TKF-7314-0，此时只播放一次关闭提示音。
   - B 阶段浮窗会一直保持 TKF-7314-B，监控不会自动关闭；只有识别到 M 并等待 3 秒后才会停止。
   - 只是路过撤离点：B 消失且没有黑屏时仍保持暂停；回到战斗 HUD 并稳定 5 秒后恢复 Alt+F4，同时播放开启提示音。
5. “退出兜底”默认关闭。启用后它是 Alt+F4 之后的兜底：程序先发送 Alt+F4；等待设为 0 秒时不再观察，立即强制结束 EscapeFromTarkov.exe。此操作可能丢失战局进度，请确认后再使用。
6. 自动按键默认关闭、间隔 30 秒、按键 F2。启用后 HUD A 就绪会立即发送一次，之后每 30 秒发送一次；每次发送后计时重置回 30 秒。
7. 浮窗位置可在“进阶设置 → 浮窗位置”中调整，顺序为：关闭、居中上、居中下、左上、左下、右上、右下；选择“关闭”会隐藏浮窗，其余六锚点统一保留 18 px 屏幕边距，不按任务栏工作区收缩。
8. 在浮窗位置下拉框上滚动鼠标不会切换选项，也不会带动设置页滚动；必须展开下拉框后选择。
9. 发布包内的 `icons` 文件夹请与 EXE 保持在同一目录；切换退出音效时，窗口与托盘图标会同步切换为对应主题。

识别编号（与 ui识别 文件夹字母一致）
- A 战斗 HUD；B 撤离点；C 游戏主页/暂停；D 背包；E 总览；F 健康。
- G 技能；H 地图；I 任务；J 成就；K 控制台；L 三级菜单/设置。
- U 未知菜单/返回页签；Z 黑屏加载/撤离过渡；M 撤离结束/战局结束；0 未识别。
- “找到撤离点”横幅不参与识别，不会因此暂停 Alt+F4。

安全说明
- 程序只截取屏幕顶部条带做模板匹配，不读取游戏内存、不注入进程、不修改游戏文件。
- 强制结束只作用于 EscapeFromTarkov.exe。
- 识别依赖 UI 位置与缩放；大幅修改 HUD 缩放、分辨率或界面布局后，需要重新生成模板。

其他
- 浮窗默认位于主屏幕右上角，可在设置中移动或关闭；独占全屏仍可能遮挡置顶窗口，建议使用无边框窗口化。
- 诊断日志与截图选项位于“日志诊断”页，可通过“打开日志”查看。
- 启动诊断日志位于 `%LOCALAPPDATA%\\TarkovHUDMonitor\\startup.log`，遇到启动异常时请把这个文件一起反馈。
- 本版本使用 ui识别 文件夹中的 34 张 16:10 实机截图、16 张 2560×1440 实机截图、7 张过曝页签切片，以及“找到撤离点”黑名单横幅；内嵌 21 张识别模板。
""".format(version=VERSION)

NOTES = """# 更新说明 V{version}

## 版本号说明
- 按 `MAJOR.MINOR.PATCH.BUILD` 四段规则，本次修正底部锚点下的浮窗排列，属于向下兼容的问题修复，递增第 3 位 PATCH 并将 BUILD 归零：`1.4.0.0` → `1.4.1.0`。
- 程序内部版本、EXE 文件名、PE FileVersion / ProductVersion、界面关于行、ZIP 名与校验文件均统一为 `1.4.1.0`。

## 版本号规则
- 第 1 位 MAJOR：不兼容的重大变更，例如架构重写、旧存档/旧接口作废、玩家必须重开。
- 第 2 位 MINOR：向下兼容地新增功能，例如新地图、新系统、新功能。
- 第 3 位 PATCH：向下兼容地修复问题，例如修崩溃、调数值、修错别字。
- 第 4 位 BUILD：构建序号或热修复号，每次打包 +1，或单独发布紧急补丁。

## 本版改动
- 测试模式新增“当前画面得分读数”：开启测试模式并开始监控后，状态卡片的分数行会显示当前界面判定所依据的得分与分项。
- A 页显示战斗得分、人形轮廓与快捷栏分项；B 页显示撤离标题得分与绿色占比；C 页显示主页面得分。
- D–J 页显示页签得分与次高分；走亮度兜底时显示页签亮度（/255）与亮度差。
- K 页显示控制台得分；L 页显示设置得分；M 页显示撤离结束得分；U 页显示返回得分；Z 显示黑屏；0 显示无匹配，并附带战斗与最高页签得分，便于排查误判。
- 测试模式下分数行使用高亮色；普通模式的分数行保持原监控读数不变。为避免两路更新互相覆盖，界面不再直接绑定监控线程的分数变量，改由界面刷新统一渲染。
- 浮窗同步显示得分：测试模式监控中会出现第二个同款独立浮窗，字号与尺寸比编号浮窗小一档，只显示 `SC <分值>`；两个浮窗同步置顶，停止监控、关闭测试模式或关闭浮窗后得分浮窗自动收起。
- 得分浮窗跟随编号浮窗的锚点与颜色：A 页琥珀、B 页红色、安全页绿色、其他页面灰色；顶部锚点时编号浮窗在上、得分浮窗在下，底部锚点时得分浮窗在上、编号浮窗贴底，两个浮窗始终保留 6 px 间距；右侧锚点对齐右边缘，左侧锚点对齐左边缘，居中锚点各自居中。
- 识别模板、阈值、撤离状态机与按键行为均未改动。

## 保留能力
- 21 张内嵌识别模板、50 张图 + 7 条过曝条带回归、16 步构建链与三套主题图标机制不变。
- 撤离流程、Alt+F4 暂停/恢复、退出兜底与启动提权交接保持原行为。

## 构建与校验
- 版本资源：FileVersion / ProductVersion 与 `VS_FIXEDFILEINFO` 均为 `1.4.1.0`。
- 50 张源图全帧与条带路径回归、7 条过曝页签条带回归通过；撤离流程状态机测试通过；`--smoke-test` 退出码 0。
- 发布包结构：EXE、SHA256、使用说明、更新说明、项目说明与 `icons` 目录下三套 ICO。

发布日期：{date}
""".format(version=VERSION, date=date.today().isoformat())


def write_text(path, text):
    path.write_text(text, encoding="utf-8-sig", newline="\r\n")


def main():
    if not SRC.is_file():
        raise SystemExit(f"missing release exe: {SRC}")
    data = SRC.read_bytes()
    digest = hashlib.sha256(data).hexdigest().upper()

    stage = STAGE
    zip_path = ZIP
    zip_hash = ZIP_HASH
    RELEASE.mkdir(parents=True, exist_ok=True)
    try:
        stage.mkdir(parents=True, exist_ok=True)
        (stage / EXE_NAME).write_bytes(data)
    except PermissionError:
        # A running copy can lock the staged EXE.  Keep the user-facing ZIP
        # name stable and stage the new build in a sibling folder instead.
        stage = DIST / f"{STAGE.name}_new"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / EXE_NAME).write_bytes(data)
        print("staging EXE busy; using", stage)

    write_text(
        stage / "SHA256.txt",
        f"{digest}  {EXE_NAME}\n"
        f"size: {len(data)} bytes\n"
        f"version: {VERSION}\n"
        f"built: {date.today().isoformat()}\n",
    )
    write_text(stage / "使用说明.txt", USAGE)
    write_text(stage / f"更新说明_V{VERSION}.md", NOTES)

    project_doc = BASE / "项目说明.md"
    if project_doc.is_file():
        (stage / "项目说明.md").write_bytes(project_doc.read_bytes())

    icon_blobs = {}
    missing_icons = []
    for name in ICON_FILES:
        path = ICON_ROOT / name
        if path.is_file():
            icon_blobs[name] = path.read_bytes()
        else:
            missing_icons.append(str(path))
    if missing_icons:
        raise SystemExit("missing icon files: " + ", ".join(missing_icons))
    icon_stage = stage / "icons"
    icon_stage.mkdir(parents=True, exist_ok=True)
    for name, blob in icon_blobs.items():
        (icon_stage / name).write_bytes(blob)

    files = [
        EXE_NAME,
        "SHA256.txt",
        "使用说明.txt",
        f"更新说明_V{VERSION}.md",
        "项目说明.md",
    ] + [f"icons/{name}" for name in ICON_FILES]
    try:
        archive = zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        )
    except PermissionError:
        zip_path = RELEASE / f"{ZIP.stem}_new.zip"
        zip_hash = RELEASE / f"{zip_path.name}.sha256"
        archive = zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        )
        print("release ZIP busy; using", zip_path)
    with archive:
        for name in files:
            path = stage / name
            if not path.is_file():
                raise SystemExit(f"missing release file: {path}")
            archive.write(path, f"{STAGE.name}/{name}")

    zip_digest = hashlib.sha256(zip_path.read_bytes()).hexdigest().upper()
    zip_hash.write_text(
        f"{zip_digest}  {zip_path.name}\n",
        encoding="utf-8", newline="\r\n",
    )

    print("staged", stage)
    print("zip", zip_path)
    print("zip size", zip_path.stat().st_size)
    print("exe sha256", digest)
    print("zip sha256", zip_digest)


if __name__ == "__main__":
    main()
