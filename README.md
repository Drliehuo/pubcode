# pubcode · 烈火智能编码

> 基于 ffprobe 智能分析 + ffmpeg 转码/封装的 Windows CLI 工具

![version](https://img.shields.io/badge/version-1.1.1-blue)
![platform](https://img.shields.io/badge/platform-Windows%20x64-lightgrey)
![ffmpeg](https://img.shields.io/badge/ffmpeg-5.1%2B-green)
![license](https://img.shields.io/badge/license-MIT-brightgreen)

自动识别源文件的 **编码 / 位深 / HDR / 色度 / 帧率类型（CFR 或 VFR）**，一键生成最稳的 ffmpeg 命令。默认输出 **H.265 + MP4 + HE-AACv2 48k**，兼容苹果设备（`hvc1` tag），HDR 素材自动做色调映射，10bit 素材正确处理位深抖动。

---

## 目录

- [特性](#特性)
- [安装](#安装)
- [快速开始](#快速开始)
- [命令速查](#命令速查)
- [动作详解](#动作详解)
- [参数完整参考](#参数完整参考)
- [智能决策机制](#智能决策机制)
- [典型场景](#典型场景)
- [常见问题](#常见问题)
- [退出码](#退出码)
- [附录ffmpeg-能力自检](#附录ffmpeg-能力自检)
- [许可证](#许可证)
- [版本历史](#版本历史)

---

## 特性

| 类别 | 能力 |
|------|------|
| 🎯 **智能决策** | 源位深 / HDR / 色度 / VFR 自动识别，参数自动适配 |
| 🎬 **转码** | H.264 / H.265，CRF 恒定质量，2-Pass VBR |
| 🎨 **HDR** | HDR10 / HLG 保留输出，HDR→SDR 自动 tonemap（按源类型分流曲线） |
| 🎞️ **位深** | 8bit / 10bit 智能选择，10→8bit 用 `error_diffusion` 抖动 |
| 🔊 **音频** | HE-AACv2 48k 默认，AAC 兜底，6ch 以上自动降混立体声 |
| 📼 **封装** | 流复制封装 + `pubcode v1` 元数据打标 |
| 🖥️ **体验** | 实时进度条 + ETA，两遍编码分遍显示，管道无死锁 |
| 🔧 **兼容** | ffmpeg 5.1+ / 6.x 自动适配（`-fps_mode` / `-vsync` 能力探测） |

---

## 安装

### 方式一：下载 zip（推荐）

1. 下载 `pubcode-v1.1.1-win64.zip`
2. 解压到任意目录（如 `D:\tools\pubcode\`）
3. 在该目录打开 CMD / PowerShell 即可使用

**目录结构**：
D:\tools\pubcode
├── pubcode.exe 主程序
├── ffmpeg
│ ├── ffmpeg.exe ffmpeg 主程序（勿删）
│ ├── ffprobe.exe ffprobe（勿删）
│ └── ffplay.exe 可选，pubcode 不使用
├── README.md 本文件
└── LICENSE-ffmpeg.txt ffmpeg 许可说明
### 方式二：源码运行

```bash
git clone https://github.com/yourname/pubcode.git
cd pubcode
# 把 ffmpeg.exe / ffprobe.exe 放到 ffmpeg\ 子目录
python pubcode.py --version

方式三：加入 PATH（可选）
把 D:\tools\pubcode\ 加入系统 PATH 后，可在任意目录直接运行 pubcode：

Win + R → 输入 sysdm.cpl → 高级 → 环境变量

在"用户变量"的 Path 里添加 D:\tools\pubcode\

重开 CMD 生效

系统要求
Windows 7 x64 及以上（推荐 Windows 10/11）

无需安装 Python（zip 版）

磁盘空间：约 200MB（含 ffmpeg）

快速验证
bat
pubcode.exe --version

正常输出示例：

text
pubcode v1.1.1
ffmpeg : D:\tools\pubcode\ffmpeg\ffmpeg.exe
ffprobe: D:\tools\pubcode\ffmpeg\ffprobe.exe
ffmpeg 版本: ffmpeg version 6.1 Copyright (c) 2000-2023 ...
libfdk_aac   : yes
zscale       : yes
tonemap      : yes
-fps_mode    : yes
-vsync       : no
关键项：

ffmpeg 路径指向解压目录内的 ffmpeg\，不是 C:\WINDOWS\system32\

libfdk_aac : yes → HE-AACv2 可用

zscale / tonemap : yes → HDR→SDR 高质量

-fps_mode : yes → 用新版参数

快速开始
bat
:: 1. 查看媒体信息
pubcode.exe info in.mkv

:: 2. 智能转码（H.265 + MP4 + HE-AACv2 48k）
pubcode.exe vc:v1 in.mkv out.mp4

:: 3. 只给输入，自动生成 in.pubcode.mp4
pubcode.exe vc:v1 in.mkv

:: 4. 纯封装（流复制，秒级完成）
pubcode.exe av:co in.mp4 out.mp4

:: 5. 版本与 ffmpeg 能力自检
pubcode.exe --version
基本概念
命令结构：

text
pubcode.exe <动作> <输入文件> [输出文件] [选项...]
三个动作：

动作	用途	是否重编码
vc:v1	视频转码	是（视频和音频都重新编码）
av:co	音视频封装	否（流复制，速度极快）
info	查看媒体信息	—
输出文件默认值：

情况	行为
指定 out.mp4	用 out.mp4
指定 out（无扩展名）	自动变 out.mp4
指定 out.avi（非标准）	改为 out.mp4 并提示
不指定输出	自动 <输入名>.pubcode.mp4
命令速查
动作
动作	含义
vc:v1	视频转码（重编码）
av:co	音视频封装（流复制，不重编码）
info	查看媒体信息
--version	版本与 ffmpeg 能力自检
常用选项
选项	取值	默认	说明
--codec	h264 / h265	h265	视频编码器
--crf	18 / 20 / 23 / 26 / 28	H.265=28，H.264=23	恒定质量
--preset	medium / slow / veryslow	slow	编码速度/质量
--mode	crf / 2pass	crf	码率控制模式
--video-br	4M / 800k	4M	仅 2pass 生效
--hdr	auto / sdr / hdr10 / hlg	auto	输出 HDR 模式
--tonemap	auto / on / off	auto	HDR→SDR 色调映射
--resolution	1920:1080 / 1920x1080	source	缩放分辨率
--fps	数字 / source	source	输出帧率
--tenbit	0 / 1	智能	强制 8bit / 10bit
--pixfmt	yuv420p10le 等	智能	强制像素格式
--audio-codec	aac / fdk_he_v2	fdk_he_v2	音频编码
--audio-br	48k / 64k / 128k	48k / 128k	音频码率
动作详解
vc:v1 — 视频转码
默认行为（不写任何选项）

项目	默认值
视频编码	H.265 (libx265) + hvc1 tag
码率控制	CRF（H.265=28，H.264=23）
编码预设	slow
像素格式	智能（8bit→420p，10bit→420p10le，4:2:2/4:4:4 保留）
HDR	智能（源 HDR → 目标 SDR 自动 tonemap）
帧率	保留源；VFR 源用 passthrough
音频编码	HE-AACv2 48k（缺失 libfdk_aac 时降级 AAC 128k）
多声道	6ch 以上自动降混 2ch
容器	MP4 + +faststart
元数据	encoder=pubcode v1、comment=pubcode v1、handler_name=pubcode v1
示例

bat
:: 全自动
pubcode.exe vc:v1 in.mkv out.mp4

:: 只给输入
pubcode.exe vc:v1 in.mkv

:: H.264 转码
pubcode.exe vc:v1 in.mp4 out.mp4 --codec h264

:: 指定 CRF 20
pubcode.exe vc:v1 in.mp4 out.mp4 --crf 20

:: 4K → 1080p
pubcode.exe vc:v1 4k.mp4 out1080p.mp4 --resolution 1920:1080

:: 竖屏
pubcode.exe vc:v1 in.mp4 out.mp4 --resolution 1080:1920

:: HDR 保留 HDR10
pubcode.exe vc:v1 hdr.mp4 hdr_out.mp4 --hdr hdr10

:: HDR 转 SDR（默认 auto 已自动开）
pubcode.exe vc:v1 hdr.mp4 sdr.mp4 --tonemap on

:: 2-Pass 固定码率 4M
pubcode.exe vc:v1 in.mp4 out.mp4 --mode 2pass --video-br 4M

:: 强制 8bit
pubcode.exe vc:v1 in10bit.mp4 out8bit.mp4 --tenbit 0

:: 强制 10bit
pubcode.exe vc:v1 in.mp4 out.mp4 --tenbit 1

:: AAC 128k（不用 HE-AACv2）
pubcode.exe vc:v1 in.mp4 out.mp4 --audio-codec aac

:: HE-AACv2 但码率 64k
pubcode.exe vc:v1 in.mp4 out.mp4 --audio-br 64k

:: 输出 MKV
pubcode.exe vc:v1 in.mp4 out.mkv

:: 保留 4:2:2
pubcode.exe vc:v1 prores422.mov out.mp4 --pixfmt yuv422p10le

:: 帧率覆盖为 30fps
pubcode.exe vc:v1 in.mp4 out.mp4 --fps 30
av:co — 音视频封装
用途：把已有视频流复制到新容器，不重新编码，速度取决于磁盘 IO。

默认行为：

所有流 -c copy

丢弃数据流

写入 encoder=pubcode v1、comment=pubcode v1、handler_name=pubcode v1

输出 MP4 加 +faststart

示例

bat
:: 直接封装
pubcode.exe av:co in.mp4 out.mp4

:: 只给输入
pubcode.exe av:co in.mp4

:: 封装为 MKV
pubcode.exe av:co in.mp4 out.mkv
验证打标

bat
ffprobe -v error -show_format -show_streams out.mp4 | findstr /i "pubcode"
预期：

text
TAG:encoder=pubcode v1
TAG:comment=pubcode v1
TAG:handler_name=pubcode v1
TAG:handler_name=pubcode v1
info — 查看媒体信息
bat
pubcode.exe info in.mkv
输出示例：

text
📄 文件: in.mkv
   容器: matroska,webm  时长: 00:22:15  总码率: 8200 kbps
   🎞️ 视频: hevc  1920x800  23.976fps  yuv420p10le  10-bit SDR
   🔊 音频: eac3  6ch  48000Hz  640 kbps
HDR 素材额外显示：

text
   🎞️ 视频: hevc  3840x2160  23.976fps  yuv420p10le  10-bit HDR10
      HDR 元数据: master-display L(10000000,1)
      MaxCLL/MaxFALL: 1000/400
VFR 素材标注 VFR：

text
   🎞️ 视频: hevc  1920x1080  30fps VFR  yuv420p  8-bit SDR
--version — 能力自检
bat
pubcode.exe --version
输出用于确认：

用的是哪个 ffmpeg

是否支持 libfdk_aac（决定 HE-AACv2）

是否支持 zscale / tonemap（决定 HDR 质量）

走 -fps_mode 还是 -vsync 分支

参数完整参考
视频参数
参数	取值	默认	说明
--codec	h264 / h265	h265	视频编码器
--crf	数字	H.265=28，H.264=23	CRF 恒定质量（越小越清晰、越大体积）
--preset	medium / slow / veryslow	slow	编码速度/质量权衡
--mode	crf / 2pass	crf	码率控制模式
--video-br	4M / 800k / 2000000	4M	仅 2pass 生效
--resolution	W:H / WxH / source	source	缩放分辨率
--fps	数字 / source	source	输出帧率
--tenbit	0 / 1	智能	强制 8bit/10bit
--pixfmt	yuv420p10le 等	智能	强制像素格式
HDR 参数
参数	取值	默认	说明
--hdr	auto / sdr / hdr10 / hlg	auto	输出 HDR 模式
--tonemap	auto / on / off	auto	HDR→SDR 色调映射开关
--hdr 行为

值	行为
auto	源 HDR → 保留 HDR；源 SDR → 输出 SDR
sdr	强制 SDR 输出（源 HDR 时自动 tonemap）
hdr10	强制 HDR10 输出（写入 master-display + max-cll 元数据）
hlg	强制 HLG 输出
--tonemap 行为

值	行为
auto	源 HDR 且目标 SDR 时自动启用（推荐）
on	强制启用
off	强制禁用
音频参数
参数	取值	默认	说明
--audio-codec	aac / fdk_he_v2	fdk_he_v2	音频编码器
--audio-br	48k / 64k / 128k	HE-AACv2=48k，AAC=128k	音频码率
注意：HE-AACv2 强制立体声（2ch），6ch 以上自动降混。缺失 libfdk_aac 时自动降级为 aac 128k。

CRF 参考值
CRF	H.264	H.265
18	视觉无损	视觉无损
20	极高质量	极高质量
23	均衡（推荐）	—
26	—	高质量
28	—	均衡（默认）
30+	—	小体积
H.265 的 CRF 与 H.264 不同档。H.265 CRF 28 的画质大致相当于 H.264 CRF 23。

智能决策机制
pubcode 会根据源文件特征自动决策，无需手动指定。

位深决策
源位深	--tenbit	输出
8bit	未指定	8bit
8bit	1	10bit
10bit	未指定	10bit
10bit	0	8bit（error_diffusion 抖动）
HDR 决策
源 HDR	--hdr	输出
SDR	auto	SDR
HDR10	auto	HDR10（保留元数据）
HLG	auto	HLG
HDR	sdr	SDR（自动 tonemap，按源曲线分流）
SDR	hdr10	HDR10 标记（内容仍是 SDR，不推荐）
色度决策
源像素格式	输出
yuv420p*	yuv420p / yuv420p10le
yuv422p*	yuv422p / yuv422p10le（x265 main422-10）
yuv444p*	yuv444p / yuv444p10le（x265 main444-10）
帧率决策
源帧率类型	--fps	输出
CFR	source	保留源帧率 + -fps_mode cfr
VFR	source	保留 VFR + -fps_mode passthrough（不补帧）
任意	数字	强制该帧率 + -fps_mode cfr
容器决策
输出扩展名	封装参数
.mp4 / .m4v / .mov	-movflags +faststart
.mkv	无（matroska）
.ts	-mpegts_flags +resend_headers
.flv	无
无扩展名	自动补 .mp4
音频决策
源声道	默认行为
无音频	-an
1ch / 2ch	HE-AACv2 48k
6ch / 8ch	HE-AACv2 48k + -ac 2 降混
典型场景
压缩手机视频（节省 50-70% 体积）
bat
pubcode.exe vc:v1 phone.mp4 out.mp4 --crf 30 --preset medium
4K 电影转 1080p
bat
pubcode.exe vc:v1 movie_4k.mkv movie_1080p.mp4 --resolution 1920:1080 --crf 24
转 H.264 兼容老电视
bat
pubcode.exe vc:v1 in.mp4 out_compat.mp4 --codec h264 --audio-codec aac --preset slow
网络分享（限制码率）
bat
pubcode.exe vc:v1 in.mkv share.mp4 --mode 2pass --video-br 3M --resolution 1280:720
HDR 电影保持 HDR
bat
pubcode.exe vc:v1 hdr_movie.mkv hdr_movie_out.mp4 --hdr hdr10 --crf 22
HDR 电影转 SDR（老播放器）
bat
pubcode.exe vc:v1 hdr_movie.mkv sdr_movie.mp4 --hdr sdr --tonemap on
下载的视频重新封装
bat
pubcode.exe av:co downloaded.mp4 out.mp4
批量处理（目前需用批处理脚本）
bat
for %%f in (*.mkv) do pubcode.exe vc:v1 "%%f" "%%~nf.mp4"
常见问题
Q1: 提示"找不到 ffmpeg.exe"
确认 pubcode.exe 同级有 ffmpeg\ 子目录，且含 ffmpeg.exe、ffprobe.exe。

Q2: 音频输出是 AAC 不是 HE-AACv2
bat
pubcode.exe --version
看 libfdk_aac 是否为 yes。为 no 说明当前 ffmpeg 构建不含该编码器，需换 nonfree 完整构建。

Q3: HDR 转 SDR 画面发灰
bat
pubcode.exe --version
看 zscale、tonemap 是否都是 yes。缺失时自动降级，质量较差，建议换完整 ffmpeg 构建。

Q4: 转码卡住 CPU 不动
v1.0.2 起已修复管道死锁。若仍出现，在 cmd_vc 里临时把调用改为：

python
run_ffmpeg(args, info['duration'], show_stderr=True)
重新打包后可查看 ffmpeg 实时日志。

Q5: 杀毒软件报警
pubcode.exe 由 PyInstaller 打包，个别杀软（360、火绒）会误报，加入白名单即可。

Q6: 输出文件 0 字节
检查磁盘空间、输出路径权限。pubcode 退出码 0 但文件 0 字节通常是 ffmpeg 编码器初始化失败，加 show_stderr=True 排查。

Q7: VFR 视频转码后卡顿
v1.1.0 起已自动检测 VFR 并切到 passthrough。若仍卡顿，可尝试 --fps 30 强制 CFR。

Q8: HDR10 元数据丢失
v1.1.0 起已自动从 ffprobe 读取并写入 master-display + max-cll。若源文件本身无元数据，会用行业默认值（BT.2020 + D65 + 1000nits）并打印警告。

Q9: 2-Pass 第一遍看起来没有缩放
这是 v1.1.0 的正常行为。2-Pass 第一遍只做码率统计，缩放和 tonemap 对率失真没有意义，已自动剔除，省时间且不影响质量。

Q10: 进度条 ETA 不准
编码前 10% 因为编码器初始化，ETA 会偏大；10% 后趋于稳定。这是所有进度条的共性。

退出码
退出码	含义
0	成功
1	文件不存在 / ffprobe 解析失败 / ffmpeg 出错 / 超时
2	参数错误（未知动作、缺少输入文件）
130	用户 Ctrl+C 中止
附录：ffmpeg 能力自检
pubcode.exe --version 会打印：

text
pubcode v1.1.1
ffmpeg : D:\tools\pubcode\ffmpeg\ffmpeg.exe
ffprobe: D:\tools\pubcode\ffmpeg\ffprobe.exe
ffmpeg 版本: ffmpeg version 6.1 Copyright ...
libfdk_aac   : yes
zscale       : yes
tonemap      : yes
-fps_mode    : yes
-vsync       : no
项目	说明
ffmpeg 路径	必须指向解压目录内的 ffmpeg\，不能是 C:\WINDOWS\system32\
libfdk_aac	yes → HE-AACv2 可用；no → 降级 AAC
zscale	yes → HDR tonemap 高质量
tonemap	yes → 支持色调映射
-fps_mode	yes → 用新版参数
-vsync	yes → 用老版参数（一般新版这里是 no）
如果 libfdk_aac / zscale / tonemap 有 no，说明 ffmpeg 构建缺这些组件。建议换 BtbN/FFmpeg-Builds 的 nonfree 完整构建（如 ffmpeg-master-latest-win64-nonfree.zip）。

许可证
pubcode：MIT License

ffmpeg：LGPL / GPL v2+（详见 LICENSE-ffmpeg.txt）

本工具仅封装 ffmpeg 命令生成逻辑，不包含 ffmpeg 源码。分发时请遵守 ffmpeg 许可条款。

致谢
FFmpeg — 音视频处理核心

BtbN/FFmpeg-Builds — Windows 构建

PyInstaller — 单文件打包

版本历史
版本	主要变化
v1.1.1	视频流/音频流写入 handler_name=pubcode v1
v1.1.0	HDR10 元数据写入、HLG tonemap 修正、VFR 自动 passthrough、2pass VBV 约束、error_diffusion 抖动、进度条 ETA、2pass 分遍进度
v1.0.3	默认 HE-AACv2 48k、默认 H.265 + MP4、输出文件名兜底
v1.0.2	修复管道死锁、-async 改滤镜、显式 map、6ch 降混
v1.0.1	HDR tonemap、10bit 智能、CRF 按编码器、2pass、容器自动、4:2:2 保留
v1.0.0	初始版本
pubcode v1.1.1 · 烈火智能编码 · Powered by FFmpeg