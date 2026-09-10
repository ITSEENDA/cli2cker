# AFK Clicker

Cross-platform process clicker with saved target aliases and global hotkeys.

## Run from source

```text
python src/main.py
```

## Commands

```text
!profile create mc --path "..\\Minecraft\\javaw.exe"
!profile list
!pwd
!cd ..\\Minecraft
!ls
!task start mc
!task toggle mc
!task config mc --mode right-left --delay 0.5 --key space --safety strict
!task reset mc
!task status
!task stop mc

!hotkey create toggle-mc --keys alt+` --action "!task toggle mc"
!hotkey list
```

Relative target paths are resolved once when saved and stored as absolute paths.
Runtime task state is kept in memory; target profiles and hotkeys are persisted
in the platform user-data directory.

## Build

Install the platform dependencies first:

```text
pip install -r requirements.txt
pip install pyinstaller
```

Build with the platform spec:

```text
pyinstaller packaging/windows.spec
pyinstaller packaging/linux.spec
```

Windows uses `pywin32`. Linux uses the X11 backend when `DISPLAY` is available;
generic Wayland synthetic input is reported as unsupported.
