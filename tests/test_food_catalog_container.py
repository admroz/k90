"""Run the exact catalog helper shipped in the network-none image smoke."""
import ast
from scripts.smoke_container import CHECK


def test_catalog_runtime_smoke_runs_twice(temp_db):
    tree = ast.parse(CHECK)
    helper = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'check_catalog_in_runtime'), None)
    assert helper is not None, 'image smoke lacks real catalog/portion path'
    assert any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == helper.name for n in tree.body)
    namespace = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<catalog-container-smoke>', 'exec'), namespace)
    namespace[helper.name]()
    namespace[helper.name]()
