# Build with: pyinstaller packaging/windows.spec
from pathlib import Path

project_root = Path(SPEC).parent.parent
src_dir = project_root / 'src'

a = Analysis(
    [str(src_dir / 'main.py')],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[],
    hiddenimports=['backends.windows'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['backends.linux_x11', 'backends.linux_wayland'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='afkclicker', console=True)
