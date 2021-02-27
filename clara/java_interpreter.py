"""
JAVA interpreter
"""

# clara lib imports
from .interpreter import Interpreter, addlanginter, RuntimeErr, UndefValue
from .model import Var, VAR_IN

import math
import re


def libcall(*args):
    '''
    Decorator for library calls
    - args is a list of types of arguments
    '''

    def dec(fun):  # fun - is an original function to call

        # Wrapper instead of real function (calls real function inside)
        def wrap(self, f, mem):

            # First check number of arguments
            if len(args) != len(f.args):
                raise RuntimeErr("Expected '%d' args in '%s', got '%d'" % (
                    len(args), f.name, len(f.args)))

            # Evaluate args
            fargs = [self.execute(x, mem) for x in f.args]

            # Convert args
            nargs = []
            for a, t in zip(fargs, args):
                nargs.append(self.convert(a, t))

            # Call original function
            return fun(self, *nargs)

        return wrap

    return dec


class JavaInterpreter(Interpreter):
    BINARY_OPS = {'+', '-', '*', '/', '%', '<', '<=', '>', '>=', '==', '!=',
                  '^', '&', '!', '&&', '||', '<<', '>>'}

    BINARY_BOOL_OPS = {'==', '!=', '&&', '||', '<', '<=', '>', '>='}

    UNARY_OPS = {'!', '-', '+'}

    def execute_Const(self, c, mem):
        if c.value == 'null':
            return None

        # Undef
        if c.value == '?':
            return UndefValue()

        # String
        if len(c.value) >= 2 and c.value[0] == c.value[-1] == '"':
            return str(c.value[1:-1])

        # Char
        if len(c.value) >= 3 and c.value[0] == c.value[-1] == "'":
            return str(c.value[1:-1])

        # Bool
        if c.value in ('true', 'false'):
            return c.value == 'true'

        # Integer
        try:
            return int(c.value)
        except ValueError:
            pass

        # Float
        try:
            return float(c.value)
        except ValueError:
            pass

        assert False, 'Unknown constant: %s' % (c.value,)

    def execute_UnaryOp(self, op, x, mem):

        x = self.tonumeric(self.execute(x, mem))

        if op == '-':
            res = -x
        elif op == '+':
            res = +x
        elif op == '!':
            res = not x
        else:
            assert False, "Unknown unary op: '%s'" % (op,)

        return self.tonumeric(res)

    def execute_BinaryOp(self, op, x, y, mem):
        t = None

        if isinstance(x, Var):
            t = x.type

        x = self.execute(x, mem)

        if x and not isinstance(x, list) and not isinstance(x, str):
            x = self.tonumeric(x)

        # Special case for short-circut
        if op in ['&&', '||']:

            if op == '||' and x:
                return x

            if op == '&&' and (not x):
                return 0

            return self.tonumeric(self.execute(y, mem))

        y = self.execute(y, mem)
        if y and not isinstance(y, list) and not isinstance(y, str):
            y = self.tonumeric(y)

        x, y = self.togreater(x, y)

        if isinstance(x, str) and (isinstance(y, int) or isinstance(y, float)):
            if len(x) == 1:
                x = ord(x)

        if isinstance(y, str) and (isinstance(x, int) or isinstance(x, float)):
            if len(y) == 1:
                y = ord(y)

        if op == '+':
            res = x + y
        elif op == '-':
            res = x - y
        elif op == '*':
            res = x * y
        elif op == '/':
            res = x / y
        elif op == '%':
            res = x % y
        elif op == '==':
            res = x == y
        elif op == '!=':
            res = x != y
        elif op == '<':
            res = x < y
        elif op == '<=':
            res = x <= y
        elif op == '>':
            res = x > y
        elif op == '>=':
            res = x >= y
        elif op == '^':
            res = x ^ y
        elif op == '&':
            res = x & y
        elif op == '|':
            res = x | y
        elif op == '<<':
            res = x << y
        elif op == '>>':
            res = x >> y
        else:
            assert False, 'Unknown binary op: %s' % (op,)

        if isinstance(x, int) and op not in self.BINARY_BOOL_OPS:
            if t and t != 'int':
                return res

            return int(res)

        return res

    def execute_cast(self, c, mem):
        t = c.args[0].value
        x = self.execute(c.args[1], mem)

        return self.convert(x, t)

    def execute_ClassCreate(self, cc, mem):
        if cc.type != 'Scanner':
            raise NotImplementedError('Constructors for other classes than Scanner not supported')

        return cc.type

    def execute_ArrayCreate(self, ac, mem):
        x = int(self.tonumeric(self.execute(ac.args[0], mem)))
        return [None for _ in range(x)]

    def execute_ArrayInit(self, ai, mem):
        return [self.execute(x, mem) for x in ai.args]

    def execute_ArrayAssign(self, aa, mem):
        a = self.execute(aa.args[0], mem)
        if not isinstance(a, list):
            raise RuntimeErr("Expected 'list', got '%s'" % (a,))
        a = list(a)

        i = int(self.tonumeric(self.execute(aa.args[1], mem)))
        if i < 0 or i >= len(a):
            raise RuntimeErr("Array index out of bounds: %d" % (i,))

        v = self.execute(aa.args[2], mem)

        a[i] = v

        return a

    def execute_ArrayIndex(self, ai, mem):
        a = self.execute(ai.args[0], mem)
        if not isinstance(a, list):
            raise RuntimeErr("Expected 'list', for '%s'" % (a,))

        i = int(self.tonumeric(self.execute(ai.args[1], mem)))
        if i < 0 or i >= len(a):
            raise RuntimeErr("Array index out of bounds: %d" % (i,))

        return a[i]

    def execute_hasNext(self, op, mem):
        if mem[VAR_IN] and isinstance(mem[VAR_IN], list) and len(mem[VAR_IN]) > 0:
            return True
        else:
            return False

    def execute_hasNextInt(self, op, mem):
        if mem[VAR_IN] and isinstance(mem[VAR_IN], list) and len(mem[VAR_IN]) > 0:
            if isinstance(mem[VAR_IN][0], int):
                return True
        else:
            return False

    def execute_length(self, op, mem):
        v = self.execute(op.args[0], mem)
        return len(v)

    def execute_substring(self, op, mem):
        v = self.execute(op.args[0], mem)
        i = self.execute(op.args[1], mem)

        if len(op.args) > 2:
            j = self.execute(op.args[2], mem)
            return v[i:j]

        return v[i:]

    def execute_matches(self, op, mem):
        s = self.execute(op.args[0], mem)
        r = self.execute(op.args[1], mem)
        regex = re.compile(r)

        return regex.match(s) is not None

    def execute_concat(self, op, mem):
        a = self.execute(op.args[0], mem)
        b = self.execute(op.args[1], mem)

        return a + b

    def execute_parseInt(self, op, mem):
        v = self.execute(op.args[0], mem)
        return int(v)

    def execute_IntegertoString(self, op, mem):
        v = self.execute(op.args[0], mem)
        return str(v)

    def execute_IntegervalueOf(self, op, mem):
        v = self.execute(op.args[0], mem)
        return int(v)

    def execute_sum(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)

        return u + v

    def execute_valueOf(self, op, mem):
        v = self.execute(op.args[0], mem)
        return str(v)

    def execute_charAt(self, op, mem):
        v = self.execute(op.args[0], mem)
        i = self.execute(op.args[1], mem)
        return v[i]

    def execute_equals(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)

        return u == v

    def execute_isEmpty(self, op, mem):
        v = self.execute(op.args[0], mem)

        return True if len(v) == 0 else False

    def execute_startsWith(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)

        return u.startswith(v)

    def execute_endsWith(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)

        return u.endswith(v)

    def execute_replace(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)
        w = self.execute(op.args[2], mem)

        return u.replace(v, w)

    def execute_replaceAll(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)
        w = self.execute(op.args[2], mem)

        return u.replace(v, w)

    def execute_replaceFirst(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)
        w = self.execute(op.args[2], mem)

        return u.replace(v, w, 1)

    def execute_indexOf(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)

        try:
            return u.index(v)
        except ValueError:
            return -1

    def execute_contains(self, op, mem):
        u = self.execute(op.args[0], mem)
        v = self.execute(op.args[1], mem)

        return v in u

    def execute_isDigit(self, op, mem):
        v = self.execute(op.args[0], mem)

        return v.isdigit()

    def execute_isLetter(self, op, mem):
        v = self.execute(op.args[0], mem)

        return v.isalpha()

    def execute_isSpace(self, op, mem):
        v = self.execute(op.args[0], mem)

        return v.isspace()

    def execute_toString(self, op, mem):
        return self.execute(op.args[0], mem)

    def execute_ArraystoString(self, op, mem):
        arr = self.execute(op.args[0], mem)
        return '[' + ', '.join(str(a) for a in arr) + ']'

    def execute_Arraysequals(self, op, mem):
        arr1 = self.execute(op.args[0], mem)
        arr2 = self.execute(op.args[1], mem)

        return arr1 == arr2

    def execute_copyOfRange(self, op, mem):
        arr = self.execute(op.args[0], mem)
        start = self.execute(op.args[1], mem)
        end = self.execute(op.args[2], mem)

        return arr[start:end]

    def execute_copyOf(self, op, mem):
        arr = self.execute(op.args[0], mem)
        length = self.execute(op.args[1], mem)

        if len(arr) < length:
            return arr + (length - len(arr)) * [0]
        else:
            return arr[:length]

    def execute_clone(self, op, mem):
        return self.execute(op.args[0], mem)

    def execute_sort(self, op, mem):
        arr = self.execute(op.args[0], mem)

        return arr.sort()

    @libcall('float')
    def execute_floor(self, x):
        return math.floor(x)

    @libcall('float')
    def execute_ceil(self, x):
        if x == float('-inf'):
            return x
        return math.ceil(x)

    @libcall('float', 'float')
    def execute_pow(self, x, y):
        try:
            return math.pow(x, y)
        except OverflowError:
            return float('inf')

    @libcall('float')
    def execute_log10(self, x):
        if x == 0:
            return float('-inf')
        return math.log(x, 10)

    @libcall('float')
    def execute_abs(self, x):
        return abs(x)

    @libcall('float', 'float')
    def execute_max(self, x, y):
        return max(x, y)

    @libcall('float', 'float')
    def execute_min(self, x, y):
        return min(x, y)

    def execute_floorDiv(self, op, mem):
        x = self.execute(op.args[0], mem)
        y = self.execute(op.args[1], mem)
        return x // y

    def execute_signum(self, op, mem):
        x = self.execute(op.args[0], mem)

        if x < 0:
            return -1
        else:
            return 1

    def tonumeric(self, v):
        if v in [True, False]:
            return 1 if v else 0

        if not isinstance(v, (int, float)):
            raise RuntimeErr("Non-numeric value: '%s'" % (v,))

        return v

    def togreater(self, x, y):
        if isinstance(x, float):
            return x, float(y)

        if isinstance(y, float):
            return float(x), y

        return x, y

    def convert(self, val, t):
        if isinstance(val, UndefValue):
            return val

        if val is None:
            return None

        if t == 'int':
            if val in [True, False]:
                val = 1 if val else 0
            elif isinstance(val, str):
                return ord(val)
            return int(val)

        if t == 'float':
            if val in [True, False]:
                val = 1.0 if val else 0.0
            return float(val)

        if t == 'char':
            if isinstance(val, int):
                return chr(val)
            if not isinstance(val, str) or len(val) > 2:
                raise RuntimeErr("Expected char, got '%s'" % (val,))

            if val == '\\\\':
                val = '\\'

            return val[0]

        if t.endswith('[]'):
            st = t[:-2]
            if isinstance(val, list):
                return [x if x is None else self.convert(x, st) for x in val]
            raise RuntimeErr("Expected list, got '%s'" % (val,))

        return val


# Register JAVA interpreter
addlanginter('java', JavaInterpreter)
