import ast
import isort
import autoimport
   
class CodeUtils:

    class NormalizedSubprocessTransformer(ast.NodeTransformer):

        def __init__(self):
            self.variable_dict = {}

        def visit_Assign(self, node):
            if isinstance(node.value, (ast.List, ast.Constant, ast.FormattedValue, ast.JoinedStr)):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.variable_dict[target.id] = type(node.value)
            self.generic_visit(node)
            return node

        # Change from 'from subprocess import ...' to 'import subprocess'
        def visit_ImportFrom(self, node):
            if node.module == "subprocess":
                return [ast.Import(names=[ast.alias(name='subprocess', asname=None)])]
            
            return node
        
        # Remove os.chdir
        def visit_Expr(self, node): 
            self.generic_visit(node)
            if isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "chdir":
                    if isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "os":
                        return None
            return node
        
        
        # Change os.system() to subprocess.run()
        # Change other instances of subprocess to subprocess.run()
        def visit_Call(self, node):
            self.generic_visit(node)
            # os.system()
            if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":

                    new_node = self.createSimpleSubprocessRunNode(node.args[0], True)
                    return ast.copy_location(new_node, node)

            # Other instances of subprocess
            elif (isinstance(node.func, ast.Name) and node.func.id in ["check_call", "call", "run", "check_output"]) or \
            (isinstance(node.func, ast.Attribute) and node.func.attr in ["check_call", "call", "run", "check_output"] and 
            isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
                
                if (isinstance(node.args[0], ast.List) and 
                    node.args[0].elts and 
                    isinstance(node.args[0].elts[0], ast.Constant) and 
                    node.args[0].elts[0].s == 'which'):
                    return node
                
                use_shell = False

                if isinstance(node.args[0], ast.Name) and node.args[0].id in self.variable_dict:
                    var_type = self.variable_dict[node.args[0].id]
                    if var_type == ast.List:
                        use_shell = False
                    elif var_type in [ast.Constant, ast.FormattedValue, ast.JoinedStr]:
                        use_shell = True
                    else:
                        print(f"[INFO] Unknown node: {ast.dump(node)}")
                        return node
                elif isinstance(node.args[0], (ast.Constant, ast.FormattedValue, ast.JoinedStr)):
                    use_shell = True
                else:
                    use_shell = any(kw.arg == 'shell' and self.isTrue(kw.value) for kw in node.keywords)

                new_node = self.createSimpleSubprocessRunNode(node.args[0], use_shell)
                return ast.copy_location(new_node, node)
            
            return node
        
        def createSimpleSubprocessRunNode(self, first_arg, use_shell):

            return ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id='subprocess', ctx=ast.Load()), 
                    attr='run', 
                    ctx=ast.Load()
                ),
                args=[first_arg],
                keywords=[ast.keyword(arg='shell', value=ast.Constant(value=use_shell))]
            )
        
        def isTrue(self, node):
            return isinstance(node, ast.Constant) and node.value is True

    # Remove try...except block to catch the exceptions in exec()
    class RemoveTryBlockAroundSubprocessTransformer(ast.NodeTransformer):

        def visit_Try(self, node):
            self.generic_visit(node)

            if any(isinstance(stmt, ast.Expr) and self.isSubprocessRun(stmt.value) for stmt in node.body):

                return node.body
            return node
        
        def isSubprocessRun(self, node):
            return (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and
                    node.func.attr == 'run' and
                    isinstance(node.func.value, ast.Name) and
                    node.func.value.id == 'subprocess')
        
    class ModifySubprocessRunTransformer(ast.NodeTransformer):

        def visit_Call(self, node): 
            self.generic_visit(node)
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess" and node.func.attr == "run":

                shell_arg = any(kw.arg == 'shell' and self.isTrue(kw.value) for kw in node.keywords)

                new_node = self.createSubprocessRunNode(node.args[0], shell_arg)
                return ast.copy_location(new_node, node)
            return node

        def createSubprocessRunNode(self, first_arg, use_shell):
            keywords = [
                ast.keyword(arg='shell', value=ast.Constant(value=use_shell)),
                ast.keyword(arg='stdout', value=ast.Attribute(value=ast.Name(id='subprocess', ctx=ast.Load()), attr='DEVNULL')),
                ast.keyword(arg='stderr', value=ast.Attribute(value=ast.Name(id='subprocess', ctx=ast.Load()), attr='DEVNULL')),
                ast.keyword(arg='timeout', value=ast.Constant(value=5)),
                ast.keyword(arg='check', value=ast.Constant(value=True)),
                ast.keyword(arg='text', value=ast.Constant(value=True)),
                ast.keyword(arg='input', value=ast.Constant(value='y\n'))
            ]

            return ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id='subprocess', ctx=ast.Load()), 
                    attr='run', 
                    ctx=ast.Load()
                ),
                args=[first_arg],
                keywords=keywords
            )

        def isTrue(self, node):
            return isinstance(node, ast.Constant) and node.value is True
        
    class AddTryBlockAroundSubprocessTransformer(ast.NodeTransformer):
        def visit_Expr(self, node):
            # Check if it is subprocess.run
            if isinstance(node.value, ast.Call) and \
                isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'run' and \
                isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == 'subprocess':

                handlers = [
                        ast.ExceptHandler(
                            type=ast.Attribute(
                                value=ast.Name(id='subprocess', ctx=ast.Load()),
                                attr=exec,
                                ctx=ast.Load()
                            ),
                            name='e',
                            body=[
                                ast.Expr(value=ast.Call(
                                    func=ast.Name(id='print', ctx=ast.Load()),
                                    args=[ast.Name(id='e', ctx=ast.Load())],
                                    keywords=[]
                                ))
                            ]
                    )
                    for exec in ["CalledProcessError", "TimeoutExpired", "SubprocessError"]
                ]

                new_node = ast.Try(
                    body=[node],
                    handlers=handlers,
                    orelse=[],
                    finalbody=[]
                )

                return ast.copy_location(new_node, node)
            return node

    def __init__(self):
        pass
    
    def processCodeString(self, code):

        try:
            src_tree = ast.parse(code, mode='exec')
        except Exception as e:
            if type(e).__name__ == "SyntaxError":
                error_msg = f"  File {e.filename}, line {e.lineno}, offset {e.offset}\n    {e.text}\n{type(e).__name__}: {e}"
                print(f"[x] Catch the SyntaxError when parsing the code: {error_msg}")
            return None
        else:
            modified_tree = self.NormalizedSubprocessTransformer().visit(src_tree)
            modified_tree = self.RemoveTryBlockAroundSubprocessTransformer().visit(modified_tree)
            modified_tree = self.ModifySubprocessRunTransformer().visit(modified_tree)
            # modified_tree = self.AddTryBlockAroundSubprocessTransformer().visit(modified_tree)

            if hasattr(ast, 'unparse'):
                new_code = ast.unparse(modified_tree) 
            else:
                import astor
                new_code = astor.to_source(modified_tree)

            
            if "subprocess" in new_code and "import subprocess" not in new_code:
                new_code = "import subprocess\n" + new_code

            return new_code
        
    def executePythonCode(self, code):
        # TODO: fix invalid code with ChatGPT
        try:
            exec(code, globals())
        except Exception as e:
            if type(e).__name__ == "NameError":
                try:
                    code = isort.code(autoimport.fix_code(code))
                    exec(code, globals())
                except Exception as err:
                    e = err
                else:
                    return None
            print(f"[x] Catch the {type(e).__module__}.{type(e).__name__}, skip to next code. Msg: {e}")
            # error_msg = f"  File {e.filename}, line {e.lineno}, offset {e.offset}\n    {e.text}\n{type(e).__name__}: {e}"
            return e
        else:
            return None

