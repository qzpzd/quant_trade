"""涨跌阶段 + MA5/10/20/30 综合分析包。"""

__all__ = ["run"]


def __getattr__(name: str):
    if name == "run":
        from .run import run as _run

        return _run
    raise AttributeError(name)
