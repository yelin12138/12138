"""运行：python -m motorlab.demo；结果保存在 outputs/。"""
import argparse
import base64
import io
import json
import os
import tempfile
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'motorlab-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from .core import Parameters, Motor, Sensors, ResistanceEKF, torque


def run(duration=2., dt=.0002, seed=7):
    p = Parameters()
    plant, sensor, estimator = Motor(p), Sensors(seed), ResistanceEKF(p)
    records = []
    # 样本 y[k] 与区间 [k,k+1) 的电压匹配；先预测再用末端测量校正。
    for k in range(round(duration/dt)):
        t = k*dt
        voltage = 180*np.array([np.cos(2*np.pi*50*t), np.sin(2*np.pi*50*t)])
        rr = 1. + .3*np.clip((t-.7)/.6, 0, 1)
        load = 2. if t < 1.4 else 5.
        plant.step(voltage, load, rr, dt)
        sample = sensor.sample(voltage, plant.state)
        estimate = estimator.update(sample, dt)
        # 只有评价/记录部分接触真值。
        records.append([t+dt, rr, estimate, sample.speed, *sample.current,
                        torque(plant.state, p), np.linalg.norm(estimator.last_innovation)])
    return np.array(records)


def report(data, folder):
    folder.mkdir(parents=True, exist_ok=True)
    np.savetxt(folder/'trace.csv', data, delimiter=',',
               header='time,rr_true,rr_est,speed,ia,ib,torque,innovation', comments='')
    tail = data[:, 0] > data[-1, 0]-.2
    metrics = {'tail_relative_mae_percent': float(np.mean(abs(data[tail, 2]-data[tail, 1])/data[tail, 1])*100),
               'full_rmse_ohm': float(np.sqrt(np.mean((data[:, 2]-data[:, 1])**2))),
               'seed': 7, 'note': 'Simulation only; not hardware accuracy or FOC validation.'}
    (folder/'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
    t = data[:, 0]
    axes[0].plot(t, data[:, 1], label='True Rr (evaluation only)')
    axes[0].plot(t, data[:, 2], label='Estimated Rr')
    axes[0].set_ylabel('Resistance / ohm'); axes[0].legend()
    axes[1].plot(t, data[:, 3]*60/(2*np.pi)); axes[1].set_ylabel('Speed / rpm')
    axes[2].plot(t, data[:, 4]); axes[2].set_ylabel('Current alpha / A')
    axes[3].plot(t, data[:, 7]); axes[3].set_ylabel('Innovation / A'); axes[3].set_xlabel('Time / s')
    for ax in axes: ax.grid(alpha=.3)
    fig.tight_layout()
    image = io.BytesIO(); fig.savefig(image, format='png', dpi=120); plt.close(fig)
    encoded = base64.b64encode(image.getvalue()).decode()
    blocks = [
        ('电源', '三相平衡电压的 αβ 表示：uα=180 cos(2π50t)，uβ=180 sin(2π50t)。本阶段没有 FOC、PWM 或逆变器非理想。'),
        ('被测电机', '状态为 iα、iβ、ψrα、ψrβ、ωm。dψr/dt=(Rr/Lr)(Lm i−ψr)+pωm Jψr；di/dt=[u−Rs i−(Lm/Lr)dψr/dt]/Lσ；Lσ=Ls−Lm²/Lr。J 表示平面旋转90°算子。机械方程：惯量×dωm/dt=Te−TL−Bωm。'),
        ('采样', '只输出电压、电流、转速。加入独立高斯噪声，标准差分别为0.05 V、0.02 A、0.05 rad/s。尚未模拟 ADC、延迟和偏置。'),
        ('EKF辨识', '状态为估计电流、估计磁链与 Rr。根据采样电压和转速预测电流，以测量电流减预测电流形成创新，再更新状态与协方差。其他参数视为已知，不读取真实磁链与电阻。'),
        ('独立评价', '只有本模块读取真实 Rr。0.7–1.3秒电阻由1增至1.3 Ω；1.4秒负载由2增至5 N·m。展示末0.2秒相对绝对误差均值和全程RMSE；前者不代表所有工况精度。')]
    cards = ''.join(f'<button onclick="show({i})">{name}</button>'+(' → ' if i<4 else '') for i,(name,_) in enumerate(blocks))
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>异步电机辨识实验 01</title>
<style>body{font:17px system-ui;max-width:1100px;margin:36px auto;padding:0 20px;background:#f4f7fc;color:#18304a}button{padding:18px 12px;background:#fff;border:2px solid #2876bc;border-radius:8px;cursor:pointer}article{background:white;padding:24px;margin:20px 0;line-height:1.8}img{width:100%}</style>
<h1>实验 01：只通过采样识别转子电阻</h1><p>这是离线数值仿真报告，尚非实时控制系统。点击模块查看模型与边界。</p>'''
    html += '<nav>'+cards+'</nav><article id="detail"></article>'
    html += f'<p>末0.2秒电阻相对绝对误差均值：{metrics["tail_relative_mae_percent"]:.2f}% · 全程 RMSE：{metrics["full_rmse_ohm"]:.4f} Ω</p>'
    html += f'<img alt="电阻、转速、电流和创新曲线" src="data:image/png;base64,{encoded}">'
    html += '<script>const blocks='+json.dumps(blocks, ensure_ascii=False)+';function show(i){document.getElementById("detail").textContent=blocks[i][1]}show(1)</script></html>'
    (folder/'report.html').write_text(html, encoding='utf-8')
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='outputs')
    args = parser.parse_args()
    print(json.dumps(report(run(), Path(args.output)), indent=2))
