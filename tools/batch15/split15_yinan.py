from __future__ import annotations

import hashlib
import re
from pathlib import Path

SOURCE = Path(r"G:\txt\novels\幽暗主宰_合并版.txt")
OUTPUT_DIR = Path(r"G:\txt\novels\幽暗主宰_每15章拆分")
REPORT = Path(r"G:\txt\tools\batch15\results\split15_yinan_报告.txt")

TITLE_RE = re.compile(r"^(?:第[一二三四五六七八九十百千零两]+章|第[0-9]+章|序章|最终章)")
NUMBERED_RE = re.compile(r"^第([一二三四五六七八九十百千零两]+|[0-9]+)章")


def chinese_number(text: str) -> int:
    if text.isdigit():
        return int(text)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for ch in text:
        if ch in digits:
            current = digits[ch]
        elif ch in units:
            unit = units[ch]
            total += (current or 1) * unit
            current = 0
        else:
            raise ValueError(f"无法解析中文章号：{text}")
    return total + current


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    source_bytes = SOURCE.read_bytes()
    if source_bytes.startswith(b"\xef\xbb\xbf"):
        raise ValueError("源文件意外包含 UTF-8 BOM")
    if b"\n" in source_bytes.replace(b"\r\n", b""):
        raise ValueError("源文件存在非 CRLF 换行")
    text = source_bytes.decode("utf-8")
    lines = text.split("\r\n")
    if lines[-1] != "":
        raise ValueError("源文件未以 CRLF 结束")
    lines.pop()  # split 产生的末尾空段；写出时统一还原最终 CRLF

    titles: list[tuple[int, str, str, int | None]] = []
    for index, line in enumerate(lines):
        # 标题必须从第0列开始；带任意空白前缀的正文一律不匹配。
        if not line or line[0].isspace():
            continue
        match = TITLE_RE.match(line)
        if not match:
            continue
        title = line
        if title.startswith("序章"):
            kind, number = "序章", None
        elif title.startswith("最终章"):
            kind, number = "最终章", None
        else:
            nm = NUMBERED_RE.match(title)
            if not nm:
                continue
            kind, number = "编号章", chinese_number(nm.group(1))
        titles.append((index, title, kind, number))

    numbered = [entry for entry in titles if entry[2] == "编号章"]
    prologues = [entry for entry in titles if entry[2] == "序章"]
    finales = [entry for entry in titles if entry[2] == "最终章"]
    if len(numbered) != 1044 or len(prologues) != 1 or len(finales) != 1:
        raise ValueError(f"标题计数异常：编号章{len(numbered)}，序章{len(prologues)}，最终章{len(finales)}")
    if [entry[3] for entry in numbered] != list(range(1, 1045)):
        raise ValueError("编号章号并非连续的第1至1044章")
    if titles[0][0] != 16 or titles[0][2] != "序章":
        raise ValueError(f"首个章标题位置不符合预期：{titles[0]}")
    if finales[0][0] <= numbered[-1][0]:
        raise ValueError("最终章未出现在编号章之后")

    # 按源文件逐行边界切片；每片写出时只恢复原有 CRLF，不改任何文本。
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT_DIR.glob("*.txt"):
        old.unlink()

    file_records: list[dict[str, object]] = []
    expected_files = 70
    for batch in range(1, expected_files + 1):
        first_num = (batch - 1) * 15 + 1
        last_num = min(batch * 15, 1044)
        start_title = numbered[first_num - 1]
        next_start = numbered[last_num] if last_num < 1044 else None
        start_idx = 0 if batch == 1 else start_title[0]
        end_idx = (next_start[0] if next_start else len(lines))
        slice_lines = lines[start_idx:end_idx]
        raw = ("\r\n".join(slice_lines) + "\r\n").encode("utf-8")
        filename = f"第{batch:03d}批_第{first_num:04d}-{last_num:04d}章.txt"
        (OUTPUT_DIR / filename).write_bytes(raw)

        in_slice = [t for t in titles if start_idx <= t[0] < end_idx]
        if batch == 1:
            expected_count = 16
        elif batch == 70:
            expected_count = 10
        else:
            expected_count = 15
        if len(in_slice) != expected_count:
            raise ValueError(f"{filename} 标题数异常：{len(in_slice)}，预期{expected_count}")
        file_records.append({
            "name": filename,
            "start": in_slice[0][1],
            "end": in_slice[-1][1],
            "chapters": len(in_slice),
            "bytes": len(raw),
        })

    out_files = sorted(OUTPUT_DIR.glob("*.txt"), key=lambda p: p.name)
    if len(out_files) != 70:
        raise ValueError(f"输出文件数异常：{len(out_files)}")
    concatenated = b"".join(path.read_bytes() for path in out_files)
    source_hash = sha(source_bytes)
    concat_hash = sha(concatenated)
    if concatenated != source_bytes:
        # 找出首个不一致位置，便于定位切片边界问题。
        mismatch = next((i for i, (a, b) in enumerate(zip(source_bytes, concatenated)) if a != b), min(len(source_bytes), len(concatenated)))
        raise ValueError(f"零丢失校验失败：源{len(source_bytes)}字节，拼接{len(concatenated)}字节，首个差异偏移{mismatch}，SHA256 {source_hash} / {concat_hash}")

    # 文件名所标章号区间按序连续核验。
    ranges = [(int(re.search(r"第(\d{4})-(\d{4})章", p.name).group(1)), int(re.search(r"第(\d{4})-(\d{4})章", p.name).group(2))) for p in out_files]
    if ranges != [(i * 15 + 1, min((i + 1) * 15, 1044)) for i in range(70)]:
        raise ValueError("文件名章号区间存在重叠、缺口或排序异常")

    lines_out = [
        "幽暗主宰按每15章拆分校验报告",
        "状态：成功",
        f"源文件：{SOURCE}",
        f"输出目录：{OUTPUT_DIR}",
        f"文件数：{len(out_files)}（预期70）",
        f"源文件字节数：{len(source_bytes)}",
        f"源文件 SHA256：{source_hash}",
        f"拼接结果字节数：{len(concatenated)}",
        f"拼接结果 SHA256：{concat_hash}",
        f"逐字节完全一致：是（{len(source_bytes)} 字节）",
        "章标题数：第001批=序章1+编号章15；第002-069批各15；第070批=编号章9+最终章1。",
        "",
        "文件清单（文件名 / 首章标题 / 末章标题 / 章数 / 字节数）",
    ]
    for rec in file_records:
        lines_out.append(f"{rec['name']} / {rec['start']} / {rec['end']} / {rec['chapters']} / {rec['bytes']}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\r\n".join(lines_out) + "\r\n", encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
