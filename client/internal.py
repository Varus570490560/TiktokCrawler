import json
import os
import sys
from threading import Thread

from PyQt6 import QtCore
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QWidget, QListWidget, QPushButton, QFileDialog, QMessageBox

from common.feishu import Feishu
from generate.generate_path import default_path
from common.logger import Logger
from common.reporter import Reporter
from common.requester import Requester
from common.signals import UpdateUISignals, AdjustConfigSignals
from common.enums import ListType, HttpResponseStatus
from common.xlsx_worker import verify_xlsx_format
from common.config_reader import ConfigReader
from common.config_windows import ConfigWindows


class DownloadWindows(QObject):
    windows: QWidget
    log_box: QListWidget
    item_list_widget: QListWidget
    message_box: QMessageBox
    download_button: QPushButton

    items: []
    list_type: ListType
    config_reader: ConfigReader
    requester: Requester
    filename: str

    update_ui_signals: UpdateUISignals

    def __init__(self, list_type: ListType, requester: Requester):
        super().__init__()
        self.list_type = list_type
        self.requester = requester
        self.config_reader = ConfigReader()
        self.config_reader.read_config()
        self.update_ui_signals = UpdateUISignals()
        self.update_ui_signals.refresh_items_signal.connect(self.handle_refresh_items_signal)

    def render(self):

        def get_items():
            if self.list_type == ListType.ByTime:
                url = self.config_reader.server_url + "/list_history_by_time"
            else:
                url = self.config_reader.server_url + "/list_history_by_increase"
            try:
                rsp = self.requester.get(url, allow_redirects=True)
            except Exception as e:
                self.update_ui_signals.refresh_items_signal.emit(["Internet error.", str(e)])
                return
            try:
                rsp = json.loads(rsp.content)
                self.items = rsp["items"]
            except Exception as e:
                self.update_ui_signals.refresh_items_signal.emit(["Json load error.", str(e)])

            items = self.items
            self.update_ui_signals.refresh_items_signal.emit(items)

        self.windows = QWidget()
        if self.list_type == ListType.ByTime:
            self.windows.setWindowTitle("Download By Time")
        else:
            self.windows.setWindowTitle("Download By Increase")
        self.windows.resize(500, 314)
        self.windows.setFixedSize(500, 314)

        self.item_list_widget = QListWidget(self.windows)
        self.item_list_widget.move(20, 20)
        self.item_list_widget.resize(460, 254)
        self.item_list_widget.clicked.connect(self.handle_item_list_widget_clicked)
        self.item_list_widget.doubleClicked.connect(self.handle_item_list_widget_double_clicked)
        self.item_list_widget.addItem("Loading...")

        self.download_button = QPushButton(self.windows)
        self.download_button.move(20, 280)
        self.download_button.setText("Download")
        self.download_button.clicked.connect(self.handle_download_button_clicked)
        self.download_button.setEnabled(False)

        self.windows.show()

        get_items_thread: Thread = Thread(target=get_items)
        get_items_thread.start()

        pass

    def handle_download_button_clicked(self):
        print(self.item_list_widget.currentItem().text())
        self.filename = self.item_list_widget.currentItem().text()
        self.download_xlsx(self.filename)
        pass

    def handle_item_list_widget_clicked(self):
        self.download_button.setEnabled(True)

    def handle_item_list_widget_double_clicked(self):
        self.filename = self.item_list_widget.currentItem().text()
        self.download_xlsx(self.filename)

    def handle_refresh_items_signal(self, items: []):
        self.item_list_widget.clear()
        for item in items:
            self.item_list_widget.addItem(item)

    def download_xlsx(self, filename):
        url = self.config_reader.server_url + f"/download?list_type={self.list_type.value}&filename={filename}"
        rsp = self.requester.get(url, allow_redirects=False)
        with open(default_path + filename, "wb") as f:
            f.write(bytes(rsp.content))


