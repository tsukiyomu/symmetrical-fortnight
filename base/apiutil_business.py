"""
apiutil_business: 接口工具类（业务场景）
为业务编排场景的测试用例提供执行入口和工具方法，支持多步骤接口测试流程

主要功能:
- 提供业务场景测试用例的执行入口
- 支持多个接口调用的编排执行
- 复用RequestCore核心执行逻辑
- 提供数据替换和响应处理工具方法

Author: tsukiyomi
Create Date: 2025
"""

from base.request_core import RequestCore


class RequestBase(object):
    def __init__(self):
        self.core = RequestCore()

    def replace_load(self, data):
        return self.core.replace_load(data)

    def specification_yaml(self, case_info):
        """
        业务编排场景：`case_info` 结构为 { baseInfo: {...}, testCase: [ {...}, ... ] }
        循环执行每条用例，复用核心执行逻辑。
        """
        base_info = dict(case_info.get("baseInfo", {}))
        test_cases = case_info.get("testCase", []) or []
        for tc in test_cases:
            self.core.execute_case(dict(base_info), dict(tc))

    @classmethod
    def allure_attach_response(cls, response):
        return RequestCore.allure_attach_response(response)