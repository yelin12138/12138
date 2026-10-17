"""固定连接的分层物理框图；signal 必须对应真实遥测，truth 仅用于评价。"""


def _s(label, unit, category):
    return dict(label=label, unit=unit, category=category)


SIGNALS = {}
for _category, _items in {
    "timing": [
        ("time", "仿真时间", "s"), ("sample_time", "采样周期 Ts", "s"),
        ("integration_step", "积分步长 h", "s"), ("sample_index", "采样序号 k", "次"),
        ("sampled_at", "本次测量对应时刻", "s"), ("estimate_time", "本次估计对应时刻", "s"),
        ("control_start", "控制保持区间起点", "s"), ("control_end", "控制保持区间终点", "s"),
        ("sensor_delay", "传感器延迟", "s"), ("control_sampled_at", "控制输入采样时刻", "s"),
    ],
    "measurement": [
        ("speed_rpm", "测量转速 n", "rpm"), ("speed_measured", "测量机械角速度", "rad/s"),
        ("i_alpha", "测量电流 iα", "A"), ("i_beta", "测量电流 iβ", "A"),
        ("u_alpha_measured", "测量电压 uα", "V"), ("u_beta_measured", "测量电压 uβ", "V"),
        ("id", "控制输入电流 id", "A"), ("iq", "控制输入电流 iq", "A"),
        ("control_i_alpha", "本拍控制输入 iα", "A"), ("control_i_beta", "本拍控制输入 iβ", "A"),
        ("control_speed", "本拍控制输入机械速度", "rad/s"),
        ("control_speed_rpm", "本拍控制输入转速", "rpm"),
        ("id_sample", "最新采样电流 id", "A"), ("iq_sample", "最新采样电流 iq", "A"),
        ("current_magnitude", "测量电流矢量幅值", "A"),
    ],
    "control": [
        ("speed_ref_rpm", "目标转速 n*", "rpm"), ("id_ref", "励磁电流给定 id*", "A"),
        ("iq_ref", "转矩电流给定 iq*", "A"), ("speed_error", "控制输入速度误差", "rad/s"),
        ("speed_error_rpm", "最新采样速度误差", "rpm"),
        ("id_error", "d 轴电流误差", "A"), ("iq_error", "q 轴电流误差", "A"),
        ("speed_p", "速度 PI 比例项", "A"), ("speed_i", "速度 PI 积分项", "A"),
        ("speed_unsat", "速度 PI 限幅前输出", "A"),
        ("id_p", "d 轴 PI 比例项", "V"), ("id_i", "d 轴 PI 积分项", "V"),
        ("iq_p", "q 轴 PI 比例项", "V"), ("iq_i", "q 轴 PI 积分项", "V"),
        ("vd_pi", "d 轴 PI 输出", "V"), ("vq_pi", "q 轴 PI 输出", "V"),
        ("vd_ff", "d 轴前馈电压", "V"), ("vq_ff", "q 轴前馈电压", "V"),
        ("vd_unsat", "限幅前 d 轴电压", "V"), ("vq_unsat", "限幅前 q 轴电压", "V"),
        ("vd", "限幅后 d 轴电压", "V"), ("vq", "限幅后 q 轴电压", "V"),
        ("u_alpha", "施加电压 uα", "V"), ("u_beta", "施加电压 uβ", "V"),
        ("voltage_magnitude", "施加电压矢量幅值", "V"),
        ("voltage_limit", "电压矢量幅值上限", "V"),
        ("voltage_saturated", "电压饱和标志", "0/1"),
        ("current_limit", "dq 电流指令幅值上限", "A"), ("iq_limit", "q 轴电流指令上限", "A"),
        ("theta", "区间末同步角 θe", "rad"), ("voltage_theta", "电压变换中点角", "rad"),
        ("control_theta", "本拍 Park 变换角", "rad"),
        ("rotor_electrical_speed", "本拍转子电角速度 pωm", "rad/s"),
        ("slip", "估计滑差角频率", "rad/s"), ("omega_e", "同步电角速度", "rad/s"),
        ("rr_control", "控制器采用的转子电阻", "Ω"),
    ],
    "estimate": [
        ("flux_est", "控制器磁链估计 ψ̂r", "Wb"), ("dflux_est", "控制器磁链变化率", "Wb/s"),
        ("rr_est", "辨识转子电阻 R̂r", "Ω"), ("rr_std", "EKF 电阻标准差", "Ω"),
        ("innovation", "电流新息范数", "A"),
        ("innovation_alpha", "α 轴电流新息", "A"), ("innovation_beta", "β 轴电流新息", "A"),
        ("i_alpha_est", "EKF 电流估计 îα", "A"), ("i_beta_est", "EKF 电流估计 îβ", "A"),
        ("flux_alpha_est", "EKF 磁链估计 ψ̂rα", "Wb"),
        ("flux_beta_est", "EKF 磁链估计 ψ̂rβ", "Wb"),
    ],
    "truth": [
        ("rr_true", "真实转子电阻（仅评价）", "Ω"),
        ("rr_true_at_estimate", "估计对应时刻真实电阻（仅评价）", "Ω"),
        ("rr_error_pct", "当前电阻相对误差（仅评价）", "%"),
        ("rr_aligned_error_pct", "时间对齐电阻相对误差（仅评价）", "%"),
        ("rr_signed_error", "有符号电阻误差（仅评价）", "Ω"),
        ("speed_true_rpm", "真实转速（仅评价）", "rpm"),
        ("speed_true", "真实机械角速度（仅评价）", "rad/s"),
        ("i_alpha_true", "真实 iα（仅评价）", "A"), ("i_beta_true", "真实 iβ（仅评价）", "A"),
        ("flux_alpha_true", "真实 ψrα（仅评价）", "Wb"),
        ("flux_beta_true", "真实 ψrβ（仅评价）", "Wb"),
        ("flux_d_true", "真实 ψrd（仅评价）", "Wb"), ("flux_q_true", "真实 ψrq（仅评价）", "Wb"),
        ("flux_true", "真实磁链幅值（仅评价）", "Wb"),
        ("flux_angle_error_deg", "真实磁链偏角（仅评价）", "°"),
        ("torque", "真实电磁转矩（仅评价）", "N·m"),
        ("load", "真实负载转矩（仅评价）", "N·m"),
        ("friction_torque", "真实摩擦转矩（仅评价）", "N·m"),
        ("acceleration", "真实机械角加速度（仅评价）", "rad/s²"),
        ("di_alpha", "真实 diα/dt（仅评价）", "A/s"),
        ("di_beta", "真实 diβ/dt（仅评价）", "A/s"),
        ("dflux_alpha", "真实 dψrα/dt（仅评价）", "Wb/s"),
        ("dflux_beta", "真实 dψrβ/dt（仅评价）", "Wb/s"),
    ],
}.items():
    for _key, _label, _unit in _items:
        SIGNALS[_key] = _s(_label, _unit, _category)


