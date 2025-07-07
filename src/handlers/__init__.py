from handlers.start import register as _reg_start
from handlers.collect import register as _reg_collect
from handlers.callbacks import register as _reg_callbacks
from handlers.delete_cmd import register as _reg_delete


def register_handlers(app):
    # keep order: start first, then data, then callbacks
    _reg_start(app)
    _reg_collect(app)
    _reg_callbacks(app)
    _reg_delete(app)
