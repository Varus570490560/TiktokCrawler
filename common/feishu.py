import json

import requests


class Feishu:
    tenant_access_token: str = ''
    robot_secret_data = '{"app_id": "cli_a24d49eae1bad013","app_secret": "6een1lFRrlxMaFJxTIRfUetTqHRklgiZ"}'
    robot_url = 'https://open.feishu.cn/open-apis/bot/v2/hook/8260d294-6983-419d-b071-fc462d36ea70'

    at_user_open_id = ''
    email: str = ''

    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }

    def __init__(self, robot_url="https://open.feishu.cn/open-apis/bot/v2/hook/8260d294-6983-419d-b071-fc462d36ea70"):
        self.robot_url = robot_url
        super().__init__()

    def __get_tenant_access_token(self) -> str:
        if self.tenant_access_token == '':
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            response = requests.post(url=url, data=self.robot_secret_data, headers=self.headers)
            response_json = json.loads(response.content)
            if response_json['code'] != 0:
                raise Exception(f"[{response_json['code']}]Get feishu tenant access token failed!\n{response_json['msg']}")
            self.tenant_access_token = response_json["tenant_access_token"]
        return self.tenant_access_token

    def send_lark(self, text: str, at: str = ""):
        if at == "":
            for i in range(0, 3):
                if self.__send_lark(text):
                    break
        elif at != "" and self.email != at:
            ok = self.verify_email(at)
            if not ok:
                for i in range(0, 3):
                    if self.__send_lark(text):
                        break
            else:
                for i in range(0, 3):
                    if self.__send_lark(text, self.at_user_open_id):
                        break
        else:
            for i in range(0, 3):
                if self.__send_lark(text, self.at_user_open_id):
                    break

    def __send_lark(self, text: str, at: str = "") -> bool:
        if at != "":
            obj = {"msg_type": "text", "content": " {\"text\":\"<at user_id=\\\"" + at + "\\\"></at> " + text + "\"}"}
        else:
            obj = {"msg_type": "text", "content": {"text": text}}
        try:
            requests.post(self.robot_url, json=obj, timeout=60)
        except Exception as e:
            print(e)
            return False
        return True

    def __get_user_open_id_by_email(self, email: str) -> str:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + self.__get_tenant_access_token()
        }
        url = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id"
        data = '{"emails": ["' + email + '"]}'
        response = requests.post(url=url, data=data, headers=headers)
        rsp = json.loads(response.content)
        if rsp["data"]["user_list"][0].get("user_id") is None:
            self.at_user_open_id = ""
            return ""
        self.at_user_open_id = rsp["data"]["user_list"][0]["user_id"]
        return self.at_user_open_id

    def verify_email(self, email: str) -> bool:
        rsp = self.__get_user_open_id_by_email(email)
        if rsp == "":
            return False
        self.email = email
        return True