def N(id, label, kind, x, y, signal=None, child=None, w=160, h=66):
    result = dict(id=id, label=label, kind=kind, x=x, y=y, w=w, h=h)
    if signal:
        result["signal"] = signal
    if child:
        result["child"] = child
    return result


def E(start, end, label="", signal=None):
    result = {"from": start, "to": end}
    if label:
        result["label"] = label
    if signal:
        result["signal"] = signal
    return result


def D(title, description, formula, source, nodes, edges, width=1100, height=550):
    return dict(title=title, description=description, formula=formula, source=source,
                nodes=nodes, edges=edges, width=width, height=height)


DIAGRAMS = {
    "system": D(
        "异步电机在线辨识实验台",
        "点击进入各层模块，探针显示实际求解信号。控制器和辨识器通过采样接口获取数据。真实电阻、磁链和转矩用于被测对象与评价；理想参数参考模式是单独标注的仿真基准。",
        "对象：ẋ = f(x,u,Rr,TL)\n测量：y[k] = Q(h(x(kTs)) + b + n[k])，可附加延迟\n辨识：x̂[k],R̂r[k] = EKF(采样数据)\nFOC：速度 PI → d/q 电流 PI → 电压 → 电机\n仿真时间由求解器推进，与界面刷新和墙钟时间区分。",
        "motorlab/simulation.py · Simulation.step()",
        [N("reference", "转速给定", "source", 20, 145, "speed_ref_rpm"),
         N("foc", "FOC\n速度环 + 电流双环", "model", 230, 145, child="foc", w=185),
         N("drive", "平均电压逆变器", "model", 490, 145, child="inverter", w=180),
         N("motor", "被测异步电机", "model", 750, 145, child="motor", w=180),
         N("load", "机械负载", "source", 950, 40, "load", w=140),
         N("thermal", "真实电阻工况", "source", 950, 255, "rr_true", w=140),
         N("sensor", "传感器 / 采样", "model", 750, 360, child="sensors", w=180),
         N("ekf", "电阻在线辨识", "model", 470, 360, "rr_est", "ekf", w=190),
         N("evaluation", "独立误差评价", "model", 180, 490, "rr_error_pct", "evaluation", w=190),
         N("clock", "离散采样时钟", "model", 20, 20, "time", "timing", w=180)],
        [E("reference", "foc", "n*", "speed_ref_rpm"), E("foc", "drive", "ud / uq：探针 ud", "vd"),
         E("drive", "motor", "uαβ：探针 α", "u_alpha"), E("load", "motor", "TL", "load"),
         E("thermal", "motor", "Rr", "rr_true"), E("motor", "sensor", "电流 / 转速"),
         E("drive", "sensor", "端电压 α", "u_alpha"), E("sensor", "foc", "电流 / 转速反馈"),
         E("sensor", "ekf", "采样电流 α", "i_alpha"),
         E("ekf", "foc", "可选参数补偿", "rr_control"), E("ekf", "evaluation", "R̂r", "rr_est"),
         E("thermal", "evaluation", "真实值仅评价", "rr_true")], width=1120, height=590),
    "timing": D(
        "采样、控制与积分时间轴",
        "一个采样周期包含多个电机积分子步。控制输出在区间内保持；区间末生成新采样并更新辨识器。有传感器延迟时，估计时刻会落后于仿真时刻。",
        "tₖ = kTs；Ts = N h\n采样 y[k] → 控制 u[k] → 积分至 tₖ₊₁ → 新采样 → EKF\nu(t) = u[k]，t ∈ [tₖ,tₖ₊₁)（零阶保持）\nFIFO 延迟 D 拍：稳定填充后采样时刻 = 当前时刻 − D Ts\n电压样本对应刚结束区间；EKF 使用相邻速度样本均值近似区间速度。",
        "motorlab/simulation.py · Simulation.step()",
        [N("sample", "当前可用采样", "source", 20, 100, "control_sampled_at"),
         N("control", "计算 FOC 输出", "model", 240, 100, child="foc"),
         N("hold", "保持 u[k]", "hold", 460, 100),
         N("integrate", "N 个 RK4 子步", "integrator", 680, 100, "integration_step"),
         N("new", "区间末采样", "model", 900, 100, "sampled_at", "sensors"),
         N("delay", "传感器 FIFO", "hold", 900, 330, "sensor_delay"),
         N("ekf", "新采样 → EKF", "model", 680, 330, "estimate_time", "ekf"),
         N("period", "采样周期 Ts", "source", 240, 330, "sample_time"),
         N("time", "当前仿真时刻", "source", 20, 330, "time")],
        [E("sample", "control"), E("control", "hold"), E("hold", "integrate"),
         E("integrate", "new"), E("new", "delay"), E("delay", "ekf"),
         E("delay", "sample", "下一拍反馈")], height=470),
    "foc": D(
        "间接转子磁场定向 FOC",
        "速度外环给出 iq*；d 轴电流建立磁场。电流内环生成电压，磁链估计与滑差确定同步角。使用 PI 控制，即 PID 的 Kd=0。显示的 id/iq 是本拍控制输入，最新区间末采样另有探针。",
        "eω = ω* − ωmeas；iq* = clip(PIω(eω), ±Iq,max)\ned = id* − id；eq = iq* − iq\nudq = 限幅(PIdq(edq) + 解耦前馈)\nωe = pωmeas + ωsl；θe = ∫ωe dt\n额定励磁给定在启动时爬升，速度给定在励磁后爬升。",
        "motorlab/control.py · FOCController.update()",
        [N("speed", "速度 PI 外环", "model", 20, 60, "iq_ref", "speed_pi", w=180),
         N("dref", "励磁电流给定", "source", 20, 245, "id_ref", w=180),
         N("qloop", "q 轴电流 PI", "model", 285, 60, "vq_pi", "iq_pi", w=175),
         N("dloop", "d 轴电流 PI", "model", 285, 245, "vd_pi", "id_pi", w=175),
         N("decouple", "解耦 + 电压限幅", "model", 565, 150, child="decoupling", w=185),
         N("inverse", "逆 Park 变换", "transform", 865, 150, child="transforms", w=175),
         N("feedback", "采样电流 → dq", "transform", 285, 425, child="transforms", w=175),
         N("angle", "磁链 / 滑差 / 角度", "model", 565, 425, "theta", "angle", w=185)],
        [E("speed", "qloop", "iq*", "iq_ref"), E("dref", "dloop", "id*", "id_ref"),
         E("qloop", "decouple", "uq,PI"), E("dloop", "decouple", "ud,PI"),
         E("decouple", "inverse", "ud / uq"), E("feedback", "dloop", "id", "id"),
         E("feedback", "qloop", "iq", "iq"), E("feedback", "angle", "id / iq"),
         E("angle", "feedback", "θe"), E("angle", "inverse", "θe"),
         E("angle", "decouple", "ωe / ψ̂r")], height=540),
    "angle": D(
        "磁链估计、滑差与同步角",
        "控制器只使用配置或补偿电阻、测量电流和测量转速。励磁初期关闭滑差计算，磁链除数使用 0.08 Wb 下限。真实磁链不参与计算。",
        "a = Rr,control/Lr\ndψ̂r/dt = a(Lm id − ψ̂r)\nψ̂r[k+1] = max(0, ψ̂r[k] + Ts dψ̂r/dt)\nωsl = a Lm iq/max(ψ̂r[k+1], 0.08)，前 0.12 s 置零\nωe = pωmeas + ωsl\nθe[k+1] = wrap(θe[k] + Ts ωe)\n电压逆变换使用中点角 θv = θe[k] + Ts ωe/2。",
        "motorlab/control.py · FOCController.update(): flux, slip, theta",
        [N("rr", "控制器电阻参数", "source", 235, 35, "rr_control"),
         N("invtr", "÷ Lr", "gain", 450, 35),
         N("id", "控制输入 id", "source", 20, 205, "id"),
         N("lm", "× Lm", "gain", 235, 205),
         N("sum", "+ −\nLm id − ψ̂r", "sum", 450, 205),
         N("rate", "× Rr/Lr", "product", 665, 205, "dflux_est"),
         N("flux", "∫ 磁链状态", "integrator", 880, 205, "flux_est"),
         N("slip", "滑差计算 / 保护", "product", 880, 35, "slip"),
         N("speed", "测量机械速度", "source", 20, 390, "control_speed"),
         N("poles", "× 极对数 p", "gain", 235, 390, "rotor_electrical_speed"),
         N("omega", "+\n同步电角速度", "sum", 665, 390, "omega_e"),
         N("theta", "∫ → 角度回绕", "integrator", 880, 390, "theta")],
        [E("rr", "invtr", "Rr", "rr_control"), E("invtr", "rate"), E("id", "lm", "id", "id"),
         E("lm", "sum", "+"), E("flux", "sum", "−"), E("sum", "rate"),
         E("rate", "flux", "dψ̂r/dt", "dflux_est"),
         E("invtr", "slip", "a"), E("flux", "slip", "ψ̂r"),
         E("speed", "poles", "ωm", "control_speed"),
         E("poles", "omega", "pωm", "rotor_electrical_speed"),
         E("slip", "omega", "ωsl", "slip"), E("omega", "theta", "ωe", "omega_e")]),
    "decoupling": D(
        "电流环解耦前馈与电压限幅",
        "旋转坐标系产生交叉耦合电压。前馈使用测量电流与控制器磁链估计。直流母线决定电压边界，限幅残差反馈给积分器。",
        "Lσ = Ls − Lm²/Lr；kr = Lm/Lr\nud,ff = −ωe Lσ iq + kr dψ̂r/dt\nuq,ff = ωe(Lσ id + kr ψ̂r)\nudq,raw = udq,PI + udq,ff\nudq = udq,raw · min(1, Umax/‖udq,raw‖)\nUmax = Vdc/√3；对应平均电压模型的线性调制范围。",
        "motorlab/control.py · FOCController.update(): vd_ff, vq_ff, factor",
        [N("dpi", "d 轴 PI", "source", 25, 65, "vd_pi", "id_pi"),
         N("qpi", "q 轴 PI", "source", 25, 280, "vq_pi", "iq_pi"),
         N("dff", "d 轴前馈", "product", 245, 175, "vd_ff"),
         N("qff", "q 轴前馈", "product", 245, 390, "vq_ff"),
         N("dsum", "+\nPI + 前馈", "sum", 465, 65, "vd_unsat"),
         N("qsum", "+\nPI + 前馈", "sum", 465, 280, "vq_unsat"),
         N("limit", "矢量电压限幅", "saturation", 685, 175, "voltage_saturated"),
         N("dout", "输出 ud", "output", 905, 65, "vd"),
         N("qout", "输出 uq", "output", 905, 280, "vq")],
        [E("dpi", "dsum"), E("dff", "dsum"), E("qpi", "qsum"), E("qff", "qsum"),
         E("dsum", "limit"), E("qsum", "limit"), E("limit", "dout"), E("limit", "qout")],
        height=500),
    "transforms": D(
        "αβ 与 dq 坐标变换",
        "幅值不变 Clarke 约定，零序为零。电机直接求解 αβ 分量；三相公式说明物理对应。电流 Park 使用区间开始角，电压逆 Park 使用区间中点角，不能把区间末 θ 当作本拍所有信号的共同角度。",
        "iα = (2/3)(ia − ib/2 − ic/2)\niβ = (√3/3)(ib − ic)；ia+ib+ic=0\nid = iα cosθ + iβ sinθ\niq = −iα sinθ + iβ cosθ\nuα = ud cosθv − uq sinθv\nuβ = ud sinθv + uq cosθv\n最新 id_sample/iq_sample 用区间末 θ 与最新可用电流计算。",
        "motorlab/control.py · park(), inverse_park()",
        [N("a", "控制输入 iα", "source", 15, 55, "control_i_alpha"),
         N("b", "控制输入 iβ", "source", 15, 245, "control_i_beta"),
         N("park", "乘法 / 求和\nPark 矩阵", "transform", 225, 155, w=180),
         N("park_theta", "本拍 Park 角 θ", "source", 225, 410, "control_theta"),
         N("d", "反馈 id", "output", 435, 55, "id"),
         N("q", "反馈 iq", "output", 435, 245, "iq"),
         N("vd", "输入 ud", "source", 645, 55, "vd"),
         N("vq", "输入 uq", "source", 645, 245, "vq"),
         N("theta", "电压中点角 θv", "source", 645, 410, "voltage_theta"),
         N("inverse", "逆 Park 矩阵", "transform", 865, 155, w=180),
         N("ua", "施加 uα", "output", 865, 410, "u_alpha"),
         N("ub", "施加 uβ", "output", 865, 530, "u_beta")],
        [E("a", "park", "iα", "control_i_alpha"), E("b", "park", "iβ", "control_i_beta"),
         E("park_theta", "park", "θ", "control_theta"), E("park", "d", "id", "id"),
         E("park", "q", "iq", "iq"), E("vd", "inverse", "ud", "vd"),
         E("vq", "inverse", "uq", "vq"), E("theta", "inverse", "θv", "voltage_theta"),
         E("inverse", "ua", "uα", "u_alpha"), E("inverse", "ub", "uβ", "u_beta")], height=640),
    "inverter": D(
        "平均电压逆变器",
        "电压矢量经过母线限制与逆 Park 后，在一个采样周期内保持。当前没有开关级 SVPWM、死区、器件压降或母线纹波。",
        "Umax = Vdc/√3\nuαβ[k] = 逆 Park(udq[k], θv[k])\nuαβ(t) = uαβ[k]，t ∈ [kTs,(k+1)Ts)\n传感器测量施加的平均端电压，而非下一拍电压指令。",
        "motorlab/control.py · FOCController.update(); motorlab/simulation.py · step()",
        [N("d", "限幅后 ud", "source", 30, 95, "vd"),
         N("q", "限幅后 uq", "source", 30, 285, "vq"),
         N("inverse", "逆 Park 变换", "transform", 290, 190, child="transforms", w=180),
         N("hold", "零阶保持 Ts", "hold", 560, 190, "sample_time"),
         N("ua", "端电压 uα", "output", 830, 95, "u_alpha"),
         N("ub", "端电压 uβ", "output", 830, 285, "u_beta")],
        [E("d", "inverse"), E("q", "inverse"), E("inverse", "hold"),
         E("hold", "ua"), E("hold", "ub")], height=440),
    "motor": D(
        "异步电机：电气与机械耦合",
        "所有转子参数折算到定子侧，采用 SI 单位与幅值不变坐标变换。内部状态 [iα,iβ,ψrα,ψrβ,ωm] 联合 RK4 积分。真实参数与内部磁链不进入正常辨识和控制接口。",
        "Lσ = Ls − Lm²/Lr\ndψr/dt = (Rr/Lr)(Lm i − ψr) + pωm J₂ψr\ndi/dt = [u − Rs i − (Lm/Lr)dψr/dt]/Lσ\nTe = (3/2)p(Lm/Lr)(ψrα iβ − ψrβ iα)\ndωm/dt = (Te − TL − Bωm)/J\nJ₂[a,b]ᵀ = [−b,a]ᵀ；p 为极对数。",
        "motorlab/core.py · electrical(), torque(), Motor.step()",
        [N("u", "施加电压 uαβ", "source", 25, 130),
         N("electrical", "电气状态方程", "model", 280, 130, child="electrical", w=190),
         N("torque", "磁链 × 电流\n电磁转矩", "model", 560, 130, "torque", "torque", w=190),
         N("mechanics", "机械运动方程", "model", 840, 130, child="mechanics", w=190),
         N("rr", "真实 Rr", "source", 280, 350, "rr_true"),
         N("load", "负载 TL", "source", 840, 350, "load"),
         N("sensor", "仅经传感器输出", "model", 560, 350, child="sensors", w=190)],
        [E("u", "electrical"), E("rr", "electrical", "对象参数"),
         E("electrical", "torque", "内部 i / ψr"), E("torque", "mechanics", "Te"),
         E("mechanics", "electrical", "内部 ωm"), E("load", "mechanics", "TL"),
         E("electrical", "sensor", "电流"), E("mechanics", "sensor", "转速")]),
    "electrical": D(
        "αβ 电气方程：相互反馈的积分状态",
        "电压改变电流，电流建立转子磁链；变化的磁链产生感应电压，再影响电流。向量线同时代表 α、β 分量，两组方程在同一 RK4 子步内联合求解。",
        "dψr/dt = (Rr/Lr)(Lm i − ψr) + pωm J₂ψr\ndi/dt = [u − Rs i − (Lm/Lr)dψr/dt]/Lσ\nLσ = Ls − Lm²/Lr > 0\n对象内部探针仅用于查看物理过程，不开放给辨识器。",
        "motorlab/core.py · electrical()",
        [N("u", "输入 uαβ", "source", 30, 110),
         N("current", "电流微分方程", "model", 280, 110, child="current_dynamics", w=190),
         N("int_i", "∫ iαβ", "integrator", 570, 110, "i_alpha_true"),
         N("flux", "磁链微分方程", "model", 570, 335, child="flux_dynamics", w=190),
         N("int_flux", "∫ ψrαβ", "integrator", 850, 335, "flux_alpha_true"),
         N("speed", "内部机械速度", "source", 280, 335, "speed_true")],
        [E("u", "current"), E("current", "int_i", "di/dt"), E("int_i", "current", "i"),
         E("int_i", "flux", "i"), E("speed", "flux", "pωm"), E("flux", "int_flux", "dψr/dt"),
         E("int_flux", "flux", "ψr"), E("flux", "current", "感应电压项")], height=490),
    "flux_dynamics": D(
        "转子磁链：增益、求和与积分",
        "电阻项描述磁链建立与衰减；旋转项描述转子运动在静止坐标系中的作用。向量框图显示两分量共同结构，探针标注所显示的具体分量。",
        "a = Rr/Lr；J₂ψr = [−ψrβ,ψrα]ᵀ\ndψrα/dt = a(Lm iα − ψrα) − pωm ψrβ\ndψrβ/dt = a(Lm iβ − ψrβ) + pωm ψrα\nψr = ∫(dψr/dt)dt",
        "motorlab/core.py · electrical(): dflux",
        [N("i", "内部电流 iαβ", "source", 20, 65, "i_alpha_true"),
         N("lm", "× Lm", "gain", 235, 65),
         N("diff", "+ −\nLm i − ψr", "sum", 450, 65),
         N("a", "× Rr/Lr", "gain", 665, 65),
         N("rot", "J₂：交换 / 取负", "transform", 235, 300),
         N("speed", "× pωm", "product", 450, 300),
         N("sum", "+\n磁链变化率", "sum", 665, 300, "dflux_alpha"),
         N("integral", "∫\n转子磁链 ψr", "integrator", 880, 300, "flux_alpha_true")],
        [E("i", "lm"), E("lm", "diff", "+"), E("integral", "diff", "− ψr"),
         E("diff", "a"), E("a", "sum"), E("integral", "rot", "ψr"),
         E("rot", "speed"), E("speed", "sum"), E("sum", "integral", "dψr/dt")], height=470),
    "current_dynamics": D(
        "定子电流：电压平衡与漏感积分",
        "施加电压扣除电阻压降与感应电压，剩余电压作用于漏感，决定电流变化率。各算子同时作用于 α、β 分量。",
        "u = Rs i + Lσ di/dt + (Lm/Lr)dψr/dt\ndi/dt = [u − Rs i − (Lm/Lr)dψr/dt]/Lσ\nLσ = Ls − Lm²/Lr\n电压 V / 电感 H = 电流变化率 A/s。",
        "motorlab/core.py · electrical(): dcurrent",
        [N("u", "端电压 uαβ", "source", 30, 55, "u_alpha"),
         N("rs", "内部 i × Rs", "gain", 30, 225),
         N("emf", "dψr/dt × Lm/Lr", "gain", 30, 395, child="flux_dynamics", w=190),
         N("sum", "+ − −\n漏感两端电压", "sum", 340, 225, w=190),
         N("leak", "÷ Lσ", "gain", 630, 225, "di_alpha"),
         N("int", "∫\n内部电流 iαβ", "integrator", 875, 225, "i_alpha_true")],
        [E("u", "sum", "+"), E("rs", "sum", "−"), E("emf", "sum", "−"),
         E("sum", "leak"), E("leak", "int", "di/dt"), E("int", "rs", "i")]),
    "torque": D(
        "电磁转矩：磁链与电流的叉积",
        "交叉乘积相减给出电磁转矩。FOC 定向正确时 ψrq≈0，转矩近似只随 iq 调节；偏离时 id 也进入转矩表达式。真实转矩仅用于物理观察与评价。",
        "Te = K(ψrα iβ − ψrβ iα)；K = (3/2)pLm/Lr\n等价 dq 形式：Te = K(ψrd iq − ψrq id)\n理想定向：ψrq = 0 ⇒ Te = Kψr iq\n若磁链相对控制 d 轴偏角为 δ：\nTe = Kψr(iq cosδ − id sinδ)",
        "motorlab/core.py · torque()",
        [N("first", "ψrα × iβ", "product", 60, 90),
         N("second", "ψrβ × iα", "product", 60, 300),
         N("diff", "+ −\n叉积", "sum", 360, 195),
         N("gain", "× (3/2)p Lm/Lr", "gain", 620, 195, w=190),
         N("out", "电磁转矩 Te", "output", 900, 195, "torque")],
        [E("first", "diff", "+"), E("second", "diff", "−"), E("diff", "gain"), E("gain", "out")],
        height=440),
    "mechanics": D(
        "机械运动：转矩平衡",
        "电磁转矩减去负载与黏性摩擦，得到加速转矩。除以转动惯量后积分为机械角速度。真实速度经过传感器才能用于正常控制。",
        "J dωm/dt = Te − TL − Bωm\nωm = ∫[(Te − TL − Bωm)/J]dt\nn = 60ωm/(2π) [rpm]\n负载增加 → 加速转矩下降 → 转速反馈变化 → 速度 PI 调整 iq*。",
        "motorlab/core.py · Motor.step(): mechanical",
        [N("te", "电磁转矩 Te", "source", 25, 55, "torque", "torque"),
         N("tl", "负载转矩 TL", "source", 25, 225, "load"),
         N("friction", "× B\n摩擦转矩", "gain", 260, 395, "friction_torque"),
         N("sum", "+ − −\n加速转矩", "sum", 300, 150),
         N("inertia", "÷ J", "gain", 535, 150, "acceleration"),
         N("int", "∫\n真实机械速度", "integrator", 770, 150, "speed_true"),
         N("sensor", "编码器 / 采样", "model", 770, 395, "speed_rpm", "sensors", w=180)],
        [E("te", "sum", "+"), E("tl", "sum", "−"), E("friction", "sum", "−"),
         E("sum", "inertia"), E("inertia", "int", "角加速度"),
         E("int", "friction", "ωm"), E("int", "sensor", "ωm")]),
    "sensors": D(
        "传感器、ADC 与采样接口",
        "电流、电压模拟 αβ 等效测量。可配置噪声、偏置、量程和 ADC 位数，并对整组样本施加整数拍 FIFO 延迟。固定种子用于复现实验。",
        "Sample = {voltage:[uα,uβ], current:[iα,iβ], speed:ωm, time:t}\nymeas = ADC(clip(yphysical + b + n, ±量程))\nADC 关闭时只保留噪声、偏置与量程约束；速度使用独立噪声\nSample 不包含真实 Rr、磁链、TL 或转矩。\n传感器延迟作用于整组样本，按样本时间推进 EKF。",
        "motorlab/core.py · Sample, Sensors.sample(); motorlab/simulation.py · queue",
        [N("u", "平均端电压", "source", 25, 55),
         N("i", "内部定子电流", "source", 25, 220),
         N("speed", "内部机械速度", "source", 25, 385),
         N("noise", "+\n电压电流噪声 / 偏置", "sum", 255, 220),
         N("speednoise", "+\n速度测量噪声", "sum", 255, 385),
         N("adc", "量程 / ADC", "saturation", 480, 220),
         N("delay", "采样 / 延迟", "hold", 705, 220, "sensor_delay"),
         N("bus", "合并 Sample", "bus", 925, 220, w=155),
         N("im", "测量 iα", "output", 705, 55, "i_alpha"),
         N("rpm", "测量转速", "output", 705, 385, "speed_rpm")],
        [E("u", "noise"), E("i", "noise"), E("speed", "speednoise"),
         E("speednoise", "delay", "独立速度通道"), E("noise", "adc"),
         E("adc", "delay"), E("delay", "bus"), E("bus", "im"), E("bus", "rpm")]),
    "ekf": D(
        "EKF：用电流预测误差修正电阻",
        "辨识器拥有自己的数学模型，只接收采样电压、电流和转速。电阻作为慢变状态，用电流新息校正。显示标准差属于模型内部协方差，不能直接当作经过标定的准确率。",
        "x̂ = [îα,îβ,ψ̂rα,ψ̂rβ,R̂r]ᵀ\nx̂⁻ = f_d(x̂, umeas, ωmeas)；预测使用 RK4\nP⁻ = FPFᵀ + Q；F 为离散状态转移雅可比\nν = imeas − Hx̂⁻；S = HP⁻Hᵀ + R\nK = P⁻HᵀS⁻¹；x̂ = x̂⁻ + Kν\nP = (I−KH)P⁻(I−KH)ᵀ + KRKᵀ\nR̂r 限制在 [0.1,3] Ω；触及边界不代表收敛。",
        "motorlab/core.py · ResistanceEKF.update()",
        [N("sample", "仅测量 Sample", "source", 25, 65, child="sensors", w=180),
         N("predict", "RK4 状态预测", "model", 280, 65, w=180),
         N("h", "H：选取电流", "gain", 540, 65),
         N("innovation", "+ −\n测量 − 预测", "sum", 785, 65, "innovation", w=185),
         N("cov", "F P Fᵀ + Q", "model", 280, 290, w=180),
         N("gain", "卡尔曼增益 K", "model", 540, 290, w=180),
         N("correct", "+ Kν\n状态校正", "sum", 785, 290, w=185),
         N("rr", "R̂r / 物理范围", "saturation", 785, 450, "rr_est", w=185),
         N("std", "√P[Rr,Rr]", "output", 540, 450, "rr_std")],
        [E("sample", "predict", "电压 / 转速"), E("predict", "h"),
         E("h", "innovation", "−"), E("sample", "innovation", "+ 电流"),
         E("predict", "cov", "离散雅可比 F"), E("cov", "gain"),
         E("innovation", "correct", "ν"), E("gain", "correct", "K"),
         E("predict", "correct", "x̂⁻"), E("correct", "rr"),
         E("correct", "std", "校正协方差")], height=570),
    "evaluation": D(
        "独立评价：电阻误差与磁场定向",
        "评价模块允许同时访问真实参数和估计值。延迟实验中，当前误差与时间对齐误差回答不同问题。真实磁链偏角在磁链接近零时缺少可靠物理意义。",
        "eR = R̂r − Rr(t)\nεR = 100|eR|/Rr(t) [%]\nεaligned = 100|R̂r − Rr(testimate)|/Rr(testimate)\nRMSE = √mean(eR²) [Ω]\n[ψrd,ψrq]ᵀ = Park(θe)[ψrα,ψrβ]ᵀ\nδ = atan2(ψrq,ψrd)·180/π\n评价结果不反馈至辨识器；理想参数模式仅用于单独的仿真对照。",
        "motorlab/simulation.py · Simulation._record(), metrics()",
        [N("truth", "真实 Rr\n仅评价", "source", 25, 65, "rr_true"),
         N("estimate", "估计 R̂r", "source", 25, 250, "rr_est", "ekf"),
         N("error", "+ −\n估计 − 真实", "sum", 285, 160, "rr_signed_error"),
         N("relative", "|误差| / Rr × 100", "product", 550, 160, "rr_error_pct", w=195),
         N("rmse", "平方 → 均值 → √", "model", 830, 160, w=195),
         N("df", "真实 ψrd\n仅评价", "source", 25, 420, "flux_d_true"),
         N("qf", "真实 ψrq\n仅评价", "source", 285, 420, "flux_q_true"),
         N("angle", "atan2(ψrq,ψrd)", "model", 550, 420, "flux_angle_error_deg", w=195)],
        [E("truth", "error", "−"), E("estimate", "error", "+"), E("error", "relative"),
         E("error", "rmse", "eR"), E("df", "angle"), E("qf", "angle")]),
}


