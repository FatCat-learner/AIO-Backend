import sys

sys.path.insert(0, "src")

from main import app  # noqa: E402


def dump(routes, prefix=""):
    """递归打印路由，兼容 Mount 和 _IncludedRouter"""
    for route in routes:
        path = getattr(route, "path", None)

        # Mount 类型没有 path，但有 path_format
        if path is None:
            path = getattr(route, "path_format", "")

        # 如果是 Mount，递归进去
        sub = getattr(route, "routes", None)
        if sub:
            print(f"{prefix}[{type(route).__name__}] {path}")
            dump(sub, prefix + "  ")
        else:
            print(f"{prefix}[{type(route).__name__}] {path}")


dump(app.routes)
