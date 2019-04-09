# Copyright: see copyright.txt

import logging
from textwrap import wrap

from .predicate import Predicate
from .constraint import Constraint


class PathToConstraint:
    def __init__(self, add, name):
        self.constraints = {}
        self.add = add
        self.name = name
        self.root_constraint = Constraint(None, None)
        self.current_constraint = self.root_constraint
        self.expected_path = None

    def reset(self, expected):
        self.current_constraint = self.root_constraint
        if expected is None:
            self.expected_path = None
        else:
            self.expected_path = []
            tmp = expected
            while tmp.predicate is not None:
                self.expected_path.append(tmp.predicate)
                tmp = tmp.parent

    def whichBranch(self, branch, symbolic_type):
        """ This function acts as instrumentation.
        Branch can be either True or False."""

        # add both possible predicate outcomes to constraint (tree)
        p = Predicate(symbolic_type, branch)
        p.negate()
        cneg = self.current_constraint.findChild(p)
        p.negate()
        c = self.current_constraint.findChild(p)

        if c is None:
            c = self.current_constraint.addChild(p)

            # we add the new constraint to the queue of the engine for later processing
            self.add(c)

        # check for path mismatch
        # IMPORTANT: note that we don't actually check the predicate is the
        # same one, just that the direction taken is the same
        if self.expected_path is not None and self.expected_path != []:
            expected = self.expected_path.pop()
            # while not at the end of the path, we expect the same predicate result
            # at the end of the path, we expect a different predicate result
            done = self.expected_path == []
            if (not done and expected.result != c.predicate.result or
                            done and expected.result == c.predicate.result):
                print("Replay mismatch (done=", done, ")")
                print(expected)
                print(c.predicate)

        if cneg is not None:
            # We've already processed both
            cneg.processed = True
            c.processed = True

        self.current_constraint = c

    def find_constraint(self, id):
        return self._find_constraint(self.root_constraint, id)

    def _find_constraint(self, constraint, id):
        if constraint.id == id:
            return constraint
        else:
            for child in constraint.children:
                found = self._find_constraint(child, id)
                if found is not None:
                    return found
        return None

    def __getstate__(self):
        return {k: v for k,v in self.__dict__.items() if k != "add"}

    def __getnewargs__(self):
        return ("","","")
