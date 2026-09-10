# Build with: pyinstaller packaging/linux.spec
from pathlib import Path

project_root = Path(SPEC).parent.parent
src_dir = project_root / 'src'

a = Analysis(
    [str(src_dir / 'main.py')],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=['backends.linux_x11'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['backends.windows'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='afkclicker', console=True)
