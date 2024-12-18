import os
import sys

sys.path.append(os.path.split(os.path.abspath(__file__))[0])

from sanguine.install.install_helpers import install_sanguine_prerequisites

install_sanguine_prerequisites()
