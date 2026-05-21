from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Cm, Pt


BASE_DIR = Path("/mnt/ai-platform")
DOCX_PATH = BASE_DIR / "docs" / "学位论文.docx"
OUTPUT_PATH = BASE_DIR / "docs" / "学位论文答辩PPT.pptx"
ASSET_DIR = BASE_DIR / "tmp" / "thesis_ppt_assets"


COLORS = {
    "navy": RGBColor(24, 54, 93),
    "blue": RGBColor(46, 88, 146),
    "sky": RGBColor(224, 235, 248),
    "border": RGBColor(176, 196, 222),
    "text": RGBColor(42, 42, 42),
    "muted": RGBColor(92, 104, 120),
    "accent": RGBColor(193, 63, 63),
    "white": RGBColor(255, 255, 255),
    "green": RGBColor(68, 123, 90),
}

FONT_CN = "宋体"
FONT_TITLE = "黑体"
FONT_EN = "Calibri"


@dataclass
class ThesisMeta:
    title: str
    school: str
    college: str
    author: str
    student_id: str
    advisor: str
    major: str
    date_text: str
    abstract: str
    keywords: str


def set_font(run, name: str, size: int, bold: bool = False, color: RGBColor | None = None) -> None:
    font = run.font
    font.name = name
    font.size = Pt(size)
    font.bold = bold
    if color is not None:
        font.color.rgb = color
    r_pr = run._r.get_or_add_rPr()
    r_pr.set(qn("a:latin"), FONT_EN)
    r_pr.set(qn("a:ea"), name)
    r_pr.set(qn("a:cs"), name)


def add_textbox(slide, left, top, width, height, text="", *, fill=COLORS["white"], line=COLORS["border"]):
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    shape.line.width = Pt(1)
    if text:
        tf = shape.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = text
        set_font(run, FONT_CN, 18, color=COLORS["text"])
    return shape


def add_paragraph(tf, text: str, *, level: int = 0, size: int = 20, bold: bool = False, color=COLORS["text"], align=PP_ALIGN.LEFT) -> None:
    p = tf.paragraphs[0] if not tf.text else tf.add_paragraph()
    p.level = level
    p.alignment = align
    p.space_after = Pt(5)
    run = p.add_run()
    run.text = text
    set_font(run, FONT_CN, size, bold=bold, color=color)


def set_background(slide) -> None:
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(248, 250, 252)


def add_header(slide, title: str, subtitle: str | None = None) -> None:
    set_background(slide)
    band = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, Cm(33.867), Cm(1.55))
    band.fill.solid()
    band.fill.fore_color.rgb = COLORS["navy"]
    band.line.fill.background()

    title_box = slide.shapes.add_textbox(Cm(0.9), Cm(0.2), Cm(15.5), Cm(0.8))
    tf = title_box.text_frame
    tf.clear()
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = title
    set_font(run, FONT_TITLE, 24, bold=True, color=COLORS["white"])

    if subtitle:
        sub_box = slide.shapes.add_textbox(Cm(24), Cm(0.24), Cm(8.6), Cm(0.7))
        tf2 = sub_box.text_frame
        tf2.clear()
        tf2.vertical_anchor = MSO_ANCHOR.MIDDLE
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.RIGHT
        run2 = p2.add_run()
        run2.text = subtitle
        set_font(run2, FONT_CN, 10, color=COLORS["white"])

    footer = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, Cm(18.65), Cm(33.867), Cm(0.4))
    footer.fill.solid()
    footer.fill.fore_color.rgb = COLORS["navy"]
    footer.line.fill.background()


