from .service import Service
from ._version import get_versions
from . import util
__version__ = get_versions()['version']
del get_versions
