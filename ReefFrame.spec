# Build with: pyinstaller --clean --noconfirm ReefFrame.spec
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'src/main.py')], pathex=[str(root / 'src')],
             datas=[(str(root / 'src/config/defaults'), 'config/defaults'),
                    (str(root / 'src/resources/reefframe.png'), 'resources')],
             hiddenimports=['gui.dialogs.' + name + '_dialog' for name in
                            ('convert', 'dehaze', 'enhance', 'reduce', 'gif', 'snapshot', 'stabilise')]
                           + ['processing.' + name for name in
                              ('convert', 'dehaze', 'enhance', 'reduce', 'gif', 'snapshot', 'stabilise')])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ReefFrame', console=False)
collection = COLLECT(exe, a.binaries, a.datas, name='ReefFrame')
app = BUNDLE(collection, name='ReefFrame.app', icon=str(root / 'assets/icons/reefframe.icns'),
             bundle_identifier='org.reefframe.desktop',
             info_plist={'NSHighResolutionCapable': True, 'CFBundleShortVersionString': '1.0.0'})
