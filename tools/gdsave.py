# Чтение/запись сохранений Geometry Dash (Windows):
# файл = XOR 11 -> base64 (url-safe) -> gzip -> plist-подобный XML.
import base64, gzip, sys, zlib

def decode_save(path):
    raw = open(path, 'rb').read()
    x = bytes(b ^ 11 for b in raw)
    x = x.rstrip(b'\0')
    x = x.replace(b'-', b'+').replace(b'_', b'/')
    x += b'=' * (-len(x) % 4)
    data = base64.b64decode(x)
    try:
        return gzip.decompress(data)
    except Exception:
        return zlib.decompress(data[10:], -zlib.MAX_WBITS)

def encode_save(xml_bytes):
    gz = gzip.compress(xml_bytes)
    b = base64.urlsafe_b64encode(gz)
    return bytes(c ^ 11 for c in b)

def decode_level_string(k4):
    s = k4.strip()
    s += '=' * (-len(s) % 4)
    data = base64.urlsafe_b64decode(s)
    try:
        return gzip.decompress(data).decode('utf-8', 'replace')
    except Exception:
        return zlib.decompress(data[10:], -zlib.MAX_WBITS).decode('utf-8', 'replace')

def encode_level_string(level):
    gz = gzip.compress(level.encode('utf-8'))
    return base64.urlsafe_b64encode(gz).decode('ascii')

if __name__ == '__main__':
    out = decode_save(sys.argv[1])
    if len(sys.argv) > 2:
        open(sys.argv[2], 'wb').write(out)
    else:
        print(out[:3000].decode('utf-8', 'replace'))
