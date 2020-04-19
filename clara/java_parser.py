'''
JAVA parser
'''

# clara lib imports
from .model import Var, Const, Op, VAR_OUT
from .parser import Parser, ParseError, addlangparser, NotSupported, ParseError

import javalang


class JavaParser(Parser):

    def __init__(self, *args, **kwargs):
        super(JavaParser, self).__init__(*args, **kwargs)

        self.fncs = {}

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
                    name, node.coord.line,))
                return

            self.addexpr(name, init)

    def visit_VariableDeclarator(self, node):
        init = self.visit_expr(node.initializer)

        return node.name, init

    def visit_BasicType(self, node):
        return node.name

    def visit_ArrayInitializer(self, node):
        exprs = list(map(self.visit_expr, node.initializers or []))
        return Op('ArrayInit', *exprs, line=node.position)

    def visit_ArrayCreator(self, node):
        if len(node.dimensions) > 1:
            raise NotSupported('Double Array', line=node.position)

        dim = self.visit_expr(node.dimensions[0])

        if node.initializer is not None:
            raise NotSupported('Array Init and Create together', line=node.position)

        return Op('ArrayCreate', dim, line=node.position)

    def visit_StatementExpression(self, node):
        return self.visit(node.expression)

    def visit_MethodInvocation(self, node):
        # Parse args
        args = list(map(self.visit_expr, node.arguments))

        if node.qualifier == 'System.out' and node.member == 'println':
            self.visit_println(node, args)

        elif node.member in self.fncs.keys():
            expr = Var(node.member, line=node.position)
            return Op('FuncCall', expr, *args, line=node.position)

        else:
            raise NotSupported(
                "Unsupported function call: '%s'" % (node.member,), line=node.position)

    def visit_println(self, node, args):
        if len(args) == 0:
            self.addwarn("'System.out.println' with zero args at line %s" % (
                node.position,))
            fmt = Const('?', line=node.position)
        else:
            if isinstance(args[0], Const):
                fmt = args[0]
                args = args[1:]
            else:
                self.addwarn("First argument of 'System.out.println' at lines %s should be a format" % (node.position,))
                fmt = Const('?', line=node.position)

        expr = Op('StrAppend', Var(VAR_OUT),
                  Op('StrFormat', fmt, *args, line=node.position),
                  line=node.position)
        self.addexpr(VAR_OUT, expr)

    def visit_Literal(self, node):
        expr = Const('{}'.format(node.value), line=node.position)

        if node.prefix_operators:
            if node.prefix_operators[0] in ['--', '++']:
                raise NotSupported('++/-- only supported for Vars')
            elif node.prefix_operators[0] == '-':
                return Op('-', expr, line=node.position)

        if node.postfix_operators:
            if node.prefix_operators[0] in ['--', '++']:
                raise NotSupported('++/-- only supported for Vars')

        return expr

    def visit_MemberReference(self, node):
        print(node.__repr__())
        expr = Var(node.member, line=node.position)

        if node.prefix_operators:
            if node.prefix_operators[0] in ['--', '++']:
                self.addexpr(expr.name, Op(node.prefix_operators[0][1], expr.copy(), Const('1'), line=node.position))
            elif node.prefix_operators[0] == '-':
                return Op('-', expr, line=node.position)

        if node.postfix_operators:
            if node.postfix_operators[0] in ['--', '++']:
                self.addexpr(expr.name, Op(node.postfix_operators[0][1], expr.copy(), Const('1'), line=node.position))

        return expr

    def visit_Assignment(self, node):
        exprl = self.visit_expr(node.expressionl)
        value = self.visit(node.value)

        if node.type == '=':
            pass
        elif len(node.type) == 2 and node.type[1] == '=':
            value = Op(node.type[0], exprl.copy(), value, line=value.position)
        else:
            raise NotSupported("Assignment operator: '%s'" % (node.type,), line=node.position)

        self.addexpr(exprl.name, value.copy(),)

        return exprl


# Register JAVA parser
addlangparser('java', JavaParser)