def make_cover(prs: Presentation, meta: ThesisMeta) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_background(slide)

    top_band = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, Cm(33.867), Cm(2.2))
    top_band.fill.solid()
    top_band.fill.fore_color.rgb = COLORS["navy"]
    top_band.line.fill.background()

    if (ASSET_DIR / "image1.jpeg").exists():
        slide.shapes.add_picture(str(ASSET_DIR / "image1.jpeg"), Cm(0.8), Cm(0.45), height=Cm(1.1))

    school_box = slide.shapes.add_textbox(Cm(12.2), Cm(0.45), Cm(9.5), Cm(1))
    tf = school_box.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = meta.school
    set_font(run, FONT_TITLE, 22, bold=True, color=COLORS["white"])

    tag = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Cm(12.5), Cm(3.0), Cm(8.8), Cm(1.3))
    tag.fill.solid()
    tag.fill.fore_color.rgb = COLORS["sky"]
    tag.line.color.rgb = COLORS["border"]
    tf = tag.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = "本科毕业论文答辩"
    set_font(run, FONT_TITLE, 20, bold=True, color=COLORS["navy"])

    title_box = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Cm(3.2), Cm(5.0), Cm(27.4), Cm(3.1))
    title_box.fill.solid()
    title_box.fill.fore_color.rgb = COLORS["white"]
    title_box.line.color.rgb = COLORS["blue"]
    title_box.line.width = Pt(1.8)
    tf = title_box.text_frame
    tf.clear()
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = meta.title
    set_font(run, FONT_TITLE, 24, bold=True, color=COLORS["text"])

    info = [
        ("学院", meta.college),
        ("专业", meta.major),
        ("学生", meta.author),
        ("学号", meta.student_id),
        ("导师", meta.advisor),
        ("日期", meta.date_text),
    ]
    for idx, (label, value) in enumerate(info):
        x = Cm(5.0 + (idx % 2) * 12)
        y = Cm(10.3 + (idx // 2) * 2.0)
        panel = add_textbox(slide, x, y, Cm(10.3), Cm(1.25), fill=COLORS["sky"])
        tf = panel.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run1 = p.add_run()
        run1.text = f"{label}："
        set_font(run1, FONT_TITLE, 16, bold=True, color=COLORS["navy"])
        run2 = p.add_run()
        run2.text = value
        set_font(run2, FONT_CN, 16, color=COLORS["text"])

    foot = slide.shapes.add_textbox(Cm(0.9), Cm(17.6), Cm(32), Cm(0.5))
    tf = foot.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = "答辩汇报内容依据《学位论文》自动整理生成"
    set_font(run, FONT_CN, 10, color=COLORS["muted"])


def add_title_and_outline(prs: Presentation, meta: ThesisMeta) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "研究概况", "课题基本信息与汇报提纲")

    left = add_textbox(slide, Cm(1.0), Cm(2.1), Cm(14.7), Cm(14.9), fill=COLORS["white"])
    tf = left.text_frame
    tf.clear()
    add_paragraph(tf, "研究摘要", size=20, bold=True, color=COLORS["navy"])
    add_paragraph(tf, meta.abstract[:220] + "……", size=16)
    add_paragraph(tf, f"关键词：{meta.keywords}", size=15, color=COLORS["blue"])

    right = add_textbox(slide, Cm(17.0), Cm(2.1), Cm(15.0), Cm(14.9), fill=COLORS["white"])
    tf2 = right.text_frame
    tf2.clear()
    add_paragraph(tf2, "答辩提纲", size=20, bold=True, color=COLORS["navy"])
    outline = [
        "1. 研究背景与研究意义",
        "2. 量子加密理论基础与技术特点",
        "3. 核心应用场景与方案设计",
        "4. 关键模块实现与融合策略",
        "5. 性能、安全性评估与结论",
        "6. 挑战、趋势与未来展望",
    ]
    for item in outline:
        add_paragraph(tf2, item, size=18)


def add_background_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "研究背景与意义", "网络安全压力持续上升")

    left = add_textbox(slide, Cm(1.0), Cm(2.0), Cm(13.0), Cm(14.9), fill=COLORS["white"])
    tf = left.text_frame
    tf.clear()
    add_paragraph(tf, "研究背景", size=20, bold=True, color=COLORS["navy"])
    points = [
        "数字化转型加速，网络已成为政企业务与个人信息流转的核心基础设施。",
        "数据泄露、网络攻击、勒索软件等事件频发，传统加密技术面临量子计算潜在威胁。",
        "论文聚焦量子加密技术，为提升传输保密性、完整性和身份认证可靠性提供新路径。",
    ]
    for point in points:
        add_paragraph(tf, f"• {point}", size=17)
    add_paragraph(tf, "研究意义", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "从理论上梳理量子加密技术在网络安全中的应用逻辑。",
        "从工程上提出可融入现有网络体系的应用方案与实施策略。",
        "从评估上验证其在安全增强和性能可接受性方面的可行性。",
    ]:
        add_paragraph(tf, f"• {point}", size=17)

    chart_data = CategoryChartData()
    chart_data.categories = ["2021年", "2022年", "2023年"]
    chart_data.add_series("数据泄露事件数量", (3500, 4200, 5100))
    chart_data.add_series("经济损失（亿美元）", (1500, 1800, 2200))
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Cm(15.0), Cm(2.4), Cm(16.4), Cm(7.3), chart_data
    ).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.value_axis.has_major_gridlines = True
    chart.category_axis.tick_labels.font.size = Pt(11)
    chart.value_axis.tick_labels.font.size = Pt(11)
    chart.series[0].format.fill.solid()
    chart.series[0].format.fill.fore_color.rgb = COLORS["blue"]
    chart.series[1].format.fill.solid()
    chart.series[1].format.fill.fore_color.rgb = COLORS["accent"]

    note = add_textbox(slide, Cm(15.0), Cm(10.3), Cm(16.4), Cm(6.6), fill=COLORS["sky"])
    tf2 = note.text_frame
    tf2.clear()
    add_paragraph(tf2, "论文中的表1-1显示：", size=19, bold=True, color=COLORS["navy"])
    add_paragraph(tf2, "• 数据泄露事件数量由 3500 起增长至 5100 起。", size=17)
    add_paragraph(tf2, "• 涉及用户数量由 12 亿人增长至 18 亿人。", size=17)
    add_paragraph(tf2, "• 经济损失由 1500 亿美元上升到 2200 亿美元。", size=17)
    add_paragraph(tf2, "结论：高安全等级通信技术具备明确研究与应用必要性。", size=17, bold=True, color=COLORS["accent"])


