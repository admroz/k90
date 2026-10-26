"""Run the exact built-image offline helper on synthetic host data as well."""
import ast
from scripts.smoke_container import CHECK


def test_built_image_observability_helper_executes_real_runtime():
    tree = ast.parse(CHECK)
    name = 'check_observability_in_runtime'
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert helpers, 'Built-image smoke must exercise the new runtime behavior'
    assert any(isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Name) and node.value.func.id == name for node in tree.body)
    namespace = {}
    exec(compile(ast.Module(body=helpers, type_ignores=[]), '<observability-runtime-smoke>', 'exec'), namespace)
    namespace[name]()
