# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform one-folder bundle for Windows and macOS."""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, copy_metadata


project_root = os.path.dirname(os.path.abspath(SPECPATH))
version = os.environ.get("LEXPILOT_VERSION", "0.1.0-dev")
bundle_version = version.split("-", 1)[0]
streamlit_datas = collect_data_files("streamlit") + copy_metadata("streamlit")

datas = streamlit_datas + [
    (os.path.join(project_root, "app.py"), "."),
    (os.path.join(project_root, "static"), "static"),
    (os.path.join(project_root, ".streamlit"), ".streamlit"),
    (os.path.join(project_root, "backend", "legal_domain", "labor", "*.yaml"), "backend/legal_domain/labor"),
    (os.path.join(project_root, "datasets", "synthetic_cases"), "datasets/synthetic_cases"),
    (os.path.join(project_root, "data"), "data"),
    (os.path.join(project_root, "LICENSE"), "."),
    (os.path.join(project_root, "desktop", "首次打开说明.txt"), "."),
]

hiddenimports = [
    "backend.config",
    "backend.graph",
    "backend.legal_domain.consultation.profiles",
    "backend.legal_domain.consultation.reporting",
    "backend.legal_domain.consultation.service",
    "backend.legal_domain.labor.evidence_upload",
    "backend.legal_domain.labor.facts",
    "backend.legal_rl.actions",
    "backend.legal_rl.state",
    "consultation_workspace",
    "evidence_constellation",
    "frontend_experience",
    "fitz",
    "PIL",
    "docx",
    "openpyxl",
]

a = Analysis(
    [os.path.join(project_root, "desktop", "launcher.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "transformers",
        "sentence_transformers",
        "chromadb",
        "ragas",
        "gymnasium",
        "backend.legal_rl.dqn",
        "backend.legal_rl.environment",
        "backend.legal_rl.train",
        "langgraph",
        "langchain",
        "langchain_openai",
        "langchain_community",
        "langchain_classic",
        "langsmith",
        "opentelemetry",
        "grpc",
        "datasets",
        "huggingface_hub",
        "scipy",
        "sklearn",
        "matplotlib",
        "pytest",
        "IPython",
        "notebook",
        "jupyter",
        "tensorflow",
        "keras",
        "cv2",
        "plotly",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LexPilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="LexPilot",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="LexPilot.app",
        icon=None,
        bundle_identifier="com.lexpilot.desktop",
        version=bundle_version,
        info_plist={
            "CFBundleDisplayName": "LexPilot 律策",
            "CFBundleName": "LexPilot",
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSHighResolutionCapable": True,
        },
    )
