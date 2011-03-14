"""PyPy replacements for the _speedups C extension"""
import sys

from simplejson.errors import JSONDecodeError

DEFAULT_ENCODING = "utf-8"

def scanstring(s, end, encoding=None, strict=True):
    """Scan the string s for a JSON string. End is the index of the
    character in s after the quote that started the JSON string.
    Unescapes all valid JSON string escape sequences and raises ValueError
    on attempt to decode an invalid string. If strict is False then literal
    control characters are allowed in the string.

    Returns a tuple of the decoded string and the index of the character in s
    after the end quote."""
    if encoding is None:
        encoding = DEFAULT_ENCODING
    chunks = None
    begin = end - 1
    is_unicode = isinstance(s, unicode)
    if is_unicode:
        empty_str = u''
    else:
        empty_str = ''
    while 1:
        # Find the next "terminator"
        chunk_end = end
        needs_decode = False
        try:
            while 1:
                c = s[chunk_end]
                if (c == '"') or (c == '\\'):
                    break
                ordc = ord(c)
                if (ordc <= 0x1f):
                    break
                elif (not is_unicode) and (ordc > 0x7f):
                    needs_decode = True
                chunk_end += 1
        except IndexError:
            raise JSONDecodeError(
                "Unterminated string starting at", s, begin)
        else:
            if end == chunk_end:
                content = empty_str
            else:
                content = s[end:chunk_end]
            terminator = c
            end = chunk_end + 1
        # Content is contains zero or more unescaped string characters
        if not is_unicode and needs_decode:
            content = unicode(content, encoding)
        # Terminator is the end of string, a literal control character,
        # or a backslash denoting that an escape sequence follows
        if terminator == '"':
            if chunks is None:
                return content, end
            elif content is not empty_str:
                chunks.append(content)
            break
        if chunks is None:
            chunks = [content]
        elif content is not empty_str:
            chunks.append(content)
        if terminator != '\\':
            if strict:
                msg = "Invalid control character %r at" % (terminator,)
                raise JSONDecodeError(msg, s, end)
            else:
                chunks.append(terminator)
                continue
        try:
            esc = s[end]
        except IndexError:
            raise JSONDecodeError(
                "Unterminated string starting at", s, begin)
        # If not a unicode escape sequence, must be in the lookup table
        if esc != 'u':
            if esc == '"':
                char =  '"'
            elif esc == '\\':
                char =  '\\'
            elif esc == '/':
                char =  '/'
            elif esc == 'b':
                char =  '\b'
            elif esc == 'f':
                char =  '\f'
            elif esc == 'n':
                char =  '\n'
            elif esc == 'r':
                char =  '\r'
            elif esc == 't':
                char =  '\t'
            else:
                msg = "Invalid \\escape: " + repr(esc)
                raise JSONDecodeError(msg, s, end)
            end += 1
        else:
            # Unicode escape sequence
            esc = s[end + 1:end + 5]
            next_end = end + 5
            if len(esc) != 4:
                msg = "Invalid \\uXXXX escape"
                raise JSONDecodeError(msg, s, end)
            uni = int(esc, 16)
            # Check for surrogate pair on UCS-4 systems
            if 0xd800 <= uni <= 0xdbff and sys.maxunicode > 65535:
                msg = "Invalid \\uXXXX\\uXXXX surrogate pair"
                if not s[end + 5:end + 7] == '\\u':
                    raise JSONDecodeError(msg, s, end)
                esc2 = s[end + 7:end + 11]
                if len(esc2) != 4:
                    raise JSONDecodeError(msg, s, end)
                uni2 = int(esc2, 16)
                uni = 0x10000 + (((uni - 0xd800) << 10) | (uni2 - 0xdc00))
                next_end += 6
            char = unichr(uni)
            end = next_end
        # Append the unescaped character
        chunks.append(char)
    return empty_str.join(chunks), end

def is_whitespace(char):
    return (char == ' ') or (char == '\t') or (char == '\n') or (char == '\r')

def skip_whitespace(s, end):
    try:
        while 1:
            nextchar = s[end]
            if not is_whitespace(nextchar):
                return nextchar, end
            end += 1
    except IndexError:
        return '', len(s)

def setitem_list(lst, k, v):
    lst.append((k, v))

def setitem_dict(dct, k, v):
    dct[k] = v

def finalize_noop(dct):
    return dct

def obj_funcs(object_hook, object_pairs_hook):
    if object_pairs_hook:
        return list, setitem_list, object_pairs_hook
    elif object_hook:
        return dict, setitem_dict, object_hook
    else:
        return dict, setitem_dict, finalize_noop

