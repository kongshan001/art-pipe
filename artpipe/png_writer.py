"""
零依赖PNG生成器 - 用struct+zlib手写PNG
支持RGBA，逐行编码，Sub过滤器优化体积
"""
import struct
import zlib


def _apply_sub_filter(row_rgba):
    """对一行RGBA数据应用Sub过滤器（每个通道减去前一像素对应通道）
    Sub filter 对像素间相关性高的图像（如精灵图）压缩效果显著
    """
    filtered = bytearray(len(row_rgba))
    # 第一个像素保持不变
    filtered[0] = row_rgba[0]
    filtered[1] = row_rgba[1]
    filtered[2] = row_rgba[2]
    filtered[3] = row_rgba[3]
    # 后续像素每个通道减去前一像素
    for i in range(4, len(row_rgba)):
        filtered[i] = (row_rgba[i] - row_rgba[i - 4]) & 0xFF
    return filtered


def create_png(width, height, pixels):
    """
    pixels: list of rows, each row is list of (R,G,B,A) tuples
    Returns: PNG bytes
    使用 Sub filter (type 1) 替代 None filter，显著减小文件体积
    """
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xffffffff)
        return struct.pack(">I", len(data)) + c + crc

    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR: 8-bit RGBA
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = chunk(b"IHDR", ihdr_data)

    # IDAT - 使用 Sub filter 编码像素数据
    raw = bytearray()
    for row in pixels:
        # 将行数据转换为紧凑字节数组
        row_bytes = bytearray()
        for r, g, b, a in row:
            row_bytes.extend([r & 0xFF, g & 0xFF, b & 0xFF, a & 0xFF])
        # 应用 Sub filter
        filtered = _apply_sub_filter(row_bytes)
        raw.append(1)  # filter type: Sub
        raw.extend(filtered)

    compressed = zlib.compress(bytes(raw), 9)
    idat = chunk(b"IDAT", compressed)

    # IEND
    iend = chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


def create_spritesheet(frames, cols, frame_w, frame_h):
    """
    frames: list of 2D pixel arrays (each is list of rows of RGBA tuples)
    Returns: PNG bytes of the spritesheet
    使用按行复制替代逐像素遍历，提升性能
    """
    rows_count = (len(frames) + cols - 1) // cols
    sheet_w = cols * frame_w
    sheet_h = rows_count * frame_h

    # 使用按帧行复制，避免逐像素 Python 循环
    sheet = [[(0, 0, 0, 0)] * sheet_w for _ in range(sheet_h)]

    for frame_idx, frame in enumerate(frames):
        col_idx = frame_idx % cols
        row_idx = frame_idx // cols
        x_offset = col_idx * frame_w
        y_offset = row_idx * frame_h

        # 逐行复制整帧数据到精灵表
        for fy in range(frame_h):
            sy = y_offset + fy
            if sy < sheet_h:
                # 切片赋值比逐像素快得多
                sheet[sy][x_offset:x_offset + frame_w] = frame[fy][:]

    return create_png(sheet_w, sheet_h, sheet)
