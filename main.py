import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import traceback
from PySide6.QtCore import QTimer, QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from zee.core import Store
from zee.gui import Window, STYLE


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--screenshot',type=Path)
    args=parser.parse_args()
    app=QApplication(sys.argv)
    app.setApplicationName('Zee Network Monitor')
    app.setStyleSheet(STYLE)
    base=args.data_dir or Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'ZeeNetworkMonitor'
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
        store=Store(base/'monitor.sqlite3')
        window=Window(store)
        assets=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'
        if (assets/'icon.png').exists():
            app.setWindowIcon(QIcon(str(assets/'icon.png')))
        window.show()
        if args.smoke_test:
            def finish():
                if args.screenshot:
                    window.grab().save(str(args.screenshot))
                window.close()
            QTimer.singleShot(500,finish)
        code=app.exec()
        if args.smoke_test and not failures:
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
    raise SystemExit(main())