def object_parser(encoding, strict, object_hook, object_pairs_hook, memo):
    new_obj, setitem, finalize = obj_funcs(object_hook, object_pairs_hook)
    def parse_object((s, end), _scan_once):
        pairs = new_obj()
        try:
            while is_whitespace(s[end]):
                end += 1
            nextchar = s[end]
            if nextchar == '}':
                return finalize(pairs), end + 1
            elif nextchar != '"':
                JSONDecodeError("Expecting property name", s, end)
        except IndexError:
            raise JSONDecodeError("Expecting property name", s, len(s))
        end += 1
        while 1:
            key, end = scanstring(s, end, encoding, strict)
            key = memo.setdefault(key, key)
            try:
                # To skip some function call overhead we optimize the fast
                # paths where the JSON key separator is ": " or just ":".
                if s[end] != ':':
                    while is_whitespace(s[end]):
                        end += 1
                    if s[end] != ':':
                        raise JSONDecodeError("Expecting : delimiter", s, end)
            except IndexError:
                raise JSONDecodeError("Expecting : delimiter", s, len(s))
            end += 1
            try:
                while is_whitespace(s[end]):
                    end += 1
            except IndexError:
                pass
            try:
                value, end = _scan_once(s, end)
            except StopIteration:
                raise JSONDecodeError("Expecting object", s, end)
            setitem(pairs, key, value)
            try:
                while is_whitespace(s[end]):
                    end += 1
                nextchar = s[end]
                end += 1
                if nextchar == '}':
                    break
                elif nextchar != ',':
                    raise JSONDecodeError("Expecting , delimiter", s, end - 1)
                while is_whitespace(s[end]):
                    end += 1
                if s[end] != '"':
                    raise JSONDecodeError("Expecting property name", s, end)
                end += 1
            except IndexError:
                raise JSONDecodeError("Expecting property name", s, len(s))
        return finalize(pairs), end
    return parse_object

def make_scanner(context):
    parse_string = scanstring
    encoding = context.encoding or DEFAULT_ENCODING
    strict = context.strict
    parse_constant = context.parse_constant
    memo = context.memo
    parse_object = object_parser(encoding, strict,
                                 context.object_hook,
                                 context.object_pairs_hook,
                                 memo)

    def parse_array((s, end), scan_once):
        values = []
        try:
            nextchar = s[end]
            if is_whitespace(nextchar):
                nextchar, end = skip_whitespace(s, end)
        except IndexError:
            nextchar = ''
        # Look-ahead for trivial empty array
        if nextchar == ']':
            return values, end + 1
        while 1:
            try:
                value, end = scan_once(s, end)
            except StopIteration:
                raise JSONDecodeError("Expecting object", s, end)
            values.append(value)
            try:
                nextchar = s[end]
            except IndexError:
                nextchar = ''
            else:
                if is_whitespace(nextchar):
                    nextchar, end = skip_whitespace(s, end)
                end += 1
            if nextchar == ']':
                break
            elif nextchar != ',':
                raise JSONDecodeError("Expecting , delimiter", s, end)

            try:
                while is_whitespace(s[end]):
                    end += 1
            except IndexError:
                pass

        return values, end

    def match_number(s, start):
        idx = start
        end_idx = len(s) - 1
        is_float = False
        if s[idx] == '-':
            # read a sign if it's there, make sure it's not the end of the
            # string
            idx += 1
            if idx > end_idx:
                raise StopIteration
        if '1' <= s[idx] <= '9':
            # read as many integer digits as we find as long as it doesn't
            # start with 0
            idx += 1
            while (idx <= end_idx) and ('0' <= s[idx] <= '9'):
                idx += 1
        elif s[idx] == '0':
            # if it starts with 0 we only expect one integer digit
            idx += 1
        else:
            # no integer digits, error
            raise StopIteration
        if (idx < end_idx) and (s[idx] == '.') and ('0' <= s[idx + 1] <= '9'):
            # if the next char is '.' followed by a digit then read all float
            # digits
            is_float = True
            idx += 2
            while (idx <= end_idx) and ('0' <= s[idx] <= '9'):
                idx += 1
        if (idx < end_idx) and (s[idx] == 'e' or s[idx] == 'E'):
            # if the next char is 'e' or 'E' then maybe read the exponent (or
            # backtrack)
            # save the index of the 'e' or 'E' just in case we need to
            # backtrack
            e_start = idx
            idx += 1
            # read an exponent sign if present
            if (idx < end_idx) and (s[idx] == '-' or s[idx] == '+'):
                idx += 1
            # read all digits
            while (idx <= end_idx) and ('0' <= s[idx] <= '9'):
                idx += 1
            # if we got a digit, then parse as float. if not, backtrack
            if '0' <= s[idx - 1] <= '9':
                is_float = True
            else:
                idx = e_start
        numstr = s[start:idx]
        if is_float:
            return context.parse_float(numstr), idx
        else:
            return context.parse_int(numstr), idx

    def _scan_once(string, idx):
        try:
            nextchar = string[idx]
        except IndexError:
            raise StopIteration

        if nextchar == '"':
            return parse_string(string, idx + 1, encoding, strict)
        elif nextchar == '{':
            return parse_object((string, idx + 1), _scan_once)
        elif nextchar == '[':
            return parse_array((string, idx + 1), _scan_once)
        elif nextchar == 'n' and string[idx:idx + 4] == 'null':
            return None, idx + 4
        elif nextchar == 't' and string[idx:idx + 4] == 'true':
            return True, idx + 4
        elif nextchar == 'f' and string[idx:idx + 5] == 'false':
            return False, idx + 5
        elif nextchar == 'N' and string[idx:idx + 3] == 'NaN':
            return parse_constant('NaN'), idx + 3
        elif nextchar == 'I' and string[idx:idx + 8] == 'Infinity':
            return parse_constant('Infinity'), idx + 8
        elif nextchar == '-' and string[idx:idx + 9] == '-Infinity':
            return parse_constant('-Infinity'), idx + 9
        else:
            return match_number(string, idx)

    def scan_once(string, idx):
        try:
            return _scan_once(string, idx)
        finally:
            memo.clear()

    return scan_once