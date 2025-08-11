# calendar_module/__init__.py
"""Calendar module package initialization."""

# Import all submodules to make them available as attributes
try:
    from . import calendar_handler
    from . import delta_sync
    from . import query_parser
    from . import sync
    from . import sync_store
    from ..utils import vector_store
except ImportError as e:
    # In case of import errors during testing, still make the package importable
    import logging
    logging.getLogger(__name__).warning(f"Failed to import calendar_module submodule: {e}")