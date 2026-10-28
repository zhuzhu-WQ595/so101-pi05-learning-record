from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BASE = Path("/home/pc/桌面/SO101_pi05_学习记录")
IMG = BASE / "images"
OUT = BASE / "SO101机械臂微调π0.5学习记录.docx"

BODY_FONT = "Microsoft YaHei"
CODE_FONT = "Consolas"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = sec.bottom_margin = Cm(2.2)


def set_font(run, name=BODY_FONT, size=None, bold=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


style = doc.styles["Normal"]
style.font.name = BODY_FONT
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
style.paragraph_format.line_spacing = 1.35
style.paragraph_format.space_after = Pt(4)

for lvl, size in ((1, 16), (2, 13), (3, 11.5)):
    hs = doc.styles[f"Heading {lvl}"]
    hs.font.name = BODY_FONT
    hs.font.size = Pt(size)
    hs.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    hs.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)


def h(text, level=1):
    p = doc.add_heading(level=level)
    set_font(p.add_run(text), size={1: 16, 2: 13, 3: 11.5}[level], bold=True, color=(0x1F, 0x3A, 0x5F))
    return p


def para(text, bold_prefix=None, indent=False):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)
    if bold_prefix:
        set_font(p.add_run(bold_prefix), bold=True)
    set_font(p.add_run(text))
    return p


def bullets(items):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        if isinstance(it, tuple):
            set_font(p.add_run(it[0]), bold=True)
            set_font(p.add_run(it[1]))
        else:
            set_font(p.add_run(it))


def shade(cell, color):
    tcpr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcpr.append(shd)


def code(text):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    shade(cell, "F3F4F6")
    cell.paragraphs[0].text = ""
    lines = text.strip("\n").split("\n")
    for i, line in enumerate(lines):
        p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        set_font(p.add_run(line), name=CODE_FONT, size=8.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def table(header, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, txt in enumerate(header):
        c = t.rows[0].cells[i]
        shade(c, "1F3A5F")
        c.paragraphs[0].text = ""
        set_font(c.paragraphs[0].add_run(txt), size=9.5, bold=True, color=(255, 255, 255))
    for r in rows:
        cells = t.add_row().cells
        for i, txt in enumerate(r):
            cells[i].paragraphs[0].text = ""
            set_font(cells[i].paragraphs[0].add_run(str(txt)), size=9.5)
    if widths:
        t.autofit = False
        for i, w in enumerate(widths):
            t.columns[i].width = Cm(w)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


fig_no = [0]


def figure(name, caption, width=16):
    fig_no[0] += 1
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG / name), width=Cm(width))
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(c.add_run(f"图 {fig_no[0]}  {caption}"), size=9, color=(0x55, 0x55, 0x55))


# ---------------- 封面 ----------------
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(30)
set_font(p.add_run("从零开始：SO-101 机械臂 + LeRobot 微调 π0.5"), size=22, bold=True, color=(0x1F, 0x3A, 0x5F))
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
set_font(p.add_run("实现“把夹子放进纸杯”的完整学习记录"), size=14, color=(0x44, 0x44, 0x44))
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
set_font(p.add_run("数据采集 → 数据清洗 → 单卡 4090 微调 → 实机部署 → 问题分析"), size=11, color=(0x66, 0x66, 0x66))

figure("01_dual_camera.jpg", "双相机视角：左为固定在桌前的主相机，右为腕部相机", 16)

h("成果一览", 2)
table(
    ["项目", "结果"],
    [
        ["任务", "Put the clip into the cup（把夹子放进纸杯）"],
        ["示范数据", "50 条遥操作示范，18474 帧，30 fps，双相机 640×480"],
        ["模型", "π0.5（pi05_base，约 41 亿参数），只训练动作专家，可训练参数 6.9 亿"],
        ["训练", "RTX 4090 24GB 单卡，6000 步，batch 16，约 5 小时 10 分钟，显存 16.3 GB"],
        ["Loss", "约 0.5 → 0.048"],
        ["实机评估", "10 轮自主运行中 7 轮成功（按评估录像人工判定）"],
        ["后续改进实验", "对比 3 种推理方式；夹子贴双面胶后“成功夹住”达 8/12，基本不再打滑"],
        ["DAgger 纠正", "录 29 条模型出错时的人工纠正，清洗后 23 条并入训练集；重训后模型学会失败恢复"],
    ],
    widths=[3.2, 13.3],
)

# ---------------- 1 背景 ----------------
h("1  项目背景与目标")
para(
    "π0.5 是 Physical Intelligence 开源的视觉-语言-动作（VLA）模型，LeRobot 已经把它移植到 PyTorch，"
    "可以直接用自己采集的数据微调。我的目标是：用一套低成本的 SO-101 主从机械臂，走通“采集数据 → 微调 π0.5 → 实机部署”的完整流程，"
    "让机械臂根据语言指令和相机画面，自主把桌面上的夹子放进纸杯。",
    indent=True,
)
para("本文记录了每一步的做法、使用的命令、遇到的坑和解决办法，希望对同样入门的朋友有帮助。", indent=True)