def add_theory_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "理论基础与技术特点", "量子加密的原理与优势")

    panel1 = add_textbox(slide, Cm(1.0), Cm(2.1), Cm(10.3), Cm(7.1), fill=COLORS["white"])
    tf1 = panel1.text_frame
    tf1.clear()
    add_paragraph(tf1, "理论基础", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "量子态叠加：单个量子可承载多状态信息，为密钥编码提供基础。",
        "量子纠缠：远距离保持关联，可用于构建高安全密钥分发机制。",
        "不可克隆与测不准：一旦窃听即改变量子态，可实现主动探测。",
    ]:
        add_paragraph(tf1, f"• {point}", size=16)

    panel2 = add_textbox(slide, Cm(11.8), Cm(2.1), Cm(10.3), Cm(7.1), fill=COLORS["white"])
    tf2 = panel2.text_frame
    tf2.clear()
    add_paragraph(tf2, "发展历程", size=20, bold=True, color=COLORS["navy"])
    for item in [
        "20世纪70年代：理论萌芽。",
        "20世纪80至90年代：BB84、E91 等协议提出。",
        "2007年：实现百公里级量子密钥分发实验。",
        "2016年：中国“墨子号”卫星实现千公里级星地分发。",
    ]:
        add_paragraph(tf2, f"• {item}", size=16)

    panel3 = add_textbox(slide, Cm(22.6), Cm(2.1), Cm(9.4), Cm(7.1), fill=COLORS["white"])
    tf3 = panel3.text_frame
    tf3.clear()
    add_paragraph(tf3, "技术特点", size=20, bold=True, color=COLORS["navy"])
    for item in [
        "理论安全性高",
        "密钥随机性强",
        "窃听可感知",
        "适合高敏感场景",
    ]:
        add_paragraph(tf3, f"• {item}", size=16)

    compare = add_textbox(slide, Cm(1.0), Cm(10.0), Cm(31.0), Cm(6.8), fill=COLORS["sky"])
    tf4 = compare.text_frame
    tf4.clear()
    add_paragraph(tf4, "与传统加密技术对比", size=20, bold=True, color=COLORS["navy"])
    for row in [
        "安全机制：传统方法依赖计算复杂度，量子加密依赖物理规律。",
        "攻击表现：传统方法存在被量子计算削弱风险，量子加密可识别窃听行为。",
        "应用侧重点：传统方法适合广泛部署，量子加密适合高价值、高保密场景。",
    ]:
        add_paragraph(tf4, f"• {row}", size=17)


