"""极简测试运行器：不需要 pytest 也能跑 tests/ 下的用例。

为什么不用 pytest：
    这台机器的 sandbox 对 pip 几乎不可用（HTTPS 被拒绝 + 临时目录不可写），
    而测试用的只是 assert，pytest 只是提供发现和报告。
    几十行就能自己实现，还不引入依赖。

用法：
    python run_tests.py
"""
import importlib.util
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TESTS = ["tests/test_verify.py", "tests/test_text.py", "tests/test_extract.py"]


def load_module(path):
    name = os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    passed = failed = 0
    failures = []

    for path in TESTS:
        if not os.path.exists(os.path.join(HERE, path)):
            print(f"跳过（不存在）：{path}")
            continue
        mod = load_module(path)
        names = sorted(n for n in dir(mod) if n.startswith("test_"))
        print(f"\n{path}  ({len(names)} 个用例)")
        for n in names:
            fn = getattr(mod, n)
            try:
                fn()
                passed += 1
                print(f"  PASS  {n}")
            except Exception:
                failed += 1
                failures.append((path, n, traceback.format_exc()))
                print(f"  FAIL  {n}")

    print("\n" + "=" * 60)
    print(f"通过 {passed}，失败 {failed}")

    for path, n, tb in failures:
        print("\n" + "-" * 60)
        print(f"{path}::{n}")
        print(tb)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
