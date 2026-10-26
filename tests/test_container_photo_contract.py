"""The built-image smoke must exercise a photo and its textual follow-up."""
import ast
from scripts.smoke_container import CHECK


def test_built_image_executes_real_photo_history_smoke():
    tree = ast.parse(CHECK)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    name = 'check_photo_history_in_runtime'
    assert name in functions, 'Missing real-image photo/history workflow smoke'
    calls = [node for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
    assert any(isinstance(node.value.func, ast.Name) and node.value.func.id == name for node in calls)
    function_calls = [node.func for node in ast.walk(functions[name]) if isinstance(node, ast.Call)]
    assert any((isinstance(f, ast.Name) and f.id == 'run_agent') or (isinstance(f, ast.Attribute) and f.attr == 'run_agent') for f in function_calls), 'Smoke must reach actual run_agent, not just standalone sanitizer'


def test_photo_smoke_runs_twice_against_synthetic_database(temp_db):
    # Execute precisely the embedded helper, without the HTTP/preview shortcut.
    tree = ast.parse(CHECK)
    helper = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == 'check_photo_history_in_runtime')
    namespace = {'json': __import__('json')}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<container-photo-smoke>', 'exec'), namespace)
    namespace[helper.name]()
    namespace[helper.name]()
