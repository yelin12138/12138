"""Always start the workbench included in THIS extracted download."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("MotorLab 需要 Python 3.10 或以上版本。")
    try:
        from motorlab.app import main
    except ModuleNotFoundError as exc:
        if exc.name not in {"numpy", "matplotlib"}:
            raise
        raise SystemExit("缺少运行依赖。请在此解压目录运行：\n"
                         "python -m pip install -r requirements.txt\n"
                         "然后运行 python run_workbench.py --open") from None
    main()
