"""
apiutil: 接口工具类（单用例场景）
为单接口测试用例提供统一的执行入口和工具方法，是接口测试框架的基础组件之一

主要功能:
- 提供单接口测试用例的执行入口
- 适配原有单用例调用签名
- 复用RequestCore核心执行逻辑
- 提供数据替换和响应处理工具方法

Author: tsukiyomi
Create Date: 2025
"""

from base.request_core import RequestCore


class RequestBase:
    def __init__(self):
        self.core = RequestCore()

    def replace_load(self, data):
        return self.core.replace_load(data)

    def specification_yaml(self, base_info, test_case):
        """
        适配原有单用例调用签名：直接复用核心执行逻辑。
        :param base_info: dict，包含 api_name/url/method/header/cookies
        :param test_case: dict，包含 case_name/validation/(data|json|params)/files/extract/extract_list
        """
        # 使用浅拷贝避免修改调用方传入的原对象
        base_info_copy = dict(base_info) if isinstance(base_info, dict) else base_info
        test_case_copy = dict(test_case) if isinstance(test_case, dict) else test_case
        self.core.execute_case(base_info_copy, test_case_copy)

    @classmethod
    def allure_attach_response(cls, response):
        return RequestCore.allure_attach_response(response)