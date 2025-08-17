"""
generateId: 生成测试模块和测试用例的唯一标识符
主要用于为allure测试报告生成唯一的模块ID和测试用例ID，确保报告中的执行顺序与pytest设定的执行顺序保持一致

主要功能:
- 生成测试模块编号 (M01, M02, ...)
- 生成测试用例编号 (C01, C02, ...)
- 提供可迭代的ID生成器

Author: tsukiyomi
Create Date: 2025
"""

def generate_module_id():
    """
    生成测试模块编号，为了保证allure报告的顺序与pytest设定的执行顺序保持一致
    :return:
    """
    for i in range(1, 1000):
        module_id = 'M' + str(i).zfill(2) + '_'
        yield module_id


def generate_testcase_id():
    """
    生成测试用例编号
    :return:
    """
    for i in range(1, 10000):
        case_id = 'C' + str(i).zfill(2) + '_'
        yield case_id


m_id = generate_module_id()
c_id = generate_testcase_id()