# ---------------- 2 环境 ----------------
h("2  硬件与软件环境")
table(
    ["类别", "配置"],
    [
        ["机械臂", "SO-101 主臂（leader）+ 从臂（follower），Feetech STS3215 舵机"],
        ["相机", "腕部相机 ×1（装在从臂夹爪上）、桌前固定相机 ×1，均为 USB UVC，640×480 @ 30 fps"],
        ["GPU", "NVIDIA RTX 4090，24 GB 显存"],
        ["系统", "Linux（Ubuntu 桌面）"],
        ["软件", "LeRobot 0.6.1，Python 3.12，conda 环境 lerobot"],
        ["物品", "蓝色、黄色晾衣夹各一个，棕色纸杯一个"],
    ],
    widths=[3, 13.5],
)

# ---------------- 3 安装 ----------------
h("3  环境搭建")
para("按照 LeRobot 官方安装文档新建 conda 环境，然后安装带训练、π0.5 和飞特舵机支持的 LeRobot：")
code("""
conda create -y -n lerobot python=3.12
conda activate lerobot
conda install -y -c conda-forge ffmpeg
pip install -i https://pypi.org/simple "lerobot[core_scripts,training,pi,feetech]"
""")
h("踩坑：国内网络", 3)
bullets([
    ("GitHub clone 超时：", "改为直接从 PyPI 安装 lerobot，不需要克隆源码。"),
    ("pip 镜像返回 403：", "我的 pip 全局配置了清华镜像，访问被拒，安装时用 -i https://pypi.org/simple 临时指定官方源。"),
    ("Hugging Face 无法访问：", "π0.5 权重从 ModelScope 下载（lerobot/pi05_base），PaliGemma 的 tokenizer 也从 ModelScope 下载后放进 HF 缓存目录，训练和推理时设置 HF_HUB_OFFLINE=1 离线加载。"),
])
code("""
# 断点续传下载 14 GB 权重（中途断开可重复执行）
curl -fL -C - --retry 20 --retry-delay 5 --retry-all-errors \\
  -o ~/models/pi05_base/model.safetensors \\
  "https://modelscope.cn/models/lerobot/pi05_base/resolve/master/model.safetensors"
""")
para("下载完成后，我解析了 safetensors 文件头，确认 813 个张量的数据区刚好写到文件末尾，以此判断文件没有被截断。")

# ---------------- 4 机械臂 ----------------
h("4  机械臂连接与标定")
bullets([
    ("串口权限：", "sudo usermod -aG dialout $USER，重新登录后用 groups 确认包含 dialout。"),
    ("固定端口名：", "/dev/ttyACM0、/dev/ttyACM1 这类名字插拔后可能互换，所以改用 /dev/serial/by-id/ 下的固定路径，并写进 ~/.bashrc。"),
])
code("""
export LEADER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E112957-if00
export FOLLOWER=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E116614-if00

lerobot-calibrate --robot.type=so101_follower --robot.port=$FOLLOWER --robot.id=my_follower
lerobot-calibrate --teleop.type=so101_leader --teleop.port=$LEADER --teleop.id=my_leader
""")
para("标定完成后先用 lerobot-teleoperate 测试遥操作，确认从臂能平稳跟随主臂。")

# ---------------- 5 相机 ----------------
h("5  相机配置")
bullets([
    ("只识别到一个相机：", "桌前相机换了一个 USB 口后才被识别。两个相机同样改用 /dev/v4l/by-id/ 下的固定路径。"),
    ("帧率不足：", "录制时开启实时画面显示（--display_data=true），循环只能跑到 24 Hz，低于目标 30 Hz；关闭显示后恢复正常，所以正式录制不开画面。"),
    ("机位：", "桌前相机调成更偏俯视的角度，保证夹子和纸杯都在画面里。机位定下后不要再动，部署时必须和录数据时一致。"),
])
figure("02_front_live.jpg", "桌前主相机画面（部署时拍摄）", 11)

# ---------------- 6 数据 ----------------
h("6  数据采集与清洗")
h("6.1  任务设计", 2)
para("为了让第一个项目尽量容易成功，我选择了单一任务：每次只在桌上放一个夹子（蓝色或黄色），"
     "语言指令统一为 “Put the clip into the cup”。每条示范从机械臂初始姿态开始，夹起夹子放进纸杯后结束。")
