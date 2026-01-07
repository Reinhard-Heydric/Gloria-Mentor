# -*- mode: python ; coding: utf-8 -*-
import platform
from PyInstaller.utils.hooks import collect_submodules

# 全平台禁用签名配置
universal_disable_sign = {
    'codesign_identity': None,
    'entitlements_file': None,
    'signing_requirements': '',
    'exclude_binaries': True
}

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config/settings_template.json', 'config'),
        ('config/locales.json', 'config'),
        ('static', 'static'),
        ('vrm', 'vrm'),
        ('tiktoken_cache', 'tiktoken_cache')
    ],
    hiddenimports=[
        'pydantic.deprecated.decorator',
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
        'botpy',
        *collect_submodules('mem0'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# 修改基础配置
base_exe_config = {
    'debug': False,
    'strip': False,
    'upx': True,
    'bootloader_ignore_signals': False,
    'disable_windowed_traceback': False,
    **universal_disable_sign
}

if platform.system() == 'Darwin':
    # macOS 特殊配置
    exe = EXE(
        pyz,
        a.scripts,
        [],
        name='server',
        argv_emulation=True,
        icon='static/source/icon.png',
        **base_exe_config
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        name='server',
        upx_exclude=[],
        **universal_disable_sign
    )
    # macOS 专用 .app 配置
    app = BUNDLE(
        coll,
        name='server.app',
        icon='static/source/icon.png',
        bundle_identifier='com.superagent.party',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'True',
            'NSAppleScriptEnabled': 'NO'
        },
        **universal_disable_sign
    )
elif platform.system() == 'Windows':
    # Windows 特殊配置
    exe = EXE(
        pyz,
        a.scripts,
        [],
        name='server',
        icon='static/source/icon.ico',  # 使用 .ico 格式图标
        **base_exe_config
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        name='server',
        upx_exclude=[],
        **universal_disable_sign
    )
else:
    # Linux 配置
    exe = EXE(
        pyz,
        a.scripts,
        [],
        name='server',
        **base_exe_config
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        name='server',
        upx_exclude=[],
        **universal_disable_sign
    )