def _pi(axis, title, ref, feedback, error, proportional, integral, raw, output):
    speed = axis == "speed"
    diagram = D(
        title,
        "误差经过比例和积分支路相加。回算抗饱和使用实际输出与请求输出之差修正积分状态。探针 I 显示本拍求和使用的积分值，更新后的值用于下一拍。",
        ("ω* = n*·2π/60 [rad/s]；eω = ω* − ωmeas\n" if speed else f"e{axis} = i{axis}* − i{axis} [A]\n")
        + "P[k] = Kp e[k]；uPI[k] = P[k] + I[k]\n"
        + ("iq* = clip(uPI, ±√(Imax² − id*²))；励磁阶段 iq*=0\n" if speed else
           "uact = 电压限幅(uPI + uff) − uff\n")
        + "I[k+1] = I[k] + Ts[Ki e[k] + Kaw(uact − uPI)]\n"
        + ("速度环 uact = iq*，Kaw = 15 s⁻¹。\n" if speed else
           "电流环 Kp=Lσ ωc，Ki=Rs ωc，Kaw=ωc。\n")
        + "Kd = 0；当前实现为 PI 控制。",
        "motorlab/control.py · PI.output(), PI.integrate(), FOCController.update()",
        [N("ref", "转速给定 n* [rpm]" if speed else "给定", "source", 20, 60, ref),
         N("fb", "测量 ωm [rad/s]" if speed else "测量反馈", "source", 20, 270, feedback),
         N("err", "+ −\n控制误差", "sum", 240, 165, error),
         N("kp", "× Kp", "gain", 455, 60, proportional),
         N("ki", "× Ki → ∫", "integrator", 455, 270, integral),
         N("sum", "+\nP + I", "sum", 670, 165, raw),
         N("limit", "电流限幅" if speed else "前馈 + 电压限幅",
           "saturation", 885, 165, output, None if speed else "decoupling", w=190),
         N("aw", "× Kaw\n实际 − 请求", "gain", 670, 415, w=180)],
        [E("ref", "err", "+"), E("fb", "err", "−"), E("err", "kp"), E("err", "ki"),
         E("kp", "sum", "P"), E("ki", "sum", "I"), E("sum", "limit"),
         E("limit", "aw", "实际输出"), E("sum", "aw", "请求输出"),
         E("aw", "ki", "积分修正")], height=530)
    if speed:
        diagram["nodes"].append(N("rpm_to_rad", "× 2π/60\nrpm → rad/s", "gain", 240, 60))
        diagram["edges"] = [edge for edge in diagram["edges"]
                            if (edge["from"], edge["to"]) != ("ref", "err")]
        diagram["edges"].extend([
            E("ref", "rpm_to_rad", "n* [rpm]", ref),
            E("rpm_to_rad", "err", "+ ω* [rad/s]"),
        ])
    else:
        feedforward = "vd_ff" if axis == "d" else "vq_ff"
        diagram["nodes"].extend([
            N("subtract_ff", "+ −\nu限幅 − uff", "sum", 885, 350, w=190),
            N("ff", "前馈电压 uff", "source", 885, 500, feedforward, w=190),
        ])
        diagram["edges"] = [edge for edge in diagram["edges"]
                            if (edge["from"], edge["to"]) != ("limit", "aw")]
        diagram["edges"].extend([
            E("limit", "subtract_ff", "+ 限幅后电压", output),
            E("ff", "subtract_ff", "− 前馈电压", feedforward),
            E("subtract_ff", "aw", "uact"),
        ])
        diagram["height"] = 610
    return diagram


