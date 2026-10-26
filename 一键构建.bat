@echo off
chcp 65001 >nul
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist build mkdir build

echo [1/16] 复制基底
copy /Y "base\base_branded.exe" "build\base_v1100.exe" >nul || goto :error

echo [2/16] 写入 V1.2.0.3 版本信息
tools\py311\python.exe scripts\patch_version_info.py "build\base_v1100.exe" || goto :error

echo [3/16] 编译音效库
tools\py311\python.exe scripts\compile_sound_library.py || goto :error

echo [4/16] 编译界面模块
tools\py311\python.exe scripts\compile_ui.py || goto :error

echo [5/16] 生成内嵌 UI 识别模板
tools\py311\python.exe scripts\build_ui_templates.py || goto :error

echo [6/16] 模板得分评估
tools\py311\python.exe scripts\evaluate_ui_templates.py || goto :error

echo [7/16] 生成内嵌 UI 识别模块
tools\py311\python.exe scripts\patch_detector.py || goto :error

echo [8/16] 41 张源图识别回归
tools\py311\python.exe scripts\test_ui_recognition.py || goto :error

echo [9/16] 撤离流程状态机测试
tools\py311\python.exe scripts\test_extraction_flow.py || goto :error

echo [10/16] 默认快捷键补丁 F1
tools\py311\python.exe scripts\patch_monitor.py || goto :error

echo [11/16] 撤离 monitor 补丁
tools\py311\python.exe scripts\patch_monitor_extraction.py || goto :error

echo [12/16] 写入 monitor 脚本条目
tools\py311\python.exe scripts\patch_monitor_entry.py "build\base_v1100.exe" || goto :error

echo [13/16] 重排 PYZ
tools\py311\python.exe scripts\repack_pyz.py "build\base_v1100.exe" "build\_V1.2.0.3_full.exe" || goto :error

echo [14/16] 移除旧识别素材并校验
tools\py311\python.exe scripts\strip_embedded_assets.py "build\_V1.2.0.3_full.exe" "build\_V1.2.0.3_stripped.exe" || goto :error
tools\py311\python.exe scripts\validate_final.py "build\_V1.2.0.3_stripped.exe" || goto :error

echo [15/16] 生成中文发布名
tools\py311\python.exe scripts\finalize_release.py "build\_V1.2.0.3_stripped.exe" || goto :error

echo [16/16] 打包发布目录与 ZIP
tools\py311\python.exe scripts\package_release.py "build\从零开始的塔科夫生活_V1.2.0.3.exe" || goto :error

echo.
echo BUILD OK: build\从零开始的塔科夫生活_V1.2.0.3.exe
echo RELEASE: release\从零开始的塔科夫生活_V1.2.0.3.zip
pause
exit /b 0

:error
echo.
echo BUILD FAILED
pause
exit /b 1
