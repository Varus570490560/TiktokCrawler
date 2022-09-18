import json
import os
import re
import sys
import time
from threading import Thread

import requests
from PyQt6 import QtCore
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QWidget, QListWidget, QPushButton, QFileDialog

from config_windows import ConfigWindows
from feishu import Feishu
from generate_path import default_path
from logger import Logger
from reporter import Reporter
from requester import Requester
from signals import UpdateUISignals, AdjustConfigSignals
from xlsx_worker import XlsxWorker, init_writer, init_remove_dup_reader
from enums import GetHashtagInfoStatus, HttpResponseStatus
from util import merge_array


class HashtagInfoResponse:
    status: GetHashtagInfoStatus
    name: str
    video_count: int
    view_count: int
    hashtag_id: str

    def __init__(self, status: GetHashtagInfoStatus, name: str, video_count: int, view_count: int, hashtag_id: str):
        self.status = status
        self.name = name
        self.video_count = video_count
        self.view_count = view_count
        self.hashtag_id = hashtag_id


class Hashtag(QObject):
    feishu: Feishu
    reporter: Reporter
    requester: Requester
    logger: Logger
    xlsx_reader: XlsxWorker = None
    xlsx_writer: XlsxWorker = None
    remove_dup_reader: XlsxWorker = None

    # ui_widget
    app: QApplication
    windows: QWidget
    log_box: QListWidget
    crawl_button: QPushButton
    import_button: QPushButton
    config_button: QPushButton
    config_windows: ConfigWindows
    import_file_dialog: QFileDialog
    output_path_file_dialog: QFileDialog

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
    contacted_xlsx_url = "https://docs.google.com/spreadsheets/d/1E4VLvzBMFyAXfg2tTJvsFPmow8FEDTAoqpJxhDy6IsU/export?format=xlsx&id=1E4VLvzBMFyAXfg2tTJvsFPmow8FEDTAoqpJxhDy6IsU"

    def __init__(self):
        super().__init__()

        self.update_ui_signals = UpdateUISignals()
        self.adjust_config_signals = AdjustConfigSignals()
        self.update_ui_signals.log_signal.connect(self.handle_log_signal)
        self.adjust_config_signals.adjust_output_path_signal.connect(self.handle_update_output_directory_signal)
        self.adjust_config_signals.adjust_notice_email.connect(self.handle_update_notice_email_signal)
        self.adjust_config_signals.adjust_hashtag.connect(self.handle_update_hashtag_signal)

        self.feishu = Feishu()
        self.logger = Logger(lark_sender=self.feishu, signals_sender=self.update_ui_signals)
        self.requester = Requester(logger=self.logger)
        self.reporter = Reporter()

    def render(self):
        self.app = QApplication(sys.argv)
        self.windows = QWidget()
        self.windows.resize(750, 421)
        self.windows.setWindowTitle("Hashtag email getter")
        self.windows.setFixedSize(750, 421)

        self.log_box = QListWidget(self.windows)
        self.log_box.move(20, 20)
        self.log_box.resize(710, 361)
        self.log_box.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.crawl_button = QPushButton(self.windows)
        self.crawl_button.setText("Run")
        self.crawl_button.setFixedWidth(80)
        self.crawl_button.move(20, 385)
        self.crawl_button.clicked.connect(self.handle_crawl_button_clicked)

        self.config_button = QPushButton(self.windows)
        self.config_button.setText("Setting")
        self.config_button.move(650, 385)
        self.config_button.setFixedWidth(80)
        self.config_button.clicked.connect(self.handle_config_button_clicked)

        self.windows.show()
        sys.exit(self.app.exec())
        pass

    def handle_log_signal(self, message):
        self.log_box.addItem(message)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())
        pass

    def handle_update_output_directory_signal(self, path):
        ok = self.check_directory_exist(path=path)
        if ok:
            self.logger.log_message("CONFIG", f"Set '{path}' as output path success.")
            self.output_path = path
        else:
            self.logger.log_message("ERROR", f"'{path}' not found.")
        pass

    def handle_update_notice_email_signal(self, email):
        if email == "":
            self.logger.log_message("CONFIG", "There will no notice when complete.")
        else:
            def run(notice_email: str):
                ok = self.feishu.verify_email(email=notice_email)
                if ok:
                    self.logger.log_message("CONFIG", f"Notice email '{notice_email}'.")
                    self.notice_email = notice_email
                else:
                    self.logger.log_message("ERROR", f"Check you email spell '{notice_email}'.")

            thread: Thread = Thread(target=run, args=(email,))
            thread.start()
        pass

    def handle_update_hashtag_signal(self, hashtag_str):
        self.hashtag_str = hashtag_str
        hashtags = self.hashtag_str.replace(" ", "")
        hashtags = hashtags.replace("\n", "")
        if len(hashtags) == 0:
            self.logger.log_message("ERROR", "You should input something to hashtag.")
        self.task_list = hashtags.split("#")
        while "" in self.task_list:
            self.task_list.remove("")
        if len(self.task_list) == 0:
            self.logger.log_message("ERROR", "There is no valid task to run, check your input.")
        else:
            self.logger.log_message("ANALYSIS", "Analysis your input success.")
            self.logger.log_message("ANALYSIS", f"Result: {self.task_list}")
        pass

    def handle_crawl_button_clicked(self):
        if len(self.task_list) == 0:
            self.logger.log_message("ERROR", "No task to run, input you hashtags on 'Setting'.")
            return

        def run():
            self.remove_duplication_page.clear()
            self.remove_duplication_author.clear()
            self.reporter.init_counter("VideoCounter")
            self.reporter.init_counter("UserCounter")
            self.reporter.set_timer()
            self.logger.log_message("BEGIN", "Crawl start")
            fields = ("HashtagName", "HashtagVideoCount", "HashtagViewCount", "UserNickname", "UserSignature", "UserHomePage",
                      "UserDiggCount", "UserFollowerCount", "UserHeartCount", "UserVideoCount", "VideoPage", "VideoDiggCount", "VideoPlayCount",
                      "VideoShareCount", "VideoCommentCount", "VideoCreateTime", "VideoDescription", "Email")
            filename = self.get_abs_output_filename()
            self.xlsx_writer = init_writer(path=filename, fields=fields)
            self.download_contacted_excel()
            self.remove_dup_reader = init_remove_dup_reader()
            if self.remove_dup_reader is None:
                self.logger.log_message("ERROR", "Initial remove duplication xlsx error.")
            else:
                self.remove_duplication_author = self.remove_dup_reader.read_unique_id()
                os.remove(default_path + "cache.xlsx")
                self.logger.log_message("CRAWL", "Initial remove duplication xlsx success.")
            for hashtag in self.task_list:
                hashtag_info = self.get_hashtag_info(hashtag)
                if hashtag_info.status == GetHashtagInfoStatus.NetworkError:
                    self.logger.log_message("ERROR", f"Get Hashtag '{hashtag_info.name}' info network error.")
                elif hashtag_info.status == GetHashtagInfoStatus.NoSuchHashtag:
                    self.logger.log_message("ERROR", f"No such hashtag:'{hashtag_info.name}'.")
                else:
                    self.logger.log_message("CRAWL", f"Get Hashtag '{hashtag_info.name}' info success.")
                    cursor = 0
                    while True:
                        video_ids = ''
                        url = f"https://www.tiktok.com/api/challenge/item_list/?aid=1988&challengeID={hashtag_info.hashtag_id}&count=30&cursor={cursor}"
                        cursor = cursor + 30
                        response = self.requester.get(url, allow_redirects=False)
                        if response.http_status != HttpResponseStatus.Success:
                            continue
                        rsp = json.loads(response.content)
                        has_more = rsp["hasMore"]
                        self.logger.log_message("CRAWL", f"Has more: {has_more}.")
                        if rsp.get("itemList") is None or len(rsp.get("itemList")) == 0:
                            break
                        for video in rsp["itemList"]:
                            self.reporter.self_increase("VideoCounter")
                            data = {
                                "HashtagName": hashtag_info.name,
                                "HashtagVideoCount": hashtag_info.video_count,
                                "HashtagViewCount": hashtag_info.view_count,
                                "UserNickname": video["author"]["nickname"],
                                "UserSignature": video["author"]["signature"],
                                "UserHomePage": f'https://www.tiktok.com/@{video["author"]["uniqueId"]}',
                                "UserDiggCount": video["authorStats"]["diggCount"],
                                "UserFollowerCount": video["authorStats"]["followerCount"],
                                "UserHeartCount": video["authorStats"]["heartCount"],
                                "UserVideoCount": video["authorStats"]["videoCount"],
                                "VideoPage": f'https://www.tiktok.com/@{video["author"]["uniqueId"]}/video/{video["id"]}',
                                "VideoDiggCount": video["stats"]["diggCount"],
                                "VideoPlayCount": video["stats"]["playCount"],
                                "VideoShareCount": video["stats"]["shareCount"],
                                "VideoCommentCount": video["stats"]["commentCount"],
                                "VideoCreateTime": self.timestamp_format(video["createTime"]),
                                "VideoDescription": video["desc"],
                                "Email": self.get_email(video["author"]["signature"])
                            }
                            video_ids = video_ids + video["id"]
                            if "@" in data.get("UserSignature"):
                                if video["author"]["uniqueId"] not in self.remove_duplication_author:
                                    self.remove_duplication_author.append(video["author"]["uniqueId"])
                                    self.xlsx_writer.writer_line(data)
                                    self.reporter.self_increase("UserCounter")
                                else:
                                    pass
                        if video_ids in self.remove_duplication_page:
                            break
                        else:
                            self.remove_duplication_page.append(video_ids)
                        if not has_more:
                            break
            video_count = self.reporter.get_counter("VideoCounter")
            user_count = self.reporter.get_counter("UserCounter")
            time_during = self.reporter.get_during()

            time.sleep(5)
            self.logger.log_message("COMPLETE", "Crawl complete.")
            self.logger.log_message("SUMMERY", f"Visit videos: {video_count}.")
            self.logger.log_message("SUMMERY", f"Get users: {user_count}.")
            self.logger.log_message("SUMMERY", f"Time cost: {time_during / 1000} s.")

        crawl_thread: Thread = Thread(target=run)
        crawl_thread.start()
        pass

    def handle_config_button_clicked(self):
        self.config_windows = ConfigWindows(self.update_ui_signals, self.adjust_config_signals, self.logger, self.output_path, True, self.hashtag_str)
        self.config_windows.render()
        pass

    def get_abs_output_filename(self) -> str:
        if self.output_path.endswith("/"):
            return self.output_path + time.strftime("%Y-%m-%d_%H:%M:%S.xlsx", time.localtime())
        else:
            return self.output_path + "/" + time.strftime("%Y-%m-%d_%H:%M:%S.xlsx", time.localtime())

    @staticmethod
    def check_directory_exist(path: str) -> bool:
        return os.path.exists(path)

    @staticmethod
    def timestamp_format(timestamp: int) -> str:
        create_time = time.localtime(timestamp)
        return str(time.strftime("%Y-%m-%d %H:%M:%S", create_time))

    def get_hashtag_info(self, hashtag: str):
        self.logger.log_message("CRAWL", f"Process {hashtag}")
        url = f"https://www.tiktok.com/api/challenge/detail/?challengeName={hashtag}"
        response = self.requester.get(url=url, allow_redirects=False)
        if response.http_status != HttpResponseStatus.Success:
            return HashtagInfoResponse(GetHashtagInfoStatus.NetworkError, hashtag, 0, 0, "0")
        rsp_json = json.loads(response.content)
        if rsp_json["statusCode"] == 10205:
            return HashtagInfoResponse(GetHashtagInfoStatus.NoSuchHashtag, hashtag, 0, 0, "0")
        return HashtagInfoResponse(GetHashtagInfoStatus.Success,
                                   rsp_json["challengeInfo"]["challenge"]["title"],
                                   rsp_json["challengeInfo"]["challenge"]["stats"]["videoCount"],
                                   rsp_json["challengeInfo"]["challenge"]["stats"]["viewCount"],
                                   rsp_json["challengeInfo"]["challenge"]["id"])

    def download_contacted_excel(self):
        try:
            response = requests.get(self.contacted_xlsx_url)
            self.logger.log_message("CRAWL", "Get remove duplication success.")
            with open(default_path + "cache.xlsx", "wb") as p:
                p.write(response.content)
        except Exception as e:
            self.logger.log_message("ERROR", f"Get remove duplication xlsx error: {e}")

    @staticmethod
    def get_email(signature: str):
        pattern = "^\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$"
        res = []
        chips = signature.split(" ")
        for chip in chips:
            merge_array(res, chip.split("\n"))
        for value in res:
            if re.match(pattern, value):
                return value
        return ""
