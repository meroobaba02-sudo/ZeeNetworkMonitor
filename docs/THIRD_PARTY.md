# Third-party software

This source code's MIT license does not replace third-party license terms.

- Python: PSF license, https://docs.python.org/3/license.html
- PySide6 / Qt for Python / Shiboken6: Qt Project, LGPLv3/GPLv3/commercial options; this build uses the available open-source components. https://www.qt.io/licensing/open-source-lgpl-obligations and https://code.qt.io/cgit/pyside/pyside-setup.git/
- Qt: module-dependent licenses; only desktop Core/Gui/Widgets and platform dependencies are needed. https://code.qt.io/cgit/qt/
- PyInstaller: GPLv2 with bootloader distribution exception, https://pyinstaller.org/en/stable/license.html

Portable folder packaging retains separate runtime libraries. Distributing a public/commercial release requires preserving the applicable notices and complying with each dependency's terms. Tests/pytest are build-time only. This package is an initial personal monitoring release, not a signed commercial installer.


Map data © OpenStreetMap contributors, licensed ODbL 1.0. https://www.openstreetmap.org/copyright and https://opendatacommons.org/licenses/odbl/1-0/ . Road/river/place data fetched from Overpass; no raster tiles downloaded.
