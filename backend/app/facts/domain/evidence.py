import hashlib

def content_hash(source: bytes, line_start=None, line_end=None):
    """SHA-256 of UTF-8 source lines, 1-based and inclusive; no source is retained."""
    if (line_start is None) != (line_end is None):
        raise ValueError('Both line bounds are required.')
    text = source.decode('utf-8').replace('\r', '')
    lines = text.split('\n')
    if text.endswith('\n'):
        lines.pop()
    if not text:
        lines = []
    if line_start is not None:
        if (type(line_start) is not int or type(line_end) is not int
                or not 1 <= line_start <= line_end <= len(lines)):
            raise ValueError('Line range is outside the source.')
        lines = lines[line_start - 1:line_end]
    return 'sha256:' + hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()
