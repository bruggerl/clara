'''
JAVA parser
'''

# clara lib imports
from .model import Var, Const, Op, VAR_OUT, VAR_RET, VAR_IN
from .parser import Parser, addlangparser, NotSupported, ParseError

import javalang


class JavaParser(Parser):
    MATH_FNCS = {'pow', 'log10', 'floor', 'ceil', 'abs', 'floorDiv', 'max'}

    TYPES_CLASSES = {'String', 'Integer', 'Double', 'Float', 'Character'}
    TYPES_FNCS = {'valueOf', 'parseInt', 'isDigit', 'toString', 'isLetter', 'isSpace'}

    SCANNER_FNCS = {'next', 'nextLine', 'nextInt', 'nextDouble', 'nextFloat', 'hasNext',
                    'hasNextInt', 'close'}

    STRING_FNCS = {'length', 'substring', 'concat', 'charAt', 'equals', 'isEmpty',
                   'startsWith', 'endsWith', 'replace', 'replaceAll', 'replaceFirst',
                   'indexOf', 'contains'}

    NOTOP = '!'
    OROP = '||'
    ANDOP = '&&'

    def __init__(self, *args, **kwargs):
        super(JavaParser, self).__init__(*args, **kwargs)

        self.fncs = {}

        self.inswitch = False

        self.fnc_names = []

        self.calling_fncs = {}  # fnc name -> [calling fnc names] (needed if method is called before declaration)

    def parse(self, code):
        """
        Parses JAVA code
        """

        try:
            ast = javalang.parse.parse(code)
        except javalang.parser.JavaSyntaxError as e:
            print(e.description)
            raise ParseError(e.description)

        self.visit(ast)

    def visit_CompilationUnit(self, node):
        for t in node.types:
            self.visit(t)

    def visit_ClassDeclaration(self, node):
        self.fnc_names = [e.name for e in node.body if e.__class__.__name__ == 'MethodDeclaration']
        for fnc in self.fnc_names:
            self.calling_fncs[fnc] = []

        for e in node.body:
            self.visit(e)

    def visit_ClassCreator(self, node):
        type = self.visit(node.type)
        exprs = []

        for decl in node.arguments:
            expr = self.visit_expr(decl)
            exprs.append(expr)

        return Op('ClassCreate', *exprs, type=type)

    def visit_MethodDeclaration(self, node):
        name = node.name
        rtype = 'void' if node.return_type is None else node.return_type.name

        params = []

        for p in node.parameters:
            param_name, param_type = self.visit(p)

            params.append((param_name, param_type))

        self.addfnc(name, params, rtype)
        self.fnc.add_calling_fncs(self.calling_fncs[name])

        for v, t in params:
            self.addtype(v, t)

        self.addloc(
            desc="at the beginning of function '%s'" % name)

        for b in node.body:
            res = self.visit(b)

            if isinstance(res, Op) and res.name == 'FuncCall':
                self.addexpr('_', res)

        self.endfnc()

    def visit_FormalParameter(self, node):
        return node.name, self.visit(node.type)

    def visit_FieldDeclaration(self, node):
        type = self.visit(node.type)

        for decl in node.declarators:
            name, init = self.visit(decl)

            if isinstance(init, Op) and (init.name == 'ArrayCreate' or init.name == 'ArrayInit'):
                type += '[]'

            try:
                self.addtype(name, type)
            except AssertionError:
                self.addwarn("Ignored global definition '%s' on line %s." % (
                    name, node.position,))
                return

            self.addexpr(name, init)

    def visit_VariableDeclaration(self, node):
        type = self.visit(node.type)

        for decl in node.declarators:
            name, init = self.visit(decl)

            if isinstance(init, Var):
                init.type = type

            if isinstance(init, Op) and (init.name == 'ArrayCreate' or init.name == 'ArrayInit'):
                type += '[]'

            try:
                self.addtype(name, type)
            except AssertionError:
                self.addwarn("Ignored global definition '%s' on line %s." % (
                    name, node.position,))
                return

            self.addexpr(name, init)

    def visit_LocalVariableDeclaration(self, node):
        type = self.visit(node.type)
        varin = False

        for decl in node.declarators:
            name, init = self.visit(decl)

            if isinstance(init, Var):
                init.type = type

            if isinstance(init, Op):
                if init.name == 'ArrayCreate' or init.name == 'ArrayInit':
                    type += '[]'

                elif init.name == 'ListHead':
                    varin = True

            try:
                self.addtype(name, type)
            except AssertionError:
                self.addwarn("Ignored global definition '%s' on line %s." % (
                    name, node.position,))
                return

            self.addexpr(name, init)

            if varin:
                self.addexpr(VAR_IN, Op('ListTail', Var(VAR_IN), line=node.position.line))

    def visit_VariableDeclarator(self, node):
        init = self.visit_expr(node.initializer, allowlist=True)

        return node.name, init

    def visit_BasicType(self, node):
        return node.name + '[]' * len(node.dimensions)

    def visit_TypeArgument(self, node):
        return self.visit(node.type)

    def visit_ArrayInitializer(self, node):
        exprs = list(map(self.visit_expr, node.initializers or []))
        return Op('ArrayInit', *exprs)

    def visit_ArrayCreator(self, node):
        if len(node.dimensions) > 1:
            raise NotSupported('Double Array')

        dim = self.visit_expr(node.dimensions[0])

        if node.initializer is not None:
            raise NotSupported('Array Init and Create together')

        return Op('ArrayCreate', dim)

    def visit_BlockStatement(self, node):
        if node.statements:
            for statement in node.statements:
                res = self.visit(statement)

                if isinstance(res, Op) and res.name == 'MethodInvocation':
                    self.addexpr('_', res)

    def visit_StatementExpression(self, node):
        return self.visit(node.expression)

    def visit_MethodInvocation(self, node):
        # Parse args
        args = list(map(self.visit_expr, node.arguments))
        if node.qualifier.startswith('System'):
            if node.member == 'println' or node.member == 'print':
                self.visit_println(node, args)

            elif node.member == 'printf':
                self.visit_printf(node, args)

            elif node.member == 'exit':
                return Op(node.member, *args, line=node.position.line)

        elif node.qualifier == 'Math' and node.member in self.MATH_FNCS:
            return Op(node.member, *args, line=node.position.line)

        elif node.qualifier in self.TYPES_CLASSES and node.member in self.TYPES_FNCS:
            return Op(node.member, *args, line=node.position.line)

        elif node.member in self.fnc_names:
            expr = Var(node.member, line=node.position.line)

            called_fnc = self.fncs.get(node.member, None)
            if called_fnc and self.fnc:
                called_fnc.add_calling_fncs([self.fnc.name])
            elif not called_fnc and self.fnc:
                if self.fnc.name not in self.calling_fncs[node.member]:
                    self.calling_fncs[node.member].append(self.fnc.name)

            return Op('FuncCall', expr, *args, line=node.position.line)

        elif self.fnc.gettype(node.qualifier) == 'String' and node.member in self.STRING_FNCS:
            expr = Var(node.qualifier, line=node.position.line)
            return Op(node.member, expr, *args, line=node.position.line)

        elif self.fnc.gettype(node.qualifier) == 'Scanner' and node.member in self.SCANNER_FNCS:
            if node.member.startswith('next'):
                t = node.member.split('next')[1].lower()

                if t == '' or t == 'line':
                    t = '*'

                rexpr = Op('ListHead', Const(t), Var(VAR_IN), line=node.position.line)

                return rexpr
            else:
                return Op(node.member, *args, line=node.position.line)

        else:
            raise NotSupported(
                "Unsupported function call: '%s'" % (node.member,), line=node.position.line)

    def visit_println(self, node, args):
        values_model = list(map(self.visit_expr, node.arguments))
        expr = Op('StrAppend', Var(VAR_OUT), *values_model, line=node.position.line)
        self.addexpr(VAR_OUT, expr)

    def visit_printf(self, node, args):
        '''
                printf function call
                '''

        # Extract format and args
        if len(args) == 0:
            self.addwarn("'printf' with zero args at line %s" % (
                node.position.line,))
            fmt = Const('?', line=node.position.line)
        else:
            if isinstance(args[0], Const):
                fmt = args[0]
                args = args[1:]
            else:
                self.addwarn("First argument of 'printf' at lines %s should \
        be a format" % (node.position.line,))
                fmt = Const('?', line=node.position.line)

        fmt.value = fmt.value.replace('%lf', '%f')
        fmt.value = fmt.value.replace('%ld', '%d')
        fmt.value = fmt.value.replace('%lld', '%d')

        expr = Op('StrAppend', Var(VAR_OUT),
                  Op('StrFormat', fmt, *args, line=node.position.line),
                  line=node.position.line)
        self.addexpr(VAR_OUT, expr)

    def visit_Literal(self, node):
        expr = Const('{}'.format(node.value), line=node.position.line)

        if node.prefix_operators:
            if node.prefix_operators[0] in ['--', '++']:
                raise NotSupported('++/-- only supported for Vars')
            elif node.prefix_operators[0] == '-':
                return Op('-', expr, line=node.position.line)

        if node.postfix_operators:
            if node.prefix_operators[0] in ['--', '++']:
                raise NotSupported('++/-- only supported for Vars')

        return expr

    def visit_MemberReference(self, node):
        if node.qualifier == 'System' and node.member == 'in':
            rexpr = Op('ListHead', Const('*'), Var(VAR_IN), line=node.position.line)
            return rexpr

        expr = Var(node.member, line=node.position.line, type=self.fnc.gettype(node.member))

        if node.selectors:
            if len(node.selectors) > 1:
                raise NotSupported('Double Array', line=node.position.line)

            expr = Op('[]', expr, self.visit_expr(node.selectors[0]), line=node.position.line)

        if node.prefix_operators:
            if node.prefix_operators[0] in ['--', '++']:
                if not isinstance(expr, Var):
                    raise NotSupported('++/-- supported only for Vars',
                                       line=node.position.line)

                self.addexpr(expr.name,
                             Op(node.prefix_operators[0][1], expr.copy(), Const('1'), line=node.position.line))

            elif node.prefix_operators[0] == '-':
                return Op('-', expr, line=node.position.line)

            elif node.prefix_operators[0] == '!':
                return Op('!', expr, line=node.position.line)

        if node.postfix_operators:
            if node.postfix_operators[0] in ['--', '++']:
                if not isinstance(expr, Var):
                    raise NotSupported('++/-- supported only for Vars',
                                       line=node.position.line)

                self.addexpr(expr.name,
                             Op(node.postfix_operators[0][1], expr.copy(), Const('1'), line=node.position.line))

        return expr

    def visit_ReferenceType(self, node):
        return node.name

    def visit_Assignment(self, node):
        exprl = self.visit_expr(node.expressionl)
        rvalue = self.visit(node.value)

        if node.type == '=':
            pass
        elif len(node.type) == 2 and node.type[1] == '=':
            rvalue = Op(node.type[0], exprl.copy(), rvalue)
        else:
            raise NotSupported("Assignment operator: '%s'" % (node.type,))

        # Distinguish lvalue (ID and Array)
        if isinstance(exprl, Var):
            lval = exprl

        elif (isinstance(exprl, Op) and exprl.name == '[]' and
              isinstance(exprl.args[0], Var)):
            rvalue = Op('ArrayAssign', exprl.args[0].copy(),
                        exprl.args[1].copy(), rvalue)
            lval = exprl.args[0]

        else:
            raise NotSupported("Assignment exprl '%s'" % (exprl,))

        if rvalue:
            self.addexpr(lval.name, rvalue.copy(), )

            if isinstance(rvalue, Op) and rvalue.name == 'ListHead':
                self.addexpr(VAR_IN, Op('ListTail', Var(VAR_IN)))

        return exprl

    def visit_ArraySelector(self, node):
        return self.visit_expr(node.index)

    def visit_BinaryOperation(self, node):
        if node.operator == '+':  # string concatenation
            l = self.visit_expr(node.operandl)
            r = self.visit_expr(node.operandr)

            if (isinstance(l, Const) and len(l.value) >= 2 and l.value[0] == l.value[-1] == '"') or \
                    (isinstance(l, Var) and self.fnc.gettype(l.name) == 'String') or \
                    (isinstance(l, Op) and l.name == 'StrAppend'):
                return Op('StrAppend', l, r)

            if (isinstance(r, Const) and len(r.value) >= 2 and r.value[0] == r.value[-1] == '"') or \
                    (isinstance(r, Var) and self.fnc.gettype(r.name) == 'String') or \
                    (isinstance(r, Op) and r.name == 'StrAppend'):
                return Op('StrAppend', l, r)

        return Op(node.operator, self.visit_expr(node.operandl), self.visit_expr(node.operandr))

    def visit_TernaryExpression(self, node):
        cond = self.visit_expr(node.condition)

        n = self.numexprs()
        ift = self.visit_expr(node.if_true)
        iff = self.visit_expr(node.if_false)

        if self.numexprs() > n:
            self.rmlastexprs(num=self.numexprs() - n)
            return self.visit_if(node, node.condition, node.if_true, node.if_false)

        return Op('ite', cond, ift, iff)

    def visit_IfStatement(self, node):
        self.visit_if(node, node.condition, node.then_statement, node.else_statement)

    def visit_SwitchStatement(self, node):
        n = len(node.cases)

        def convert(i):
            if i >= n:
                return

            item = node.cases[i]
            # Item statement
            stmt = item.statements

            if i == (n - 1) and len(item.case) == 0:
                return stmt

            expr = item.case[0]

            if isinstance(item, javalang.parser.tree.SwitchStatementCase):
                next = convert(i + 1)

                ifcond = javalang.parser.tree.BinaryOperation(operator='==', operandl=node.expression,
                                                              operandr=expr)
                ifstmt = javalang.parser.tree.IfStatement(condition=ifcond, then_statement=stmt,
                                                          else_statement=next)

                return ifstmt

        stmt = convert(0)
        if stmt:
            insw = self.inswitch
            self.inswitch = True

            res = self.visit(stmt)

            self.inswitch = insw

            return res

    def visit_ForStatement(self, node):
        if self.inswitch:
            raise NotSupported("Loop inside switch", line=node.position.line)

        self.visit_loop(node, node.control.init, node.control.condition,
                        node.control.update, node.body, False, 'for')

    def visit_WhileStatement(self, node):
        if self.inswitch:
            raise NotSupported("Loop inside switch", line=node.position.line)

        self.visit_loop(node, None, node.condition, None, node.body,
                        False, 'while')

    def visit_DoStatement(self, node):
        if self.inswitch:
            raise NotSupported("Loop inside switch", line=node.position.line)

        self.visit_loop(node, None, node.condition, None, node.body,
                        True, 'do-while')

    def visit_ContinueStatement(self, node):
        if self.nobcs:
            return

        # Find loop
        lastloop = self.lastloop()
        if not lastloop:
            self.addwarn("'continue' outside loop at line %s", node.position.line)
            return

        # Add new location and jump to condition location
        self.hasbcs = True
        preloc = self.loc
        self.loc = self.addloc(
            desc="after 'continue' statement at line %s" % (
                node.position.line,))
        self.addtrans(preloc, True, lastloop[2] if lastloop[2] else lastloop[0])

    def visit_BreakStatement(self, node):
        if self.inswitch or self.nobcs:
            return

        # Find loop
        lastloop = self.lastloop()

        if not lastloop:
            self.addwarn("'break' outside loop at line %s", node.position.line)
            return

        # Add new location and jump to exit location
        self.hasbcs = True
        preloc = self.loc
        self.loc = self.addloc(
            desc="after 'break' statement at line %s" % (
                node.position.line,))

        self.addtrans(preloc, True, lastloop[1])

    def visit_ReturnStatement(self, node):
        expr = self.visit_expr(node.expression)

        if not expr:
            expr = Const('top', line=node.position.line)

        self.addexpr(VAR_RET, expr)

    def visit_AssertStatement(self, node):
        return

    def visit_Statement(self, node):
        return

    def visit_Cast(self, node):
        to_type = self.visit(node.type)
        expr = self.visit_expr(node.expression)
        return Op('cast', Const(to_type), expr)

    def visit_list(self, node):
        for child in node:
            self.visit(child)

    def getline(self, node):
        if isinstance(node, list):
            if len(node):
                return self.getline(node[0])
            else:
                return

        if node.position:
            return node.position.line

        # position property is not set in all nodes
        return 1


# Register JAVA parser
addlangparser('java', JavaParser)