h("6.2  录制命令", 2)
code("""
lerobot-record \\
  --robot.type=so101_follower --robot.port=$FOLLOWER --robot.id=my_follower \\
  --robot.cameras="{ front: {type: opencv, index_or_path: $FRONT_CAM, width: 640, height: 480, fps: 30},
                     wrist: {type: opencv, index_or_path: $WRIST_CAM, width: 640, height: 480, fps: 30}}" \\
  --teleop.type=so101_leader --teleop.port=$LEADER --teleop.id=my_leader \\
  --dataset.repo_id=local/so101_clip_cup \\
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/so101_clip_cup \\
  --dataset.no_stamp=true \\
  --dataset.single_task="Put the clip into the cup" \\
  --dataset.num_episodes=6 \\
  --dataset.episode_time_s=50 --dataset.reset_time_s=15 \\
  --dataset.streaming_encoding=true --dataset.encoder_threads=2 \\
  --dataset.push_to_hub=false \\
  --resume=true        # 第一次录制时去掉这一行
""")
bullets([
    ("键盘控制：", "→ 提前结束当前条（或跳过复位时间），← 丢弃当前条重录，Esc 结束录制。"),
    ("分批录制：", "每批录几条，用 --resume=true 续录到同一个数据集，累了可以随时停。"),
])
h("6.3  踩坑：方向键与空 episode", 3)
para("方向键按得稍久，键盘自动重复会连续触发多次“结束”，结果跳过了复位，或者保存了一条 0 帧的 episode，程序报错：")
code("ValueError: You must add one or several frames with add_frame before calling add_episode.")
para("解决办法：方向键轻点后立刻松开；在 X11 下可以录制前执行 xset r off 关闭按键重复，录完再 xset r on 恢复。"
     "续录时还遇到 resume() 要求显式提供 root 的报错，加上 --dataset.root 即可。")
h("6.4  数据清洗", 2)
para("每批录完都检查每条的帧数，删除误触产生的极短 episode（如只有 19 帧、28 帧的）。删除前先备份，"
     "用 lerobot-edit-dataset 输出到新目录，验证无误再替换原数据。最终数据集：")
table(
    ["指标", "数值"],
    [
        ["episode 数", "50"],
        ["总帧数", "18474（约 10 分钟）"],
        ["单条时长", "9.7–14.8 秒，平均 12.3 秒"],
        ["相机", "front、wrist 两路视频，帧数与数据帧一致"],
        ["状态/动作", "6 维：5 个关节 + 夹爪"],
    ],
    widths=[4, 12.5],
)
figure("03_train_samples.jpg", "训练数据中夹爪闭合时刻的主相机画面（夹子颜色、纸杯位置有变化）", 16)
figure("08_episode_length.png", "示范时长分布", 12)
para("可以用 lerobot-dataset-viz 逐条回放检查数据（需要先 conda activate lerobot）。")

h("6.5  采集数据的注意事项", 2)
para("数据质量决定模型上限，比模型结构重要得多。结合这次的经验，录制示范时最需要注意的是：")
bullets([
    ("场景一致性：", "相机机位、光照、桌面背景从录制到部署必须保持一致。机位定下后不要动——模型记住的是画面里物体和杯子的相对位置，相机挪一点等于数据全废。"),
    ("覆盖范围要刻意设计：", "夹子摆放位置要遍历机械臂需要工作的所有区域（可以用网格法逐格摆），而不是图省事总放同一个地方。我第一批数据只覆盖了正前方一小块，模型换位置就失败——这是本项目最大的教训。"),
    ("动作连贯、不犹豫：", "录制中途停顿、来回微调、抓空后僵住，这些都会变成模型的一部分。录得不好宁可按 ← 当场丢弃重录，不要靠后期清洗补救。"),
    ("起点终点统一：", "每条从相同的初始姿态开始，明确地在任务完成后结束。起始姿态不一致会让模型的动作在 episode 开头就发飘。"),
    ("时长适中：", "单条 8–15 秒比较合适。太短可能没录全动作，太长会稀释关键操作的学习信号，还增加出错重录的成本。"),
    ("多样性优先于数量：", "50 条只是能跑通的下限。与其再录 50 条一模一样的，不如变换夹子颜色、纸杯位置、摆放角度，或者故意安排“先放偏再调整”的轨迹。"),
    ("录完逐条检查：", "检查每条首尾帧（是否在初始位、夹子是否真进了杯子）和时长，极短条基本是误触；回放时注意机械臂有没有明显停顿或画蛇添足的动作。"),
    ("USB 与硬件状态：", "两个相机要插在带宽足够的 USB 口（不要都挤在一个 hub 里，会抢带宽读不到帧）；录制前确认舵机供电正常、遥操作跟随没有延迟。"),
])

# ---------------- 7 训练 ----------------
h("7  模型微调")
h("7.1  π0.5 模型简介", 2)
para("π0.5（pi-zero-point-five）是 Physical Intelligence 2025 年发布的视觉-语言-动作（VLA, Vision-Language-Action）通用机器人基础模型，"
     "是目前开源可用的最强通用机器人策略之一。它的核心思想是：把“看懂场景、听懂指令、输出动作”放进同一个模型，"
     "在多种机器人平台的大规模数据上预训练后，只需少量本机数据微调就能迁移到新机器人、新任务。")
