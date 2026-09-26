#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_reader_clone.py —— 校验 projects/reader 的工作区文件与 GitHub 仓库逐字节一致。

说明（重要）：
    这个脚本是**重建版**。原文件 `G:\txt\_verify_reader.py` 在 2026-09-26 的目录整理中
    被误删（我把它 1658 字节的大小误读成 0 字节后无条件删除），内容无法恢复。
    重建时保留了原有的 EXPECTED 清单与校验方式，并做了两点改进：
      1) 兼容 core.autocrlf 检出：同时比对「原始字节」与「LF 规范化后」两种 blob SHA；
      2) 给出明确的退出码（0=全部一致，1=有差异或缺文件）。

用法：
    py -3 verify_reader_clone.py [仓库路径]
    默认仓库路径：<本脚本所在目录>/../../projects/reader
"""

import hashlib
import pathlib
import sys

DEFAULT_ROOT = pathlib.Path(__file__).resolve().parent.parent / 'projects' / 'reader'

# (相对路径, 字节数, git blob SHA-1) —— 来自 GitHub API 的仓库文件树（main 分支）
EXPECTED = [
    ('.gitignore', 62, '929329b65642b24ff5eefa5f2dc841806eb2c8df'),
    ('LICENSE', 529, 'b0613aaa467720709b9276e761bf26fec5d7b8eb'),
    ('README.md', 3717, '883e875d95e61cc050a8691a6cc99fc8e3ae3e06'),
    ('package.json', 829, 'c86515891944be62d4654dc7701e9b277aa9209c'),
    ('src/main.js', 2631, '87005a324bad636be09064e45eea7879c1e30e13'),
    ('src/preload.js', 360, '5434a49ebe3e337250ebbd8fdd8feb95b59c2a6d'),
    ('src/index.html', 32026, '32f5d2f98650b8f1c6fbddee4f902a03ca708c25'),
    ('site/index.html', 4669, '740df085e6ec7b822802627ec43ca98a46c7d129'),
    ('assets/icon.png', 5283, '18cbf14fd6fc61c7fbb0230d0a06ddf4dac49119'),
    ('assets/icon.ico', 33510, 'f3cf7b7b4fc067d9e21c601676226d8759c6dd6b'),
    ('assets/donate.png', 14129, 'cdbe1e52f39794e91bf8d5db03117190acd29fa0'),
]

# 本地整合新增/修改过、不应再按上游 SHA 比对的文件
LOCALLY_CHANGED = {'README.md', 'src/main.js', 'src/preload.js', 'src/index.html'}


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def main() -> int:
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROOT
    if not root.is_dir():
        print(f'仓库路径不存在：{root}')
        return 1

    print(f'校验目标：{root}\n')
    print(f'{"文件":<22}{"本地字节":>10}{"上游字节":>10}  结果')
    print('-' * 62)
    bad = 0
    for rel, size, sha in EXPECTED:
        p = root / rel
        if rel in LOCALLY_CHANGED:
            note = '已本地修改（预期不一致）' if p.is_file() else '缺失'
            print(f'{rel:<22}{"-":>10}{size:>10}  {note}')
            continue
        if not p.is_file():
            print(f'{rel:<22}{"-":>10}{size:>10}  缺失')
            bad += 1
            continue
        raw = p.read_bytes()
        lf = raw.replace(b'\r\n', b'\n')
        hit = (len(raw) == size and blob_sha(raw) == sha) or blob_sha(lf) == sha
        how = 'OK' if len(raw) == size and blob_sha(raw) == sha else ('OK(CRLF 检出)' if blob_sha(lf) == sha else '不一致')
        if not hit:
            bad += 1
        print(f'{rel:<22}{len(raw):>10}{size:>10}  {how}')
    print('-' * 62)
    if bad:
        print(f'有 {bad} 个文件与上游不一致或缺文件。')
    else:
        print('未修改的文件全部与上游一致（assets / site / package.json / LICENSE 等）。')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
