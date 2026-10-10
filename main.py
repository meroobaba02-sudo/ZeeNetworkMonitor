import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import traceback
from PySide6.QtCore import QTimer, QLockFile
from PySide6.QtGui import QIcon,QPixmap,QColor,QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox,QSplashScreen
from zee.core import Store
from zee.gui import Window, STYLE


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--screenshot',type=Path)
    args=parser.parse_args()
    from PySide6.QtCore import Qt
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app=QApplication(sys.argv)
    from zee.licensing import branding
    app.setApplicationName(branding()['app_name'])
    app.setStyleSheet(STYLE)
    from zee.licensing import customer_profile
    profile=customer_profile();data_name='ZeeCustomer-'+profile['profile_id'] if profile else 'ZeeNetworkMonitor'
    base=args.data_dir or Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/data_name
    base.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(base/'app.lock'))
    if not lock.tryLock(100):
        QMessageBox.warning(None,'Already running','Zee Network Monitor is already using this data directory.')
        return 2
    handler=RotatingFileHandler(base/'diagnostic.log',maxBytes=1_000_000,backupCount=3,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    failures=[]
    def error_hook(kind,value,tb):
        failures.append(str(value))
        logging.error('Unhandled exception',exc_info=(kind,value,tb))
        if not args.smoke_test:
            QMessageBox.critical(None,'Application error','An operation failed. See diagnostic.log in the data folder.\n'+str(value))
    sys.excepthook=error_hook
    try:
        from zee.recovery import restore_pending
        restore_pending(base)
        from zee.customer_theme import splash_pixmap
        from zee.core import VERSION
        pix=splash_pixmap(VERSION,app.primaryScreen().devicePixelRatio(),branding());splash=QSplashScreen(pix);splash.show();app.processEvents()
        store=Store(base/'monitor.sqlite3')
        window=Window(store)
        assets=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'
        if (assets/'icon.png').exists():
            app.setWindowIcon(QIcon(str(assets/'icon.png')))
        from zee.licensing import status
        licence=status(base)
        splash.finish(window)
        if not licence['valid'] and not args.smoke_test:
            from zee.system_dialogs import LicenseDialog
            LicenseDialog(window).exec()
            if not status(base)['valid']:window.close();return 3
            window.check_licence() # Apply the newly imported package before showing the dashboard.
        window.show()
        if args.smoke_test:
            from pysnmp.hlapi.v3arch.asyncio import SnmpEngine
            snmp_check=SnmpEngine();snmp_check.close_dispatcher()
            def finish():
                if args.screenshot:
                    window.grab().save(str(args.screenshot))
                window.close()
            QTimer.singleShot(500,finish)
        code=app.exec()
        if args.smoke_test and not failures:
            import json
            from zee.licensing import customer_profile,EXPECTED_PROFILE_SHA256,REQUIRE_ISSUER
            profile=customer_profile()
            (base/'customer-build-smoke.json').write_text(json.dumps({'title':window.windowTitle(),'branding':window.branding,'profile_id':profile['profile_id'] if profile else None,'require_issuer':REQUIRE_ISSUER,'profile_digest':EXPECTED_PROFILE_SHA256,'licence':status(base),'device_limit':window.policy.max_devices,'features':sorted(window.policy.features)}),encoding='utf-8')
            (base/'smoke-ok.txt').write_text('GUI startup and graceful shutdown passed.\n',encoding='utf-8')
        return 1 if failures else code
    except Exception:
        logging.exception('Startup failed')
        if not args.smoke_test:
            QMessageBox.critical(None,'Startup failed','Could not start. See diagnostic.log in '+str(base))
        return 1
    finally:
        lock.unlock()

if __name__=='__main__':
    try:
        exit_code=main()
    except Exception:
        logging.exception('Customer build startup integrity check failed')
        if '--smoke-test' not in sys.argv and QApplication.instance():
            QMessageBox.critical(None,'Repair customer installation','Required signed customer build files could not be verified. Reinstall the reviewed customer package; do not replace issuer/profile files manually.')
        exit_code=1
    raise SystemExit(exit_code)
