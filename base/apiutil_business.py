# -*- coding: utf-8 -*-
# sys.path.insert(0, "..")


from common.sendrequest import SendRequest
from common.readyaml import ReadYamlData
from common.recordlog import logs
from conf.operationConfig import OperationConfig
from common.assertions import Assertions
from common.debugtalk import DebugTalk
from common.yaml_utils import YamlUtils
from common.extract_utils import ExtractUtils
import allure
import json
import jsonpath
import re
import traceback
from json.decoder import JSONDecodeError

assert_res = Assertions()


class RequestBase(object):
    def __init__(self):
        self.run = SendRequest()
        self.read = ReadYamlData()
        self.conf = OperationConfig()
        self.extract_utils = ExtractUtils()

    def handler_yaml_list(self, data_dict):
        """处理yaml文件测试用例请求参数为list情况，以数组形式"""
        return YamlUtils.handler_yaml_list(data_dict)

    def replace_load(self, data):
        """yaml数据替换解析"""
        return YamlUtils.replace_load(data, self.handler_yaml_list)

    def specification_yaml(self, case_info):
        """
        规范yaml测试用例的写法
        :param case_info: list类型,调试取case_info[0]-->dict
        :return:
        """
        params_type = ['params', 'data', 'json']
        cookie = None
        try:
            base_url = self.conf.get_section_for_data('api_envi', 'host')
            # base_url = self.replace_load(case_info['baseInfo']['url'])
            url = base_url + case_info["baseInfo"]["url"]
            allure.attach(url, f'接口地址：{url}')
            api_name = case_info["baseInfo"]["api_name"]
            allure.attach(api_name, f'接口名：{api_name}')
            method = case_info["baseInfo"]["method"]
            allure.attach(method, f'请求方法：{method}')
            header = self.replace_load(case_info["baseInfo"]["header"])
            allure.attach(str(header), '请求头信息', allure.attachment_type.TEXT)
            try:
                cookie = self.replace_load(case_info["baseInfo"]["cookies"])
                allure.attach(str(cookie), 'Cookie', allure.attachment_type.TEXT)
            except:
                pass
            for tc in case_info["testCase"]:
                case_name = tc.pop("case_name")
                allure.attach(case_name, f'测试用例名称：{case_name}', allure.attachment_type.TEXT)
                # 断言结果解析替换
                val = self.replace_load(tc.get('validation'))
                tc['validation'] = val
                # 字符串形式的列表转换为list类型
                validation = eval(tc.pop('validation'))
                allure_validation = str([str(list(i.values())) for i in validation])
                allure.attach(allure_validation, "预期结果", allure.attachment_type.TEXT)
                extract = tc.pop('extract', None)
                extract_lst = tc.pop('extract_list', None)
                for key, value in tc.items():
                    if key in params_type:
                        tc[key] = self.replace_load(value)
                file, files = tc.pop("files", None), None
                if file is not None:
                    for fk, fv in file.items():
                        allure.attach(json.dumps(file), '导入文件')
                        files = {fk: open(fv, 'rb')}
                res = self.run.run_main(name=api_name,
                                        url=url,
                                        case_name=case_name,
                                        header=header,
                                        cookies=cookie,
                                        method=method,
                                        file=files, **tc)
                res_text = res.text
                allure.attach(res_text, '接口响应信息', allure.attachment_type.TEXT)
                status_code = res.status_code
                allure.attach(self.allure_attach_response(res.json()), '接口响应信息', allure.attachment_type.TEXT)

                try:
                    res_json = json.loads(res_text)
                    if extract is not None:
                        self.extract_utils.extract_data(extract, res_text)
                    if extract_lst is not None:
                        self.extract_utils.extract_data_list(extract_lst, res_text)
                    # 处理断言
                    assert_res.assert_result(validation, res_json, status_code)
                except JSONDecodeError as js:
                    logs.error("系统异常或接口未请求！")
                    raise js
                except Exception as e:
                    logs.error(str(traceback.format_exc()))
                    raise e
        except Exception as e:
            logs.error(e)
            raise e

    @classmethod
    def allure_attach_response(cls, response):
        if isinstance(response, dict):
            allure_response = json.dumps(response, ensure_ascii=False, indent=4)
        else:
            allure_response = response
        return allure_response

    # 数据提取方法已迁移到 ExtractUtils 工具类中
    # 使用 self.extract_utils.extract_data() 和 self.extract_utils.extract_data_list()
