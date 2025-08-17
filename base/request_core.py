"""
request_core: 接口用例执行核心模块
封装了可复用的接口用例执行流程，是整个接口测试框架的核心组件

主要功能:
- URL/方法/头/Cookie 解析
- 参数替换(支持 data/json/params)
- 文件上传处理
- 发送请求与响应上报
- 数据提取与断言验证
- Allure测试报告集成

Author: tsukiyomi
Create Date: 2025
"""

import json
from json.decoder import JSONDecodeError
from typing import Any, Dict, Optional

import allure

from common.assertions import Assertions
from common.extract_utils import ExtractUtils
from common.recordlog import logs
from common.readyaml import ReadYamlData
from common.sendrequest import SendRequest
from common.yaml_utils import YamlUtils
from conf.operationConfig import OperationConfig


class RequestCore:
    """
    可复用的接口用例执行核心，封装共同流程：
    - URL/方法/头/Cookie 解析
    - 参数替换(支持 data/json/params)
    - 文件上传
    - 发送请求与响应上报
    - 提取与断言
    """

    def __init__(self) -> None:
        self.run = SendRequest()
        self.conf = OperationConfig()
        self.read = ReadYamlData()
        self.asserts = Assertions()
        self.extract_utils = ExtractUtils()

    # —— YAML 解析与替换 ——
    def handler_yaml_list(self, data_dict: Any) -> Any:
        """处理 yaml 中列表场景的辅助函数。"""
        return YamlUtils.handler_yaml_list(data_dict)

    def replace_load(self, data: Any) -> Any:
        """统一的数据占位符替换解析，兼容列表处理。"""
        return YamlUtils.replace_load(data, self.handler_yaml_list)

    # —— Allure ——
    @classmethod
    def allure_attach_response(cls, response: Any) -> str:
        if isinstance(response, dict):
            return json.dumps(response, ensure_ascii=False, indent=4)
        return str(response)

    # —— 执行单条用例 ——
    def execute_case(self, base_info: Dict[str, Any], test_case: Dict[str, Any]) -> None:
        """
        按统一流程执行一条测试用例。
        base_info: 包含 api_name/url/method/header/cookies
        test_case: 包含 case_name/validation/(data|json|params)/files/extract/extract_list 等
        """
        try:
            params_type = ["data", "json", "params"]

            # URL/方法/名称
            url_host = self.conf.get_section_for_data("api_envi", "host")
            api_name = base_info["api_name"]
            url_path = base_info["url"]
            method = base_info["method"]
            url = url_host + url_path

            # 请求信息
            allure.attach(api_name, f"接口名称：{api_name}", allure.attachment_type.TEXT)
            allure.attach(url, f"接口地址：{url}", allure.attachment_type.TEXT)
            allure.attach(method, f"请求方法：{method}", allure.attachment_type.TEXT)

            # Header/Cookie
            header = self.replace_load(base_info.get("header"))
            allure.attach(str(header), "请求头信息", allure.attachment_type.TEXT)

            cookie: Optional[Dict[str, Any]] = None
            if base_info.get("cookies") is not None:
                cookie = self.replace_load(base_info.get("cookies"))
                allure.attach(str(cookie), "Cookie", allure.attachment_type.TEXT)

            # 用例名与断言
            case_name = test_case.pop("case_name")
            allure.attach(case_name, f"测试用例名称：{case_name}", allure.attachment_type.TEXT)

            # 断言解析
            val = self.replace_load(test_case.get("validation"))
            test_case["validation"] = val
            validation = eval(test_case.pop("validation"))

            # 数据提取配置
            extract = test_case.pop("extract", None)
            extract_list = test_case.pop("extract_list", None)

            # 参数(data/json/params)替换
            for key, value in list(test_case.items()):
                if key in params_type:
                    test_case[key] = self.replace_load(value)

            # 文件上传
            file_cfg = test_case.pop("files", None)
            files = None
            if file_cfg is not None:
                for fk, fv in file_cfg.items():
                    allure.attach(json.dumps(file_cfg), "导入文件", allure.attachment_type.TEXT)
                    files = {fk: open(fv, mode="rb")}

            # 发送请求
            res = self.run.run_main(
                name=api_name,
                url=url,
                case_name=case_name,
                header=header,
                method=method,
                file=files,
                cookies=cookie,
                **test_case,
            )

            status_code = res.status_code

            # 响应上报
            try:
                allure.attach(
                    self.allure_attach_response(res.json()),
                    "接口响应信息",
                    allure.attachment_type.TEXT,
                )
            except Exception:
                # res.json() 失败时，附原文本
                allure.attach(res.text, "接口响应信息", allure.attachment_type.TEXT)

            # 提取/断言
            try:
                res_json = json.loads(res.text)
                if extract is not None:
                    self.extract_utils.extract_data(extract, res.text)
                if extract_list is not None:
                    self.extract_utils.extract_data_list(extract_list, res.text)

                self.asserts.assert_result(validation, res_json, status_code)
            except JSONDecodeError as js:
                logs.error("系统异常或接口未请求！")
                raise js
            except Exception as e:
                logs.error(e)
                raise e

        except Exception as e:
            # 保底兜底
            logs.error(e)
            raise e