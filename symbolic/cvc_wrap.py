import time
from os import path
from hashlib import sha224
from string import Template

from CVC4 import ExprManager, SmtEngine, SExpr

from symbolic.cvc_expr.exprbuilder import ExprBuilder

from symbolic.cvc_expr.integer import CVCInteger
from symbolic.cvc_expr.string import CVCString


class CVCWrapper(object):
    options = {'produce-models': 'true',
               # Enable experimental string support
               'strings-exp': 'true',
               # Enable modular arithmetic with constant modulus
               'rewrite-divk': 'true',
               'output-language': 'smt2',
               'input-language': 'smt2'}
    logic = 'ALL_SUPPORTED'

    def __init__(self):
        self.asserts = None
        self.query = None
        self.em = None
        self.solver = None
        self.smtlib = None

    def findCounterexample(self, asserts, query, timeout=None):
        """Tries to find a counterexample to the query while
           asserts remains valid."""
        self.em = ExprManager()
        self.solver = SmtEngine(self.em)
        if timeout is not None:
            self.options['tlimit-per'] = timeout*1000
        for name, value in CVCWrapper.options.items():
            self.solver.setOption(name, SExpr(str(value)))
        self.solver.setLogic(CVCWrapper.logic)
        self.query = query
        self.asserts = asserts
        result, model = self._findModel()
        return result, model

    def _findModel(self):
        self.solver.push()
        exprbuilder = ExprBuilder(self.asserts, self.query, self.solver)
        print("FORMULA: (assert " + exprbuilder.query.cvc_expr.toString() + " )")
        self.solver.assertFormula(exprbuilder.query.cvc_expr)
        model = None
        try:
            result = self.solver.checkSat()
            if not result.isSat():
                ret = "UNSAT"
            elif result.isUnknown():
                ret = "UNKNOWN"
            elif result.isSat():
                ret = "SAT"
                model = self._getModel(exprbuilder.cvc_vars)
            else:
                raise Exception("Unexpected SMT result")
        except RuntimeError as r:
            print("CVC exception %s" % r)
            ret = "UNKNOWN"
        except TypeError as t:
            print("CVC exception %s" % t)
            ret = "UNKNOWN"
        self.solver.pop()

        return ret, model

    @staticmethod
    def _getModel(variables):
        """Retrieve the model generated for the path expression."""
        return {name: cvc_var.getvalue() for (name, cvc_var) in variables.items()}
