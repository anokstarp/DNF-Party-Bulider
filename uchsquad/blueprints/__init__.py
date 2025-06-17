# blueprints/__init__.py
from flask import Blueprint
from importlib import import_module
import pkgutil

# 블루프린트 모듈을 자동으로 로드하고, bp 객체를 수집
blueprints = []
package = __name__

for finder, name, ispkg in pkgutil.iter_modules(__path__, package + '.'):
    module = import_module(name)
    # 모듈 내에 Blueprint 객체가 있을 경우 수집
    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, Blueprint):
            blueprints.append(obj)

# app.py에서 사용할 리스트
__all__ = ['blueprints']