DIAGRAMS["speed_pi"] = _pi(
    "speed", "速度 PI：速度误差 → 转矩电流给定", "speed_ref_rpm", "control_speed",
    "speed_error", "speed_p", "speed_i", "speed_unsat", "iq_ref")
DIAGRAMS["id_pi"] = _pi(
    "d", "d 轴电流 PI：维持励磁电流", "id_ref", "id", "id_error",
    "id_p", "id_i", "vd_pi", "vd")
DIAGRAMS["iq_pi"] = _pi(
    "q", "q 轴电流 PI：实现转矩电流给定", "iq_ref", "iq", "iq_error",
    "iq_p", "iq_i", "vq_pi", "vq")

# 开关级扩展：控制采样快照是边界处读数；载波/门极内部波形由独立高频记录提供。
for _category, _items in {
    'timing': [('pwm_period','PWM 周期','s'),('pwm_frequency','PWM 频率','Hz'),
               ('integration_count','累计物理积分子步','次'),('switching_rows','累计高频记录点','次'),
               ('inverter_switching','开关模型启用标志','0/1')],
    'control': [('u_alpha_command','SVPWM α 电压指令','V'),('u_beta_command','SVPWM β 电压指令','V'),
                ('duty_a','A 相占空比',''),('duty_b','B 相占空比',''),('duty_c','C 相占空比',''),
                ('modulation_a','A 相归一化调制波',''),('modulation_b','B 相归一化调制波',''),
                ('modulation_c','C 相归一化调制波',''),('zero_sequence','零序注入电压','V'),
                ('pwm_sector','空间矢量扇区',''),('pwm_t1','相邻有效矢量作用时间 T1','s'),
                ('pwm_t2','相邻有效矢量作用时间 T2','s'),('pwm_t0','零矢量总作用时间 T0','s'),
                ('carrier','控制边界处三角载波',''),('gate_au','A 相上桥臂（边界左值）','0/1'),
                ('gate_al','A 相下桥臂（边界左值）','0/1'),('gate_bu','B 相上桥臂（边界左值）','0/1'),
                ('gate_bl','B 相下桥臂（边界左值）','0/1'),('gate_cu','C 相上桥臂（边界左值）','0/1'),
                ('gate_cl','C 相下桥臂（边界左值）','0/1'),('u_alpha_switch','瞬时开关电压 α（边界左值）','V'),
                ('u_beta_switch','瞬时开关电压 β（边界左值）','V'),
                ('phase_voltage_a','瞬时 A 相端电压（边界左值）','V'),
                ('phase_voltage_b','瞬时 B 相端电压（边界左值）','V'),
                ('phase_voltage_c','瞬时 C 相端电压（边界左值）','V')],
    'measurement': [('i_a','采样 A 相电流（αβ 重构）','A'),('i_b','采样 B 相电流（αβ 重构）','A'),
                    ('i_c','采样 C 相电流（αβ 重构）','A')],
    'truth': [('peak_instant_current_a','高频电流矢量峰值（仅评价）','A'),
              ('rotor_angle','真实转子机械角度（仅评价/3D）','rad'),
              ('rotor_turns','真实转子累计转数（仅评价/3D）','转')],
}.items():
    for _key, _label, _unit in _items:
        SIGNALS[_key] = _s(_label, _unit, _category)
