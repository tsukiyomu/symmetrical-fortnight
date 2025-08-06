import json
import re
from json.decoder import JSONDecodeError

import allure
import jsonpath

from common.assertions import Assertions
from common.debugtalk import DebugTalk
from common.readyaml import get_testcase_yaml, ReadYamlData
from common.recordlog import logs
from common.sendrequest import SendRequest
from common.yaml_utils import YamlUtils
from common.extract_utils import ExtractUtils
from conf.operationConfig import OperationConfig
from conf.setting import FILE_PATH


class RequestBase:

 
    def __init__(self):
        # 初始化请求发送、配置读取、yaml读写、断言与数据提取工具
        self.run = SendRequest()              # HTTP请求执行器
        self.conf = OperationConfig()         # 配置读取（如环境host）
        self.read = ReadYamlData()            # YAML读写工具
        self.asserts = Assertions()          # 断言工具
        self.extract_utils = ExtractUtils()   # 提取工具

    def replace_load(self, data):
        """yaml数据替换解析"""
        return YamlUtils.replace_load(data)

    def specification_yaml(self, base_info, test_case):
        """
        接口请求处理基本方法
        :param base_info: yaml文件里面的baseInfo
        :param test_case: yaml文件里面的testCase
        :return:
        """
        try:
            # 支持 data, json, params 三种参数类型
            params_type = ['data', 'json', 'params']
           # 1. 构造请求 URL
            url_host = self.conf.get_section_for_data('api_envi', 'host')
            api_name = base_info['api_name']
            url = url_host + base_info['url']

            allure.attach(api_name, f'接口名称：{api_name}', allure.attachment_type.TEXT)
            allure.attach(api_name, f'接口地址：{url}', allure.attachment_type.TEXT)
            method = base_info['method']
            allure.attach(api_name, f'请求方法：{method}', allure.attachment_type.TEXT)

             # 2. 准备请求头和 Cookie
            header = self.replace_load(base_info['header'])
            allure.attach(api_name, f'请求头：{header}', allure.attachment_type.TEXT)
            # 处理cookie
            cookie = None
            if base_info.get('cookies') is not None:
                cookie = eval(self.replace_load(base_info['cookies']))

             # 3. 用例名称 & 验证规则
            case_name = test_case.pop('case_name')
            allure.attach(api_name, f'测试用例名称：{case_name}', allure.attachment_type.TEXT)
            # 处理断言
            val = self.replace_load(test_case.get('validation'))
            test_case['validation'] = val
            validation = eval(test_case.pop('validation'))

            # 4. 处理参数提取
            extract = test_case.pop('extract', None)
            extract_list = test_case.pop('extract_list', None)
            # 5. 处理请求参数（data/json/params）
            for key, value in test_case.items():
                if key in params_type:
                    test_case[key] = self.replace_load(value)

            # 6. 文件上传支持
            file, files = test_case.pop('files', None), None
            if file is not None:
                for fk, fv in file.items():
                    allure.attach(json.dumps(file), '导入文件')
                    files = {fk: open(fv, mode='rb')}
            # 7. 发送 HTTP 请求
            res = self.run.run_main(
                name=api_name,
                url=url,
                case_name=case_name,
                header=header,
                method=method,
                file=files,
                cookies=cookie,
                **test_case
            )
            status_code = res.status_code
            # 把原始 JSON 响应附加到 Allure
            allure.attach(
                self.allure_attach_response(res.json()),
                '接口响应信息',
                allure.attachment_type.TEXT
            )
            try:
                # 解析响应文本为 dict
                res_json = json.loads(res.text)
                # 8. 数据提取
                if extract is not None:
                    self.extract_utils.extract_data(extract, res.text)
                if extract_list is not None:
                    self.extract_utils.extract_data_list(extract_list, res.text)
                # 9. 执行断言
                self.asserts.assert_result(validation, res_json, status_code)

            except JSONDecodeError as js:
                logs.error('系统异常或接口未请求！')
                raise js
            except Exception as e:
                logs.error(e)
                raise e

        except Exception as e:
            # 捕获整体流程的任何异常并抛出
            raise e

    @classmethod
    def allure_attach_response(cls, response):
        """
        将返回的 JSON 对象格式化为漂亮的字符串，方便在报告中阅读
        """
        if isinstance(response, dict):
            allure_response = json.dumps(response, ensure_ascii=False, indent=4)
        else:
            allure_response = response
        return allure_response

    # 数据提取方法已迁移到 ExtractUtils 工具类中
    # 使用 self.extract_utils.extract_data() 和 self.extract_utils.extract_data_list()


if __name__ == '__main__':
     # 从 YAML 加载首个用例并执行验证方法
    case_info = get_testcase_yaml(FILE_PATH['YAML'] + '/LoginAPI/login.yaml')[0]
    # print(case_info)
    req = RequestBase()
    # res = req.specification_yaml(case_info)
    res = req.specification_yaml(case_info)
    print(res)
