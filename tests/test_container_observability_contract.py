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


def test_image_smoke_covers_split_logs_rotation_and_persistent_volume(tmp_path, monkeypatch):
    import scripts.smoke_container as smoke
    assert hasattr(smoke, 'LOG_WRITER'), 'image acceptance needs actual concurrent log writers'
    from test_logging import _child
    monkeypatch.setenv('K90_LOG_SMOKE_DIR', str(tmp_path))
    children = [_child(smoke.LOG_WRITER, tmp_path, str(index)) for index in (1,2)]
    output = []
    for child in children:
        assert child.wait(timeout=90) == 0
        output.append(child.output_log.read_text())
    smoke.check_log_storage(tmp_path)
    assert all('CANARY' not in value and '"component":"profiling"' not in value for value in output)
    # Exercise persistence comparison itself without claiming Docker execution.
    smoke.check_log_storage(tmp_path, record=True)
    smoke.check_log_storage(tmp_path, verify=True)
    import inspect
    source = inspect.getsource(smoke.main)
    assert 'volume' in source and 'restart' in source and 'record=True' in source and 'verify=True' in source