def add_scene_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "应用场景分析", "论文归纳的四类核心场景")

    scenes = [
        ("数据传输环节", "保障链路中的机密性与完整性，降低误码率与泄露风险。"),
        ("网络通信协议层", "增强身份认证与会话密钥协商安全性。"),
        ("云存储安全", "降低非授权访问与数据篡改概率。"),
        ("物联网设备连接", "提升复杂连接环境中的安全通信可靠性。"),
    ]
    for idx, (title, desc) in enumerate(scenes):
        col = idx % 2
        row = idx // 2
        box = add_textbox(
            slide,
            Cm(1.0 + col * 15.8),
            Cm(2.2 + row * 5.1),
            Cm(15.0),
            Cm(4.2),
            fill=COLORS["white"],
        )
        tf = box.text_frame
        tf.clear()
        add_paragraph(tf, title, size=19, bold=True, color=COLORS["navy"])
        add_paragraph(tf, desc, size=16)

    if (ASSET_DIR / "image2.png").exists():
        slide.shapes.add_picture(str(ASSET_DIR / "image2.png"), Cm(4.0), Cm(12.9), width=Cm(25.8))


def add_design_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "应用方案设计", "整体架构与实施路径")

    left = add_textbox(slide, Cm(1.0), Cm(2.1), Cm(11.0), Cm(14.8), fill=COLORS["white"])
    tf = left.text_frame
    tf.clear()
    add_paragraph(tf, "整体设计思路", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "以量子密钥分发模块为核心，支撑网络侧加密与解密业务。",
        "在既有网络拓扑中增加量子密钥中心、加密设备和适配模块。",
        "明确量子密钥生成、分发、加密传输、接收解密的完整链路。",
    ]:
        add_paragraph(tf, f"• {point}", size=16)
    add_paragraph(tf, "论文强调：架构设计不仅关注安全性，也强调与现网系统的兼容性和工程可落地性。", size=16)

    if (ASSET_DIR / "image4.png").exists():
        slide.shapes.add_picture(str(ASSET_DIR / "image4.png"), Cm(12.8), Cm(2.4), width=Cm(18.7))

    bottom = add_textbox(slide, Cm(12.8), Cm(10.8), Cm(18.7), Cm(6.1), fill=COLORS["sky"])
    tf2 = bottom.text_frame
    tf2.clear()
    add_paragraph(tf2, "方案价值", size=20, bold=True, color=COLORS["navy"])
    add_paragraph(tf2, "• 通过量子密钥增强数据传输过程保密性。", size=17)
    add_paragraph(tf2, "• 支持在复杂网络环境下构建统一安全链路。", size=17)
    add_paragraph(tf2, "• 为金融、政务、能源、物联网等高等级场景提供可扩展模板。", size=17)