SIGNALS['u_alpha']['label'] = '区间平均端电压 α'
SIGNALS['u_beta']['label'] = '区间平均端电压 β'
SIGNALS['u_alpha_measured']['label'] = '测量区间平均电压 α'
SIGNALS['u_beta_measured']['label'] = '测量区间平均电压 β'
SIGNALS['integration_step']['label'] = '当前积分步长上限（事件段可更短）'
for _key in ['gate_au','gate_al','gate_bu','gate_bl','gate_cu','gate_cl','carrier',
             'phase_voltage_a','phase_voltage_b','phase_voltage_c','u_alpha_switch','u_beta_switch']:
    SIGNALS[_key]['description'] = '这里只显示控制区间末端读数，可能总是零矢量。请在 SVPWM 开关显微镜观察周期内边沿，控制采样率不足以恢复 PWM 波形。'

DIAGRAMS['inverter'] = D(
    'SVPWM 与六开关三相逆变器',
    '默认模式将真实门极状态转换成三相脉冲电压并驱动电机。精确分割开关边沿，积分上限控制段内求解。平均电压模式保留为对照；下方显微镜显示完整高频波形。',
    'udq → 逆 Park → uαβ* → SVPWM 占空比\n上桥臂 Sj = 1[dj ≥ c(t)]；下桥臂 = 1−Sj\nun = Vdc[Sa,Sb,Sc] − Vdc(Sa+Sb+Sc)/3\n电机实际使用分段开关电压；采样电压为区间端电压的测量平均\n没有死区、器件压降、母线纹波或寄生参数。',
    'motorlab/inverter.py · SVPWM, bridge_voltage(); simulation.py · _drive()',
    [N('reference','αβ 电压指令','source',20,100,'u_alpha_command'),
     N('svpwm','空间矢量调制','model',260,100,'pwm_sector','svpwm',w=185),
     N('bridge','六开关三相桥','model',540,100,child='bridge',w=185),
     N('motor','脉冲电压 → 电机','model',820,100,child='motor',w=210),
     N('clock','控制 Ts / PWM 周期','model',260,330,'pwm_period','timing',w=185),
     N('monitor','高频事件记录','model',540,330,'switching_rows',w=185),
     N('sample','区间平均电压采样','model',820,330,'u_alpha_measured','sensors',w=210)],
    [E('reference','svpwm','uα*','u_alpha_command'),E('clock','svpwm','TPWM'),
     E('svpwm','bridge','六路门极'),E('bridge','motor','瞬时脉冲电压'),
     E('bridge','monitor','完整开关边沿'),E('bridge','sample','端电压积分/Ts')],height=470)
