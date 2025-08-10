import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import re
import time
from dataclasses import dataclass
from typing import Dict, Optional, Any, List, Tuple

import jenkins
import json
from jenkins import JenkinsException, NotFoundException, EmptyResponseException

from conf.operationConfig import OperationConfig


@dataclass
class JenkinsConfig:
    url: str
    username: str
    password: str   # 建议用 API Token
    timeout: int
    job_name: str


class PJenkins:
    """更健壮的 Jenkins 封装：连接、触发构建、等待状态、读取日志/报告、抽取 Allure 链接"""

    def __init__(self, conf: Optional[OperationConfig] = None):
        self._conf = conf or OperationConfig()
        self.cfg = JenkinsConfig(
            url=self._conf.get_section_jenkins('url'),
            username=self._conf.get_section_jenkins('username'),
            password=self._conf.get_section_jenkins('password'),
            timeout=int(self._conf.get_section_jenkins('timeout')),
            job_name=self._conf.get_section_jenkins('job_name'),
        )

        # 明确指定 requester，未来你需要 crumb 时可打开 crumb=True
        self._server = jenkins.Jenkins(
            self.cfg.url,
            username=self.cfg.username,
            password=self.cfg.password,
            timeout=self.cfg.timeout,
            # requester=jenkins.Requester(
            #     self.cfg.username, self.cfg.password, baseurl=self.cfg.url, timeout=self.cfg.timeout, crumb=True
            # )
        )

    # ---------------- 基础能力 ----------------

    def test_connection(self) -> bool:
        """验证与 Jenkins 的连接是否成功"""
        try:
            who = self._server.get_whoami()
            ver = self._server.get_version()
            print(f"✅ 已连接 Jenkins {self.cfg.url}，登录用户：{who.get('fullName') or self.cfg.username}，版本：{ver}")
            return True
        except JenkinsException as e:
            msg = str(e)
            print(f"❌ 连接 Jenkins 失败：{msg}")
            if "Connection refused" in msg or "Failed to establish a new connection" in msg:
                print("  可能原因：Jenkins 未启动 / URL 或端口错误 / 网络不通")
            elif "Authentication failed" in msg or "401" in msg:
                print("  可能原因：用户/密码（token）错误，或需要开启 crumb")
            return False
        except Exception as e:
            print(f"❌ 未知错误：{e}")
            return False

    def get_last_build_number(self, completed: bool = True) -> Optional[int]:
        """获取最后一次（已完成 or 最后触发）构建号，并打印 job_info 的详细内容用于调试"""
        info = self._server.get_job_info(self.cfg.job_name)
        print(f"Job info for '{self.cfg.job_name}': {json.dumps(info, indent=2, ensure_ascii=False)}")
        if info is None:
            print(f"警告：无法获取job '{self.cfg.job_name}' 的信息，可能是job不存在或名称错误")
            return None
        key = 'lastCompletedBuild' if completed else 'lastBuild'
        node = info.get(key) or {}
        if not node:
            print(f"警告：job '{self.cfg.job_name}' 没有构建记录")
        return node.get('number')

    def get_build_info(self, build_number: int) -> Dict[str, Any]:
        return self._server.get_build_info(self.cfg.job_name, build_number)

    # ---------------- 触发 & 等待 ----------------

    def trigger_build(self, params: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> int:
        """触发构建（支持参数化），返回队列 ID 或估算的构建号"""
        queue_id = self._server.build_job(self.cfg.job_name, parameters=params or {}, token=token)
        return queue_id  # 注意：这是 queue item id，不是 build number

    def wait_for_build_to_start(self, queue_id: int, timeout: int = 120, interval: float = 2.0) -> int:
        """等待队列进入构建，返回 build_number"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                qi = self._server.get_queue_item(queue_id)
                if qi.get('cancelled'):
                    raise RuntimeError("队列项已被取消")
                # 当 executable 出现时，表示正式开建
                executable = qi.get('executable')
                if executable and 'number' in executable:
                    return executable['number']
            except EmptyResponseException:
                # Jenkins 偶尔返回空响应，忽略重试
                pass
            time.sleep(interval)
        raise TimeoutError(f"等待构建开始超时（queue_id={queue_id}）")

    def wait_for_build_to_finish(self, build_number: int, timeout: int = 1800, interval: float = 3.0) -> Dict[str, Any]:
        """等待构建完成，返回 build_info"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            info = self.get_build_info(build_number)
            if not info.get('building'):
                return info
            time.sleep(interval)
        raise TimeoutError(f"等待构建完成超时（build #{build_number}）")

    # ---------------- 日志 & 报告 ----------------

    def get_console_log(self, build_number: Optional[int] = None) -> str:
        """获取控制台日志（完整）"""
        build_number = build_number or self.get_last_build_number(completed=False)
        if build_number is None:
            raise NotFoundException("未找到任何构建")
        return self._server.get_build_console_output(self.cfg.job_name, build_number)

    def get_test_report(self, build_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取 JUnit 测试报告（依赖 Jenkins JUnit/Test Result 插件）
        返回示例：{'duration': 1.23, 'failCount': 0, 'passCount': 10, 'skipCount': 0, ...}
        """
        build_number = build_number or self.get_last_build_number(completed=True)
        if build_number is None:
            return None
        try:
            return self._server.get_build_test_report(self.cfg.job_name, build_number)
        except NotFoundException:
            # 未安装 test report 插件或该次构建未产生报告
            return None

    def summarize_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """把测试报告汇总为更友好的结构"""
        pass_count = int(report.get('passCount', 0))
        fail_count = int(report.get('failCount', 0))
        skip_count = int(report.get('skipCount', 0))
        total = pass_count + fail_count + skip_count
        duration = int(report.get('duration', 0))
        h, m, s = duration // 3600, (duration % 3600) // 60, duration % 60
        return {
            'total': total,
            'pass_count': pass_count,
            'fail_count': fail_count,
            'skip_count': skip_count,
            'execute_duration': f'{h}时{m}分{s}秒'
        }

    # ---------------- Allure 链接抽取（更通用） ----------------

    _ALLURE_URL_RE = re.compile(r'(https?://[^\s"]+/allure[^\s"]*)', re.IGNORECASE)

    def find_allure_url(self, build_number: Optional[int] = None) -> Optional[str]:
        """
        从控制台日志或构建 actions 中提取 Allure 报告 URL：
        1) 优先从 build actions 里找（如果 Allure 插件把 URL 暴露出来）
        2) 再退化到控制台日志正则匹配（去掉写死 IP）
        """
        build_number = build_number or self.get_last_build_number(completed=True)
        if build_number is None:
            return None

        # 1) 尝试从 actions 里找提示（不同 Allure 插件版本字段不同，仅做尽力匹配）
        try:
            info = self.get_build_info(build_number)
            for act in info.get('actions', []):
                # 常见模式：某些插件会在 actions 里放一个带 urlName 或报告链接的结构
                for k, v in (act or {}).items():
                    if isinstance(v, str) and 'allure' in v.lower() and v.startswith('http'):
                        return v
        except Exception:
            pass

        # 2) 回退到日志匹配
        try:
            log = self.get_console_log(build_number)
            m = self._ALLURE_URL_RE.search(log)
            if m:
                return m.group(1)
        except Exception:
            pass

        return None

    # ---------------- 一条龙：触发->等待->汇总 ----------------

    def run_and_collect(self, params: Optional[Dict[str, Any]] = None, token: Optional[str] = None,
                        start_timeout: int = 180, finish_timeout: int = 3600) -> Dict[str, Any]:
        """
        触发一次构建并等待完成，返回：构建号、结果、报告汇总、Allure 链接（可为空）
        """
        queue_id = self.trigger_build(params=params, token=token)
        build_no = self.wait_for_build_to_start(queue_id, timeout=start_timeout)
        info = self.wait_for_build_to_finish(build_no, timeout=finish_timeout)
        result = info.get('result')

        report = self.get_test_report(build_no)
        summary = self.summarize_report(report) if report else None
        allure_url = self.find_allure_url(build_no)

        return {
            'build_number': build_no,
            'result': result,
            'report_summary': summary,
            'allure_url': allure_url,
        }


if __name__ == '__main__':
    j = PJenkins()
    if not j.test_connection():
        raise SystemExit(1)

    # 例：不触发新构建，直接读取最新完成的构建信息
    last_done = j.get_last_build_number(completed=True)
    if last_done:
        print(f"最后一次完成的构建号：#{last_done}")
        rep = j.get_test_report(last_done)
        if rep:
            print("报告摘要：", j.summarize_report(rep))
        print("Allure 链接：", j.find_allure_url(last_done))

    # 例：触发一次新的构建并等待结果（需要你的 job 支持无参/有参构建）
    # result = j.run_and_collect(params={"env": "test"})
    # print("构建结果：", result)