def add_implementation_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "关键模块实现", "密钥分发与加解密模块")

    left = add_textbox(slide, Cm(1.0), Cm(2.1), Cm(15.0), Cm(14.7), fill=COLORS["white"])
    tf1 = left.text_frame
    tf1.clear()
    add_paragraph(tf1, "模块一：量子密钥分发", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "基于 BB84 协议思想，随机生成基并制备量子态。",
        "通过量子信道完成状态传输，依托不可克隆定理确保安全。",
        "通信双方通过比对测量基筛选有效密钥。",
    ]:
        add_paragraph(tf1, f"• {point}", size=16)
    add_paragraph(tf1, "论文中给出了随机基生成与量子态制备的示意代码，用于说明密钥形成机制。", size=16)
    add_paragraph(tf1, "模块二：加密解密算法", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "采用一次一密思路，将明文与量子密钥进行异或运算得到密文。",
        "接收方使用相同密钥再次异或，恢复原始明文。",
        "该过程突出体现量子密钥在实际业务加解密中的承载作用。",
    ]:
        add_paragraph(tf1, f"• {point}", size=16)

    code_box = add_textbox(slide, Cm(16.6), Cm(2.1), Cm(15.4), Cm(8.0), fill=COLORS["sky"])
    tf2 = code_box.text_frame
    tf2.clear()
    add_paragraph(tf2, "实现逻辑摘要", size=20, bold=True, color=COLORS["navy"])
    for line in [
        "generate_basis(length) -> 随机生成测量基",
        "prepare_quantum_states(bits, bases) -> 制备量子态",
        "encrypt(plaintext, key) -> 逐位异或得到密文",
        "decrypt(ciphertext, key) -> 使用同密钥恢复明文",
    ]:
        add_paragraph(tf2, line, size=16)

    bottom = add_textbox(slide, Cm(16.6), Cm(10.6), Cm(15.4), Cm(6.2), fill=COLORS["white"])
    tf3 = bottom.text_frame
    tf3.clear()
    add_paragraph(tf3, "与现有网络融合策略", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "分析现网拓扑，选择量子加密设备部署位置。",
        "对路由器、交换机等设备进行兼容性评估与适配。",
        "兼顾软件识别、监管要求与运维管理机制。",
    ]:
        add_paragraph(tf3, f"• {point}", size=16)


def add_assessment_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "性能与安全性评估", "应用效果验证")

    chart_data = CategoryChartData()
    chart_data.categories = ["非授权访问概率", "数据篡改率"]
    chart_data.add_series("使用前", (15, 8))
    chart_data.add_series("使用后", (2, 1))
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED, Cm(1.0), Cm(2.4), Cm(14.4), Cm(7.6), chart_data
    ).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.category_axis.tick_labels.font.size = Pt(12)
    chart.value_axis.tick_labels.font.size = Pt(11)
    chart.series[0].format.fill.solid()
    chart.series[0].format.fill.fore_color.rgb = COLORS["accent"]
    chart.series[1].format.fill.solid()
    chart.series[1].format.fill.fore_color.rgb = COLORS["green"]

    eval_box = add_textbox(slide, Cm(16.0), Cm(2.2), Cm(16.0), Cm(7.8), fill=COLORS["white"])
    tf = eval_box.text_frame
    tf.clear()
    add_paragraph(tf, "评估指标与方法", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "加密解密计算开销：采用时间复杂度与性能监测工具分析。",
        "数据传输延迟：基于网络抓包与监测仪进行测评。",
        "带宽占用率：利用流量统计与分析软件观察影响。",
        "安全性分析：重点考察抗暴力破解、中间人攻击等能力。",
    ]:
        add_paragraph(tf, f"• {point}", size=16)

    if (ASSET_DIR / "image3.png").exists():
        slide.shapes.add_picture(str(ASSET_DIR / "image3.png"), Cm(3.6), Cm(11.0), width=Cm(26.6))

    summary = add_textbox(slide, Cm(1.0), Cm(13.2), Cm(31.0), Cm(3.6), fill=COLORS["sky"])
    tf2 = summary.text_frame
    tf2.clear()
    add_paragraph(tf2, "论文结论", size=20, bold=True, color=COLORS["navy"])
    add_paragraph(tf2, "应用量子加密技术后，关键安全指标显著改善，且在网络延迟、密钥生成速率等方面表现出可接受的工程可行性。", size=17)