h("模型结构", 3)
bullets([
    ("总参数约 41 亿", "，分两大部分："),
    ("PaliGemma 视觉语言主干（约 30 亿）：", "SigLIP 视觉编码器把多路相机画面编码成 token，Gemma 语言模型处理任务指令和视觉 token，输出多模态特征。"),
    ("动作专家（Gemma 300M）：", "一个较小的 transformer，接收 VLM 的特征和机器人当前关节状态，用流匹配（flow matching）从噪声迭代去噪，一次生成 50 步动作序列（action chunk）。"),
    ("图像输入名：", "base_0_rgb、left_wrist_0_rgb、right_wrist_0_rgb 三路相机 + 一路语言指令；缺路数时可以补空图屏蔽。"),
])
h("与 π0 的主要区别：知识隔离（knowledge insulation）", 3)
para("π0.5 训练时让 VLM 部分和动作专家解耦：预训练阶段用网页图文等开放知识教 VLM“理解世界”，机器人数据只教动作专家，"
     "这样语言理解能力不会在机器人数据上过拟合，泛化到新指令、新物体时更稳。代价是推理时两部分要串行计算，"
     "在 RTX 4090 上单次推理约 100 ms 量级，靠 action chunk（一次出 50 步）保证 30 Hz 控制频率下的实时性。")
h("为什么适合小数据微调", 3)
para("预训练已经见过了跨平台的抓取、放置、收拾等大量操作技能，微调只需要让它学会“我的机械臂长什么样、我的任务是什么”。"
     "LeRobot 提供 train_expert_only 选项，可以冻结 VLM 主干只训练动作专家——可训练参数从 41 亿降到 6.9 亿，"
     "单卡 24 GB 显存即可放下，50 条示范就能得到一个能用的策略。")

h("7.2  显存估算：为什么只训练动作专家", 2)
para("π0.5 总参数约 41 亿。全量微调时，bf16 权重、梯度和 AdamW 的两份状态加起来约 29 GB，超过 4090 的 24 GB。"
     "因此我设置 train_expert_only=true：冻结 PaliGemma 视觉语言部分，只训练动作专家（Gemma 300M）和投影层，"
     "可训练参数 6.9 亿。对于单任务、固定指令的场景，这是一个合理的起点。同时开启梯度检查点进一步节省显存。", indent=True)
h("7.3  关键配置", 2)
bullets([
    ("相机名映射：", "预训练模型的图像输入叫 base_0_rgb / left_wrist_0_rgb / right_wrist_0_rgb，我的数据集叫 front / wrist，"
                 "需要用 --rename_map 映射。缺少的 right_wrist 会自动补空图并屏蔽。"),
    ("设备：", "pi05_base 的 config.json 里写的是 \"device\": \"mps\"（苹果芯片），必须用 --policy.device=cuda 覆盖。"),
    ("不上传：", "预训练配置默认 push_to_hub=true，本地训练要设为 false，否则会因缺少 repo_id 报错。"),
    ("先跑冒烟测试：", "正式训练前先跑 20 步，确认能加载权重、显存够、loss 在下降，避免跑几个小时才发现配置错误。"),
])
code("""
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1

lerobot-train \\
  --policy.path=/home/pc/models/pi05_base \\
  --policy.device=cuda --policy.dtype=bfloat16 \\
  --policy.train_expert_only=true \\
  --policy.gradient_checkpointing=true \\
  --policy.push_to_hub=false \\
  --dataset.repo_id=local/so101_clip_cup \\
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/so101_clip_cup \\
  --rename_map='{"observation.images.front": "observation.images.base_0_rgb",
                 "observation.images.wrist": "observation.images.left_wrist_0_rgb"}' \\
  --batch_size=16 --num_workers=4 \\
  --steps=6000 --save_freq=2000 --log_freq=100 \\
  --wandb.enable=false \\
  --output_dir=$HOME/outputs/train/pi05_so101_clip_cup
""")
h("7.4  训练结果", 2)
table(
    ["指标", "数值"],
    [
        ["训练步数", "6000 步，batch 16，共约 9.6 万个样本（约 5.2 轮）"],
        ["速度", "约 3.1 秒/步，总耗时 5 小时 10 分钟"],
        ["显存", "16.3 GB / 24 GB"],
        ["Loss", "开始约 0.5，最终 0.048，最后 1000 步基本稳定在 0.05 左右"],
        ["学习率", "余弦衰减，峰值 2.5e-5，步数少于默认值时 LeRobot 会自动缩放预热和衰减长度"],
        ["检查点", "第 2000 / 4000 / 6000 步各一个，每个约 11 GB"],
    ],
    widths=[3, 13.5],
)

