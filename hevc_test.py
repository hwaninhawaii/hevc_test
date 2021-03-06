import re
import os
import os.path
import sys
import csv
import subprocess
import configparser

FPS_DICT = {'bike1': 25,
            'circuit1': 29.97,
            'city1': 23.98,
            'concert1': 29.97,
            'game1': 59.44,
            'movie1': 23.98,
            'tennis1': 29.97
            }

MC_PRESET = {'fast': 19,
             'medium': 23,
             'slow': 27
             }

MC_NVENC_PRESET = {'fast': 19,
                   'medium': 23,
                   'slow': 27
                   }

#MC_NVENC_PRESET = {'perf28': 28,
#                   'perf24': 24,
#                   'perf20': 20
#                   }

FF_PRESET = {'fast': 'superfast',
             'medium': 'fast',
             'slow': 'slow'
             }

INPUT_PATH = '../original'
OUTPUT_PATH = '../result'
CONFIG_PATH = '../config'


def calc_vmaf(inputfile, speed, crf, method):
    fps = FPS_DICT[os.path.basename(os.path.splitext(inputfile)[0])]
    ref = f'{INPUT_PATH}/{inputfile}.yuv'

    enc = f'{OUTPUT_PATH}/{method}/{inputfile}_{speed}_crf{crf}.hevc'
    enc_raw = f'{OUTPUT_PATH}/{method}/{inputfile}_{speed}_crf{crf}.yuv'
    cmd_raw = ['/home1/irteam/donghwan/ffmpeg-git-20210528-amd64-static/ffmpeg',
               '-y',
               '-i', f'{enc}', f'{enc_raw}',
               '-hide_banner', '-loglevel', 'error'
               ]
    subprocess.run(cmd_raw)
    p = run_vmaf(enc_raw, ref, fps)
    vmaf, psnr, ssim = parse_vmaf(p)
    subprocess.run(['rm', f'{enc_raw}'])

    return vmaf, psnr, ssim


def run_vmaf(enc, ref, fps):
    log_path = os.path.basename(os.path.splitext(enc)[0])
    cmd = ['/home1/irteam/donghwan/ffmpeg-git-20210528-amd64-static/ffmpeg',
           '-video_size', '3840x2160',
           '-r', f'{fps}',
           '-pixel_format', 'yuv420p',
           '-i', f'{ref}',
           '-video_size', '3840x2160',
           '-r', f'{fps}',
           '-pixel_format', 'yuv420p',
           '-i', f'{enc}',
           '-lavfi', '[0:v]crop=w=3000:h=2160:x=0:y=0, setpts=PTS-STARTPTS[reference]; \
                        [1:v]crop=w=3000:h=2160:x=0:y=0, setpts=PTS-STARTPTS[distorted]; \
                        [distorted][reference]libvmaf=log_path=/dev/stdout:log_fmt=xml:ssim=1:psnr=1',
           '-f', 'null', '-'
           ]

    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def parse_vmaf(p):
    pattern = 'aggregateVMAF="(.*)" aggregatePSNR="(.*)" aggregateSSIM="(.*)" execFps'
    stdout = str(p.stdout.read())
    r = re.compile(pattern, re.DOTALL)
    searched = r.search(stdout)
    if not searched:
        print('No VMAF data matched')
        return
    vmaf = searched.group(1)
    psnr = searched.group(2)
    ssim = searched.group(3)
    return vmaf, psnr, ssim


def run_enc(inputfile, method, speed='fast', crf=28):
    fps = FPS_DICT[os.path.basename(os.path.splitext(inputfile)[0])]
    input = f'{INPUT_PATH}/{inputfile}.yuv'
    output = f'{OUTPUT_PATH}/{method}/{inputfile}_{speed}_crf{crf}.hevc'

    if method == 'mc':
        cmd = ['/home1/irteam/donghwan/demo_hevc_sdk_linux_x64_release/bin/sample_enc_hevc',
               '-I420',
               '-w', '3840',
               '-h', '2160',
               '-f', f'{fps}',
               '-v', f'{input}',
               '-o', f'{output}',
               '-perf', f'{MC_PRESET[speed]}',
               '-preset', '4k',
               '-c', f'../config/crf{crf}.ini'
               ]
    elif method == 'mc_hybrid':
        cmd = ['/home1/irteam/donghwan/demo_hevc_sdk_linux_x64_release/bin/sample_enc_hevc',
               '-I420',
               '-w', '3840',
               '-h', '2160',
               '-f', f'{fps}',
               '-v', f'{input}',
               '-o', f'{output}',
               '-perf', f'{MC_NVENC_PRESET[speed]}',
               '-preset', '4k',
               '-c', f'../config/crf{crf}_hybrid.ini',
               ]
    elif method == 'mc_driven':
        cmd = ['/home1/irteam/donghwan/demo_hevc_sdk_linux_x64_release/bin/sample_enc_hevc',
               '-I420',
               '-w', '3840',
               '-h', '2160',
               '-f', f'{fps}',
               '-v', f'{input}',
               '-o', f'{output}',
               '-perf', f'{MC_NVENC_PRESET[speed]}',
               '-preset', '4k',
               '-c', f'../config/crf{crf}_driven.ini',
               ]
    elif method == 'ff':
        cmd = ['/home1/irteam/donghwan/ffmpeg-git-20210528-amd64-static/ffmpeg',
               '-y',
               '-video_size', '3840x2160',
               '-i', f'{input}',
               '-c:v', 'libx265',
               '-crf', f'{crf}',
               '-preset', f'{FF_PRESET[speed]}',
               '-c:a', 'copy',
               f'{output}'
               ]
    else:
        print('Method should be either ff OR mc!')
        return

    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def parse_fps_bitrate(p, method):
    if method in ['mc', 'mc_hybrid', 'mc_driven']:
        pattern = r'Average speed achieved \\t(\d*.*\d*) fps.*Average bitrate\s*(\d*.*\d*) kb/s'
    elif method == 'ff':
        pattern = r'encoded .* frames in .*s \((.*) fps\), (.*) kb/s, Avg QP:.*'
    else:
        print('Method should be either ff OR mc!')
        return

    stdout = str(p.stdout.read())
    try:
        fps, bitrate = _parse_stdout(pattern, stdout)
    except Exception as e:
        print('Parse Error!')
        raise e
    return fps, bitrate


