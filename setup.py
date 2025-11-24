from setuptools import setup

APP = ['bot-vinted.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'packages': ['tkinter', 'PIL', 'requests', 'selenium', 'webdriver_manager'],
    'iconfile': 'robot_ico.icns',  # icône à utiliser
    'includes': ['pkg_resources'],
    'plist': {
        'CFBundleName': 'VintedBot',
        'CFBundleDisplayName': 'VintedBot',
        'CFBundleIdentifier': 'com.ovilamanche.vintedbot',
        'CFBundleVersion': '1.0',
        'CFBundleShortVersionString': '1.0',
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
