import sys

import logbook

logbook.StreamHandler(sys.stdout, level=logbook.DEBUG).push_application()
