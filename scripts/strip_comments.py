"""Strip all Python comments (COMMENT tokens) from a file while preserving docstrings.
Usage: python scripts/strip_comments.py path/to/file.py
This script writes a backup to <file>.bak and overwrites the file in-place.
"""
import sys
import io
import tokenize


def strip_comments(path: str):
    src = open(path, 'rb').read()
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(src).readline))
    except Exception as e:
        print('tokenize error:', e)
        return 1
    out = []
    prev_end = (1, 0)
    for tok in tokens:
        ttype = tok.type
        tstring = tok.string
        start = tok.start
        end = tok.end
        # keep everything except COMMENT and NL tokens that are comments
        if ttype == tokenize.COMMENT:
            # skip
            continue
        if ttype == tokenize.ENCODING:
            out.append(tok)
            continue
        out.append(tok)
    # untokenize
    try:
        new = tokenize.untokenize(out)
    except Exception as e:
        print('untokenize error:', e)
        return 2
    # write backup
    bak = path + '.bak'
    open(bak, 'wb').write(src)
    open(path, 'wb').write(new)
    print(f'stripped comments from {path}, backup saved to {bak}')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python strip_comments.py path/to/file.py')
        sys.exit(3)
    sys.exit(strip_comments(sys.argv[1]))
