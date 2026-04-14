"""
零依赖PNG生成器 - 用struct+zlib手写PNG
支持RGBA，逐行编码
"""
import struct
import zlib

def create_png(width, height, pixels):
    """
    pixels: list of rows, each row is list of (R,G,B,A) tuples
    Returns: PNG bytes
    """
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xffffffff)
        return struct.pack(">I", len(data)) + c + crc

    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = chunk(b"IHDR", ihdr_data)

    # IDAT - raw pixel data with filter byte
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter: None
        for r, g, b, a in row:
            raw.extend([r & 0xFF, g & 0xFF, b & 0xFF, a & 0xFF])

    compressed = zlib.compress(bytes(raw), 9)
    idat = chunk(b"IDAT", compressed)

    # IEND
    iend = chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


def create_spritesheet(frames, cols, frame_w, frame_h):
    """
    frames: list of 2D pixel arrays (each is list of rows of RGBA tuples)
    Returns: PNG bytes of the spritesheet
    """
    rows_count = (len(frames) + cols - 1) // cols
    sheet_w = cols * frame_w
    sheet_h = rows_count * frame_h

    # Create blank sheet
    sheet = []
    for sy in range(sheet_h):
        row = []
        for sx in range(sheet_w):
            frame_idx = (sy // frame_h) * cols + (sx // frame_w)
            fx = sx % frame_w
            fy = sy % frame_h
            if frame_idx < len(frames):
                row.append(frames[frame_idx][fy][fx])
            else:
                row.append((0, 0, 0, 0))
        sheet.append(row)

    return create_png(sheet_w, sheet_h, sheet)