DIAGRAMS['svpwm'] = D(
    'SVPWM：零序注入、载波比较与七段序列',
    '中心对齐载波比较采用 min/max 零序注入，在此线性调制范围内等价于对称七段 SVPWM。显示 T1/T2/T0 便于与扇区法对照；实际门极时刻由占空比精确生成。',
    'ua*=uα*；ub*=−uα*/2+√3uβ*/2；uc*=−uα*/2−√3uβ*/2\nu0=−(max(ua*,ub*,uc*)+min(ua*,ub*,uc*))/2\ndj=1/2+(uj*+u0)/Vdc\nc(t)=|2 frac(t/TPWM)−1|；Sj=1[dj≥c(t)]\n扇区 q=1+floor(arg(uα*+j uβ*)/(π/3))\nT1=√3 TPWM |u*|/Vdc · sin(π/3−θq)\nT2=√3 TPWM |u*|/Vdc · sinθq；T0=TPWM−T1−T2\n每周期两次比较边沿：(1−dj)TPWM/2、(1+dj)TPWM/2。',
    'motorlab/inverter.py · SVPWM.set_command(), segments()',
    [N('ab','αβ 电压指令','source',15,80,'u_alpha_command'),
     N('abc','逆 Clarke','transform',235,80,w=170),
     N('zero','min/max → 零序','model',470,80,'zero_sequence',w=200),
     N('duty','+u0 → ÷Vdc → +½','model',750,80,'duty_a',w=230),
     N('carrier','中心对齐三角载波','source',470,300,'carrier',w=200),
     N('compare','≥ 比较','operator',750,300,'gate_au',w=180),
     N('sector','扇区 / 作用时间','model',15,300,'pwm_sector',w=180),
     N('bridge','三相桥','model',750,460,child='bridge',w=180)],
    [E('ab','abc'),E('abc','zero'),E('zero','duty'),E('abc','duty','相指令'),
     E('duty','compare','A 占空比','duty_a'),E('carrier','compare','c(t)'),
     E('compare','bridge','A 上桥臂','gate_au'),E('ab','sector')],height=560)
