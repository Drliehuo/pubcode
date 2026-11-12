#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pubcode - 烈火智能编码 v1.1.1
基于 ffprobe 智能分析 + ffmpeg 转码/封装的 Windows CLI 工具

用法:
    pubcode.exe vc:v1 input.mp4 output.mp4
    pubcode.exe av:co input.mp4 output.mp4
    pubcode.exe info  input.mp4
    pubcode.exe --version
"""

import sys
import os
import re
import json
import subprocess
import shutil
import time
import argparse
import threading
from collections import deque
from pathlib import Path
from math import gcd

VERSION = '1.1.1'

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


# ============================================================
# 工具定位
# ============================================================
def _get_resource_dir() -> Path:
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _find_tool(name):
    cands = []
    if getattr(sys, 'frozen', False):
        cands.append(Path(sys.executable).parent / 'ffmpeg' / f'{name}.exe')
    cands.append(Path(__file__).parent / 'ffmpeg' / f'{name}.exe')
    cands.append(Path.cwd() / 'ffmpeg' / f'{name}.exe')
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        cands.append(Path(sys._MEIPASS) / 'ffmpeg' / f'{name}.exe')

    for c in cands:
        if c.exists():
            return str(c)
    onpath = shutil.which(name)
    if onpath:
        return onpath
    sys.stderr.write(f'[错误] 找不到 {name}.exe，请放到 exe 同级 ffmpeg 子目录，或加入 PATH。\n')
    sys.exit(1)


FFMPEG  = _find_tool('ffmpeg')
FFPROBE = _find_tool('ffprobe')


# ============================================================
# 能力探测
# ============================================================
_FFMPEG_HELP_FULL = None
_FILTERS_TXT = None
_FDK_AAC_OK = None


def _ffmpeg_help_full():
    global _FFMPEG_HELP_FULL
    if _FFMPEG_HELP_FULL is None:
        try:
            _FFMPEG_HELP_FULL = subprocess.check_output(
                [FFMPEG, '-hide_banner', '-h', 'full'],
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            ).decode('utf-8', errors='replace')
        except Exception:
            _FFMPEG_HELP_FULL = ''
    return _FFMPEG_HELP_FULL


def _ffmpeg_supports(option_name):
    return option_name in _ffmpeg_help_full()


def _ffmpeg_version_line():
    try:
        out = subprocess.check_output(
            [FFMPEG, '-hide_banner', '-version'],
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        ).decode('utf-8', errors='replace').splitlines()
        return out[0] if out else '无法获取'
    except Exception:
        return '无法获取'


def _has_filter(name):
    global _FILTERS_TXT
    if _FILTERS_TXT is None:
        try:
            _FILTERS_TXT = subprocess.check_output(
                [FFMPEG, '-hide_banner', '-filters'],
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            ).decode('utf-8', errors='replace')
        except Exception:
            _FILTERS_TXT = ''
    return name in _FILTERS_TXT


def _has_fdk_aac():
    global _FDK_AAC_OK
    if _FDK_AAC_OK is not None:
        return _FDK_AAC_OK
    try:
        out = subprocess.check_output(
            [FFMPEG, '-hide_banner', '-encoders'],
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        ).decode('utf-8', errors='replace')
        _FDK_AAC_OK = 'libfdk_aac' in out
    except Exception:
        _FDK_AAC_OK = False
    return _FDK_AAC_OK


def _fps_mode_args(fps='cfr'):
    if _ffmpeg_supports('-fps_mode'):
        return ['-fps_mode', fps]
    if _ffmpeg_supports('-vsync'):
        return ['-vsync', fps]
    return []


# ============================================================
# ffprobe
# ============================================================
def probe(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f'输入文件不存在: {path}')
    cmd = [FFPROBE, '-v', 'error', '-show_format', '-show_streams',
           '-print_format', 'json', path]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                      creationflags=CREATE_NO_WINDOW,
                                      timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'ffprobe 超时（60 秒）：{path}')
    except subprocess.CalledProcessError:
        raise RuntimeError(f'ffprobe 解析失败: {path}')
    return _normalize_probe(json.loads(out.decode('utf-8', 'replace')), path)


def _normalize_probe(data, path):
    fmt = data.get('format', {})
    info = {
        'file': path,
        'format_name': (fmt.get('format_name') or '').lower(),
        'duration': float(fmt.get('duration') or 0),
        'bitrate': int(fmt.get('bit_rate') or 0),
        'has_video': False,
        'has_audio': False,
        'video': {},
        'audio': {},
    }
    for s in data.get('streams', []):
        t = s.get('codec_type')
        if t == 'video' and not info['has_video']:
            if s.get('disposition', {}).get('attached_pic') == 1:
                continue
            info['has_video'] = True
            fr = s.get('r_frame_rate', '0/1')
            try:
                n, d = fr.split('/')
                fps = round(float(n) / float(d), 3) if float(d) else 0
            except Exception:
                fps = 0
            afr = s.get('avg_frame_rate', '0/1')
            try:
                an, ad = afr.split('/')
                avg_fps = float(an) / float(ad) if float(ad) else 0
            except Exception:
                avg_fps = 0
            is_vfr = False
            if fps > 0 and avg_fps > 0:
                if abs(fps - avg_fps) / max(fps, avg_fps) > 0.01:
                    is_vfr = True
            elif avg_fps > 0 and fps == 0:
                fps = round(avg_fps, 3)

            pix = s.get('pix_fmt', '')
            bd = 10 if ('10le' in pix or '10be' in pix) else 8
            bprs = s.get('bits_per_raw_sample')
            if bprs and str(bprs).isdigit():
                bd = int(bprs)
            trc = s.get('color_transfer', '')
            prim = s.get('color_primaries', '')
            is_hdr, htype = False, ''
            if trc == 'smpte2084':
                is_hdr, htype = True, 'hdr10'
            elif trc == 'arib-std-b67':
                is_hdr, htype = True, 'hlg'
            elif prim == 'bt2020':
                is_hdr, htype = True, 'hdr10'

            hdr_master = None
            hdr_cll = None
            for sd in s.get('side_data_list', []) or []:
                sd_type = sd.get('side_data_type', '')
                if 'Mastering display' in sd_type:
                    try:
                        hdr_master = (
                            int(sd['green_x']), int(sd['green_y']),
                            int(sd['blue_x']),  int(sd['blue_y']),
                            int(sd['red_x']),   int(sd['red_y']),
                            int(sd['white_point_x']), int(sd['white_point_y']),
                            int(sd['max_luminance']), int(sd['min_luminance']),
                        )
                    except (KeyError, TypeError, ValueError):
                        pass
                elif 'Content light' in sd_type:
                    try:
                        hdr_cll = (int(sd['max_content']), int(sd['max_average']))
                    except (KeyError, TypeError, ValueError):
                        pass

            info['video'] = {
                'codec': (s.get('codec_name') or '').lower(),
                'width': int(s.get('width') or 0),
                'height': int(s.get('height') or 0),
                'fps': fps,
                'avg_fps': round(avg_fps, 3),
                'is_vfr': is_vfr,
                'pix_fmt': pix,
                'bit_depth': bd,
                'is_hdr': is_hdr,
                'hdr_type': htype,
                'hdr_master': hdr_master,
                'hdr_cll': hdr_cll,
                'profile': s.get('profile', ''),
                'bit_rate': int(s.get('bit_rate') or 0),
            }
        elif t == 'audio' and not info['has_audio']:
            info['has_audio'] = True
            info['audio'] = {
                'codec': (s.get('codec_name') or '').lower(),
                'channels': int(s.get('channels') or 0),
                'sample_rate': int(s.get('sample_rate') or 0),
                'bit_rate': int(s.get('bit_rate') or 0),
            }
    return info


# ============================================================
# 进度条
# ============================================================
def _fmt(sec):
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


class ProgressPrinter:
    def __init__(self, total_sec, pass_idx=1, pass_total=1):
        self.total = total_sec if total_sec > 0 else 0
        self.start = time.time()
        self.last_len = 0
        self.enabled = sys.stdout.isatty()
        self.speed = '0x'
        self.last_bucket = -1
        self.pass_idx = pass_idx
        self.pass_total = pass_total

    def _prefix(self):
        if self.pass_total > 1:
            return f'[{self.pass_idx}/{self.pass_total}] '
        return ''

    def feed(self, line):
        if '=' not in line:
            return
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip()
        if k in ('out_time_ms', 'out_time_us'):
            try:
                cur = int(v) / 1_000_000.0
            except ValueError:
                return
            self._render(cur)
        elif k == 'speed':
            self.speed = v
        elif k == 'progress' and v == 'end':
            self._finish()

    def _render(self, cur):
        pct_local = min(100.0, cur / self.total * 100) if self.total > 0 else None
        if pct_local is not None and self.pass_total > 1:
            pct_global = ((self.pass_idx - 1) + pct_local / 100.0) / self.pass_total * 100
        else:
            pct_global = pct_local

        if not self.enabled:
            bucket = -1 if pct_global is None else int(pct_global // 10)
            if bucket != self.last_bucket:
                self.last_bucket = bucket
                if pct_global is None:
                    print(f'  {self._prefix()}处理中 {_fmt(cur)}')
                else:
                    print(f'  {self._prefix()}进度 {pct_global:5.1f}%  {_fmt(cur)}/{_fmt(self.total)}  速度 {self.speed}')
            return

        elapsed = time.time() - self.start
        eta_str = ''
        if pct_local is not None and pct_local > 0 and elapsed > 0.5:
            est_total_local = elapsed / (pct_local / 100.0)
            remain_time = max(0, est_total_local - elapsed)
            if self.pass_total > 1 and self.pass_idx < self.pass_total:
                remain_time += est_total_local * (self.pass_total - self.pass_idx)
            eta_str = f'  ETA {_fmt(remain_time)}'

        if pct_global is None:
            line = f'\r{self._prefix()}已处理 {_fmt(cur)}  用时 {_fmt(elapsed)}{eta_str}  '
        else:
            bar_len = 30
            filled = int(bar_len * pct_global / 100)
            bar = '█' * filled + '░' * (bar_len - filled)
            line = (f'\r{self._prefix()}进度 [{bar}] {pct_global:5.1f}%  '
                    f'{_fmt(cur)}/{_fmt(self.total)}  '
                    f'速度 {self.speed}  用时 {_fmt(elapsed)}{eta_str}')
        pad = ' ' * max(0, self.last_len - len(line))
        sys.stdout.write(line + pad)
        sys.stdout.flush()
        self.last_len = len(line)

    def _finish(self):
        if self.enabled and self.last_len:
            sys.stdout.write('\n')
            sys.stdout.flush()


# ============================================================
# 执行 ffmpeg
# ============================================================
def run_ffmpeg(args, total_sec, show_stderr=False, pass_idx=1, pass_total=1):
    full = [FFMPEG, '-hide_banner', '-y', '-progress', 'pipe:1', '-nostats'] + args
    printable = ' '.join(f'"{a}"' if ' ' in a else a for a in full)
    print('▶ 执行:')
    print('  ' + printable)
    print()

    proc = subprocess.Popen(
        full,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
        creationflags=CREATE_NO_WINDOW,
    )

    prog = ProgressPrinter(total_sec, pass_idx=pass_idx, pass_total=pass_total)
    stderr_tail = deque(maxlen=40)

    def _read_stderr():
        try:
            for line in proc.stderr:
                line = line.rstrip('\n')
                stderr_tail.append(line)
                if show_stderr:
                    print('  [ffmpeg] ' + line)
        except Exception:
            pass

    t = threading.Thread(target=_read_stderr, daemon=True)
    t.start()

    try:
        for line in proc.stdout:
            prog.feed(line.rstrip('\n'))
    finally:
        code = proc.wait()
        t.join(timeout=2)

    if code != 0:
        hexcode = f'0x{code & 0xFFFFFFFF:08X}' if (code < 0 or code > 0x7FFFFFFF) else str(code)
        print(f'\n[FFmpeg 错误输出] 退出码 {code} ({hexcode})')
        for l in list(stderr_tail)[-10:]:
            print('  ' + l)
        raise RuntimeError(f'ffmpeg 退出码 {code}')

    prog._finish()
    print('✔ 完成')


# ============================================================
# 决策
# ============================================================
def _parse_resolution(res):
    if not res or res == 'source':
        return None
    res = res.lower().replace('x', ':')
    try:
        w, h = res.split(':')
        return int(w), int(h)
    except Exception:
        return None


def build_tonemap_chain(hdr_type='hdr10'):
    if _has_filter('zscale') and _has_filter('tonemap'):
        if hdr_type == 'hlg':
            return (
                'zscale=t=arib-std-b67:m=bt2020nc,'
                'zscale=t=linear:npl=100,'
                'format=gbrpf32le,'
                'tonemap=tonemap=hable:desat=0,'
                'zscale=t=bt709:m=bt709:r=tv,'
                'format=yuv420p'
            )
        else:
            return (
                'zscale=t=smpte2084:m=bt2020nc,'
                'zscale=t=linear:npl=100,'
                'format=gbrpf32le,'
                'tonemap=tonemap=hable:desat=0,'
                'zscale=t=bt709:m=bt709:r=tv,'
                'format=yuv420p'
            )
    elif _has_filter('tonemap'):
        return 'tonemap=tonemap=hable:desat=0,format=yuv420p'
    else:
        return 'format=yuv420p'


def _build_hdr10_x265_params(video_info):
    master = video_info.get('hdr_master')
    cll = video_info.get('hdr_cll')
    parts = []

    if master:
        Gx, Gy, Bx, By, Rx, Ry, WPx, WPy, Lmax, Lmin = master
        parts.append(
            f'master-display=G({Gx},{Gy})B({Bx},{By})R({Rx},{Ry})'
            f'WP({WPx},{WPy})L({Lmax},{Lmin})'
        )
    else:
        parts.append(
            'master-display=G(13250,34500)B(7500,3000)R(34000,16000)'
            'WP(15635,16450)L(10000000,1)'
        )

    if cll and (cll[0] > 0 or cll[1] > 0):
        parts.append(f'max-cll={cll[0]},{cll[1]}')
    else:
        parts.append('max-cll=1000,400')

    return ':'.join(parts)


def decide_video_params(info, overrides):
    v = info.get('video', {})
    codec_target = overrides.get('codec', 'h265')
    hdr_choice = overrides.get('hdr', 'auto')
    force_10bit = overrides.get('tenbit')
    tonemap_opt = overrides.get('tonemap', 'auto')
    pixfmt_override = overrides.get('pixfmt')
    mode = overrides.get('mode', 'crf')
    video_br = overrides.get('video_br', '4M')

    if hdr_choice == 'auto':
        hdr_choice = v.get('hdr_type', 'sdr') if v.get('is_hdr') else 'sdr'

    src_is_hdr = bool(v.get('is_hdr'))
    need_tonemap = (tonemap_opt == 'on') or (
        tonemap_opt == 'auto' and src_is_hdr and hdr_choice == 'sdr'
    )

    if force_10bit is not None:
        need_10bit = bool(force_10bit)
    else:
        need_10bit = (hdr_choice != 'sdr') or (v.get('bit_depth', 8) >= 10)
    if need_tonemap:
        need_10bit = False

    src_pix = v.get('pix_fmt', '')
    if pixfmt_override:
        pix_fmt = pixfmt_override
        chroma = '444' if '444' in pix_fmt else ('422' if '422' in pix_fmt else '420')
    else:
        if '444' in src_pix:
            chroma = '444'
        elif '422' in src_pix:
            chroma = '422'
        else:
            chroma = '420'
        pix_fmt = f'yuv{chroma}p10le' if need_10bit else f'yuv{chroma}p'

    if codec_target == 'h264':
        venc = 'libx264'
        tag = []
        default_crf = '23'
        if need_10bit:
            profile = {'420': 'high10', '422': 'high422', '444': 'high444'}[chroma]
        else:
            profile = {'420': 'high', '422': 'high422', '444': 'high444'}[chroma]
    else:
        venc = 'libx265'
        tag = ['-tag:v', 'hvc1']
        default_crf = '28'
        if need_10bit:
            profile = {'420': 'main10', '422': 'main422-10', '444': 'main444-10'}[chroma]
        else:
            profile = {'420': 'main', '422': 'main422-10', '444': 'main444-10'}[chroma]
            if chroma != '420':
                need_10bit = True
                pix_fmt = f'yuv{chroma}p10le'
                profile = {'422': 'main422-10', '444': 'main444-10'}[chroma]

    hdr_params = []
    x265_params_extra = []
    if hdr_choice == 'hdr10':
        hdr_params = ['-color_primaries', 'bt2020', '-color_trc', 'smpte2084',
                      '-colorspace', 'bt2020_ncl']
        if codec_target == 'h265':
            x265_params_extra.append(_build_hdr10_x265_params(v))
    elif hdr_choice == 'hlg':
        hdr_params = ['-color_primaries', 'bt2020', '-color_trc', 'arib-std-b67',
                      '-colorspace', 'bt2020_ncl']
        if codec_target == 'h265':
            x265_params_extra.append(
                'master-display=G(13250,34500)B(7500,3000)R(34000,16000)'
                'WP(15635,16450)L(10000000,1):max-cll=1000,400'
            )

    if mode == '2pass':
        try:
            br_num = _parse_bitrate(video_br)
            if br_num > 0:
                maxrate = int(br_num * 1.5)
                bufsize = int(br_num * 3)
                if codec_target == 'h265':
                    x265_params_extra.append(
                        f'vbv-maxrate={maxrate // 1000}:vbv-bufsize={bufsize // 1000}'
                    )
        except Exception:
            pass

    vf_parts = []
    dim = _parse_resolution(overrides.get('resolution', 'source'))
    if dim:
        tw, th = dim
        vf_parts.append(f'scale={tw}:{th}:flags=lanczos')
        g = gcd(tw, th)
        vf_parts.append(f'setdar={tw//g}/{th//g}')

    if need_tonemap:
        vf_parts.append(build_tonemap_chain(v.get('hdr_type') or 'hdr10'))
        hdr_params = []
        pix_fmt = 'yuv420p'
        profile = 'high' if codec_target == 'h264' else 'main'
        need_10bit = False
    elif v.get('bit_depth', 8) >= 10 and not need_10bit:
        if _has_filter('zscale') and _has_filter('format'):
            vf_parts.append(f'zscale=d=error_diffusion,format={pix_fmt}')
        else:
            vf_parts.append(f'format={pix_fmt}')

    fps_choice = overrides.get('fps', 'source')
    if fps_choice == 'source' and v.get('is_vfr'):
        fps_mode = 'passthrough'
    else:
        fps_mode = 'cfr'

    return {
        'venc': venc,
        'profile': profile,
        'pix_fmt': pix_fmt,
        'tag': tag,
        'hdr_params': hdr_params,
        'x265_params_extra': x265_params_extra,
        'vf': ','.join(vf_parts),
        'need_10bit': need_10bit,
        'hdr_choice': hdr_choice,
        'need_tonemap': need_tonemap,
        'default_crf': default_crf,
        'fps_choice': fps_choice,
        'fps_mode': fps_mode,
        'chroma': chroma,
    }


def decide_audio_params(info, overrides):
    if not info.get('has_audio'):
        return ['-an']
    codec = overrides.get('audio_codec', 'fdk_he_v2')
    br = overrides.get('audio_br')
    if codec == 'fdk_he_v2':
        br = br or '48k'
        if not _has_fdk_aac():
            print('⚠ 当前 ffmpeg 不含 libfdk_aac，自动降级为原生 aac 128k')
            return ['-c:a', 'aac', '-b:a', '128k']
        return ['-c:a', 'libfdk_aac', '-profile:a', 'aac_he_v2',
                '-b:a', br, '-ac', '2', '-afterburner', '1']
    br = br or '128k'
    return ['-c:a', 'aac', '-b:a', br]


def _parse_bitrate(s):
    if not s:
        return 0
    s = s.strip().lower()
    try:
        if s.endswith('m'):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith('k'):
            return int(float(s[:-1]) * 1_000)
        return int(float(s))
    except Exception:
        return 0


# ============================================================
# 容器封装参数
# ============================================================
def _container_args(output_file):
    ext = Path(output_file).suffix.lower()
    if ext in ('.mp4', '.m4v', '.mov'):
        return ['-movflags', '+faststart'], True
    if ext == '.mkv':
        return [], False
    if ext == '.ts':
        return ['-mpegts_flags', '+resend_headers'], False
    if ext == '.flv':
        return [], False
    return [], ext in ('.mp4', '.m4v', '.mov')


# ============================================================
# 子命令
# ============================================================
def cmd_info(input_file):
    info = probe(input_file)
    print(f'📄 文件: {info["file"]}')
    print(f'   容器: {info["format_name"] or "?"}  '
          f'时长: {_fmt(info["duration"])}  '
          f'总码率: {info["bitrate"]//1000} kbps')
    if info['has_video']:
        v = info['video']
        hdr = f' {v["hdr_type"].upper()}' if v['is_hdr'] else ' SDR'
        vfr = ' VFR' if v['is_vfr'] else ''
        print(f'   🎞️ 视频: {v["codec"]}  {v["width"]}x{v["height"]}  '
              f'{v["fps"]}fps{vfr}  {v["pix_fmt"]}  {v["bit_depth"]}-bit{hdr}')
        if v['is_hdr'] and v.get('hdr_master'):
            m = v['hdr_master']
            print(f'      HDR 元数据: master-display L({m[8]},{m[9]})')
        if v['is_hdr'] and v.get('hdr_cll'):
            print(f'      MaxCLL/MaxFALL: {v["hdr_cll"][0]}/{v["hdr_cll"][1]}')
    if info['has_audio']:
        a = info['audio']
        print(f'   🔊 音频: {a["codec"]}  {a["channels"]}ch  '
              f'{a["sample_rate"]}Hz  {a["bit_rate"]//1000} kbps')
    return 0


def _build_video_args(vp, mode, crf, preset, video_br, include_filters=True):
    out = []
    if include_filters and vp['vf']:
        out += ['-vf', vp['vf']]
    if mode == 'crf':
        out += ['-c:v', vp['venc'], '-preset', preset,
                '-profile:v', vp['profile'], '-crf', crf,
                '-pix_fmt', vp['pix_fmt']]
    else:
        out += ['-c:v', vp['venc'], '-preset', preset,
                '-profile:v', vp['profile'], '-b:v', video_br,
                '-pix_fmt', vp['pix_fmt']]
    out += vp['tag']
    out += vp['hdr_params']
    if vp['x265_params_extra'] and vp['venc'] == 'libx265':
        combined = ':'.join(vp['x265_params_extra'])
        out += ['-x265-params', combined]
    return out


def _stream_metadata_args(has_audio):
    out = ['-metadata:s:v:0', 'handler_name=pubcode v1']
    if has_audio:
        out += ['-metadata:s:a:0', 'handler_name=pubcode v1']
    return out


def cmd_vc(input_file, output_file, overrides):
    info = probe(input_file)
    print('📊 源文件分析:')
    if info['has_video']:
        v = info['video']
        vfr_tag = ' VFR' if v['is_vfr'] else ''
        print(f'   视频 {v["codec"]} {v["width"]}x{v["height"]} '
              f'{v["pix_fmt"]} {v["bit_depth"]}bit '
              f'{v["fps"]}fps{vfr_tag} HDR={v["hdr_type"] or "no"}')
        if v['is_hdr']:
            if v.get('hdr_master'):
                m = v['hdr_master']
                print(f'      HDR 元数据: master-display L({m[8]},{m[9]})')
            if v.get('hdr_cll'):
                print(f'      MaxCLL/MaxFALL: {v["hdr_cll"][0]}/{v["hdr_cll"][1]}')
    if info['has_audio']:
        a = info['audio']
        print(f'   音频 {a["codec"]} {a["channels"]}ch {a["sample_rate"]}Hz')
    if not info['has_video']:
        print('[错误] 源文件无视频流')
        return 1
    print()

    out_ext = Path(output_file).suffix.lower()
    if out_ext == '':
        output_file = output_file + '.mp4'
        print(f'ℹ 未指定输出扩展名，默认使用 .mp4：{output_file}')
    elif out_ext not in ('.mp4', '.m4v', '.mov', '.mkv', '.ts', '.flv'):
        print(f'ℹ 输出扩展名 {out_ext} 非标准，仍按 .mp4 封装（如需其它容器请显式指定）')
        output_file = str(Path(output_file).with_suffix('.mp4'))

    v = info['video']
    src_channels = info.get('audio', {}).get('channels', 0)

    dim = _parse_resolution(overrides.get('resolution', 'source'))
    if dim is None and (v['width'] >= 3840 or v['height'] >= 2160):
        print(f'💡 源为 {v["width"]}x{v["height"]}，建议指定 --resolution 1920:1080 以加速并减小体积（本次仍按源分辨率编码）\n')

    vp = decide_video_params(info, overrides)
    ap = decide_audio_params(info, overrides)

    if info['has_audio'] and src_channels > 2 and '-ac' not in ap:
        ap += ['-ac', '2']

    mode = overrides.get('mode', 'crf')
    crf = str(overrides.get('crf', vp['default_crf']))
    preset = overrides.get('preset', 'slow')
    video_br = overrides.get('video_br', '4M')

    fmt_args, _ = _container_args(output_file)

    fps_choice = vp['fps_choice']
    fps_args = []
    if fps_choice != 'source':
        try:
            int(fps_choice)
            fps_args = ['-r', str(fps_choice)]
        except Exception:
            pass

    print(f'🎯 编码方案: {vp["venc"]} / {vp["profile"]} / {vp["pix_fmt"]} / '
          f'mode={mode} / ' + (f'crf={crf}' if mode == 'crf' else f'bitrate={video_br}') +
          f' / preset={preset}')
    print(f'   HDR 输出: {vp["hdr_choice"].upper()}'
          + ('（含 tonemap 色调映射）' if vp['need_tonemap'] else ''))
    if vp['fps_mode'] == 'passthrough':
        print(f'   帧率: 源 {v["fps"]}fps（VFR 保留，不补帧）')
    else:
        print(f'   帧率: {"源 " + str(v["fps"]) + "fps（CFR 恒定）" if fps_choice == "source" else str(fps_choice) + "fps（覆盖）"}')
    if info['has_audio']:
        ac_name = 'HE-AACv2' if overrides.get('audio_codec', 'fdk_he_v2') == 'fdk_he_v2' else 'AAC'
        ab = overrides.get('audio_br') or ('48k' if ac_name == 'HE-AACv2' else '128k')
        print(f'   音频: {src_channels}ch → 2ch / {ac_name} {ab}')
    print(f'   容器: {Path(output_file).suffix.lower() or "auto"}')
    if vp['need_tonemap']:
        print('   ⚠ HDR→SDR 已启用 tonemap（按源 HDR 类型分流 zscale 曲线）')
    if vp['x265_params_extra']:
        print(f'   x265 附加参数: {":".join(vp["x265_params_extra"])}')
    print()

    if mode == '2pass':
        keep_vf_parts = [p for p in vp['vf'].split(',') if p.startswith(('format=', 'zscale=d='))]
        vf_p1 = ','.join(keep_vf_parts)

        p1 = ['-i', input_file, '-map', '0:v:0']
        if vf_p1:
            p1 += ['-vf', vf_p1]
        if fps_args:
            p1 += fps_args
        p1 += _build_video_args(
            {**vp, 'vf': ''}, mode, crf, preset, video_br, include_filters=False
        )
        p1 += _fps_mode_args(vp['fps_mode'])
        p1 += ['-pass', '1', '-passlogfile', 'pubcode_2pass',
               '-an', '-f', 'null', os.devnull]

        run_ffmpeg(p1, info['duration'], pass_idx=1, pass_total=2)

        p2 = ['-i', input_file]
        p2 += ['-map', '0:v:0']
        if info['has_audio']:
            p2 += ['-map', '0:a:0?']
        if fps_args:
            p2 += fps_args
        p2 += _build_video_args(vp, mode, crf, preset, video_br, include_filters=True)
        p2 += ap
        if info['has_audio']:
            p2 += ['-af', 'aresample=async=1:min_hard_comp=0.02:first_pts=0']
        p2 += _fps_mode_args(vp['fps_mode'])
        p2 += fmt_args
        p2 += ['-metadata', 'encoder=pubcode v1',
               '-metadata', 'comment=pubcode v1']
        p2 += _stream_metadata_args(info['has_audio'])
        p2 += ['-pass', '2', '-passlogfile', 'pubcode_2pass', output_file]

        run_ffmpeg(p2, info['duration'], pass_idx=2, pass_total=2)

        for f in Path.cwd().glob('pubcode_2pass*'):
            try:
                f.unlink()
            except Exception:
                pass
    else:
        args = ['-i', input_file]
        args += ['-map', '0:v:0']
        if info['has_audio']:
            args += ['-map', '0:a:0?']
        if fps_args:
            args += fps_args
        args += _build_video_args(vp, mode, crf, preset, video_br, include_filters=True)
        args += ap
        if info['has_audio']:
            args += ['-af', 'aresample=async=1:min_hard_comp=0.02:first_pts=0']
        args += _fps_mode_args(vp['fps_mode'])
        args += fmt_args
        args += ['-metadata', 'encoder=pubcode v1',
                 '-metadata', 'comment=pubcode v1']
        args += _stream_metadata_args(info['has_audio'])
        args += [output_file]

        run_ffmpeg(args, info['duration'])

    print(f'\n✅ 输出: {output_file}')
    return 0


def cmd_avco(input_file, output_file):
    info = probe(input_file)
    print('📊 源文件分析:')
    if info['has_video']:
        v = info['video']
        print(f'   视频 {v["codec"]} {v["width"]}x{v["height"]}')
    if info['has_audio']:
        a = info['audio']
        print(f'   音频 {a["codec"]} {a["channels"]}ch')
    print()

    out_ext = Path(output_file).suffix.lower()
    if out_ext == '':
        output_file = output_file + '.mp4'
        print(f'ℹ 未指定输出扩展名，默认使用 .mp4：{output_file}')

    fmt_args, _ = _container_args(output_file)
    args = ['-i', input_file, '-c', 'copy', '-map', '0', '-map', '-0:d?']
    args += fmt_args
    args += ['-metadata', 'encoder=pubcode v1',
             '-metadata', 'comment=pubcode v1']
    args += _stream_metadata_args(info['has_audio'])
    args += [output_file]

    run_ffmpeg(args, info['duration'])
    print(f'\n✅ 封装完成: {output_file}')
    print('   已写入元数据:')
    print('     format  : encoder=pubcode v1, comment=pubcode v1')
    print('     video   : handler_name=pubcode v1')
    if info['has_audio']:
        print('     audio   : handler_name=pubcode v1')
    return 0


# ============================================================
# CLI
# ============================================================
OPT_WITH_VALUE = {
    '--codec', '--crf', '--preset', '--hdr', '--resolution',
    '--audio-br', '--audio-codec', '--tenbit', '--tonemap',
    '--mode', '--video-br', '--fps', '--pixfmt',
}


def _split_argv(argv):
    opts, pos = [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith('--'):
            opts.append(a)
            if a in OPT_WITH_VALUE and i + 1 < len(argv):
                opts.append(argv[i + 1])
                i += 2
                continue
        elif a in ('-h', '--help'):
            opts.append(a)
        else:
            pos.append(a)
        i += 1
    return opts, pos


def _build_overrides(args):
    o = {}
    for k, a in (
        ('codec', 'codec'), ('crf', 'crf'), ('preset', 'preset'),
        ('hdr', 'hdr'), ('resolution', 'resolution'),
        ('audio_br', 'audio_br'), ('audio_codec', 'audio_codec'),
        ('tonemap', 'tonemap'), ('mode', 'mode'),
        ('video_br', 'video_br'), ('fps', 'fps'), ('pixfmt', 'pixfmt'),
    ):
        v = getattr(args, a, None)
        if v is not None:
            o[k] = v
    if getattr(args, 'tenbit', None) is not None:
        o['tenbit'] = args.tenbit
    return o


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    argv = sys.argv[1:]
    action = argv[0]
    rest = argv[1:]

    if action in ('-h', '--help'):
        print(__doc__)
        return 0

    if action == '--version':
        print(f'pubcode v{VERSION}')
        print(f'ffmpeg : {FFMPEG}')
        print(f'ffprobe: {FFPROBE}')
        print(f'ffmpeg 版本: {_ffmpeg_version_line()}')
        print(f'libfdk_aac   : {"yes" if _has_fdk_aac() else "no"}')
        print(f'zscale       : {"yes" if _has_filter("zscale") else "no"}')
        print(f'tonemap      : {"yes" if _has_filter("tonemap") else "no"}')
        print(f'-fps_mode    : {"yes" if _ffmpeg_supports("-fps_mode") else "no"}')
        print(f'-vsync       : {"yes" if _ffmpeg_supports("-vsync") else "no"}')
        return 0

    if action == 'info':
        if len(rest) < 1:
            print('[错误] 用法: pubcode info <input>')
            return 2
        try:
            return cmd_info(rest[0])
        except (FileNotFoundError, RuntimeError) as e:
            print(f'[错误] {e}')
            return 1

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--codec', choices=['h264', 'h265'])
    parser.add_argument('--crf')
    parser.add_argument('--preset', choices=['medium', 'slow', 'veryslow'])
    parser.add_argument('--hdr', choices=['auto', 'sdr', 'hdr10', 'hlg'], default='auto')
    parser.add_argument('--resolution')
    parser.add_argument('--audio-br', dest='audio_br')
    parser.add_argument('--audio-codec', choices=['aac', 'fdk_he_v2'])
    parser.add_argument('--tenbit', type=int, choices=[0, 1])
    parser.add_argument('--tonemap', choices=['auto', 'on', 'off'], default='auto')
    parser.add_argument('--mode', choices=['crf', '2pass'], default='crf')
    parser.add_argument('--video-br', dest='video_br')
    parser.add_argument('--fps')
    parser.add_argument('--pixfmt')
    parser.add_argument('-h', '--help', action='help')

    opt_args, pos_args = _split_argv(rest)
    try:
        args = parser.parse_args(opt_args)
    except SystemExit:
        return 2

    if len(pos_args) < 1:
        print('[错误] 缺少输入文件')
        return 2
    input_file = pos_args[0]
    output_file = pos_args[1] if len(pos_args) >= 2 else None

    if not output_file:
        stem = Path(input_file).stem
        output_file = str(Path(input_file).parent / f'{stem}.pubcode.mp4')
        print(f'ℹ 未指定输出文件，自动使用：{output_file}')

    if action not in ('vc:v1', 'av:co'):
        print(f'[错误] 未知动作: {action}')
        print('可用: vc:v1 | av:co | info | --version')
        return 2

    try:
        if action == 'vc:v1':
            return cmd_vc(input_file, output_file, _build_overrides(args))
        else:
            return cmd_avco(input_file, output_file)
    except FileNotFoundError as e:
        print(f'[错误] {e}')
        return 1
    except RuntimeError as e:
        print(f'[错误] {e}')
        return 1
    except KeyboardInterrupt:
        print('\n[中止] 用户取消')
        return 130


if __name__ == '__main__':
    sys.exit(main())