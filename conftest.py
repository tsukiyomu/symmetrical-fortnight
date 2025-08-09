# -*- coding: utf-8 -*-
import time

import pytest

from common.readyaml import ReadYamlData
from base.removefile import remove_file
from common.dingRobot import send_dd_msg
from common.sendEmail import SendEmail
from conf.operationConfig import OperationConfig
from conf.setting import dd_msg
from common.recordlog import logs
try:
    from conf.setting import email_msg
except Exception:
    email_msg = False

import warnings

yfd = ReadYamlData()


@pytest.fixture(scope="session", autouse=True)
def clear_extract():
    # 禁用HTTPS告警，ResourceWarning
    warnings.simplefilter('ignore', ResourceWarning)

    yfd.clear_yaml_data()
    remove_file("./report/temp", ['json', 'txt', 'attach', 'properties'])


def generate_test_summary(terminalreporter):
    """生成测试结果摘要字符串"""
    logs.info("开始汇总测试结果用于通知...")
    total = terminalreporter._numcollected
    passed = len(terminalreporter.stats.get('passed', []))
    failed = len(terminalreporter.stats.get('failed', []))
    error = len(terminalreporter.stats.get('error', []))
    skipped = len(terminalreporter.stats.get('skipped', []))
    start = terminalreporter._session_start
    if hasattr(start, "timestamp"):
        start = start.timestamp()
    else:
        # 如果没有timestamp属性，则使用当前时间作为结束时间，并设置duration为0
        start = time.time()
    duration = time.time() - start

    summary = f"""
    自动化测试结果，通知如下，请着重关注测试失败的接口，具体执行结果如下：
    测试用例总数：{total}
    测试通过数：{passed}
    测试失败数：{failed}
    错误数量：{error}
    跳过执行数量：{skipped}
    执行总时长：{duration:.2f}s
    """
    print(summary)
    return summary
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """自动收集pytest框架执行的测试结果并打印摘要信息"""
    summary = generate_test_summary(terminalreporter)
    logs.info(f"email_msg: {email_msg}"+ "dd_msg: "+ str(dd_msg))
    if dd_msg:
        try:
            logs.info("准备发送钉钉通知...")
            res = send_dd_msg(summary)
            logs.info(f"钉钉返回：{str(res)[:256]}")
        except Exception as ex:
            logs.error(f"发送钉钉通知失败：{ex}")
    if email_msg:
        try:
            subject = OperationConfig().get_section_for_data('EMAIL', 'subject') or '接口自动化测试结果'
            logs.info(f"准备发送邮件通知，主题：{subject}")
            SendEmail().build_content(subject=subject, email_content=summary)
        except Exception:
            # 邮件发送异常不应影响测试主流程
            logs.exception("发送邮件通知失败")