DIAGRAMS['bridge'] = D(
    '六开关逆变器：浮动中性点与端电压',
    '理想开关，三相各一对互补桥臂。没有中性线，电机相电压必须减去公共中性点电位，不能直接把桥臂极点电压当作相电压。门极周期内详情见开关显微镜。',
    'SAl=1−SAu；SBl=1−SBu；SCl=1−SCu（无死区）\nvNO=Vdc(Sa+Sb+Sc)/3\nva=Vdc Sa−vNO；vb=Vdc Sb−vNO；vc=Vdc Sc−vNO\nuα=(2/3)Vdc(Sa−Sb/2−Sc/2)\nuβ=Vdc(Sb−Sc)/√3\nva+vb+vc=0；000 与111均为零电压矢量。',
    'motorlab/inverter.py · bridge_voltage()',
    [N('a','A 上桥臂','source',20,40,'gate_au'),N('b','B 上桥臂','source',20,200,'gate_bu'),
     N('c','C 上桥臂','source',20,360,'gate_cu'),N('common','求和 × Vdc/3','model',260,200,w=200),
     N('phase','极点电压 − 中性点','model',550,200,'phase_voltage_a',w=220),
     N('clarke','Clarke → αβ','transform',830,200,'u_alpha_switch',w=210)],
    [E('a','common'),E('b','common'),E('c','common'),E('common','phase'),
     E('a','phase','Sa×Vdc'),E('phase','clarke')],height=490)