# ---------------- 8 部署 ----------------
h("8  实机部署与评估")
para("LeRobot 0.6.1 中，用训练好的策略控制真机使用 lerobot-rollout。部署时只需要连接从臂和两个相机，主臂不用接。")
code("""
lerobot-rollout \\
  --strategy.type=episodic \\
  --policy.path=$HOME/outputs/train/pi05_so101_clip_cup/checkpoints/last/pretrained_model \\
  --robot.type=so101_follower --robot.port=$FOLLOWER --robot.id=my_follower \\
  --robot.cameras="{ front: {...同录制...}, wrist: {...同录制...} }" \\
  --rename_map='{"observation.images.front": "observation.images.base_0_rgb",
                 "observation.images.wrist": "observation.images.left_wrist_0_rgb"}' \\
  --dataset.repo_id=local/rollout_so101_clip_cup \\
  --dataset.single_task="Put the clip into the cup" \\
  --dataset.num_episodes=10 --dataset.episode_time_s=30 --dataset.reset_time_s=15 \\
  --dataset.push_to_hub=false
""")
h("踩坑：部署时的两个报错", 3)
bullets([
    ("Visual feature mismatch：", "虽然训练好的检查点里已经保存了相机名映射，但 lerobot-rollout 会在加载预处理器之前单独比对相机名，"
                                 "所以部署时也必须传入同样的 --rename_map。"),
    ("数据集名必须以 rollout_ 开头：", "用 episodic 模式边评估边录制时，repo_id 必须是 xxx/rollout_<名字>；"
                                    "不传 --dataset.root 时会自动加时间戳，重复评估不会冲突。"),
])
h("推理是怎么进行的", 3)
para("控制循环以 30 Hz 运行。π0.5 每次推理输出 50 步动作放进队列，队列用完再根据新的画面重新推理，"
     "所以大约每 1.7 秒推理一次。抓偏了，下一次推理会根据新画面修正。", indent=True)
h("评估结果", 2)
para("在 10 轮自主运行中（按评估录像人工判定）：")
table(
    ["结果", "轮数", "说明"],
    [
        ["成功", "7", "夹起夹子并放进纸杯"],
        ["失败", "2", "没能把夹子夹起（第 0、7 轮）"],
        ["中途人工介入", "1", "第 3 轮中途有人手进入画面"],
    ],
    widths=[3.5, 2, 11],
)
figure("04_rollout_success_ep9_front.jpg", "自主运行成功示例（主相机）：靠近 → 夹取 → 移到纸杯上方 → 松开", 16)
figure("05_rollout_success_ep9_wrist.jpg", "同一轮的腕部相机视角", 16)
figure("06_rollout_success_ep2_front.jpg", "另一轮成功示例（黄色夹子）", 16)
figure("07_rollout_fail_ep0_front.jpg", "失败示例：夹爪多次尝试仍未把夹子夹起", 16)

# ---------------- 9 分析 ----------------
h("9  问题分析")
h("9.1  抓取位置覆盖范围小", 2)
para("在实测中，夹子放在某一小块区域内成功率很高，换到别处就容易失败。我统计了 50 条示范中夹爪闭合时刻的关节位置："
     "底座转角 shoulder_pan 只分布在 -15.5 到 8.3 之间（归一化范围 -100~100），标准差仅 5.4。"
     "也就是说，示范时夹子几乎都放在机械臂正前方一小片区域，模型没有见过其他位置。", indent=True)
figure("09_grasp_coverage.png", "示范中抓取时刻的关节位置分布", 12)
h("9.2  主相机视野偏小", 2)
para("桌前相机离桌面较近，画面只覆盖机械臂前方一小块区域；机械臂本体还会遮挡画面上半部分，"
     "纸杯放在右下角时也有一部分出了画面。夹子放到画面边缘或画面外时，模型就看不到它。", indent=True)
h("9.3  夹子打滑", 2)
para("失败最常见的直接原因是夹子在夹爪里打滑。从数据看，夹住夹子期间，主臂指令的夹爪位置平均为 7.6（0 为完全闭合），"
     "从臂实际位置平均为 10.9，两者只差约 3。舵机是位置控制，夹紧力大致和这个差值成正比，"
     "所以示范时本来就夹得很轻，模型学到的也是“轻轻夹”。另外，LeRobot 默认把夹爪舵机力矩限制在 50%，以防电机过热。", indent=True)
figure("10_gripper_curve.png", "一条示范中的夹爪指令与实际位置", 13)
figure("13_base_fail_ep0_wrist.jpg", "原始评估第 0 轮（腕部相机）：夹取时夹子被指尖推动，约 16 秒后滑出视野，之后机械臂一直在空处寻找", 15)
h("9.4  打滑之后：夹子被推远，模型不会补救", 2)
para("进一步观察发现，失败往往不是一次打滑就结束：夹子一滑，就会被夹爪推开，滑到很远、或者训练数据里从没出现过的位置。"
     "模型在这些没见过的位置不知道该怎么抓，于是越抓越偏。这就是模仿学习中典型的分布偏移（covariate shift）问题："
     "小误差把系统带到训练数据之外，而模型在训练数据之外的表现很差，误差会不断累积。", indent=True)
