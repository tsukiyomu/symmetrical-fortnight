# -*- coding: utf-8 -*-
"""
pytest 配置文件
提供测试环境初始化、结果汇总和通知功能
Author: tsukiyomi
"""
import time
import warnings
from typing import Optional, Dict, Any
from dataclasses import dataclass

import pytest

from common.readyaml import ReadYamlData
from base.removefile import remove_file
from common.dingRobot import send_dd_msg
from common.sendEmail import EmailSender  # 修改导入的类
from conf.operationConfig import OperationConfig
from conf.setting import dd_msg
from common.recordlog import logs

# 安全导入邮件配置
try:
    from conf.setting import email_msg
except ImportError:
    email_msg = False
    logs.warning("邮件配置未找到，将跳过邮件通知")


# 常量定义
class TestConstants:
    """测试相关常量"""
    TEMP_REPORT_PATH = "./report/temp"
    TEMP_FILE_EXTENSIONS = ['json', 'txt', 'attach', 'properties']
    DEFAULT_EMAIL_SUBJECT = '接口自动化测试结果'
    MAX_LOG_LENGTH = 256


@dataclass
class TestResult:
    """测试结果数据类"""
    total: int
    passed: int
    failed: int
    error: int
    skipped: int
    duration: float

    @property
    def success_rate(self) -> float:
        """计算成功率"""
        return (self.passed / self.total * 100) if self.total > 0 else 0

    def to_summary_text(self) -> str:
        """生成汇总文本"""
        return f"""
自动化测试结果通知：

测试统计：
  测试用例总数：{self.total}
  测试通过数：{self.passed}
  测试失败数：{self.failed}
  错误数量：{self.error}
  跳过执行数量：{self.skipped}
  成功率：{self.success_rate:.1f}%
  执行总时长：{self.duration:.2f}秒

{"[通过] 测试全部通过" if self.failed == 0 and self.error == 0 else "[失败] 请关注失败的测试用例"}
        """.strip()


class TestEnvironmentManager:
    """测试环境管理器"""

    def __init__(self):
        self.yaml_reader = ReadYamlData()

    def setup_test_environment(self) -> None:
        """初始化测试环境"""
        try:
            # 禁用警告
            self._disable_warnings()

            # 清理数据和文件
            self._cleanup_test_data()

            logs.info("测试环境初始化完成")
        except Exception as e:
            logs.error(f"测试环境初始化失败: {e}")
            raise

    def _disable_warnings(self) -> None:
        """禁用指定的警告类型"""
        warnings.simplefilter('ignore', ResourceWarning)
        warnings.simplefilter('ignore', DeprecationWarning)

    def _cleanup_test_data(self) -> None:
        """清理测试数据和临时文件"""
        # 清理 YAML 数据
        self.yaml_reader.clear_yaml_data()

        # 清理临时文件
        remove_file(
            TestConstants.TEMP_REPORT_PATH,
            TestConstants.TEMP_FILE_EXTENSIONS
        )


class TestResultCollector:
    """测试结果收集器"""

    @staticmethod
    def extract_test_result(terminalreporter) -> TestResult:
        """从 pytest 终端报告器中提取测试结果"""
        total = terminalreporter._numcollected
        passed = len(terminalreporter.stats.get('passed', []))
        failed = len(terminalreporter.stats.get('failed', []))
        error = len(terminalreporter.stats.get('error', []))
        skipped = len(terminalreporter.stats.get('skipped', []))

        # 计算执行时长
        start_time = TestResultCollector._get_start_timestamp(terminalreporter)
        duration = time.time() - start_time

        return TestResult(
            total=total,
            passed=passed,
            failed=failed,
            error=error,
            skipped=skipped,
            duration=duration
        )

    @staticmethod
    def _get_start_timestamp(terminalreporter) -> float:
        """获取测试开始时间戳"""
        start = terminalreporter._session_start
        if hasattr(start, "timestamp"):
            return start.timestamp()
        else:
            # 如果没有 timestamp 属性，使用当前时间
            logs.warning("无法获取测试开始时间，使用当前时间")
            return time.time()


class NotificationManager:
    """通知管理器"""

    def __init__(self):
        self.config = OperationConfig()

    def send_notifications(self, test_result: TestResult) -> None:
        """发送测试结果通知"""
        summary_text = test_result.to_summary_text()

        # 打印到控制台
        print(summary_text)
        logs.info("开始发送测试结果通知...")

        # 发送钉钉通知
        self._send_dingtalk_notification(summary_text)

        # 发送邮件通知
        self._send_email_notification(summary_text)

    def _send_dingtalk_notification(self, message: str) -> None:
        """发送钉钉通知"""
        if not dd_msg:
            logs.info("钉钉通知已禁用，跳过发送")
            return

        try:
            logs.info("正在发送钉钉通知...")
            response = send_dd_msg(message)
            log_content = str(response)[:TestConstants.MAX_LOG_LENGTH]
            logs.info(f"钉钉通知发送成功: {log_content}")
        except Exception as e:
            logs.error(f"钉钉通知发送失败: {e}")

    def _send_email_notification(self, message: str) -> None:
        """发送邮件通知"""
        if not email_msg:
            logs.info("邮件通知已禁用，跳过发送")
            return

        try:
            subject = self._get_email_subject()
            logs.info(f"正在发送邮件通知，主题: {subject}")

            # 使用新的EmailSender类
            email_sender = EmailSender()
            # 获取收件人信息
            addressee = self.config.get_section_for_data('EMAIL', 'addressee')
            # 正确调用send方法
            email_sender.send(
                subject=subject,
                content=message,
                recipients=addressee.split(';') if addressee else None
            )

            logs.info("邮件通知发送成功")
        except Exception as e:
            logs.error(f"邮件通知发送失败: {e}")

    def _get_email_subject(self) -> str:
        """获取邮件主题"""
        try:
            return (self.config.get_section_for_data('EMAIL', 'subject')
                    or TestConstants.DEFAULT_EMAIL_SUBJECT)
        except Exception:
            logs.warning("获取邮件主题失败，使用默认主题")
            return TestConstants.DEFAULT_EMAIL_SUBJECT


# ===== Pytest Fixtures and Hooks =====

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Session 级别的测试环境初始化 fixture
    在整个测试会话开始前自动执行一次
    """
    environment_manager = TestEnvironmentManager()
    environment_manager.setup_test_environment()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Pytest 钩子函数：在所有测试执行完成后自动调用
    收集测试结果并发送通知

    Args:
        terminalreporter: pytest 终端报告器对象
        exitstatus: 测试退出状态码
        config: pytest 配置对象
    """
    try:
        # 收集测试结果
        result_collector = TestResultCollector()
        test_result = result_collector.extract_test_result(terminalreporter)

        # 发送通知
        notification_manager = NotificationManager()
        notification_manager.send_notifications(test_result)

        logs.info("测试结果汇总和通知发送完成")

    except Exception as e:
        logs.error(f"测试结果汇总或通知发送失败: {e}")
        # 不抛出异常，避免影响测试主流程