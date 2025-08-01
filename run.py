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
    cmd = f"allure serve {report_dir}"
    # 1) 用 shell=True 保证在 Windows 下能跑 .bat
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    url = None
    # 2) 更宽松的匹配，让它捕获到“Server started at http://…”即可
    pattern = re.compile(r"Server started at (http://[^\s]+)")
    for line in proc.stdout:
        print(line, end="")
        m = pattern.search(line)
        if m:
            url = m.group(1)
            break
    time.sleep(2)
    return url

if __name__ == "__main__":
    if REPORT_TYPE == "allure":
        # 生成报告目录
        pytest.main([ "-s", "-v",
                      "--alluredir=./report/temp",
                      "--clean-alluredir",
                      "./testcase",
                      "--junitxml=./report/results.xml" ])
        shutil.copy("./environment.xml", "./report/temp")

        # 启动并捕获 URL，再打开
        report_url = serve_allure("./report/temp")
        print("Opening Allure at:", report_url)
        webbrowser.open_new_tab(report_url)

    elif REPORT_TYPE == 'tm':
        pytest.main([
            '-vs',
            '--pytest-tmreport-name=testReport.html',
            '--pytest-tmreport-path=./report/tmreport'
        ])
        webbrowser.open_new_tab(
            os.path.abspath('./report/tmreport/testReport.html')
        )
