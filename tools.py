#!/bin/env python
# -*- coding: UTF-8 -*-

import time
from functools import wraps
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def timed(f):
    @wraps(f)
    def wrapper(*args, **kwds):
        start = time.time()
        result = f(*args, **kwds)
        elapsed = time.time() - start
        log.debug("%s took %dms to finish" % (f.__name__, elapsed*1000))
        #print "%s took %dms to finish" % (f.__name__, elapsed*1000)
        return result
    return wrapper
