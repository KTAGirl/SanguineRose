import os
import sys

sys.path.append(os.path.split(os.path.abspath(__file__))[0])

import sanguine.sanguine_install_helpers as sanguine_install

sanguine_install.install_sanguine_prerequisites()
