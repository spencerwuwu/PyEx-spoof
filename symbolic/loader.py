# Copyright: copyright.txt

import inspect
import os
import sys
from importlib.machinery import SourceFileLoader

from symbolic.symbolic_types import SymbolicType, SymbolicInteger, getSymbolic, SymbolicStr

class FunctionInvocation:
    def __init__(self, function, name, reset):
        self.function = function
        self.name = name
        self.reset = reset
        self.arg_constructor = {}
        self.initial_value = {}

    def callFunction(self,args):
        self.reset()
        result = self.function(**args)
        return result

    def addArgumentConstructor(self, name, init, constructor):
        self.initial_value[name] = init
        self.arg_constructor[name] = constructor

    def getNames(self):
        return self.arg_constructor.keys()

    def createArgumentValue(self, name, val=None):
        if val is None:
            val = self.initial_value[name]
        return self.arg_constructor[name](name, val)

class Loader:
    def __init__(self, filename):
        self.app = None
        self.modulename = os.path.basename(filename)
        self.modulename, ext = os.path.splitext(self.modulename)
        self.filename = filename
        self.entrypoint = self.modulename

        self._reset(True)

    def _reset(self, firstpass=False, modulename=None):
        if modulename is None:
            modulename = self.modulename
        if firstpass and modulename in sys.modules and modulename != "__main__":
            print("There already is a module loaded named " + modulename)
            raise ImportError()
        try:
            if modulename in sys.modules:
                del (sys.modules[modulename])
            self.app = SourceFileLoader(modulename, self.filename).load_module()
        except Exception as arg:
            print("Couldn't import " + modulename)
            print(arg)
            raise ImportError()

    def _initializeArgumentConcrete(self, inv: FunctionInvocation, f, val):
        inv.addArgumentConstructor(f, val, lambda n, v: val)

    def _initializeArgumentSymbolic(self, inv: FunctionInvocation, f: str, val, st: SymbolicType):
        inv.addArgumentConstructor(f, val, lambda n, v: st(n, v))

class FunctionLoader(Loader):
    def createInvocation(self):
        inv = FunctionInvocation(self._execute, self.entrypoint, self._reset)
        func = self.app.__dict__[self.entrypoint]
        argspec = inspect.getargspec(func)
        # check to see if user specified initial values of arguments
        if "concrete_args" in func.__dict__:
            for (f, v) in func.concrete_args.items():
                if not f in argspec.args:
                    print("Error in @concrete: " + self.entrypoint + " has no argument named " + f)
                    raise ImportError()
                else:
                    self._initializeArgumentConcrete(inv, f, v)
        if "symbolic_args" in func.__dict__:
            for (f, v) in func.symbolic_args.items():
                if not f in argspec.args:
                    print("Error (@symbolic): " + self.entrypoint + " has no argument named " + f)
                    raise ImportError()
                elif f in inv.getNames():
                    print("Argument " + f + " defined in both @concrete and @symbolic")
                    raise ImportError()
                else:
                    s = getSymbolic(v)
                    if (s == None):
                        print(
                            "Error at argument " + f + " of entry point " + self.entrypoint +
                            " : no corresponding symbolic type found for type " + str(type(v)))
                        raise ImportError()
                    self._initializeArgumentSymbolic(inv, f, v, s)
        for a in argspec.args:
            if not a in inv.getNames():
                self._initializeArgumentSymbolic(inv, a, 0, SymbolicInteger)
        return inv

    def _execute(self, **kwargs):
        return self.app.__dict__[self.entrypoint](**kwargs)
