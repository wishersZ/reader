from pathlib import Path
import hashlib
import re
import sys

SOURCE = Path(r"G:\txt\novels\混沌冠冕.txt")
OUTPUT = Path(r"G:\txt\novels\混沌冠冕_每15章拆分")
REPORT = Path(r"G:\txt\tools\batch15\results\split15_hundun_报告.txt")

TITLE_RE = re.compile(r"^第([0-9]+)章")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    source_bytes = SOURCE.read_bytes()
    if source_bytes.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError("源文件带 UTF-8 BOM，与已知格式不符")
    if b"\n" in source_bytes.replace(b"\r\n", b""):
        raise RuntimeError("源文件存在非 CRLF 换行")
    text = source_bytes.decode("utf-8")
    lines = text.split("\r\n")
    # 文件末尾 CRLF 对应 split 后的空字符串；保存原文时由 join 恢复，不将其当作内容行。
    if lines and lines[-1] == "":
        lines.pop()

    chapters = []
    for index, line in enumerate(lines):
        match = TITLE_RE.match(line)
        if match:
            chapters.append((index, int(match.group(1)), line))
    if len(chapters) != 645:
        raise RuntimeError(f"章标题数应为645，实测{len(chapters)}")
    if [number for _, number, _ in chapters] != list(range(1, 646)):
        raise RuntimeError("章号不是1至645连续递增")
    if len(lines) != 64701:
        raise RuntimeError(f"行数应为64701，实测{len(lines)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    # 输出目录为本任务新建目录；删除其中旧有文件，确保最终仅包含本次43个批次。
    for old in OUTPUT.iterdir():
        if old.is_file():
            old.unlink()
        elif old.is_dir():
            raise RuntimeError(f"输出目录含意外子目录，停止以免误删：{old}")

    files = []
    for batch in range(43):
        first_chapter_index = batch * 15
        start_line = 0 if batch == 0 else chapters[first_chapter_index][0]
        end_line = len(lines) if batch == 42 else chapters[first_chapter_index + 15][0]
        start_num = first_chapter_index + 1
        end_num = start_num + 14
        name = f"第{batch + 1:03d}批_第{start_num:04d}-{end_num:04d}章.txt"
        # 将行间 CRLF 原样恢复；全书每份分片均以CRLF结束，使字节拼接等于源文件。
        piece = "\r\n".join(lines[start_line:end_line]) + "\r\n"
        data = piece.encode("utf-8")
        (OUTPUT / name).write_bytes(data)
        title_rows = [(n, title) for _, n, title in chapters if start_num <= n <= end_num]
        files.append((name, title_rows[0][1], title_rows[-1][1], len(title_rows), len(data), data))

    ordered = sorted(OUTPUT.glob("*.txt"), key=lambda p: p.name)
    joined_hash = hashlib.sha256()
    joined_size = 0
    listing = []
    all_ok = len(ordered) == 43 and len(files) == 43
    expected_names = []
    for batch in range(43):
        start_num = batch * 15 + 1
        end_num = start_num + 14
        expected_names.append(f"第{batch + 1:03d}批_第{start_num:04d}-{end_num:04d}章.txt")
    if [p.name for p in ordered] != expected_names:
        all_ok = False

    for p in ordered:
        data = p.read_bytes()
        joined_hash.update(data)
        joined_size += len(data)
        piece_text = data.decode("utf-8")
        piece_lines = piece_text.split("\r\n")
        titles = [line for line in piece_lines if TITLE_RE.match(line)]
        # 文件名给出确定章号范围，验证标题数和首尾标题。
        m = re.match(r"第(\d{3})批_第(\d{4})-(\d{4})章\.txt$", p.name)
        if not m:
            all_ok = False
            continue
        start_num, end_num = int(m.group(2)), int(m.group(3))
        expected_titles = [line for _, n, line in chapters if start_num <= n <= end_num]
        if len(titles) != 15 or titles != expected_titles:
            all_ok = False
        listing.append((p.name, titles[0] if titles else "[缺失]", titles[-1] if titles else "[缺失]", len(titles), len(data)))

    joined_digest = joined_hash.hexdigest()
    source_digest = sha256(source_bytes)
    byte_match = joined_size == len(source_bytes) and joined_digest == source_digest
    if not byte_match:
        all_ok = False
    if any(row[3] != 15 for row in listing):
        all_ok = False

    report_lines = [
        "混沌冠冕每15章拆分校验报告",
        f"源文件：{SOURCE}",
        f"输出目录：{OUTPUT}",
        f"输出文件数：{len(ordered)}（预期43）",
        f"文件名及章号范围连续、无重叠无缺口：{'通过' if [p.name for p in ordered] == expected_names else '失败'}",
        f"源文件字节数：{len(source_bytes)}",
        f"源文件 SHA-256：{source_digest}",
        f"拼接结果字节数：{joined_size}",
        f"拼接结果 SHA-256：{joined_digest}",
        f"逐字节完全一致：{'是' if byte_match else '否'}",
        f"每份恰含15个章标题：{'通过' if listing and all(row[3] == 15 for row in listing) else '失败'}",
        "",
        "文件名 / 首章标题 / 末章标题 / 章数 / 字节数",
    ]
    report_lines.extend(f"{name} / {first} / {last} / {count} / {size}" for name, first, last, count, size in listing)
    report_lines.extend(["", f"总体验证：{'全部通过' if all_ok else '失败'}"])
    REPORT.write_text("\r\n".join(report_lines) + "\r\n", encoding="utf-8", newline="")
    if not all_ok:
        raise RuntimeError(f"校验失败，详见报告：{REPORT}")
    print(f"成功：43个文件；零丢失={byte_match}；报告={REPORT}")


if __name__ == "__main__":
    main()
