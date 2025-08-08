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