def add_challenge_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "挑战与应对策略", "技术、成本与标准三重约束")

    cols = [
        (
            "技术挑战",
            [
                "设备稳定性不足",
                "远距离量子信号传输衰减",
                "复杂环境下兼容性与维护难度较高",
            ],
            [
                "优化散热与芯片设计",
                "研发低损耗光纤与量子中继技术",
                "推进模块化适配部署",
            ],
        ),
        (
            "成本挑战",
            [
                "量子密钥分发设备成本高",
                "部署、维护与培训门槛较高",
                "中小机构短期内普及困难",
            ],
            [
                "扩大产业规模形成规模效应",
                "通过持续技术革新降低设备成本",
                "优先在高价值场景分阶段推广",
            ],
        ),
        (
            "标准与法规",
            [
                "行业标准尚未统一",
                "跨厂商互操作性不足",
                "专门法规与监管细则仍待完善",
            ],
            [
                "推动行业协会制定统一标准",
                "建立测试方法与认证体系",
                "完善配套法律与监管机制",
            ],
        ),
    ]

    for idx, (title, risks, actions) in enumerate(cols):
        box = add_textbox(slide, Cm(1.0 + idx * 10.5), Cm(2.3), Cm(9.6), Cm(14.1), fill=COLORS["white"])
        tf = box.text_frame
        tf.clear()
        add_paragraph(tf, title, size=19, bold=True, color=COLORS["navy"])
        add_paragraph(tf, "主要问题", size=17, bold=True, color=COLORS["accent"])
        for item in risks:
            add_paragraph(tf, f"• {item}", size=15)
        add_paragraph(tf, "对应策略", size=17, bold=True, color=COLORS["green"])
        for item in actions:
            add_paragraph(tf, f"• {item}", size=15)


def add_trend_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "发展趋势", "技术融合与场景外延持续增强")

    trends = [
        ("技术融合趋势", "量子加密与人工智能、5G、区块链协同，将提升密钥分发效率、实时监测能力与可信通信能力。"),
        ("场景拓展趋势", "工业互联网、智能电网、云边协同等新型网络环境对高等级安全通信需求不断增长。"),
        ("全球化趋势", "国际量子通信网络建设加速，标准化、普及化与跨国协同将成为长期方向。"),
    ]
    for idx, (title, desc) in enumerate(trends):
        box = add_textbox(slide, Cm(1.2), Cm(2.4 + idx * 4.7), Cm(30.8), Cm(3.8), fill=COLORS["white"])
        tf = box.text_frame
        tf.clear()
        add_paragraph(tf, title, size=19, bold=True, color=COLORS["navy"])
        add_paragraph(tf, desc, size=16)

    band = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.CHEVRON, Cm(5.5), Cm(16.8), Cm(22.8), Cm(1.0))
    band.fill.solid()
    band.fill.fore_color.rgb = COLORS["blue"]
    band.line.color.rgb = COLORS["blue"]
    tf = band.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = "量子加密技术将从“高安全专用”逐步走向“关键行业规模化应用”"
    set_font(run, FONT_CN, 16, bold=True, color=COLORS["white"])


def add_conclusion_slide(prs: Presentation) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, "研究结论与展望", "答辩总结")

    left = add_textbox(slide, Cm(1.0), Cm(2.0), Cm(15.0), Cm(14.9), fill=COLORS["white"])
    tf1 = left.text_frame
    tf1.clear()
    add_paragraph(tf1, "研究结论", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "论文系统梳理了量子加密技术在计算机网络安全中的应用逻辑与典型场景。",
        "提出了以量子密钥分发为核心的网络安全应用方案，并明确关键模块实现路径。",
        "通过性能与安全性分析，验证了方案在高安全场景中的可行性与应用价值。",
    ]:
        add_paragraph(tf1, f"• {point}", size=16)

    right = add_textbox(slide, Cm(17.0), Cm(2.0), Cm(15.0), Cm(14.9), fill=COLORS["white"])
    tf2 = right.text_frame
    tf2.clear()
    add_paragraph(tf2, "未来展望", size=20, bold=True, color=COLORS["navy"])
    for point in [
        "进一步提升量子加密系统在复杂网络中的稳定性与兼容性。",
        "深化与人工智能、区块链等前沿技术的融合创新。",
        "加快标准体系与产业化路径建设，推动在更多行业落地。",
    ]:
        add_paragraph(tf2, f"• {point}", size=16)
    add_paragraph(tf2, "总体判断：量子加密技术将在关键基础设施和高敏感业务中发挥越来越重要的作用。", size=16, bold=True, color=COLORS["accent"])