para("由此可见，几个问题是串在一起的：打滑是起因，数据覆盖不足导致无法恢复。", bold_prefix="结论：")

# ---------------- 10 失败恢复 ----------------
h("10  让机械臂失败后自我调整：三种方法")
para("模型本身是闭环运行的：默认每次推理输出 50 步动作，执行完后再根据新画面重新推理，约每 1.7 秒一次。"
     "但重试效果不好，一是因为每次推理后要盲目执行 50 步，反应慢；二是训练数据里没有“失败后再抓”的示范。"
     "针对这两点，我们提出了三种方法，改动由小到大：", indent=True)
table(
    ["方法", "做法", "成本", "状态"],
    [
        ["1. 更频繁地重新规划", "部署时缩短每次执行的步数（n_action_steps），或改用 RTC 推理", "零成本，只改部署参数", "已测试"],
        ["2. 补录恢复示范", "录制“抓空后抬高、重新对准再抓”的示范，或用 DAgger 在模型出错时接管纠正", "需要补录数据并重新训练", "已实施"],
        ["3. 失败检测与重试模块", "检测抓空（夹爪闭合到接近 0）或打滑（舵机电流突降），清空动作队列，退回抓取前姿态后重试", "需要写控制代码、读取舵机电流", "计划中（论文方法）"],
    ],
    widths=[3.5, 7, 3.5, 2.5],
)
h("10.1  方法 1 的实验：n_action_steps=15 与 RTC", 2)
para("在部署命令中加上 --policy.n_action_steps=15，让模型每 15 步（约 0.5 秒）就重新推理一次：")
code("""
lerobot-rollout --strategy.type=episodic \\
  --policy.path=.../checkpoints/last/pretrained_model \\
  --policy.n_action_steps=15 \\
  ...其余参数同第 8 节...
""")
para("实测结果：机械臂明显一顿一顿，抓取效果也变差。原因是同步推理时，每次推理机械臂都要停下来等模型算完，"
     "推理频率提高 3 倍多，停顿也就密了 3 倍多；而且每一段新动作都是重新规划的，和上一段衔接不上，看起来像在“犹豫”。", indent=True)
para("随后改用 RTC（Real-Time Chunking）推理：模型在后台线程推理，机械臂不用停下来等；新的一段动作会参照上一段还没执行完的部分生成，衔接更平滑。")
code("""
  --inference.type=rtc \\
  --inference.rtc.execution_horizon=10 \\
  --inference.rtc.max_guidance_weight=10.0
""")
para("为了量化动作是否平滑，我统计了录像中相邻两帧关节指令的最大变化量，把变化超过 3（归一化单位）的记为一次“大跳变”：")
table(
    ["推理方式", "每秒大跳变次数", "相邻帧变化的 95 分位数"],
    [
        ["原始同步推理（每 50 步推理一次）", "0.42", "1.81"],
        ["同步推理 + n_action_steps=15", "1.45（约为原始的 3.4 倍）", "2.92"],
        ["RTC 推理", "0.89", "2.06"],
    ],
    widths=[7, 4.5, 5],
)
figure("11_inference_jumps.png", "三种推理方式的动作跳变对比（n_action_steps=15 和 RTC 各录了 2 轮，样本较少）", 16.5)
para("实验说明，单靠“更频繁地重新规划”解决不了问题：夹子被推到没见过的位置后，模型反应再快也不知道该怎么抓。"
     "要想真正提高重试能力，还得靠方法 2（补数据）和方法 3（检测与重试），同时从源头减少打滑。", bold_prefix="结论：")

h("10.2  方法 2 的实施：DAgger 接管纠正", 2)
h("DAgger 算法原理", 3)
para("DAgger（Dataset Aggregation，Ross 等人 2011 年提出）是解决模仿学习分布偏移问题的经典迭代算法。"
     "行为克隆的根本缺陷是：模型只在示范出现过的状态上训练，一旦执行中出现误差把自己带到没见过的状态，"
     "模型就不知道该怎么办，误差不断累积（covariate shift）。DAgger 的做法是：")
bullets([
    "第 1 步：用当前策略在真实环境运行，让它自己探索到各种（包括出错的）状态；",
    "第 2 步：在这些状态上由人类专家接管，示范“正确动作是什么”；",
    "第 3 步：把这些“策略访问到的状态 + 专家的动作”聚合进训练集，重新训练；",
    "第 4 步：重复以上步骤，逐步把数据分布对齐到策略实际会遇到的状态分布。",
])
para("理论保证是：只要专家标注足够好，策略性能随迭代次数收敛到接近专家水平。"
     "在 LeRobot 里对应 --strategy.type=dagger：策略自主运行时随时可以接管，只把接管期间的画面、状态和遥操作动作录成新的纠正 episode。")
