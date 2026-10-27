"""軽い確認のMP4と比較画像を作り、全境目の0.1秒刻みのコマを照合する。"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageStat, ImageDraw, ImageFont

DECK = Path('typst_manual/動画/01_1ラウンドの流れ').resolve()
OUT = DECK / 'out/v2-enemy-boundaries'
RENDER = OUT / 'render'
FF = Path('C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/'
          'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin')


def run(name, *args):
    result = subprocess.run([str(FF / (name + '.exe')), *map(str, args)],
                            capture_output=True, check=True)
    return result.stdout


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def frame(movie, at, target):
    run('ffmpeg', '-v', 'error', '-ss', at, '-i', movie, '-frames:v', '1', '-y', target)


report = read(OUT / 'boundary-report.json')
meta = read(RENDER / 'timeline.out.json')
cache = read(RENDER / '.render-cache.json')['clips']
keys = ['s-selection:2', 's-resolve:0', 's-resolve:1',
        's-power-enemy:0', 's-power-enemy:1', 's-power-enemy:2']
clips = []
for key in keys:
    segment = next(s for s in meta['segments'] if s['key'] == key)
    assert cache[segment['clip'][:-4]]['input'] == segment['input'], key
    clips.append(RENDER / segment['clip'])
concat = OUT / 'review-concat.txt'
concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p in clips), encoding='utf-8')
review = OUT / 'revised-scenes.mp4'
run('ffmpeg', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', concat,
    '-c', 'copy', '-movflags', '+faststart', '-y', review)
boundaries = OUT / 'all-boundaries.mp4'
run('ffmpeg', '-v', 'error', '-framerate', '10', '-i',
    OUT / 'boundary-png/boundary-%04d.png', '-c:v', 'libx264', '-crf', '18',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-y', boundaries)
decoded = OUT / 'decoded-boundaries'
decoded.mkdir(exist_ok=True)
run('ffmpeg', '-v', 'error', '-i', boundaries, '-fps_mode', 'passthrough',
    '-start_number', '0', '-y', decoded / 'frame-%04d.png')
errors = []
for n, record in enumerate(report['records']):
    source = Image.open(OUT / 'boundary-png' / record['file']).convert('RGB')
    actual = Image.open(decoded / f'frame-{n:04d}.png').convert('RGB')
    error = sum(ImageStat.Stat(ImageChops.difference(source, actual)).mean) / 3
    assert error < 5, (n, error)
    errors.append(error)
assert len(list(decoded.glob('frame-*.png'))) == 231

font = ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc', 16)
sheet = Image.new('RGB', (1600, 11 * 208), '#fffdfb')
draw = ImageDraw.Draw(sheet)
for row in range(11):
    for col, tick in enumerate([1, 9, 10, 11, 19]):
        n = row * 21 + tick
        record = report['records'][n]
        pic = Image.open(decoded / f'frame-{n:04d}.png').resize((320, 180))
        sheet.paste(pic, (col * 320, row * 208 + 28))
        draw.text((col * 320 + 5, row * 208 + 3),
                  f"C{row + 1:02}→C{row + 2:02} {record['relative']:+.1f}秒", fill='#222', font=font)
sheet.save(OUT / 'all-boundaries.png')

old = read(DECK / 'out/v2-sync/timeline.out.json')
old_enemy = next(s for s in old['segments'] if s['key'] == 's-power-enemy:1')
frame(DECK / 'out/v2-sync/full.mp4', old_enemy['clipStart'] + .25, OUT / 'enemy-before.png')
frame(DECK / 'out/v2-sync/full.mp4', 80.9, OUT / 'white-before.png')
enemy_clip = clips[-1]
frame(enemy_clip, .25, OUT / 'enemy-after.png')
frame(enemy_clip, 4.25, OUT / 'compare-after.png')
frame(clips[0], 4.5, OUT / 'white-after.png')
quarter = OUT / 'enemy-quarter'
quarter.mkdir(exist_ok=True)
run('ffmpeg', '-v', 'error', '-i', enemy_clip, '-vf', 'select=not(mod(n\,6))',
    '-fps_mode', 'vfr', '-start_number', '0', '-y', quarter / 'frame-%03d.png')
reference = Image.open(OUT / 'enemy-after.png').convert('RGB')
comparison_visible = Image.open(OUT / 'compare-after.png').convert('RGB')


def region(selector):
    r = report['geometry'][selector]
    # 字形の中を比較し、文末の赤いcircleは検査領域から外す。
    return (round(r['x']) + 3, round(r['y']) + 6,
            round(r['right']) - 3, round(r['bottom']) - 6)


quarters = sorted(quarter.glob('frame-*.png'))
for n, file in enumerate(quarters):
    image = Image.open(file).convert('RGB')
    for selector in ['[data-first-die]', '[data-dice-target]', '[data-dice-total]']:
        box = region(selector)
        error = sum(ImageStat.Stat(ImageChops.difference(image.crop(box), reference.crop(box))).mean) / 3
        assert error < 8, (n / 4, selector, error)
    box = region('.v2-compare')
    expected = comparison_visible if n / 4 >= report['end'] else reference
    error = sum(ImageStat.Stat(ImageChops.difference(image.crop(box), expected.crop(box))).mean) / 3
    assert error < 8, ('comparison', n / 4, error)
cards = [('white-before.png', '修正前：C04の白い覆い'),
         ('white-after.png', '修正後：背景を保った縁取り'),
         ('enemy-before.png', '修正前：結果の語り開始時'),
         ('enemy-after.png', '修正後：語り開始前に1＋1と＝6'),
         ('compare-after.png', '修正後：読み終えた後の比較')]
comparison = Image.new('RGB', (1280, 3 * 388), '#fffdfb')
draw = ImageDraw.Draw(comparison)
for n, (file, label) in enumerate(cards):
    x, y = n % 2 * 640, n // 2 * 388
    comparison.paste(Image.open(OUT / file).resize((640, 360)), (x, y + 28))
    draw.text((x + 8, y + 3), label, fill='#222', font=font)
comparison.save(OUT / 'comparison.png')

for movie in [review, boundaries]:
    run('ffmpeg', '-v', 'error', '-i', movie, '-f', 'null', '-')
probe = json.loads(run('ffprobe', '-v', 'error', '-show_entries',
                       'format=duration:stream=width,height,r_frame_rate', '-of', 'json', review))
result = {'boundaries': 11, 'frames': len(errors), 'interval': .1,
          'enemyQuarterFrames': len(quarters),
          'maxMeanPixelError': max(errors), 'review': probe, 'decode': 'pass'}
(OUT / 'video-report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