def add_thanks_slide(prs: Presentation, meta: ThesisMeta) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_background(slide)

    band = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, Cm(33.867), Cm(19.05))
    band.fill.solid()
    band.fill.fore_color.rgb = RGBColor(245, 248, 252)
    band.line.fill.background()

    center = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Cm(5.0), Cm(4.2), Cm(23.8), Cm(10.8))
    center.fill.solid()
    center.fill.fore_color.rgb = COLORS["white"]
    center.line.color.rgb = COLORS["blue"]
    center.line.width = Pt(1.8)
    tf = center.text_frame
    tf.clear()
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p1 = tf.paragraphs[0]
    p1.alignment = PP_ALIGN.CENTER
    r1 = p1.add_run()
    r1.text = "感谢各位老师聆听"
    set_font(r1, FONT_TITLE, 28, bold=True, color=COLORS["navy"])
    p2 = tf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text = f"答辩人：{meta.author}    指导教师：{meta.advisor}"
    set_font(r2, FONT_CN, 18, color=COLORS["text"])
    p3 = tf.add_paragraph()
    p3.alignment = PP_ALIGN.CENTER
    r3 = p3.add_run()
    r3.text = meta.date_text
    set_font(r3, FONT_CN, 16, color=COLORS["muted"])


def extract_meta(doc: Document) -> ThesisMeta:
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    title = texts[1]
    college = next(t.split("：", 1)[1] for t in texts if t.startswith("所在学院"))
    author = next(t.split("：", 1)[1] for t in texts if t.startswith("学生姓名"))
    student_id = next(t.split("：", 1)[1] for t in texts if t.startswith("学生学号"))
    advisor = next(t.split("：", 1)[1] for t in texts if t.startswith("指导教师"))
    major = next(t.split("：", 1)[1] for t in texts if t.startswith("专"))
    date_text = next(t for t in texts if "年" in t and "月" in t and len(t) <= 10)

    abstract = ""
    keywords = ""
    for idx, para in enumerate(doc.paragraphs):
        if para.text.strip() == "中文摘要":
            abstract = doc.paragraphs[idx + 1].text.strip()
            keywords = doc.paragraphs[idx + 2].text.strip().replace("关键词：", "")
            break

    return ThesisMeta(
        title=title,
        school="东北农业大学",
        college=college,
        author=author,
        student_id=student_id,
        advisor=advisor,
        major=major,
        date_text=date_text,
        abstract=abstract,
        keywords=keywords,
    )


def generate_presentation() -> Path:
    doc = Document(str(DOCX_PATH))
    meta = extract_meta(doc)

    prs = Presentation()
    prs.slide_width = Cm(33.867)
    prs.slide_height = Cm(19.05)

    make_cover(prs, meta)
    add_title_and_outline(prs, meta)
    add_background_slide(prs)
    add_theory_slide(prs)
    add_scene_slide(prs)
    add_design_slide(prs)
    add_implementation_slide(prs)
    add_assessment_slide(prs)
    add_challenge_slide(prs)
    add_trend_slide(prs)
    add_conclusion_slide(prs)
    add_thanks_slide(prs, meta)

    prs.save(str(OUTPUT_PATH))
    return OUTPUT_PATH


if __name__ == "__main__":
    out = generate_presentation()
    print(out)