h("我们的工作流程", 3)
bullets([
    ("启动方式：", "lerobot-rollout --strategy.type=dagger，键位：空格暂停/恢复策略，Tab 开始/结束人工接管。为了让“成功后一键回初始位”，我写了一个 dagger_with_home.py 包装器，加了 → 键回 home 位等待换场景。"),
    ("接管时机：", "模型碰跑夹子、抓空、或者走到陌生位置明显不知道该干嘛时按 Tab 接管，把夹子夹起放进杯子后按空格交还；只录接管段，不录整轮。"),
    ("共录 29 条纠正", "，时长 1.6–18 秒，来自 4 个录制批次。"),
])
figure("18_dagger_inspect_a.jpg", "DAgger 纠正数据检查图（每行一条：腕部首帧、腕部尾帧、主相机尾帧）", 16)
h("数据质量检查：三种坏样本", 3)
para("合并训练前，我对每条纠正做了首/尾帧人工检查 + 动作统计量检查，剔除了 6 条：")
table(
    ["坏样本类型", "如何发现", "条数"],
    [
        ["时长极短（<2 秒）", "误触保存，基本没有有效动作", "1"],
        ["任务未完成", "尾帧里夹子还在桌面上不在杯中（提前按了结束）", "2"],
        ["遥操作不连贯", "动作统计：长时间静止（|Δaction| 只有正常的 1/3）后突然出现突变尖峰（占总帧数 5–7%），说明中途停顿后猛拉", "3"],
    ],
    widths=[4, 9.5, 3],
)
para("第三类只能量化发现——肉眼从首尾帧看不出来，但“停顿→猛冲”的轨迹会把模型也教得犹犹豫豫。"
     "剩余 23 条与原 50 条示范合并为新数据集（73 条、26780 帧，纠正约占 32%）。")
h("初步结果与教训", 3)
bullets([
    ("恢复能力确实学到了：", "重训后的模型在夹子被碰跑、抓空后能主动返回重新抓取——这正是 DAgger 数据要教的行为。"),
    ("但整体成功率下降：", "纠正数据占总数据约 1/3，且全是“失败状态→恢复”的非常态轨迹，正常抓取轨迹被稀释；加上部分纠正有动作断点（接管瞬间机械臂会向主臂位置滑移），整体动作变得不够果断。"),
    ("经验：", "纠正数据宁缺毋滥——占比建议控制在 20–30%，且每一条都要检查连贯性；接管前后最好让机械臂先停稳再开始录。"),
    ("下一步：", "按更干净的配比重新训练评估，或者再补一轮更高质量的纠正（DAgger 本来就是多轮迭代的算法）。"),
])

# ---------------- 11 摩擦实验 ----------------
h("11  从源头减少打滑：摩擦改进实验")
para("既然打滑是起因，就先从摩擦力入手。我在夹子上粘了一点双面胶，部署时使用和第一次评估完全相同的原始同步推理命令，唯一的变量就是双面胶。", indent=True)
h("11.1  结果", 2)
table(
    ["条件", "有效轮次", "任务成功", "成功夹住并提起", "打滑/抓不起", "碰跑", "粘住松不开", "人工介入"],
    [
        ["原始", "10", "7（70%）", "7", "2", "0", "0", "1"],
        ["夹子贴双面胶", "12", "4（33%）", "8（67%）", "0", "3", "4", "0"],
    ],
    widths=[2.8, 1.6, 2.1, 2.4, 2, 1.4, 2.1, 1.6],
)
para("注：结果按评估录像逐轮核对；双面胶测试实际进行 13 次，其中 1 次被丢弃未保存，另有 1 轮结果从录像中无法判断，未计入上表。"
     "原始评估第 0 轮是打滑后夹子被推走，归入“打滑/抓不起”。", bold_prefix="")
figure("12_outcome_compare.png", "两组实机评估的结果分布对比", 14)
h("11.2  三种典型情况", 2)
figure("14_tape_success_ep3_front.jpg", "成功：牢牢夹住，没有打滑，顺利放进纸杯", 16)
figure("15_tape_stuck_ep4.jpg", "粘住：夹爪已经张开，但夹子仍粘在夹爪上（右为腕部相机）", 15)
figure("16_tape_knock_ep2_front.jpg", "碰跑：夹爪下降时碰到夹子，把它推到一旁", 16)
figure("17_tape_knock_ep7_wrist.jpg", "碰跑（腕部相机）：重新抓取时夹爪抬得不够高，贴着桌面把夹子推走", 15)
h("11.3  分析", 2)
bullets([
    ("打滑基本解决：", "贴胶后没有再出现“夹住又滑掉”，成功夹住的比例为 8/12，说明原始失败的主要原因确实是摩擦不够。"),
    ("成功率下降的原因是松不开：", "有 4 次夹子粘在夹爪上。如果能正常松开，成功率最好可以接近 8/12，和原始水平相当。"
                         "其中一轮最后夹爪只张开到 15（成功的几轮都在 30 以上），模型没有完全松开，也加重了粘住的问题。"),
    ("碰跑成为主要问题：", "一是接近夹子时轨迹偏低，夹爪或机械臂先碰到夹子；二是重新抓取时没有抬高，贴着桌面平移。"
                   "训练数据里从来没有“抓失败后抬起来、重新对准”的动作，这又是分布偏移。"),
    ("对比条件不完全相同：", "双面胶测试全部使用黄色夹子，原始测试两种颜色都有。正式实验需要统一夹子颜色和摆放位置。"),
])

