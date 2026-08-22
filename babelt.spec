# -*- mode: python ; coding: utf-8 -*-
"""Empacotamento do babelt com PyInstaller.

    pyinstaller babelt.spec

As tabelas editáveis (extensions.txt, headers.txt, glossary.txt,
literals.txt, function_words.txt) são lidas em
tempo de execução com `Path(__file__).parent`, então precisam viajar junto e
no mesmo lugar relativo — daí `datas`.

O modelo NMT **não** é embutido: são 230 MB e licença própria. O binário o
baixa na primeira execução, para `~/.local/share/babelt`.

torch e transformers só existem para converter o modelo. Excluí-los tira
centenas de MB do binário.
"""

from PyInstaller.utils.hooks import collect_dynamic_libs

datas = [
    ("babelt/extensions.txt", "babelt"),
    ("babelt/headers.txt", "babelt"),
    ("babelt/glossary.txt", "babelt"),
    ("babelt/literals.txt", "babelt"),
    ("babelt/function_words.txt", "babelt"),
]

# ctranslate2 carrega bibliotecas nativas que o analisador estático não vê.
binaries = collect_dynamic_libs("ctranslate2")

excludes = [
    "torch",
    "transformers",
    "tensorflow",
    "matplotlib",
    "IPython",
    "tkinter",
    "pytest",
    "setuptools",
]

a = Analysis(
    ["babelt/__main__.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["sentencepiece", "ctranslate2"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="babelt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