class PlayCountClient(QObject):
    feishu: Feishu
    reporter: Reporter
    requester: Requester
    logger: Logger
    config_reader: ConfigReader

    # ui_widget
    app: QApplication
    windows: QWidget
    log_box: QListWidget
    get_history_button: QPushButton
    upload_button: QPushButton
    download_by_time_button: QPushButton
    download_by_increase_button: QPushButton
    setting_button: QPushButton
    import_file_dialog: QFileDialog
    output_path_file_dialog: QFileDialog
    download_windows: DownloadWindows
    config_windows: ConfigWindows

    # signals
    update_ui_signals: UpdateUISignals
    adjust_config_signals: AdjustConfigSignals

    # status
    task_list = []
    remove_duplication_author = []
    remove_duplication_page = []
    hashtag_str = ''
    output_path = default_path
    input_file_name = ''
    notice_email = ''
    ms_token = 'g8vXKy2fjhjd7xrrPcCU7Wfop7isL5KAuyjofBp061Mtaxm_fA5vZ_lAlj46mvE_NnR7x-m-022QnOLdb6Em6HbYv1qm-ek2LXKHh6aTtnLpk_Ke8h7MUTkvWAUZX0cQ1JhrowY='

    def __init__(self):
        super().__init__()

        self.update_ui_signals = UpdateUISignals()
        self.adjust_config_signals = AdjustConfigSignals()

        self.feishu = Feishu()
        self.logger = Logger(lark_sender=self.feishu, signals_sender=self.update_ui_signals)
        self.requester = Requester(logger=self.logger)
        self.reporter = Reporter()
        self.config_reader = ConfigReader()
        self.config_reader.read_config()

        self.update_ui_signals.log_signal.connect(self.handle_log_signal)
        self.adjust_config_signals.adjust_output_path_signal.connect(self.handle_update_output_directory_signal)

    def render(self):
        self.app = QApplication(sys.argv)
        self.windows = QWidget()
        self.windows.resize(750, 421)
        self.windows.setWindowTitle("Played Count Client")
        self.windows.setFixedSize(750, 421)

        self.upload_button = QPushButton(self.windows)
        self.upload_button.setText("Update Data Source")
        self.upload_button.setFixedWidth(150)
        self.upload_button.move(20, 385)
        self.upload_button.clicked.connect(self.handle_upload_button_click)

        self.download_by_time_button = QPushButton(self.windows)
        self.download_by_time_button.setText("Download By Time")
        self.download_by_time_button.setFixedWidth(150)
        self.download_by_time_button.move(210, 385)
        self.download_by_time_button.clicked.connect(self.handle_download_by_time_button_click)

        self.download_by_increase_button = QPushButton(self.windows)
        self.download_by_increase_button.setText("Download By Increase")
        self.download_by_increase_button.setFixedWidth(150)
        self.download_by_increase_button.move(390, 385)
        self.download_by_increase_button.clicked.connect(self.handle_download_by_increase_button_click)

        self.setting_button = QPushButton(self.windows)
        self.setting_button.setFixedWidth(150)
        self.setting_button.setText("Setting")
        self.setting_button.move(580, 385)
        self.setting_button.clicked.connect(self.handle_setting_button_click)

        self.log_box = QListWidget(self.windows)
        self.log_box.move(20, 20)
        self.log_box.resize(710, 361)
        self.log_box.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.update_ui_signals.log_signal.connect(self.handle_log_signal)

        self.windows.show()
        sys.exit(self.app.exec())
        pass

    def handle_log_signal(self, message: str):
        self.log_box.addItem(message)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def handle_download_by_time_button_click(self):
        self.download_windows = DownloadWindows(ListType.ByTime, self.requester)
        self.download_windows.render()

    pass

    def handle_download_by_increase_button_click(self):
        self.download_windows = DownloadWindows(ListType.ByIncrease, self.requester)
        self.download_windows.render()

    def handle_upload_button_click(self):
        self.import_file_dialog = QFileDialog(self.windows)
        filename = self.import_file_dialog.getOpenFileNames()[0]
        if len(filename) == 0:
            self.logger.log_message("UPLOAD", "Cancel")
            return
        else:
            filename = filename[0]
        is_xlsx = verify_xlsx_format(filename)
        if not is_xlsx:
            self.logger.log_message("ERROR", f"File '{filename}' may not a xlsx file.")
            return
        files = {"file": open(file=f"{filename}", mode="rb")}
        url = self.config_reader.server_url
        response = self.requester.post(url=f"{url}/upload", files=files, json={})
        if response.http_status == HttpResponseStatus.Created:
            self.logger.log_message("SUCCESS", "Upload source file success.")
        else:
            self.logger.log_message("ERROR", "Upload source file failed.")
        pass

    def handle_setting_button_click(self):
        self.config_windows = ConfigWindows(adjust_config_signals=self.adjust_config_signals,
                                            update_ui_signals=self.update_ui_signals,
                                            hashtag_str="",
                                            is_hashtag=False,
                                            logger=self.logger,
                                            output_path=self.output_path)
        self.config_windows.render()
        pass

    def handle_update_output_directory_signal(self, path: str):
        ok = self.check_directory_exist(path=path)
        if ok:
            self.logger.log_message("CONFIG", f"Set '{path}' as output path success.")
            self.output_path = path
        else:
            self.logger.log_message("ERROR", f"'{path}' not found.")

    @staticmethod
    def check_directory_exist(path: str) -> bool:
        return os.path.exists(path)