# ---------------- 12 踩坑汇总 ----------------
h("12  踩坑汇总")
table(
    ["现象", "原因", "解决办法"],
    [
        ["串口无权限 / usermod 无效", "命令里误写了 $pc，变量为空", "sudo usermod -aG dialout $USER"],
        ["标定时端口为空", "LEADER 等变量没在当前终端设置", "export 并写入 ~/.bashrc，旧终端要 source"],
        ["只识别到一个相机", "USB 口问题", "换 USB 口，用 /dev/v4l/by-id 固定路径"],
        ["录制帧率只有 24 Hz", "开启了实时画面显示", "录制时不加 --display_data"],
        ["保存空 episode 报错", "方向键自动重复连续触发", "轻点方向键；xset r off"],
        ["续录报 FileExistsError / 要求 root", "未开启续录或缺少 root", "--resume=true 加 --dataset.root"],
        ["lerobot-dataset-viz 未找到命令", "没激活 conda 环境", "conda activate lerobot"],
        ["pip 403 / HF 超时", "镜像与网络限制", "官方 PyPI；ModelScope 下载；HF_HUB_OFFLINE=1"],
        ["rollout 相机名不匹配", "rollout 单独校验相机名", "部署时也传 --rename_map"],
        ["rollout 数据集名报错", "要求以 rollout_ 开头", "repo_id 改为 xxx/rollout_名字"],
        ["连接时报 Torque_Enable 写入失败", "舵机串联线偶发通信错误", "重试；断电后重插舵机间连线"],
        ["n_action_steps=15 后一顿一顿", "同步推理每次推理都要停下等待", "恢复默认值，或改用 RTC 推理"],
        ["相机读不到帧（rollout 即崩）", "两个相机+串口挤在一个 USB hub 里带宽不足", "相机插主板 USB3 蓝口，绕开 hub"],
        ["DAgger 重训后整体变差", "纠正占比过高 + 部分纠正动作断点/停顿", "纠正控制在 20–30%，逐条查连贯性"],
        ["DAgger 退出时主臂报电压错", "试图驱动未独立供电的主臂电机", "主臂设为 LEADER_ACTUATED=False，交还时只滑移从臂"],
        ["双面胶导致夹子松不开", "黏性太强", "改在夹爪内侧贴不黏的摩擦材料"],
    ],
    widths=[4.5, 5, 7],
)

# ---------------- 13 下一步 ----------------
h("13  下一步计划")
bullets([
    ("摩擦材料改贴夹爪：", "去掉夹子上的双面胶，在夹爪内侧贴硅胶垫或电工胶布这类不黏但摩擦大的材料，既防滑又能松开。"),
    ("补录“从上往下抓”的示范：", "夹爪先移到夹子正上方再垂直下降，减少碰跑。"),
    ("DAgger 第二轮：", "第一轮纠正让模型学会了恢复但整体变钝，按更干净配比重训后若仍不足，再补录一轮高质量纠正（接管前停稳、动作连贯）。"),
    ("失败检测与重试（方法 3）：", "记录夹爪舵机电流，检测打滑和抓空，自动重试；这也是学位论文的方法部分。"),
    ("限制夹子滑动范围：", "用浅托盘或围挡，让被碰到的夹子不会跑太远。"),
    ("扩大覆盖范围、调整相机：", "网格化摆放；必要时把主相机调高或后移（需要重新录数据）。"),
    ("统一评估条件：", "固定夹子颜色和摆放位置，每个条件测 20 轮以上。"),
])

h("14  参考资料")
bullets([
    "LeRobot 官方仓库与文档：https://github.com/huggingface/lerobot",
    "OpenPI（π0 / π0.5 原始实现）：https://github.com/Physical-Intelligence/openpi",
    "π0.5 论文：Black et al., “π0.5: a Vision-Language-Action Model with Open-World Generalization”, 2025, https://arxiv.org/abs/2504.16054",
    "DAgger 论文：Ross, Gordon & Bagnell, “A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning”, AISTATS 2011, https://arxiv.org/abs/1011.0686",
    "π0.5 预训练权重（ModelScope）：https://modelscope.cn/models/lerobot/pi05_base",
])

doc.save(OUT)
print("saved", OUT)
