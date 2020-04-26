'''
JAVA parser
'''

# clara lib imports
from .model import Var, Const, Op, VAR_OUT, VAR_RET
from .parser import Parser, ParseError, addlangparser, NotSupported, ParseError

import javalang


class JavaParser(Parser):

    def __init__(self, *args, **kwargs):
        super(JavaParser, self).__init__(*args, **kwargs)

        self.fncs = {}

        self.inswitch = False

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
        for e in node.body:
            self.visit(e)

    def visit_MethodDeclaration(self, node):
        name = node.name
        rtype = 'void' if node.return_type is None else '%s' % node.return_type

        params = []

        for p in node.parameters:
            (param_name, param_modifier, param_type) = self.visit(p)

            if isinstance(param_modifier, set):
                param_type = param_type + '[]'

            params.append((param_name, param_type))

        self.addfnc(name, params, rtype)

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
        return node.name, node.modifiers, node.type.name

    def visit_VariableDeclaration(self, node):
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

    def visit_LocalVariableDeclaration(self, node):
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

    def visit_VariableDeclarator(self, node):
        init = self.visit_expr(node.initializer)

        return node.name, init

    def visit_BasicType(self, node):
        return node.name

    def visit_ArrayInitializer(self, node):
        exprs = list(map(self.visit_expr, node.initializers or []))
        return Op('ArrayInit', *exprs, line=node.position.line)

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

        if node.qualifier == 'System.out' and node.member == 'println':
            self.visit_println(node, args)

        elif node.member in self.fncs.keys():
            expr = Var(node.member, line=node.position.line)
            return Op('FuncCall', expr, *args, line=node.position.line)

        else:
            raise NotSupported(
                "Unsupported function call: '%s'" % (node.member,), line=node.position.line)

    def visit_println(self, node, args):
        if len(args) == 0:
            self.addwarn("'System.out.println' with zero args at line %s" % (
                node.position.line,))
            fmt = Const('?', line=node.position.line)
        else:
            if isinstance(args[0], Const):
                fmt = args[0]
                args = args[1:]
            else:
                self.addwarn(
                    "First argument of 'System.out.println' at lines %s should be a format" % (node.position.line,))
                fmt = Const('?', line=node.position.line)

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
        expr = Var(node.member, line=node.position.line)

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

        if node.postfix_operators:
            if node.postfix_operators[0] in ['--', '++']:
                if not isinstance(expr, Var):
                    raise NotSupported('++/-- supported only for Vars',
                                       line=node.position.line)

                self.addexpr(expr.name,
                             Op(node.postfix_operators[0][1], expr.copy(), Const('1'), line=node.position.line))

        return expr

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

        self.addexpr(lval.name, rvalue.copy(), )

        return exprl

    def visit_ArraySelector(self, node):
        return self.visit_expr(node.index)

    def visit_BinaryOperation(self, node):
        return Op(node.operator, self.visit_expr(node.operandl), self.visit_expr(node.operandr))

    def visit_TernaryExpression(self, node):
        print(node.__repr__())
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
