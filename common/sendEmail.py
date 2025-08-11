import smtplib
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from contextlib import contextmanager
import re

from conf.operationConfig import OperationConfig
from common.recordlog import logs

"""
sendEmail：往邮箱发送测试结果
Author: tsukiyomi
"""
class EmailConfig:
    """邮件配置管理类"""

    def __init__(self, config: Optional[OperationConfig] = None):
        self.config = config or OperationConfig()
        self._cache: Dict[str, Any] = {}

    def get_email_config(self, key: str) -> str:
        """获取邮件配置，带缓存"""
        if key not in self._cache:
            self._cache[key] = self.config.get_section_for_data('EMAIL', key)
        return self._cache[key]

    @property
    def host(self) -> str:
        return self.get_email_config('host')

    @property
    def user(self) -> str:
        return self.get_email_config('user')

    @property
    def passwd(self) -> str:
        return self.get_email_config('passwd')

    @property
    def addressee(self) -> List[str]:
        return self.get_email_config('addressee').split(';')

    @property
    def subject(self) -> str:
        return self.get_email_config('subject')


class EmailBuilder:
    """邮件构建器"""

    @staticmethod
    def format_email_address(email: str, display_name: Optional[str] = None) -> str:
        """格式化邮件地址

        Args:
            email: 邮件地址
            display_name: 显示名称

        Returns:
            格式化后的邮件地址
        """
        email = email.strip()
        if not display_name:
            # 尝试从邮件地址提取用户名作为显示名
            match = re.match(r'^([^@]+)@', email)
            display_name = match.group(1) if match else email
        return f'{display_name} <{email}>'

    @staticmethod
    def build_message(
            subject: str,
            content: str,
            sender: str,
            recipients: List[str],
            attachments: Optional[List[Dict[str, Any]]] = None
    ) -> MIMEMultipart:
        """构建邮件消息

        Args:
            subject: 邮件主题
            content: 邮件正文
            sender: 发件人
            recipients: 收件人列表
            attachments: 附件列表，每个附件是包含'path'和'filename'的字典

        Returns:
            构建好的邮件消息
        """
        message = MIMEMultipart()
        message['Subject'] = subject
        message['From'] = sender
        message['To'] = ';'.join([EmailBuilder.format_email_address(r) for r in recipients])

        # 添加正文
        text = MIMEText(content, _subtype='plain', _charset='utf-8')
        message.attach(text)

        # 添加附件
        if attachments:
            for attachment in attachments:
                EmailBuilder._attach_file(message, attachment)

        return message

    @staticmethod
    def _attach_file(message: MIMEMultipart, attachment: Dict[str, Any]) -> None:
        """添加附件到邮件

        Args:
            message: 邮件消息对象
            attachment: 附件信息字典
        """
        file_path = attachment.get('path')
        if not file_path or not os.path.exists(file_path):
            logs.warning(f"附件文件不存在: {file_path}")
            return

        filename = attachment.get('filename', Path(file_path).name)

        try:
            with open(file_path, 'rb') as f:
                atta = MIMEApplication(f.read())
                atta['Content-Type'] = 'application/octet-stream'
                atta['Content-Disposition'] = f'attachment; filename="{filename}"'
                message.attach(atta)
                logs.info(f"成功添加附件: {filename}")
        except Exception as e:
            logs.error(f"添加附件失败 {file_path}: {e}")


