# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\convo_backend\\app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ("src/convo_backend/assets/default_prompt.txt", "./assets"),
        ("src/convo_backend/assets/choose_space_prompt.txt", "./assets"),
        (".env", "."),
        ("google-credentials-2.json", "."),
        (".venv/Lib/site-packages/silero_vad/data", "silero_vad/data"),
        ("src/convo_backend/assets/convo.ico", "./assets"),
        ("src/convo_backend/models/classifier.onnx", "./models"),
        ("src/convo_backend/assets/filler_prompt.txt", "./assets")
    ],
    hiddenimports=[
        'pydantic.deprecated.decorator',
        'pydantic.deprecated',
        'pydantic.json',
        'langchain_core',
        'langchain_community',
        'silero_vad',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Convo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="src/convo_backend/assets/convo.ico"
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='app',
)