DIAGRAMS['motor_visual'] = D(
    '三维电机：物理状态到几何显示',
    '首页三维视图是鼠笼异步电机的结构示意。转子、轴与风扇按积分得到的机械角旋转；定子不转。绕组亮度根据三相电流变化，青色箭头表示真实磁链方向。',
    'θm(t)=∫ωm(t)dt\n几何旋转矩阵 = RotX(θm)\n磁链箭头角 = atan2(ψrβ,ψrα)\n三相电流由 αβ 逆变换重构。\n结构尺寸为示意，不从几何反算惯量，不输出有限元场分布。\n这些状态仅用于评价和可视化，不传给辨识器。',
    'motorlab/core.py · Motor.rotor_angle; web/motor3d.js · MotorView',
    [N('speed','真实机械速度','source',25,80,'speed_true'),N('angle','∫ 机械角度','integrator',280,80,'rotor_angle'),
     N('geometry','转子 / 轴 / 风扇','model',570,80,w=240),N('flux','真实磁链 αβ（α探针）','source',25,300,'flux_alpha_true'),
     N('arrow','磁链方向箭头','model',280,300,w=180)],
    [E('speed','angle'),E('angle','geometry'),E('flux','arrow')],height=440)
DIAGRAMS['system']['nodes'] += [N('visual','三维物理示意','model',760,490,'rotor_angle','motor_visual',w=190)]
DIAGRAMS['system']['edges'] += [E('motor','visual','内部状态，仅显示','rotor_angle')]
for _node in DIAGRAMS['system']['nodes']:
    if _node['id']=='drive': _node['label']='SVPWM / 六开关桥'
DIAGRAMS['system']['description'] = '从 FOC 到 SVPWM、三相开关电压、机械响应和在线电阻辨识的完整运行链路。首页三维视图由实际仿真状态驱动；高频显微镜显示控制采样之间的开关过程。'
DIAGRAMS['system']['formula'] += '\n驱动：SVPWM → 六开关桥 → 分段脉冲电压 → 电机\n可切换平均模型作对照；三维视图为集总参数模型的几何映射。'
DIAGRAMS['timing']['description'] = '控制与传感器采样周期 Ts 为 PWM 周期的整数倍。每个开关事件精确分割，再按积分步长上限细分求解。图形刷新不改变物理步长。'
DIAGRAMS['timing']['formula'] = 'TPWM=1/fPWM；Ts=N·TPWM（N为正整数）\nFOC 指令在每个 Ts 内保持，PWM 每个 TPWM 重复\n每次积分不得跨过门极边沿；h≤min(hmax,Ts/最少子步数)\n传感器每 Ts 采样电流/速度，以及区间平均端电压\n高频记录保留边沿与每个物理子步；控制 CSV 只保留 Ts 采样。'
DIAGRAMS['sensors']['description'] += ' 开关模式中电压通道测量区间平均端电压，电流与转速在区间末采样；这相当于电压积分测量前端，不是瞬时取一个开关电压作为周期电压。'
DIAGRAMS['ekf']['description'] += ' EKF 使用测量区间平均电压，保留平均模型近似；高频纹波不应被解释成电阻真值，低 PWM 频率等工况需要额外验证。'
