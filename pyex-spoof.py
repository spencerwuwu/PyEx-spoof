#!/usr/bin/env python3
# Copyright: see copyright.txt

import pickle
import time
from multiprocessing import freeze_support
import sys
import os

from symbolic.loader import FunctionLoader
from symbolic.explore import ExplorationEngine

def main():
    filename = os.path.abspath(sys.argv[1])

    # Get the object describing the application
    app = FunctionLoader(filename)
    engine = ExplorationEngine(app.createInvocation())
    generatedInputs, return_values, path = engine.explore()

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: ./pyex-spoof.py TargetFile")
        exit(1)
    main()