def _parse_stdout(pattern, stdout):
    r = re.compile(pattern, re.DOTALL)
    searched = r.search(stdout)
    if not searched:
        print(stdout)
        raise Exception('no match')

    return searched.group(1), searched.group(2)


def write_result_csv(csv_file, csv_columns, result_data):
    with open(csv_file, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
        writer.writeheader()
        for data in result_data:
            writer.writerow(data)


def run_test(input_set, speed_set, crf_set, method):
    for speed in speed_set:
        csv_file = f'../data/{method}_{speed}_wide_crf.csv'
        csv_columns = ['inputfile', 'crf', 'bitrate', 'psnr', 'ssim', 'vmaf', 'fps']
        result_data = []
        for inputfile in input_set:
            for crf in crf_set:
                print(f'Encoding {method} {inputfile}_{speed}_crf{crf}...')
                p = run_enc(inputfile, method=method, speed=speed, crf=crf)
                fps, bitrate = parse_fps_bitrate(p, method)
                vmaf, psnr, ssim = calc_vmaf(inputfile, speed, crf, method)
                result_data.append({'inputfile': inputfile,
                                    'crf': crf,
                                    'bitrate': bitrate,
                                    'psnr': psnr,
                                    'ssim': ssim,
                                    'vmaf': vmaf,
                                    'fps': fps,
                                    })
                print(f'Bitrate: {bitrate}, VMAF: {vmaf}, fps: {fps}')
        write_result_csv(csv_file, csv_columns, result_data)


def generate_config():
    for crf in range(1, 52):
        _write_sw_config(crf)
        _write_hybrid_config(crf)
        _write_driven_config(crf)


def _write_sw_config(crf):
    sw_config = os.path.join(CONFIG_PATH, f'crf{crf}.ini')
    config = configparser.ConfigParser()
    config['HEVC Layer 0000'] = {'width': '3840',
                                 'height': '2160',
                                 'bit_rate_mode': 'HEVC_CRF',
                                 'rate_factor': f'{crf}'
                                 }
    with open(sw_config, 'w') as configfile:
        config.write(configfile)


def _write_hybrid_config(crf):
    hybrid_config = os.path.join(CONFIG_PATH, f'crf{crf}_hybrid.ini')
    config = configparser.ConfigParser()
    config['HEVC Settings'] = {'hw_acceleration': '2',
                               'hw_acc_mode': '2'}
    config['HEVC Layer 0000'] = {'width': '3840',
                                 'height': '2160',
                                 'bit_rate_mode': 'HEVC_CRF',
                                 'rate_factor': f'{crf}'
                                 }
    with open(hybrid_config, 'w') as configfile:
        config.write(configfile)


def _write_driven_config(crf):
    driven_config = os.path.join(CONFIG_PATH, f'crf{crf}_driven.ini')
    config = configparser.ConfigParser()
    config['HEVC Settings'] = {'hw_acceleration': '2',
                               'hw_acc_mode': '1'}
    config['HEVC Layer 0000'] = {'width': '3840',
                                 'height': '2160',
                                 'bit_rate_mode': 'HEVC_CRF',
                                 'rate_factor': f'{crf}',
                                 'hw_acc_indices': '{0, 1}'
                                 }
    with open(driven_config, 'w') as configfile:
        config.write(configfile)


if __name__ == '__main__':
    #input_set = ['bike1', 'circuit1', 'city1', 'concert1', 'game1', 'movie1', 'tennis1']
    #speed_set = ['fast', 'medium', 'slow']
    #crf_set = [22, 24, 26, 28, 30, 32, 34]

    input_set = ['bike1', 'circuit1', 'city1', 'concert1', 'game1', 'movie1', 'tennis1']
    speed_set = ['fast']
    crf_set = [14, 17, 20, 23, 26, 29, 32]

    #run_test(input_set, speed_set, crf_set, 'ff')
    run_test(input_set, speed_set, crf_set, 'mc')
    #run_test(input_set, speed_set, crf_set, 'mc_hybrid')

    print('done')
