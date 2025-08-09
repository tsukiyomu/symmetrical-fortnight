# import shutil
# import pytest
# import os
# import webbrowser
# from conf.setting import REPORT_TYPE

# if __name__ == '__main__':

#     if REPORT_TYPE == 'allure':
#         pytest.main(
#             ['-s', '-v', '--alluredir=./report/temp', './testcase', '--clean-alluredir',
#              '--junitxml=./report/results.xml'])

#         shutil.copy('./environment.xml', './report/temp')
#         os.system(f'allure serve ./report/temp')
#         time.sleep(2)  # 等待服务启动
#         webbrowser.open('http://localhost:4087')

#     elif REPORT_TYPE == 'tm':
#         pytest.main(['-vs', '--pytest-tmreport-name=testReport.html', '--pytest-tmreport-path=./report/tmreport'])
#         webbrowser.open_new_tab(os.getcwd() + '/report/tmreport/testReport.html')
import shutil
import pytest
import time
import os
import subprocess
import re
import webbrowser
from conf.setting import REPORT_TYPE


def serve_allure(report_dir):
    cmd = f"allure generate {report_dir} --clean -o ./report/allureReport && allure open ./report/allureReport"
    # 用 shell=True 保证在 Windows 下能跑
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    url = None
    # 匹配 URL
    pattern = re.compile(r"http://[^\s]+")
    for line in proc.stdout:
        print(line, end="")
        m = pattern.search(line)
        if m:
            url = m.group(0)
            break
    time.sleep(2)
    return url

if __name__ == "__main__":
    if REPORT_TYPE == "allure":
        # 执行测试并生成报告数据
        pytest.main([
            "-s", "-v",
            "--alluredir=./report/temp",
            "--clean-alluredir",
            "./testcase",
            "--junitxml=./report/results.xml"
        ])
        shutil.copy("./environment.xml", "./report/temp")
        
        # 生成并打开报告
        os.system("allure generate ./report/temp --clean -o ./report/allureReport")
        os.system("allure open ./report/allureReport")
        
    elif REPORT_TYPE == 'tm':
        pytest.main([
            '-vs',
            '--pytest-tmreport-name=testReport.html',
            '--pytest-tmreport-path=./report/tmreport'
        ])
        webbrowser.open_new_tab(
            os.path.abspath('./report/tmreport/testReport.html')
        )