class EmailSender:
    """邮件发送器"""

    def __init__(self, config: Optional[EmailConfig] = None):
        self.config = config or EmailConfig()

    @contextmanager
    def _smtp_connection(self):
        """SMTP连接上下文管理器"""
        service = None
        try:
            logs.info(f"连接SMTP服务器: {self.config.host}")
            service = smtplib.SMTP_SSL(self.config.host)

            logs.info(f"登录SMTP账户: {self.config.user}")
            service.login(self.config.user, self.config.passwd)

            yield service

        except smtplib.SMTPConnectError as e:
            logs.error(f'邮箱服务器连接失败: {e}')
            raise
        except smtplib.SMTPAuthenticationError as e:
            logs.error(f'邮箱服务器认证错误，请检查POP3/SMTP服务是否开启，密码是否为授权码: {e}')
            raise
        except smtplib.SMTPException as e:
            logs.error(f'SMTP错误: {e}')
            raise
        finally:
            if service:
                try:
                    service.quit()
                    logs.info('SMTP连接已关闭')
                except Exception:
                    pass

    def send(
            self,
            subject: str,
            content: str,
            recipients: Optional[List[str]] = None,
            attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """发送邮件

        Args:
            subject: 邮件主题
            content: 邮件正文
            recipients: 收件人列表
            attachments: 附件列表

        Returns:
            发送是否成功
        """
        try:
            # 准备发件人和收件人
            sender = EmailBuilder.format_email_address(
                self.config.user,
                'Liaison Officer'
            )
            recipients = recipients or self.config.addressee

            # 构建邮件
            message = EmailBuilder.build_message(
                subject=subject,
                content=content,
                sender=sender,
                recipients=recipients,
                attachments=attachments
            )

            # 发送邮件
            with self._smtp_connection() as service:
                logs.info(f"发送邮件到: {recipients}")
                service.sendmail(self.config.user, recipients, message.as_string())
                logs.info('邮件发送成功!')
                return True

        except smtplib.SMTPSenderRefused as e:
            logs.error(f'发件人地址未经验证: {e}')
        except smtplib.SMTPDataError as e:
            logs.error(f'邮件内容被拒绝（可能被识别为垃圾邮件）: {e}')
        except Exception as e:
            logs.exception(f'邮件发送失败: {e}')

        return False


class TestReportEmailSender:
    """测试报告邮件发送器"""

    def __init__(self, config: Optional[EmailConfig] = None):
        self.config = config or EmailConfig()
        self.sender = EmailSender(config)

    @staticmethod
    def calculate_statistics(
            success: List,
            failed: List,
            error: List,
            not_running: List
    ) -> Dict[str, Any]:
        """计算测试统计数据

        Args:
            success: 成功用例列表
            failed: 失败用例列表
            error: 错误用例列表
            not_running: 未执行用例列表

        Returns:
            统计数据字典
        """
        success_num = len(success)
        fail_num = len(failed)
        error_num = len(error)
        notrun_num = len(not_running)

        total = success_num + fail_num + error_num + notrun_num
        executed = success_num + fail_num + error_num

        # 避免除零错误
        if executed > 0:
            pass_rate = f"{success_num / executed * 100:.2f}%"
            fail_rate = f"{fail_num / executed * 100:.2f}%"
            error_rate = f"{error_num / executed * 100:.2f}%"
        else:
            pass_rate = fail_rate = error_rate = "N/A"

        return {
            'total': total,
            'success_num': success_num,
            'fail_num': fail_num,
            'error_num': error_num,
            'notrun_num': notrun_num,
            'executed': executed,
            'pass_rate': pass_rate,
            'fail_rate': fail_rate,
            'error_rate': error_rate
        }

    @staticmethod
    def format_report_content(stats: Dict[str, Any], project_name: str = "***项目") -> str:
        """格式化测试报告内容

        Args:
            stats: 统计数据
            project_name: 项目名称

        Returns:
            格式化的报告内容
        """
        if stats['executed'] == 0:
            return f"{project_name}接口测试：未执行任何测试用例。"

        template = (
            f"{project_name}接口测试报告\n\n"
            f"测试概况：\n"
            f"- 总用例数：{stats['total']}\n"
            f"- 执行用例数：{stats['executed']}\n"
            f"- 通过：{stats['success_num']}\n"
            f"- 失败：{stats['fail_num']}\n"
            f"- 错误：{stats['error_num']}\n"
            f"- 未执行：{stats['notrun_num']}\n\n"
            f"执行率统计：\n"
            f"- 通过率：{stats['pass_rate']}\n"
            f"- 失败率：{stats['fail_rate']}\n"
            f"- 错误率：{stats['error_rate']}\n\n"
            f"详细测试结果请参见附件。"
        )

        return template

    def send_test_report(
            self,
            success: List,
            failed: List,
            error: List,
            not_running: List,
            report_file: Optional[str] = None,
            project_name: str = "***项目",
            subject: Optional[str] = None,
            recipients: Optional[List[str]] = None
    ) -> bool:
        """发送测试报告邮件

        Args:
            success: 成功用例列表
            failed: 失败用例列表
            error: 错误用例列表
            not_running: 未执行用例列表
            report_file: 报告文件路径
            project_name: 项目名称
            subject: 邮件主题（可选）
            recipients: 收件人列表（可选）

        Returns:
            发送是否成功
        """
        # 计算统计数据
        stats = self.calculate_statistics(success, failed, error, not_running)

        # 准备邮件内容
        content = self.format_report_content(stats, project_name)
        subject = subject or self.config.subject

        # 准备附件
        attachments = None
        if report_file and os.path.exists(report_file):
            attachments = [{
                'path': report_file,
                'filename': f'test_report_{Path(report_file).name}'
            }]

        # 发送邮件
        return self.sender.send(
            subject=subject,
            content=content,
            recipients=recipients,
            attachments=attachments
        )