"""可选浏览器验收，需 playwright 和 Chromium；不属于运行时依赖。"""
import json
from pathlib import Path
import sys
import threading
import time
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motorlab.app import WorkbenchServer
from playwright.sync_api import sync_playwright


def main():
    output = Path('outputs')
    output.mkdir(exist_ok=True)
    server = WorkbenchServer(('127.0.0.1', 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    errors = []
    def state():
        with urlopen(base+'/api/state') as response:
            return json.load(response)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1600, 'height': 1050}, device_scale_factor=1)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            page.wait_for_function('!document.getElementById("stepButton").disabled')
            assert page.locator('#versionBadge').inner_text() == 'v0.4.0 · 已连接'
            assert page.locator('#motorForm').is_visible()
            assert page.locator('#motorCanvas').bounding_box()['width'] > 600
            assert page.locator('#motorCanvas').bounding_box()['y'] < 400
            # 首页参数表实际重建物理电机，且与详细参数表同步。
            page.fill('#motorInput_motor_rs', '2')
            page.fill('#motorInput_motor_poles', '3')
            page.locator('#motorForm button[type="submit"]').click()
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            assert state()['motor_parameters']['rs'] == 2
            assert state()['motor_parameters']['poles'] == 3
            assert page.locator('[name="motor_rs"]').input_value() == '2'
            page.fill('#motorInput_motor_rs', '1.4')
            page.fill('#motorInput_motor_poles', '2')
            page.locator('#motorForm button[type="submit"]').click()
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            page.click('#stepButton')
            page.wait_for_function('document.getElementById("sampleNumber").textContent.includes("1 次")')
            assert state()['snapshot']['sample_index'] == 1
            page.click('#batchButton')
            page.wait_for_function('!document.getElementById("batchButton").disabled')
            assert state()['snapshot']['sample_index'] == 101
            page.locator('.diagram-edge[data-signal="u_alpha"]').first.press('Enter')
            assert '区间平均端电压 α' in page.locator('#probeTitle').inner_text()
            assert page.locator('.trace-chip').filter(has_text='区间平均端电压 α').count() == 1
            page.click('#runButton')
            page.wait_for_timeout(250)
            page.click('#runButton')
            page.wait_for_function('!document.getElementById("batchButton").disabled')
            paused = state()['snapshot']['time']
            page.wait_for_timeout(200)
            assert state()['snapshot']['time'] == paused
            page.locator('#timeCursor').evaluate('(el)=>{el.value="5";el.dispatchEvent(new Event("input",{bubbles:true}));}')
            page.wait_for_function('document.getElementById("viewMode").textContent.includes("历史")')
            assert '0.0025' in page.locator('#cursorTime').inner_text()
            page.click('#latestButton')
            page.click('#zoomIn')
            assert '125%' in page.locator('#zoomValue').inner_text()
            page.click('#fitDiagram')
            page.reload()
            page.wait_for_function('!document.getElementById("stepButton").disabled')
            assert int(page.locator('#timeCursor').get_attribute('max')) >= 100
            page.wait_for_function('document.getElementById("motorCanvas").dataset.renderer')
            assert page.locator('#motorCanvas').get_attribute('data-renderer') in ['WebGL','Canvas3D']
            page.click('#expandMotor')
            page.wait_for_timeout(150)
            assert page.locator('#motorDialog').is_visible()
            page.locator('#motorDialog').screenshot(path=str(output/'motor-3d.png'))
            page.click('#closeMotor')
            page.wait_for_selector('#motorHost canvas')
            assert page.locator('#motorHost canvas').count()==1
            # 顶部时序控制直接修改求解配置，不只改变显示。
            page.fill('#quickSample','250')
            page.locator('#timingForm button').click()
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            assert state()['config']['sample_time']==.00025
            page.click('#stepButton')
            page.wait_for_function('!document.getElementById("stepButton").disabled')
            assert state()['snapshot']['time']==.00025
            page.fill('#quickSample','500')
            page.locator('#timingForm button').click()
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            # 参数修改后原子重置，并在完整运行结束后重新打开模型。
            page.click('#settingsTab')
            page.locator('details.motor-parameters').evaluate('(el)=>el.open=true')
            page.locator('[name="motor_rs"]').fill('2')
            page.locator('[name="motor_poles"]').fill('3')
            page.locator('#settingsForm button[type="submit"]').click()
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            assert state()['motor_parameters']['rs']==2
            assert state()['motor_parameters']['poles']==3
            page.locator('details.motor-parameters').evaluate('(el)=>el.open=true')
            page.locator('[name="motor_rs"]').fill('1.4')
            page.locator('[name="motor_poles"]').fill('2')
            page.locator('[name="mode"]').select_option('adaptive')
            page.locator('#settingsForm button[type="submit"]').click()
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            assert state()['config']['mode'] == 'adaptive'
            assert state()['snapshot']['time'] == 0
            page.click('#modelTab')
            page.select_option('#playSpeed', '5')
            page.click('#runButton')
            page.wait_for_function('document.getElementById("statusText").textContent==="实验完成"', timeout=60000)
            assert state()['done']
            page.wait_for_function('Math.abs(Number(document.getElementById("motorCanvas").dataset.sampleTime)-4)<1e-9')
            assert abs(float(page.locator('#motorCanvas').get_attribute('data-rotor-angle'))-state()['snapshot']['rotor_angle'])<1e-9
            page.wait_for_function('document.getElementById("pwmStatus").textContent.includes("事件对齐")')
            page.wait_for_function('Number(document.getElementById("pwmCanvas").dataset.windowEnd)===4')
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(output/'overview-v0.4.png'))
            page.screenshot(path=str(output/'workbench.png'), full_page=True)
            page.locator('.pwm-area').screenshot(path=str(output/'svpwm-scope.png'))
            page.click('#expandMotor')
            page.wait_for_timeout(100)
            page.locator('#motorDialog').screenshot(path=str(output/'motor-3d.png'))
            page.click('#closeMotor')
            page.wait_for_selector('#motorHost canvas')
            with urlopen(base+'/api/config') as response:
                metadata = json.load(response)
            # 遍历所有层级，确认节点、公式、信号值渲染无 JS 异常。
            for identifier, diagram in metadata['diagrams'].items():
                page.locator('.tree-button').filter(has_text=diagram['title']).first.click()
                assert page.locator('#diagramTitle').inner_text() == diagram['title']
                assert page.locator('.diagram-node').count() == len(diagram['nodes'])
            foc = next((d for d in metadata['diagrams'].values() if '电流' in d['title'] and 'PI' in d['title']), None)
            if foc:
                page.locator('.tree-button').filter(has_text=foc['title']).first.click()
                page.screenshot(path=str(output/'workbench-detail.png'), full_page=True)
            with page.expect_download() as downloaded:
                page.click('.export-button')
            download = downloaded.value
            download.save_as(str(output/'browser-export.csv'))
            lines = (output/'browser-export.csv').read_text(encoding='utf-8-sig').splitlines()
            assert len(lines) == int(state()['snapshot']['sample_index'])+1
            # 运行中的重置必须等待批次结束，之后不再接纳旧数据。
            page.click('#resetButton')
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            page.click('#runButton')
            page.click('#resetButton')
            page.wait_for_function('!document.getElementById("resetButton").disabled')
            page.wait_for_timeout(200)
            assert state()['snapshot']['time'] == 0
            # A bookmark carrying a different build must not control this engine.
            mismatch = browser.new_page()
            mismatch.goto(base+'/?build=obsolete')
            mismatch.wait_for_selector('#errorBanner:not([hidden])')
            assert '版本不一致' in mismatch.locator('#errorText').inner_text()
            assert mismatch.locator('#stepButton').is_disabled()
            mismatch.close()
            # Small screens keep the primary motor view on the main page.
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('window.scrollTo(0,0)')
            page.wait_for_timeout(150)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), page.evaluate('[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.id,e.className,e.getBoundingClientRect().right]).slice(0,20)')
            assert page.locator('#motorCanvas').bounding_box()['width'] > 300
            page.screenshot(path=str(output/'overview-mobile-v0.4.png'), full_page=True)
            assert not errors, errors
            assert page.locator('#errorBanner').is_hidden()
            browser.close()
            print(json.dumps({'browser': 'Chromium', 'diagrams': len(metadata['diagrams']), 'signals':len(metadata['signals']), 'result':'passed', 'checks':'SVPWM trace, 3D, top timing, motor parameters, history, control, export', 'javascript_errors':errors}, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
